from flask import Blueprint, render_template, request, flash, redirect, url_for
from flask_login import login_required, current_user
import logging
from models.utility.utility_room_bill_record import RoomUtilityRecord      #导入主表模型
from models.user.user import User  # 导入用户模型获取部门信息
from models.department.department import Department  # 导入部门模型
from models.room.room import Room  # 导入房间模型获取楼栋信息
from utils.db import db
from utils.log import log_operation

from utils.auth import require_permission
from models.utility.utility_room_bill_checkout import CheckoutUtilityRecord # 退宿费用子表

# 蓝图定义，前缀设为'/utility'便于区分系统其他模块
utility_index_bp = Blueprint('utility_index', __name__, url_prefix='/utility')

@utility_index_bp.route('', methods=['GET'])
@login_required
@require_permission('utility.view')
def utility_home():
    """水电费管理系统首页（默认路由）"""
    try:
        # 记录页面访问日志
        log_operation(
            user_id=current_user.id,
            module='utility',#这里记载模块
            operation_type='records',#这里记载类型
            action=f"访问水电费管理首页",#这里记载成功与失败的记录
            result="成功"#这里只有成功与失败
        )
        return render_template('utility_bill/utility_index.html', title=f"水电费管理")
    except Exception as e:
        logging.error(f"访问水电费管理首页失败: {str(e)}")
        log_operation(
            user_id=current_user.id,
            module='utility',#这里记载模块
            operation_type='records',#这里记载类型
            action=f"访问水电费管理首页 [错误: {str(e)}]",#这里记载成功与失败的记录
            result="失败"#这里只有成功与失败
        )
        return render_template('utility_bill/utility_index.html', title=f"水电费管理", error=str(e))

@utility_index_bp.route('/index', methods=['GET'])
@login_required
@require_permission('utility.view')
def utility_index():
    """冗余路由，确保通过/index也能访问首页（兼容前端可能的跳转）"""
    try:
        log_operation(
            user_id=current_user.id,
            module='utility',#这里记载模块
            operation_type='records',#这里记载类型
            action=f"通过/index访问水电费管理首页",#这里记载成功与失败的记录
            result="成功"#这里只有成功与失败
        )
        return render_template('utility_bill/utility_index.html', title=f"水电费管理")
    except Exception as e:
        logging.error(f"通过/index访问首页失败: {str(e)}")
        log_operation(
            user_id=current_user.id,
            module='utility',#这里记载模块
            operation_type='records',#这里记载类型
            action=f"通过/index访问首页 [错误: {str(e)}]",#这里记载成功与失败的记录
            result="失败"#这里只有成功与失败
        )
        return render_template('utility_bill/utility_index.html', title=f"水电费管理", error=str(e))


# 水电费核算页面
@utility_index_bp.route('/utility_calculate_fees', methods=['GET'])
@login_required
@require_permission('utility.view')
def utility_calculate_fees():
    """核算水电费页面（已修正模板文件名）"""
    try:
        log_operation(
            user_id=current_user.id,
            module='utility',#这里记载模块
            operation_type='records',#这里记载类型
            action=f"访问核算水电费页面",#这里记载成功与失败的记录
            result="成功"#这里只有成功与失败
        )
        return render_template('utility_bill/utility_calculate_fees.html', title=f"月度账单管理")
    except Exception as e:
        logging.error(f"访问核算水电费页面失败: {str(e)}")
        log_operation(
            user_id=current_user.id,
            module='utility',#这里记载模块
            operation_type='records',#这里记载类型
            action=f"访问核算水电费页面 [错误: {str(e)}]",#这里记载成功与失败的记录
            result="失败"#这里只有成功与失败
        )
        return render_template('utility_bill/utility_calculate_fees.html', title=f"月度账单管理", error=str(e))

@utility_index_bp.route('/utility_room_records_detail')
@login_required
@require_permission('utility.view')
def utility_room_records_detail():
    """显示房间费用记录查询页面"""
    try:
        # 获取查询参数用于日志
        room_id = request.args.get('room_id', '未指定')
        billing_period = request.args.get('period', '未指定')
        
        log_operation(
            user_id=current_user.id,
            module='utility',#这里记载模块
            operation_type='records',#这里记载类型
            action=f"访问房间水电费查询页面 [房间ID: {room_id}, 账期: {billing_period}]",#这里记载成功与失败的记录
            result="成功"#这里只有成功与失败
        )
        return render_template('utility_bill/utility_room_records_detail.html', title=f"房间水电费查询")
    except Exception as e:
        logging.error(f"访问房间水电费查询页面失败: {str(e)}")
        log_operation(
            user_id=current_user.id,
            module='utility',#这里记载模块
            operation_type='records',#这里记载类型
            action=f"访问房间水电费查询页面 [错误: {str(e)}]",#这里记载成功与失败的记录
            result="失败"#这里只有成功与失败
        )
        return render_template('utility_bill/utility_room_records_detail.html', title=f"房间水电费查询", error=str(e))

@utility_index_bp.route('/utility_room_checkout')
@login_required
@require_permission('utility.view')
def utility_room_checkout():
    """退宿人员费用查询页面"""
    try:
        # 获取查询参数用于日志
        checkout_date = request.args.get('date', '未指定')
        room_id = request.args.get('room_id', '未指定')
        
        # 获取所有部门信息（去重并排序）
        departments_list = [d.name for d in Department.query.filter_by(status='正常').order_by(Department.name).all()]
        
        # 获取所有楼栋信息（去重并排序）
        buildings = db.session.query(Room.building).distinct().filter(Room.building.isnot(None)).filter(Room.building != '').all()
        # 转换为列表格式并排序
        buildings_list = sorted([building[0] for building in buildings])
        
        log_operation(
            user_id=current_user.id,
            module='utility',#这里记载模块
            operation_type='records',#这里记载类型
            action=f"访问退宿人员费用查询页面 [房间ID: {room_id}, 退宿日期: {checkout_date}]",#这里记载成功与失败的记录
            result="成功"#这里只有成功与失败
        )
        return render_template('utility_bill/utility_room_checkout.html', title=f"退宿人员费用查询", departments=departments_list, buildings=buildings_list)
    except Exception as e:
        logging.error(f"访问退宿人员费用查询页面失败: {str(e)}")
        log_operation(
            user_id=current_user.id,
            module='utility',#这里记载模块
            operation_type='checkout',#这里记载类型
            action=f"访问退宿人员费用查询页面 [错误: {str(e)}]",#这里记载成功与失败的记录
            result="失败"#这里只有成功与失败
        )
        # 即使出错也尝试获取部门和楼栋信息
        try:
            departments_list = [d.name for d in Department.query.filter_by(status='正常').order_by(Department.name).all()]
            buildings = db.session.query(Room.building).distinct().filter(Room.building.isnot(None)).filter(Room.building != '').all()
            buildings_list = sorted([building[0] for building in buildings])
        except Exception:
            departments_list = []
            buildings_list = []
            
        return render_template('utility_bill/utility_room_checkout.html', title=f"退宿人员费用查询", error=str(e), departments=departments_list, buildings=buildings_list)

@utility_index_bp.route('/utility_room_checkout_edit')
@login_required
@require_permission('utility.edit')
def utility_room_checkout_edit():
    """编辑退宿人员费用页面"""
    try:
        # 获取查询参数用于日志
        record_id = request.args.get('record_id', '未指定')
        user_id = request.args.get('user_id', '未指定')
        
        log_operation(
            user_id=current_user.id,
            module='utility',#这里记载模块
            operation_type='checkout_edit',#这里记载类型
            action=f"访问编辑退宿人员费用页面 [记录ID: {record_id}, 用户ID: {user_id}]",#这里记载成功与失败的记录
            result="成功"#这里只有成功与失败
        )
        return render_template('utility_bill/utility_room_checkout_edit.html', title=f"编辑退宿人员费用")
    except Exception as e:
        logging.error(f"访问编辑退宿人员费用页面失败: {str(e)}")
        log_operation(
            user_id=current_user.id,
            module='utility',#这里记载模块
            operation_type='checkout_edit',#这里记载类型
            action=f"访问编辑退宿人员费用页面 [错误: {str(e)}]",#这里记载成功与失败的记录
            result="失败"#这里只有成功与失败
        )
        return render_template('utility_bill/utility_room_checkout_edit.html', title=f"编辑退宿人员费用", error=str(e))

# 退宿费用计算结果页面
@utility_index_bp.route('/utility_user_checkout_detail')
@login_required
@require_permission('utility.view')
def utility_user_checkout_detail():

    # 获取URL参数，只需要checkout_id
    checkout_id = request.args.get('id', type=int)
    
    if not checkout_id:
        flash('参数错误，无法查看费用结果', 'danger')
        return redirect(url_for('dorm.dorm_query'))
    
    # 查询相关记录
    checkout_record = CheckoutUtilityRecord.query.get_or_404(checkout_id)
    
    # 从checkout_record中获取用户和房间信息
    user = User.query.get_or_404(checkout_record.user_id)
    room = Room.query.get_or_404(checkout_record.room_id)
    
    # 渲染费用结果页面
    return render_template('utility_bill/utility_user_checkout_detail.html', 
                          title=f"退宿费用核算-{user.name}(ID:{user.id})",
                          checkout_record=checkout_record, 
                          user=user, 
                          room=room)
    
# 房间人员费用明细页面
@utility_index_bp.route('/utility_occupant_manage')
@login_required
@require_permission('utility.view')
def utility_occupant_manage():
    """加载房间人员费用明细页面"""
    try:
        # 获取查询参数用于日志
        billing_period = request.args.get('period', '未指定')
        room_id = request.args.get('room_id', '未指定')
        
        # 获取所有账期用于下拉选择
        periods = db.session.query(RoomUtilityRecord.billing_period).distinct().order_by(RoomUtilityRecord.billing_period.desc()).all()
        billing_periods = [p[0] for p in periods]
        
        # 获取所有楼栋数据用于筛选
        buildings = db.session.query(Room.building).distinct().order_by(Room.building).all()
        building_list = [building[0] for building in buildings if building[0]]
        
        # 获取所有部门数据用于筛选
        department_list = [d.name for d in Department.query.filter_by(status='正常').order_by(Department.name).all()]
        
        log_operation(
            user_id=current_user.id,
            module='utility',#这里记载模块
            operation_type='records',#这里记载类型
            action=f"访问用户费用管理页面 [账期: {billing_period}, 房间ID: {room_id}, 加载账期数量: {len(billing_periods)}, 加载楼栋数量: {len(building_list)}, 加载部门数量: {len(department_list)}]",#这里记载成功与失败的记录
            result="成功"#这里只有成功与失败
        )
        return render_template('utility_bill/utility_occupant_manage.html', billing_periods=billing_periods, buildings=building_list, departments=department_list, title=f"用户费用管理")
    except Exception as e:
        logging.error(f"访问用户费用管理页面失败: {str(e)}")
        log_operation(
            user_id=current_user.id,
            module='utility',#这里记载模块
            operation_type='records',#这里记载类型
            action=f"访问用户费用管理页面 [错误: {str(e)}]",#这里记载成功与失败的记录
            result="失败"#这里只有成功与失败
        )
        return render_template('utility_bill/utility_occupant_manage.html', billing_periods=[], buildings=[], departments=[], title=f"用户费用管理", error=str(e))

