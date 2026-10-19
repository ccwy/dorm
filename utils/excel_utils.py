"""
通用 openpyxl 导入导出工具模块
不依赖 pandas/numpy，供各业务模块统一复用，
解决 Android(Chaquopy) 平台 C 扩展跨平台受限问题。
"""
import datetime
import io
import logging

from utils.lazy_imports import (  # 延迟导入openpyxl，避免启动时加载重型库
    Workbook, load_workbook, get_column_letter, Font, Alignment
)

logger = logging.getLogger(__name__)

# Excel 1900 日期系统纪元（序列号 1 = 1900-01-01）
_EXCEL_EPOCH = datetime.date(1899, 12, 30)

# 常用日期字符串解析格式
_DATE_FORMATS = (
    '%Y-%m-%d',
    '%Y/%m/%d',
    '%Y.%m.%d',
    '%Y%m%d',
    '%Y年%m月%d日',
    '%Y-%m-%d %H:%M:%S',
    '%Y/%m/%d %H:%M:%S',
    '%Y年%m月%d日 %H时%M分%S秒',
    '%Y-%m-%dT%H:%M:%S',
)


def is_empty(value):
    """判断值是否为空（None、空串、纯空白、nan/none/null 文本）"""
    if value is None:
        return True
    if isinstance(value, str):
        text = value.strip()
        return text == '' or text.lower() in ('nan', 'none', 'null')
    return False


def to_str(value, default=''):
    """安全转字符串；浮点整数 1.0 转为 '1'，日期转标准格式，空值返回 default"""
    if is_empty(value):
        return default
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if isinstance(value, datetime.datetime):
        return value.strftime('%Y-%m-%d %H:%M:%S')
    if isinstance(value, datetime.date):
        return value.strftime('%Y-%m-%d')
    return str(value).strip()


def to_int(value, default=None):
    """安全转整数；兼容 1.0/'1.0'/'1e3' 等形式，失败返回 default"""
    if is_empty(value):
        return default
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    try:
        return int(float(str(value).strip()))
    except (ValueError, TypeError):
        logger.debug('to_int 转换失败: %r', value)
        return default


def to_float(value, default=None):
    """安全转浮点数；兼容 '1.5'/'1e3' 等形式，失败返回 default"""
    if is_empty(value):
        return default
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).strip())
    except (ValueError, TypeError):
        logger.debug('to_float 转换失败: %r', value)
        return default


def to_date(value, fmt='%Y-%m-%d'):
    """安全转日期（datetime.date）；兼容 datetime、Excel 序列号、多种字符串格式，失败返回 None"""
    if is_empty(value):
        return None
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    if isinstance(value, (int, float)):
        try:
            return _EXCEL_EPOCH + datetime.timedelta(days=int(value))
        except (ValueError, OverflowError):
            logger.debug('to_date 序列号转换失败: %r', value)
            return None
    if isinstance(value, str):
        text = value.strip()
        try:
            return datetime.datetime.strptime(text, fmt).date()
        except ValueError:
            pass
        for pattern in _DATE_FORMATS:
            try:
                return datetime.datetime.strptime(text, pattern).date()
            except ValueError:
                continue
        logger.debug('to_date 字符串解析失败: %r', value)
    return None


def write_sheet(wb, sheet_name, headers, rows):
    """在工作簿中创建并写入一个工作表：表头加粗居中，逐行写入数据
    rows 元素支持 list（按列顺序）或 dict（按表头取值）"""
    ws = wb.create_sheet(title=str(sheet_name))
    header_font = Font(bold=True)
    center = Alignment(horizontal='center', vertical='center')
    for col_idx, header in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=col_idx, value=header)
        cell.font = header_font
        cell.alignment = center
    for row_idx, row in enumerate(rows, start=2):
        if isinstance(row, dict):
            for col_idx, header in enumerate(headers, start=1):
                ws.cell(row=row_idx, column=col_idx, value=row.get(header))
        else:
            for col_idx, val in enumerate(row, start=1):
                ws.cell(row=row_idx, column=col_idx, value=val)
    return ws


def export_to_excel(sheets, output):
    """将多个工作表导出并保存到 output（BytesIO 或文件路径）
    sheets: list of dict，每项含 {name, headers, rows}"""
    wb = Workbook()
    if sheets:
        wb.remove(wb.active)
    try:
        for item in sheets:
            write_sheet(
                wb,
                item.get('name', 'Sheet'),
                item.get('headers', []),
                item.get('rows', []),
            )
        wb.save(output)
    finally:
        wb.close()
    return output


def _to_stream(file_bytes):
    """将 bytes 包装为 BytesIO（openpyxl 需要类文件对象）"""
    if isinstance(file_bytes, (bytes, bytearray)):
        return io.BytesIO(file_bytes)
    return file_bytes


def _get_sheet(wb, sheet_name):
    """按索引或名称获取工作表；名称不存在时回退到第一个工作表"""
    if isinstance(sheet_name, int):
        try:
            return wb.worksheets[sheet_name]
        except IndexError:
            return None
    if sheet_name in wb.sheetnames:
        return wb[sheet_name]
    return wb.worksheets[0] if wb.worksheets else None


def read_excel_header(file_bytes, sheet_name=0):
    """读取 Excel 表头行，返回表头字符串列表；失败或空表返回空列表"""
    try:
        wb = load_workbook(_to_stream(file_bytes), data_only=True, read_only=True)
    except Exception:
        logger.exception('打开 Excel 文件失败')
        return []
    try:
        ws = _get_sheet(wb, sheet_name)
        if ws is None:
            return []
        for row in ws.iter_rows(min_row=1, max_row=1, values_only=True):
            return [to_str(v) for v in row]
        return []
    finally:
        wb.close()


def read_excel_rows(file_bytes, sheet_name=0, header_row=1):
    """读取 Excel 数据行，返回 list of dict（key 为表头字符串）
    自动跳过全空行；空单元格保留 None，由调用方用 is_empty 判断"""
    try:
        wb = load_workbook(_to_stream(file_bytes), data_only=True, read_only=True)
    except Exception:
        logger.exception('打开 Excel 文件失败')
        return []
    try:
        ws = _get_sheet(wb, sheet_name)
        if ws is None:
            return []
        rows_iter = ws.iter_rows(min_row=header_row, values_only=True)
        try:
            header_tuple = next(rows_iter)
        except StopIteration:
            return []
        headers = [to_str(v) for v in header_tuple]
        result = []
        for row in rows_iter:
            if all(is_empty(v) for v in row):
                continue
            record = {}
            for idx, header in enumerate(headers):
                if header == '':
                    continue
                record[header] = row[idx] if idx < len(row) else None
            result.append(record)
        return result
    finally:
        wb.close()


def set_column_widths(ws, widths):
    """按顺序设置列宽；widths 为列宽列表（如 [10, 20, 15]），None 跳过"""
    for idx, width in enumerate(widths, start=1):
        if width is not None:
            ws.column_dimensions[get_column_letter(idx)].width = width


def auto_fit_columns(ws, min_width=8, max_width=50):
    """根据内容自动调整列宽（取最长文本 + 2，钳制在 min_width 与 max_width 之间）"""
    for col_idx in range(1, ws.max_column + 1):
        max_len = 0
        for row_idx in range(1, ws.max_row + 1):
            val = ws.cell(row=row_idx, column=col_idx).value
            if not is_empty(val):
                length = len(to_str(val))
                if length > max_len:
                    max_len = length
        width = min(max(max_len + 2, min_width), max_width)
        ws.column_dimensions[get_column_letter(col_idx)].width = width