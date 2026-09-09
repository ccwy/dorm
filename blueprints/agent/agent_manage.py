# -*- coding: utf-8 -*-
"""Agent管理页面路由 - 渲染HTML模板"""
from flask import Blueprint, render_template, redirect, url_for
from flask_login import login_required
from utils.auth import require_permission
from models.system_config.system_config import SystemConfig

agent_manage_bp = Blueprint(
    'agent_manage',
    __name__,
    url_prefix='/agent_manage'
)


@agent_manage_bp.route('/')
@login_required
@require_permission('agent.view')
def index():
    """Agent管理首页 - 设备列表"""
    # 获取Agent系统启用状态
    enabled = SystemConfig.get_config_value('AGENT_ENABLED', default='true')
    if isinstance(enabled, bool):
        agent_enabled = enabled
    else:
        agent_enabled = str(enabled).lower() == 'true'
    return render_template('agent_manage/agent_manage.html', agent_enabled=agent_enabled)


@agent_manage_bp.route('/settings')
@login_required
@require_permission('agent.manage')
def settings():
    """Agent设置页 - 配置管理、API Key管理、全局开关"""
    enabled = SystemConfig.get_config_value('AGENT_ENABLED', default='true')
    if isinstance(enabled, bool):
        agent_enabled = enabled
    else:
        agent_enabled = str(enabled).lower() == 'true'
    return render_template('agent_manage/agent_settings.html', agent_enabled=agent_enabled)


@agent_manage_bp.route('/device/<agent_id>')
@login_required
@require_permission('agent.view')
def device_detail(agent_id):
    """设备详情页"""
    enabled = SystemConfig.get_config_value('AGENT_ENABLED', default='true')
    if isinstance(enabled, bool):
        agent_enabled = enabled
    else:
        agent_enabled = str(enabled).lower() == 'true'
    return render_template(
        'agent_manage/agent_device_detail.html',
        agent_id=agent_id,
        agent_enabled=agent_enabled
    )