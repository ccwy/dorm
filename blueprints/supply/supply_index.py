from flask import Blueprint, render_template
from flask_login import login_required, current_user
import logging
from utils.log import log_operation
from utils.auth import admin_required

# 蓝图定义，前缀设为'/supply'作为低值易耗品模块总入口
supply_index_bp = Blueprint('supply_index', __name__, url_prefix='/supply',
                            template_folder='../../templates',
                            static_folder='../../static')


@supply_index_bp.route('', methods=['GET'])
@login_required
@admin_required
def supply_home():
    """低值易耗品管理系统首页（默认路由）"""
    try:
        # 记录页面访问日志
        log_operation(
            user_id=current_user.id,
            module='supply',
            operation_type='index',
            action=f"访问低值易耗品管理首页",
            result="成功"
        )
        return render_template('supply_manage/supply_index.html', title="低值易耗品管理")
    except Exception as e:
        logging.error(f"访问低值易耗品管理首页失败: {str(e)}")
        log_operation(
            user_id=current_user.id,
            module='supply',
            operation_type='index',
            action=f"访问低值易耗品管理首页 [错误: {str(e)}]",
            result="失败"
        )
        return render_template('supply_manage/supply_index.html', title="低值易耗品管理", error=str(e))


@supply_index_bp.route('/index', methods=['GET'])
@login_required
@admin_required
def supply_index():
    """冗余路由，确保通过/index也能访问首页（兼容前端可能的跳转）"""
    try:
        log_operation(
            user_id=current_user.id,
            module='supply',
            operation_type='index',
            action=f"通过/index访问低值易耗品管理首页",
            result="成功"
        )
        return render_template('supply_manage/supply_index.html', title="低值易耗品管理")
    except Exception as e:
        logging.error(f"通过/index访问低值易耗品管理首页失败: {str(e)}")
        log_operation(
            user_id=current_user.id,
            module='supply',
            operation_type='index',
            action=f"通过/index访问低值易耗品管理首页 [错误: {str(e)}]",
            result="失败"
        )
        return render_template('supply_manage/supply_index.html', title="低值易耗品管理", error=str(e))