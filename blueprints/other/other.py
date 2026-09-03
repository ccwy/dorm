from flask import Blueprint, render_template
from flask_login import login_required, current_user
import logging
from utils.log import log_operation

# 直接创建其他功能入口蓝图
other_bp = Blueprint('other', __name__, url_prefix='/other')

@other_bp.route('/index', methods=['GET'])
@login_required
def index():
    """其他功能入口页面"""
    try:
        # 记录访问日志
        log_operation(
            user_id=current_user.id,
            module='other',
            operation_type='records',
            action="访问其他功能页面",
            result="成功"
        )
        return render_template('other/other_index.html', title="其他功能")
    except Exception as e:
        logging.error(f"访问其他功能页面失败: {str(e)}")
        return render_template('other/other_index.html', title="其他功能", error=str(e))