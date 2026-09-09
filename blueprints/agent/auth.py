# -*- coding: utf-8 -*-
"""Agent认证模块 - API Key认证装饰器和全局开关检查"""
import logging
from functools import wraps
from datetime import datetime
from flask import request, jsonify
from models.agent.agent_api_key import AgentApiKey
from utils.rate_limiter import agent_limiter

logger = logging.getLogger(__name__)


def require_agent_key(f):
    """Agent API Key认证装饰器

    验证请求头中的 X-Agent-API-Key 是否有效：
    1. 检查速率限制（每IP每分钟60次请求）
    2. 检查认证失败速率限制（每IP每分钟10次失败）
    3. 检查请求头是否包含 X-Agent-API-Key
    4. 查询 agent_api_keys 表验证 Key 是否存在且启用
    5. 将 agent_id 注入请求上下文供后续使用
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        ip = request.remote_addr

        # 检查总体速率限制（每IP每分钟60次）
        if agent_limiter.check_and_cleanup(ip, limit_name='default'):
            return jsonify({"success": False, "message": "请求过于频繁，请稍后再试"}), 429

        api_key = request.headers.get('X-Agent-API-Key')
        if not api_key:
            # 认证失败：记录并检查更严格的速率限制
            logger.warning("Agent API请求缺少API Key, IP=%s", ip)
            if agent_limiter.record_auth_failure(ip):
                return jsonify({"success": False, "message": "请求过于频繁，请稍后再试"}), 429
            return jsonify({"success": False, "message": "缺少API Key"}), 401

        key_record = AgentApiKey.query.filter_by(
            api_key=api_key, is_active=True
        ).first()
        if key_record and key_record.expires_at:
            if key_record.expires_at < datetime.utcnow():
                # 认证失败：Key过期
                logger.warning("Agent API Key已过期: agent_id=%s, IP=%s", key_record.agent_id, ip)
                if agent_limiter.record_auth_failure(ip):
                    return jsonify({"success": False, "message": "请求过于频繁，请稍后再试"}), 429
                return jsonify({"success": False, "message": "API Key已过期"}), 403
        if not key_record:
            # 认证失败：Key无效
            logger.warning("Agent API Key无效, IP=%s", ip)
            if agent_limiter.record_auth_failure(ip):
                return jsonify({"success": False, "message": "请求过于频繁，请稍后再试"}), 429
            return jsonify({"success": False, "message": "无效的API Key"}), 403

        # 将agent_id和key_record注入请求上下文
        request.agent_id = key_record.agent_id
        request.api_key_record = key_record
        return f(*args, **kwargs)
    return decorated


def check_agent_enabled():
    """检查Agent系统是否启用，未启用时返回403

    检查 SystemConfig 表中的 AGENT_ENABLED 配置项，
    禁用后所有 Agent API（注册、心跳、上报、离线通知）返回 403。
    管理端端点不受此开关影响。

    Returns:
        None: Agent系统已启用
        Response: Agent系统已禁用，返回403 JSON响应
    """
    from models.system_config.system_config import SystemConfig
    enabled = SystemConfig.get_config_value('AGENT_ENABLED', default='true')
    if isinstance(enabled, bool):
        enabled = enabled
    else:
        enabled = str(enabled).lower() == 'true'
    if not enabled:
        return jsonify({"success": False, "message": "Agent系统已禁用"}), 403
    return None