import datetime
import re
from typing import List, Any
import pandas as pd
import datetime

class ExcelDateUtils:
    """
    批量Excel日期时间处理工具，专为Excel数据导入过程中的日期时间转换设计
    专注于批量处理功能，不支持单个值处理
    """
    
    # Excel日期基准（1899年12月30日）
    EXCEL_EPOCH = datetime.datetime(1899, 12, 30)
    
    # 支持的日期时间格式列表（覆盖Excel中绝大多数日期格式）
    DATE_FORMATS = [
        # 标准格式
        '%Y-%m-%d %H:%M:%S',
        '%Y-%m-%d %H:%M',
        '%Y-%m-%d',
        # 斜杠分隔格式
        '%Y/%m/%d %H:%M:%S',
        '%Y/%m/%d %H:%M',
        '%Y/%m/%d',
        # 日-月-年格式
        '%d-%m-%Y %H:%M:%S',
        '%d-%m-%Y %H:%M',
        '%d-%m-%Y',
        # 月-日-年格式
        '%m/%d/%Y %H:%M:%S',
        '%m/%d/%Y %H:%M',
        '%m/%d/%Y',
        # 中文格式
        '%Y年%m月%d日 %H:%M:%S',
        '%Y年%m月%d日 %H:%M',
        '%Y年%m月%d日',
        # 简写年份格式
        '%y-%m-%d %H:%M:%S',
        '%y-%m-%d %H:%M',
        '%y-%m-%d',
        '%y/%m/%d %H:%M:%S',
        '%y/%m/%d %H:%M',
        '%y/%m/%d',
        '%d-%m-%y %H:%M:%S',
        '%d-%m-%y %H:%M',
        '%d-%m-%y',
        '%m/%d/%y %H:%M:%S',
        '%m/%d/%y %H:%M',
        '%m/%d/%y',
        # 无分隔符格式
        '%Y%m%d%H%M%S',
        '%Y%m%d%H%M',
        '%Y%m%d',
        '%y%m%d%H%M%S',
        '%y%m%d%H%M',
        '%y%m%d',
        # ISO格式
        '%Y-%m-%dT%H:%M:%S',
        '%Y-%m-%dT%H:%M:%SZ',
        '%Y-%m-%dT%H:%M:%S.%f',
        '%Y-%m-%dT%H:%M:%S.%fZ',
        # 相对宽松格式
        '%Y.%m.%d',
        '%d.%m.%Y',
        '%m.%d.%Y',
        '%Y.%m.%d %H:%M:%S',
        '%d.%m.%Y %H:%M:%S',
        '%m.%d.%Y %H:%M:%S',
        # 带有时区的格式
        '%Y-%m-%d %H:%M:%S%z',
        '%Y-%m-%dT%H:%M:%S%z',
        # 中文带时间格式
        '%Y年%m月%d日%H时%M分%S秒',
        '%Y年%m月%d日%H时%M分',
    ]
    
    # 时间格式列表（当只有时间信息时）
    TIME_FORMATS = [
        '%H:%M:%S',
        '%H:%M',
        '%H时%M分%S秒',
        '%H时%M分',
    ]
    
    @classmethod
    def _get_context_info(cls, field_name: str = None, row_num: int = None) -> str:
        """获取字段名和行号的上下文信息字符串"""
        context = []
        if field_name:
            context.append(f"字段：{field_name}")
        if row_num is not None:
            context.append(f"行号：{row_num + 2}")
        
        if context:
            return f"，{', '.join(context)}"
        return ""
    
    @classmethod
    def _parse_with_regex(cls, value_str: str) -> datetime.datetime:
        """使用正则表达式解析一些特殊的日期格式"""
        # 处理类似 "2023年05月15日 08:30:45" 这样的格式（可能有多余空格）
        pattern = r'(\d{4})[年\s](\d{1,2})[月\s](\d{1,2})[日\s]?\s*(\d{1,2})?:?(\d{1,2})?:?(\d{1,2})?'
        match = re.match(pattern, value_str)
        if match:
            try:
                year = int(match.group(1))
                month = int(match.group(2))
                day = int(match.group(3))
                
                # 处理时间部分 - 不使用默认值，确保所有时间部分都存在
                hour_group = match.group(4)
                minute_group = match.group(5)
                second_group = match.group(6)
                
                # 确保时间部分完整
                if hour_group:
                    # 要求分钟和秒也必须存在，不使用默认值
                    if not minute_group:
                        raise ValueError(f"时间格式不完整，缺少分钟部分: {value_str}")
                    
                    hour = int(hour_group)
                    minute = int(minute_group)
                    
                    # 如果有秒部分才解析，否则不添加
                    if second_group:
                        second = int(second_group)
                        return datetime.datetime(year, month, day, hour, minute, second)
                    else:
                        return datetime.datetime(year, month, day, hour, minute)
                else:
                    # 没有时间部分，只返回日期
                    return datetime.datetime(year, month, day)
            except ValueError:
                pass
                
        # 处理类似 "2023/5/15 8:30" 这样的简短格式
        pattern = r'(\d{4})[-/](\d{1,2})[-/](\d{1,2})\s+(\d{1,2}):(\d{1,2})'
        match = re.match(pattern, value_str)
        if match:
            try:
                year = int(match.group(1))
                month = int(match.group(2))
                day = int(match.group(3))
                hour = int(match.group(4))
                minute = int(match.group(5))
                
                # 不使用秒的默认值，只返回时和分
                return datetime.datetime(year, month, day, hour, minute)
            except ValueError:
                pass
                
        raise ValueError(f"无法使用正则表达式解析日期格式: {value_str}")
    
    @classmethod
    def _parse_single_date(cls, value: Any, field_name: str = None, row_num: int = None) -> datetime.datetime:
        """内部方法：解析单个Excel日期值为datetime对象，仅在批量处理中使用"""
        if value is None or pd.isna(value):
            raise ValueError(f"日期值不能为空{cls._get_context_info(field_name, row_num)}")
            
        # 如果已经是日期类型，直接返回
        if isinstance(value, (datetime.date, datetime.datetime)):
            if isinstance(value, datetime.date) and not isinstance(value, datetime.datetime):
                return datetime.datetime.combine(value, datetime.time.min)
            return value
        
        # 处理pandas Timestamp类型
        if isinstance(value, pd.Timestamp):
            return value.to_pydatetime()
            
        # 处理Excel序列号（数字）
        if isinstance(value, (int, float)):
            # 检查序列号是否有效
            if value < 0:
                raise ValueError(f"无效的Excel日期序列号: {value}，序列号不能为负数{cls._get_context_info(field_name, row_num)}")
                
            try:
                # 整数部分表示日期
                days = int(value)
                # 小数部分表示时间
                seconds = int((value - days) * 86400)  # 一天86400秒
                
                # 计算日期时间
                result = cls.EXCEL_EPOCH + datetime.timedelta(days=days, seconds=seconds)
                
                # 处理Excel的1900年闰年bug
                if result.year == 1900 and result.month == 2 and result.day == 29:
                    result = datetime.datetime(1900, 3, 1)
                    
                return result
            except OverflowError as e:
                raise ValueError(f"Excel日期序列号计算溢出: {value}，错误: {str(e)}{cls._get_context_info(field_name, row_num)}") from e
                
        # 确保是字符串
        if not isinstance(value, str):
            try:
                value = str(value)
            except:
                raise TypeError(f"无法将值转换为字符串进行日期解析{cls._get_context_info(field_name, row_num)}")
            
        # 预处理：去除首尾空白字符
        value_str = value.strip()
        if not value_str:
            raise ValueError(f"日期字符串为空{cls._get_context_info(field_name, row_num)}")
            
        # 尝试所有日期格式
        for fmt in cls.DATE_FORMATS:
            try:
                return datetime.datetime.strptime(value_str, fmt)
            except ValueError:
                continue
                
        # 不尝试单独的时间格式，避免使用默认日期
        
                
        # 尝试使用正则表达式处理一些特殊格式
        return cls._parse_with_regex(value_str)
    
    @classmethod
    def parse_excel_date(cls, values: Any, field_name: str = None, raise_error: bool = True) -> List[datetime.datetime]:
        """
        批量解析Excel中的日期值为datetime对象，专为批量导入过程设计
        
        参数:
            values: 要解析的日期值列表或pandas Series（仅支持批量输入）
            field_name: 可选，字段名，用于错误信息
            raise_error: 可选，解析失败时是否抛出异常，默认为True
        
        返回:
            解析后的日期时间对象列表，失败项为None（当raise_error为False时）
        
        异常:
            ValueError: 当解析失败且raise_error为True时
            TypeError: 当输入类型不是列表或pandas Series时
        """
        # 检查输入类型，只接受列表或pandas Series
        if not isinstance(values, (list, pd.Series)):
            raise TypeError(f"只支持批量处理列表或pandas Series类型的输入，不支持单个值处理")
            
        # 转换pandas Series为列表
        if isinstance(values, pd.Series):
            batch_values = values.tolist()
        else:
            batch_values = values
            
        # 创建结果列表用于存储批量处理的结果
        results = []
        failed_indices = []
        failed_values = []
        error_messages = []
            
        # 批量处理所有日期值
        for idx, value in enumerate(batch_values):
            try:
                # 调用内部方法处理单个值
                parsed_date = cls._parse_single_date(value, field_name=field_name, row_num=idx)
                results.append(parsed_date)
            except (ValueError, TypeError) as e:
                failed_indices.append(idx)
                failed_values.append(value)
                error_messages.append(str(e))
                results.append(None)
                
        # 如果有失败项且需要抛出异常
        if failed_indices and raise_error:
            error_info = "\n".join([f"第{idx}项: {val}, 错误: {msg}" 
                                   for idx, val, msg in zip(failed_indices, failed_values, error_messages)])
            raise ValueError(f"批量解析日期失败:\n{error_info}")
            
        return results

# 创建工具实例，方便直接使用
excel_date_utils = ExcelDateUtils()