from flask import Blueprint, request, make_response, abort, jsonify
from flask_login import login_required, current_user
from utils.auth import require_permission
from utils.log import log_operation
from utils.lazy_imports import pd  # 延迟导入pandas
from io import BytesIO
from urllib.parse import quote
from datetime import datetime
import logging

from models.dorm.dorm_application import DormApplication
from models.user.user import User
from sqlalchemy.orm import joinedload
from sqlalchemy import or_

# 宿舍申请导出蓝图
dorm_application_export_bp = Blueprint('dorm_application_export', __name__, url_prefix='/admin/dorm_application_export')


@dorm_application_export_bp.route('/export', methods=['GET'])
@login_required
@require_permission('dorm_application.export')
def export_applications():
    """导出宿舍申请数据为Excel文件"""
    try:
        user_id = current_user.id
        if not user_id or str(user_id).strip() == '':
            return jsonify({'success': False, 'message': '用户信息无效'}), 401
        user_id = int(str(user_id))

        # 获取筛选参数（与管理列表页一致）
        application_type = request.args.get('application_type', '').strip()
        status = request.args.get('status', '').strip()
        search = request.args.get('search', '').strip()

        # 构建查询（与管理列表页一致）
        query = DormApplication.query.options(
            joinedload(DormApplication.user),
            joinedload(DormApplication.current_room),
            joinedload(DormApplication.target_room),
            joinedload(DormApplication.reviewer)
        )

        if application_type:
            query = query.filter_by(application_type=application_type)
        if status:
            query = query.filter_by(status=status)
        if search:
            query = query.join(User, DormApplication.user_id == User.id).filter(
                or_(
                    User.name.like(f'%{search}%'),
                    DormApplication.application_number.like(f'%{search}%')
                )
            )

        applications = query.order_by(DormApplication.created_at.desc()).all()

        # 类型映射
        type_map = {'allocate': '申请宿舍', 'change': '申请换宿', 'checkout': '申请退宿'}
        status_map = {'pending': '待审核', 'approved': '已通过', 'rejected': '已拒绝', 'cancelled': '已取消'}

        # 构建导出数据
        data = []
        for app in applications:
            # 构建宿舍信息显示（与操作记录页面一致的格式）
            if app.application_type == 'change':
                current_str = f"{app.current_room.building}{app.current_room.room_number}" if app.current_room else ''
                target_str = f"{app.target_room.building}{app.target_room.room_number}" if app.target_room else ''
                if current_str and target_str:
                    room_info = f"{current_str} → {target_str}"
                elif target_str:
                    room_info = target_str
                elif current_str:
                    room_info = current_str
                else:
                    room_info = ''
            elif app.application_type == 'checkout':
                room_info = f"{app.current_room.building}{app.current_room.room_number}" if app.current_room else ''
            else:
                room_info = f"{app.target_room.building}{app.target_room.room_number}" if app.target_room else ''

            row = {
                '申请编号': app.application_number or '',
                '申请人': app.user.name if app.user else '',
                '部门': app.user.dept.name if app.user and app.user.dept else '',
                '性别': app.user.gender if app.user else '',
                '年龄': app.user.age if app.user and app.user.age else '',
                '职位': app.user.position if app.user and app.user.position else '',
                '申请类型': type_map.get(app.application_type, app.application_type or ''),
                '状态': status_map.get(app.status, app.status or ''),
                '宿舍信息': room_info,
                '申请原因': app.reason or '',
                '期望入住日期': app.check_in_date.strftime('%Y-%m-%d') if app.check_in_date else '',
                '期望退宿日期': app.check_out_date.strftime('%Y-%m-%d') if app.check_out_date else '',
                '审核人': app.reviewer.name if app.reviewer else '',
                '审核时间': app.reviewed_at.strftime('%Y-%m-%d %H:%M') if app.reviewed_at else '',
                '审核备注': app.review_remark or '',
                '申请日期': app.created_at.strftime('%Y-%m-%d %H:%M') if app.created_at else '',
            }
            data.append(row)

        # 生成Excel文件
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df = pd.DataFrame(data)
            df.to_excel(writer, index=False, sheet_name='宿舍申请记录')

            # 调整列宽
            worksheet = writer.sheets['宿舍申请记录']
            column_widths = {
                'A': 18,  # 申请编号
                'B': 10,  # 申请人
                'C': 12,  # 部门
                'D': 6,   # 性别
                'E': 6,   # 年龄
                'F': 10,  # 职位
                'G': 10,  # 申请类型
                'H': 8,   # 状态
                'I': 18,  # 宿舍信息
                'J': 25,  # 申请原因
                'K': 14,  # 期望入住日期
                'L': 14,  # 期望退宿日期
                'M': 10,  # 审核人
                'N': 18,  # 审核时间
                'O': 25,  # 审核备注
                'P': 18,  # 申请日期
            }
            for col_letter, width in column_widths.items():
                worksheet.column_dimensions[col_letter].width = width

        output.seek(0)

        # 构建下载响应
        filename = f"宿舍申请记录_{datetime.now().strftime('%Y%m%d')}.xlsx"
        encoded_filename = quote(filename)

        response = make_response(output.getvalue())
        response.headers["Content-Disposition"] = f"attachment; filename*=UTF-8''{encoded_filename}"
        response.headers["Content-Type"] = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

        log_operation(
            user_id=user_id,
            module='dorm_application',
            operation_type='export',
            action=f"导出宿舍申请记录 {len(data)} 条",
            result="成功"
        )
        logging.info(f"管理员 {user_id} 导出宿舍申请记录 {len(data)} 条")
        return response

    except Exception as e:
        logging.error(f"导出宿舍申请记录失败: {str(e)}")
        abort(500, description=f"导出失败: {str(e)}")