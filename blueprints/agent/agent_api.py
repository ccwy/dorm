# -*- coding: utf-8 -*-
"""Agent API端点 - Agent客户端API和管理端API

Agent端(4个, API Key认证):
  POST /register, POST /heartbeat, POST /report, POST /offline

管理端(17个, login_required + permission):
  GET/POST /keys, PUT/DELETE /keys/<id>,
  GET /devices, GET /devices/<agent_id>,
  GET /download, GET /download/<asset_number>,
  GET /stop-script, GET /uninstall-script, GET /edit-info-script,
  GET/PUT /config, POST /toggle, POST /migrate,
  PUT /devices/<agent_id>/manual-fields, POST /sync-from-asset/<asset_id>
"""
import uuid
import secrets
import json
import os
import io
import re
import zipfile
import logging
import traceback
from datetime import datetime
from flask import Blueprint, request, jsonify, send_file, current_app
from flask_login import login_required, current_user
from utils.db import db
from utils.auth import require_permission
from utils.log import log_operation
from models.agent.agent_device import AgentDevice
from models.agent.agent_api_key import AgentApiKey
from models.agent.agent_config import AgentConfig
from models.agent.agent_heartbeat_log import AgentHeartbeatLog
from models.fixed_asset.fixed_asset import FixedAsset
from models.department.department import Department
from models.system_config.system_config import SystemConfig
from .auth import require_agent_key, check_agent_enabled

logger = logging.getLogger(__name__)

# 允许通过API更新的配置键白名单
ALLOWED_CONFIG_KEYS = {
    'server_url', 'inject_server_url', 'inject_api_key',
    'heartbeat_interval', 'offline_threshold',
    'migration_new_url', 'migration_enabled',
    'heartbeat_log_enabled', 'heartbeat_log_retention_days',
    'allow_remote_stop'
}

# 设备自动更新字段白名单（Agent采集上报的字段）
DEVICE_AUTO_UPDATE_FIELDS = {
    'os_name', 'os_version', 'os_arch', 'cpu_model', 'cpu_cores',
    'total_memory_mb', 'available_memory_mb', 'disks',
    'mac_address', 'ip_address', 'network_interfaces',
    'agent_version', 'logged_in_user', 'hostname',
    'platform', 'device_fingerprint', 'info_hash'
}

# 设备手动字段白名单（可由用户/管理端编辑的字段）
DEVICE_MANUAL_FIELDS = {'asset_number', 'location', 'department', 'responsible_person'}


def mask_ip(ip):
    """IP地址脱敏：将最后一段替换为***，如 192.168.1.100 → 192.168.1.***"""
    if not ip:
        return ''
    parts = ip.split('.')
    if len(parts) == 4:
        return '.'.join(parts[:3]) + '.***'
    # IPv6或非标准格式，返回前8字符+***
    return ip[:8] + '***' if len(ip) > 8 else ip


agent_api_bp = Blueprint(
    'agent_api',
    __name__,
    url_prefix='/api/agent'
)


# ==================== 辅助函数 ====================

def _get_agent_exe_path():
    """获取Agent二进制文件路径（兼容Windows部署和安卓部署）"""
    try:
        from utils.android_adapter import get_agent_binary_path
        return get_agent_binary_path()
    except (ImportError, AttributeError):
        return os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'static', 'agent', 'asset-agent.exe'
        )


def _sync_device_to_asset(device):
    """将Agent设备的手动字段同步到关联的固定资产（最后修改者胜出）

    双向同步字段映射：
      agent_devices.location ↔ fixed_assets.storage_location
      agent_devices.department ↔ fixed_assets.dept_using.name (需Department表查询)
      agent_devices.responsible_person ↔ fixed_assets.responsible_person
    """
    if not device.asset_id:
        return
    asset = FixedAsset.query.get(device.asset_id)
    if not asset:
        return
    # 仅当设备端更新时间 >= 资产端时才同步
    if not (device.updated_at and asset.updated_at and device.updated_at >= asset.updated_at):
        return
    changed = False
    # location → storage_location
    if (device.location or '') != (asset.storage_location or ''):
        asset.storage_location = device.location or None
        changed = True
    # department → department_using_id (需通过Department表查询)
    if device.department:
        dept = Department.query.filter_by(name=device.department).first()
        if dept and asset.department_using_id != dept.id:
            asset.department_using_id = dept.id
            changed = True
    elif asset.department_using_id:
        asset.department_using_id = None
        changed = True
    # responsible_person → responsible_person
    if (device.responsible_person or '') != (asset.responsible_person or ''):
        asset.responsible_person = device.responsible_person or None
        changed = True
    if changed:
        asset.updated_at = datetime.utcnow()


def _sync_asset_to_device(asset, device):
    """将固定资产的字段同步到Agent设备（最后修改者胜出）"""
    # 仅当资产端更新时间 >= 设备端时才同步
    if not (asset.updated_at and device.updated_at and asset.updated_at >= device.updated_at):
        return
    changed = False
    # storage_location → location
    if (asset.storage_location or '') != (device.location or ''):
        device.location = asset.storage_location or None
        changed = True
    # dept_using.name → department
    dept_name = asset.dept_using.name if asset.dept_using else None
    if (dept_name or '') != (device.department or ''):
        device.department = dept_name
        changed = True
    # responsible_person → responsible_person
    if (asset.responsible_person or '') != (device.responsible_person or ''):
        device.responsible_person = asset.responsible_person or None
        changed = True
    if changed:
        device.updated_at = datetime.utcnow()


def _generate_api_key(name=None, remark=None, created_by=None):
    """生成新的API Key"""
    api_key = f"AGENT_{secrets.token_hex(16)}"
    key_record = AgentApiKey(
        api_key=api_key,
        name=name or '自动生成',
        remark=remark,
        is_active=True,
        created_by=created_by,
    )
    db.session.add(key_record)
    db.session.flush()
    return key_record


def _get_effective_server_url():
    """获取有效的服务器地址，用于注入config.json

    优先级：
    1. inject_server_url（管理员明确配置的注入地址）
    2. server_url（当前服务器地址配置）
    3. request.host_url（请求来源地址，支持X-Forwarded-Host反向代理）

    返回值确保不以/结尾，格式如 http://192.168.1.100:35168
    """
    # 优先使用管理员配置的注入地址
    inject_url = AgentConfig.get_value('inject_server_url', default='')
    if inject_url:
        return inject_url.rstrip('/')

    # 其次使用当前服务器地址配置
    server_url = AgentConfig.get_value('server_url', default='')
    if server_url:
        return server_url.rstrip('/')

    # 最后使用请求来源地址（支持反向代理）
    # 优先检查X-Forwarded-Host/X-Forwarded-Proto（反向代理场景）
    forwarded_host = request.headers.get('X-Forwarded-Host', '')
    forwarded_proto = request.headers.get('X-Forwarded-Proto', '')
    if forwarded_host:
        scheme = forwarded_proto or request.scheme
        return f"{scheme}://{forwarded_host}".rstrip('/')

    # 直接使用request.host_url
    return request.host_url.rstrip('/')


def _get_effective_api_key(name='通用下载自动创建', remark='通用下载自动创建'):
    """获取有效的API Key，用于注入config.json

    当inject_api_key配置为空时，复用已有的"通用下载"Key而非每次创建新Key，
    避免Key无限膨胀问题。

    优先级：
    1. inject_api_key（管理员明确配置的注入Key）
    2. 已有的同名活跃Key（复用，避免Key膨胀）
    3. 创建新Key（首次下载时）

    Args:
        name: 自动创建Key时使用的名称，默认'通用下载自动创建'
        remark: 自动创建Key时使用的备注
    """
    # 优先使用管理员配置的注入Key
    inject_key = AgentConfig.get_value('inject_api_key', default='')
    if inject_key:
        # 验证Key是否有效（存在且活跃）
        key_record = AgentApiKey.query.filter_by(
            api_key=inject_key, is_active=True
        ).first()
        if key_record:
            return inject_key
        # 配置的Key无效，清除配置并继续
        logger.warning(f"inject_api_key配置值无效或已禁用: {inject_key[:10]}...")

    # 查找已有的同名活跃Key（复用，避免Key膨胀）
    existing_key = AgentApiKey.query.filter_by(
        name=name, is_active=True
    ).first()
    if existing_key:
        return existing_key.api_key

    # 首次下载，创建新的通用Key
    key_record = _generate_api_key(name=name, remark=remark)
    db.session.commit()
    return key_record.api_key


# ==================== Agent端点 (API Key认证) ====================

@agent_api_bp.route('/register', methods=['POST'])
@require_agent_key
def register():
    """设备注册 - 三级查重策略

    查重顺序：1.device_fingerprint 2.hostname+mac_address 3.mac_address
    匹配成功则更新现有设备信息并重新分配UUID，否则创建新设备
    """
    disabled = check_agent_enabled()
    if disabled:
        return disabled
    data = request.get_json()
    if not data:
        return jsonify({"success": False, "message": "请求数据无效"}), 400
    # 验证 device_fingerprint 格式（SHA-256 hex：64个十六进制字符）
    if 'device_fingerprint' in data and data['device_fingerprint']:
        fp = data['device_fingerprint']
        if not (len(fp) == 64 and all(c in '0123456789abcdefABCDEF' for c in fp)):
            return jsonify({"success": False, "message": "device_fingerprint格式无效，必须为64位SHA-256十六进制字符串"}), 400
    # 验证 mac_address 格式
    if 'mac_address' in data and data['mac_address']:
        mac_pattern = re.compile(r'^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$')
        if not mac_pattern.match(data['mac_address']):
            return jsonify({"success": False, "message": "mac_address格式无效，必须为XX:XX:XX:XX:XX:XX格式"}), 400
    # 验证数值字段
    for num_field in ['cpu_cores', 'total_memory_mb', 'available_memory_mb']:
        if num_field in data and data[num_field] is not None:
            if not isinstance(data[num_field], (int, float)) or data[num_field] < 0:
                return jsonify({"success": False, "message": f"{num_field}必须为非负数值"}), 400
    device_fingerprint = data.get('device_fingerprint', '')
    hostname = data.get('hostname', '')
    mac_address = data.get('mac_address', '')
    # 三级查重
    device = None
    if device_fingerprint:
        device = AgentDevice.query.filter_by(device_fingerprint=device_fingerprint).first()
    if not device and hostname and mac_address:
        device = AgentDevice.query.filter_by(hostname=hostname, mac_address=mac_address).first()
    if not device and mac_address:
        # 三级匹配：仅MAC地址匹配，增加hostname校验降低误匹配风险
        if hostname:
            device = AgentDevice.query.filter_by(mac_address=mac_address).first()
            if device and device.hostname != hostname:
                logger.warning(f"MAC地址匹配但hostname不一致: 查询hostname={hostname}, 匹配设备hostname={device.hostname}, agent_id={device.agent_id}")
                device = None  # hostname不一致，不匹配
        else:
            # 无hostname时仍允许MAC匹配，但记录警告
            logger.warning(f"仅凭MAC地址匹配设备(无hostname): mac_address={mac_address}")
            device = AgentDevice.query.filter_by(mac_address=mac_address).first()
    try:
        if device:
            # 更新现有设备
            device.device_fingerprint = device_fingerprint or device.device_fingerprint
            device.hostname = hostname or device.hostname
            device.mac_address = mac_address or device.mac_address
            for field in DEVICE_AUTO_UPDATE_FIELDS:
                if field in data and data[field] is not None:
                    setattr(device, field, data[field])
            # 更新手动字段（空字符串转为None表示清空）
            for field in DEVICE_MANUAL_FIELDS:
                if field in data:
                    new_val = data[field] if data[field] else None
                    setattr(device, field, new_val)
            device.status = 'online'
            device.last_heartbeat_at = datetime.utcnow()
            device.uuid = str(uuid.uuid4())  # 重新分配UUID防止旧UUID被窃取
        else:
            # 创建新设备
            device = AgentDevice(
                agent_id=f"agent_{secrets.token_hex(8)}",
                uuid=str(uuid.uuid4()),
                device_fingerprint=device_fingerprint,
                hostname=hostname,
                mac_address=mac_address,
                os_name=data.get('os_name'),
                os_version=data.get('os_version'),
                os_arch=data.get('os_arch'),
                cpu_model=data.get('cpu_model'),
                cpu_cores=data.get('cpu_cores'),
                total_memory_mb=data.get('total_memory_mb'),
                available_memory_mb=data.get('available_memory_mb'),
                disks=json.dumps(data.get('disks')) if data.get('disks') is not None else None,
                network_interfaces=json.dumps(data.get('network_interfaces')) if data.get('network_interfaces') is not None else None,
                ip_address=data.get('ip_address'),
                agent_version=data.get('agent_version'),
                logged_in_user=data.get('logged_in_user'),
                platform=data.get('platform', 'windows'),
                asset_number=data.get('asset_number', ''),
                location=data.get('location', ''),
                department=data.get('department', ''),
                responsible_person=data.get('responsible_person', ''),
                status='online',
                last_heartbeat_at=datetime.utcnow(),
                first_seen_at=datetime.utcnow(),
            )
            db.session.add(device)
        # 回填API Key的agent_id（防止多设备覆盖绑定）
        if request.api_key_record.agent_id and request.api_key_record.agent_id != device.agent_id:
            logger.warning(f"API Key {request.api_key_record.api_key[:8]}... 已绑定设备 {request.api_key_record.agent_id}，"
                           f"拒绝设备 {device.agent_id} 的覆盖绑定请求")
        else:
            request.api_key_record.agent_id = device.agent_id
        request.api_key_record.last_used_at = datetime.utcnow()
        db.session.commit()
        heartbeat_interval = int(AgentConfig.get_value('heartbeat_interval', default='120'))
        server_url = AgentConfig.get_value('server_url', default='')
        return jsonify({
            "success": True,
            "data": {
                "agent_id": device.agent_id,
                "uuid": device.uuid,
                "heartbeat_interval": heartbeat_interval,
                "server_url": server_url,
            }
        })
    except Exception as e:
        db.session.rollback()
        logger.error(f"设备注册失败: {str(e)}", exc_info=True)
        return jsonify({"success": False, "message": "注册失败，请稍后重试"}), 500


@agent_api_bp.route('/heartbeat', methods=['POST'])
@require_agent_key
def heartbeat():
    """心跳上报 - UUID校验 + 配置下发 + 迁移通知"""
    disabled = check_agent_enabled()
    if disabled:
        return disabled
    data = request.get_json() or {}
    device_uuid = data.get('uuid', '')
    device = AgentDevice.query.filter_by(agent_id=request.agent_id).first()
    if not device:
        return jsonify({"success": False, "message": "设备未注册"}), 404
    # UUID校验 - 防止agent_id伪造
    if device.uuid and device_uuid and device_uuid != device.uuid:
        return jsonify({"success": False, "message": "UUID不匹配，请重新注册",
                         "uuid_mismatch": True}), 401
    try:
        device.status = 'online'
        device.last_heartbeat_at = datetime.utcnow()
        # 更新可选变化字段
        if data.get('ip_address'):
            device.ip_address = data['ip_address']
        if data.get('available_memory_mb'):
            device.available_memory_mb = data['available_memory_mb']
        if data.get('logged_in_user'):
            device.logged_in_user = data['logged_in_user']
        # 更新info_hash（客户端发送时更新服务端存储）
        if data.get('info_hash'):
            device.info_hash = data['info_hash']
        # 处理迁移确认：客户端确认迁移成功后，清除迁移配置
        if data.get('migration_confirmed'):
            AgentConfig.set_value('migration_enabled', 'false')
            AgentConfig.set_value('migration_new_url', '')
            logger.info(f"Agent {request.agent_id} 确认迁移成功，已清除迁移配置")
        # 双向同步到固定资产
        _sync_device_to_asset(device)
        # 心跳日志（可配置开关）
        if AgentConfig.get_value('heartbeat_log_enabled', default='false').lower() == 'true':
            db.session.add(AgentHeartbeatLog(
                agent_id=device.agent_id, ip_address=request.remote_addr))
        db.session.commit()
        # 构建响应
        heartbeat_interval = int(AgentConfig.get_value('heartbeat_interval', default='120'))
        # 构建 config_update 供客户端解析
        config_update = {"heartbeat_interval": heartbeat_interval}
        # 检查迁移配置
        if AgentConfig.get_value('migration_enabled', default='false').lower() == 'true':
            m_url = AgentConfig.get_value('migration_new_url', default='')
            if m_url:
                config_update["server_url"] = m_url
        # 解析并下发待执行远程指令
        commands = []
        if device.pending_commands:
            try:
                commands = json.loads(device.pending_commands)
                # 检查allow_remote_stop配置，如果未启用则过滤掉stop/restart指令
                if not AgentConfig.get_value('allow_remote_stop', default='false').lower() == 'true':
                    commands = [cmd for cmd in commands if isinstance(cmd, dict) and cmd.get('command') not in ('stop', 'restart')]
                if not isinstance(commands, list):
                    commands = []
                # 下发后清空待执行指令
                device.pending_commands = None
                db.session.commit()
            except (json.JSONDecodeError, TypeError):
                commands = []
        # info_hash变更检测：客户端发送的info_hash与服务端存储的不同时，下发report_now指令
        client_info_hash = data.get('info_hash', '')
        if client_info_hash and device.info_hash and client_info_hash != device.info_hash:
            cmd_names = [cmd.get('command', cmd) if isinstance(cmd, dict) else cmd for cmd in commands]
            if 'report_now' not in cmd_names:
                commands.append('report_now')
            logger.info(f"Agent {request.agent_id} info_hash变更，下发report_now指令")
        # 构建 sync_fields：服务端→客户端同步三字段
        sync_fields = {}
        if device.location:
            sync_fields["location"] = device.location
        if device.department:
            sync_fields["department"] = device.department
        if device.responsible_person:
            sync_fields["responsible_person"] = device.responsible_person

        resp = {"success": True, "data": {
            "heartbeat_interval": heartbeat_interval,
            "config_update": config_update,
            "commands": commands,
            "sync_fields": sync_fields}}
        return jsonify(resp)
    except Exception as e:
        db.session.rollback()
        logger.error(f"心跳处理失败: {str(e)}", exc_info=True)
        return jsonify({"success": False, "message": "心跳处理失败"}), 500


@agent_api_bp.route('/report', methods=['POST'])
@require_agent_key
def report():
    """设备信息上报 - 含双向同步（最后修改者胜出）"""
    disabled = check_agent_enabled()
    if disabled:
        return disabled
    data = request.get_json()
    if not data:
        return jsonify({"success": False, "message": "请求数据无效"}), 400
    # 验证 uuid 格式
    if 'uuid' in data and data['uuid']:
        uuid_pattern = re.compile(r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$')
        if not uuid_pattern.match(data['uuid']):
            return jsonify({"success": False, "message": "uuid格式无效"}), 400
    # 验证 info_hash 格式（SHA-256 hex）
    if 'info_hash' in data and data['info_hash']:
        ih = data['info_hash']
        if not (len(ih) == 64 and all(c in '0123456789abcdefABCDEF' for c in ih)):
            return jsonify({"success": False, "message": "info_hash格式无效"}), 400
    # 验证数值字段
    for num_field in ['cpu_cores', 'total_memory_mb', 'available_memory_mb']:
        if num_field in data and data[num_field] is not None:
            if not isinstance(data[num_field], (int, float)) or data[num_field] < 0:
                return jsonify({"success": False, "message": f"{num_field}必须为非负数值"}), 400
    device_uuid = data.get('uuid', '')
    device = AgentDevice.query.filter_by(agent_id=request.agent_id).first()
    if not device:
        return jsonify({"success": False, "message": "设备未注册"}), 404
    if device_uuid and device_uuid != device.uuid:
        return jsonify({"success": False, "message": "UUID不匹配，请重新注册",
                         "uuid_mismatch": True}), 401
    elif not device.uuid and device_uuid:
        # 设备UUID为空但客户端提交了UUID，可能是异常状态，记录但不拒绝
        logger.warning(f"设备 {device.agent_id} UUID为空但客户端提交了UUID: {device_uuid}")
    try:
        # 更新采集字段
        for field in DEVICE_AUTO_UPDATE_FIELDS:
            if field in data and data[field] is not None:
                setattr(device, field, data[field])
        # 更新手动字段
        manual_changed = False
        for field in DEVICE_MANUAL_FIELDS:
            if field in data:
                new_val = data[field] or None
                old_val = getattr(device, field) or None
                if new_val != old_val:
                    setattr(device, field, new_val)
                    manual_changed = True
        if manual_changed:
            device.updated_at = datetime.utcnow()
        # 双向同步到固定资产
        _sync_device_to_asset(device)
        db.session.commit()
        return jsonify({"success": True, "message": "信息上报成功"})
    except Exception as e:
        db.session.rollback()
        logger.error(f"信息上报失败: {str(e)}", exc_info=True)
        return jsonify({"success": False, "message": "信息上报失败"}), 500


@agent_api_bp.route('/offline', methods=['POST'])
@require_agent_key
def offline():
    """离线通知 - Agent主动通知服务端即将下线"""
    disabled = check_agent_enabled()
    if disabled:
        return disabled
    device = AgentDevice.query.filter_by(agent_id=request.agent_id).first()
    if not device:
        return jsonify({"success": False, "message": "设备未注册"}), 404
    try:
        device.status = 'offline'
        db.session.commit()
        return jsonify({"success": True, "message": "离线通知已接收"})
    except Exception as e:
        db.session.rollback()
        logger.error(f"离线通知处理失败: {str(e)}", exc_info=True)
        return jsonify({"success": False, "message": "离线通知处理失败"}), 500


# ==================== 管理端点 (login_required + permission) ====================

# --- API Key 管理 ---

@agent_api_bp.route('/keys', methods=['GET'])
@login_required
@require_permission('agent.manage')
def list_keys():
    """获取API Key列表"""
    keys = AgentApiKey.query.order_by(AgentApiKey.created_at.desc()).all()
    result = []
    for k in keys:
        # 关联设备数
        device_count = AgentDevice.query.filter_by(
            agent_id=k.agent_id).count() if k.agent_id else 0
        result.append({
            "id": k.id,
            "key_preview": k.api_key[:10] + '***' if k.api_key else '',  # 脱敏预览
            "name": k.name,
            "remark": k.remark,
            "is_active": k.is_active,
            "agent_id": k.agent_id,
            "device_count": device_count,
            "created_at": k.created_at.strftime('%Y-%m-%d %H:%M:%S') if k.created_at else None,
            "expires_at": k.expires_at.strftime('%Y-%m-%d %H:%M:%S') if k.expires_at else None,
            "last_used_at": k.last_used_at.strftime('%Y-%m-%d %H:%M:%S') if k.last_used_at else None,
        })
    return jsonify({"success": True, "data": {"keys": result}})


@agent_api_bp.route('/keys', methods=['POST'])
@login_required
@require_permission('agent.manage')
def create_key():
    """创建新API Key"""
    data = request.get_json() or {}
    name = data.get('name', '')
    remark = data.get('remark', '')
    try:
        key_record = _generate_api_key(
            name=name or '手动创建',
            remark=remark,
            created_by=current_user.id if hasattr(current_user, 'id') else None,
        )
        db.session.commit()
        log_operation(current_user.id if hasattr(current_user, 'id') else None,
                      f'创建API Key: {key_record.name}', module='资产代理')
        return jsonify({"success": True, "data": {
            "id": key_record.id,
            "api_key": key_record.api_key,  # 创建时返回完整Key
            "key": key_record.api_key,  # 兼容前端data.key读取方式
            "name": key_record.name,
        }})
    except Exception as e:
        db.session.rollback()
        logger.error(f"创建API Key失败: {str(e)}", exc_info=True)
        return jsonify({"success": False, "message": "创建失败"}), 500


@agent_api_bp.route('/keys/<int:key_id>', methods=['PUT'])
@login_required
@require_permission('agent.manage')
def update_key(key_id):
    """更新API Key（名称、备注、启用/禁用）"""
    key_record = AgentApiKey.query.get(key_id)
    if not key_record:
        return jsonify({"success": False, "message": "Key不存在"}), 404
    data = request.get_json() or {}
    try:
        if 'name' in data:
            key_record.name = data['name']
        if 'remark' in data:
            key_record.remark = data['remark']
        if 'is_active' in data:
            key_record.is_active = bool(data['is_active'])
        db.session.commit()
        log_operation(current_user.id if hasattr(current_user, 'id') else None,
                      f'更新API Key: {key_record.name}', module='资产代理')
        return jsonify({"success": True, "message": "更新成功"})
    except Exception as e:
        db.session.rollback()
        logger.error(f"更新API Key失败: {str(e)}", exc_info=True)
        return jsonify({"success": False, "message": "更新失败"}), 500


@agent_api_bp.route('/keys/<int:key_id>', methods=['DELETE'])
@login_required
@require_permission('agent.manage')
def delete_key(key_id):
    """删除API Key"""
    key_record = AgentApiKey.query.get(key_id)
    if not key_record:
        return jsonify({"success": False, "message": "Key不存在"}), 404
    try:
        key_name = key_record.name
        db.session.delete(key_record)
        db.session.commit()
        log_operation(current_user.id if hasattr(current_user, 'id') else None,
                      f'删除API Key: {key_name}', module='资产代理')
        return jsonify({"success": True, "message": "删除成功"})
    except Exception as e:
        db.session.rollback()
        logger.error(f"删除API Key失败: {str(e)}", exc_info=True)
        return jsonify({"success": False, "message": "删除失败"}), 500


# --- 设备管理 ---

@agent_api_bp.route('/devices', methods=['GET'])
@login_required
@require_permission('agent.view')
def list_devices():
    """获取设备列表（支持分页和筛选）"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    status = request.args.get('status', '')
    keyword = request.args.get('keyword', '')
    query = AgentDevice.query
    if status:
        query = query.filter_by(status=status)
    if keyword:
        query = query.filter(
            db.or_(
                AgentDevice.hostname.contains(keyword),
                AgentDevice.agent_id.contains(keyword),
                AgentDevice.mac_address.contains(keyword),
                AgentDevice.asset_number.contains(keyword),
            )
        )
    query = query.order_by(AgentDevice.last_heartbeat_at.desc())
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    # 计算设备在线/离线/总计统计
    stats_query = db.session.query(
        AgentDevice.status, db.func.count(AgentDevice.agent_id)
    ).group_by(AgentDevice.status).all()
    stats = {'online': 0, 'offline': 0, 'total': 0}
    for status_val, count in stats_query:
        if status_val == 'online':
            stats['online'] = count
        else:
            stats['offline'] += count
        stats['total'] += count

    devices = []
    for d in pagination.items:
        devices.append({
            "agent_id": d.agent_id,
            "hostname": d.hostname,
            "os_name": d.os_name,
            "os_version": d.os_version,
            "ip_address": mask_ip(d.ip_address),
            "mac_address": d.mac_address,
            "asset_number": d.asset_number,
            "status": d.status,
            "location": d.location,
            "department": d.department,
            "responsible_person": d.responsible_person,
            "agent_version": d.agent_version,
            "last_heartbeat_at": d.last_heartbeat_at.strftime('%Y-%m-%d %H:%M:%S') if d.last_heartbeat_at else None,
            "first_seen_at": d.first_seen_at.strftime('%Y-%m-%d %H:%M:%S') if d.first_seen_at else None,
        })
    return jsonify({
        "success": True,
        "data": {
            "devices": devices,
            "total": pagination.total,
            "page": pagination.page,
            "per_page": pagination.per_page,
            "pages": pagination.pages,
            "total_pages": pagination.pages,
            "stats": stats,
        }
    })


@agent_api_bp.route('/devices/by-asset/<int:asset_id>', methods=['GET'])
@login_required
@require_permission('agent.view')
def get_device_by_asset(asset_id):
    """根据固定资产ID查询关联的Agent设备信息"""
    device = AgentDevice.query.filter_by(asset_id=asset_id).first()
    if not device:
        return jsonify({"success": True, "device": None})
    return jsonify({
        "success": True,
        "device": {
            "id": device.id,
            "agent_id": device.agent_id,
            "hostname": device.hostname,
            "os_name": device.os_name,
            "os_version": device.os_version,
            "os_info": f"{device.os_name or ''} {device.os_version or ''}".strip() or None,
            "status": device.status,
            "agent_version": device.agent_version,
            "ip_address": mask_ip(device.ip_address),
            "last_heartbeat": device.last_heartbeat_at.strftime('%Y-%m-%d %H:%M:%S') if device.last_heartbeat_at else None,
            "last_heartbeat_at": device.last_heartbeat_at.strftime('%Y-%m-%d %H:%M:%S') if device.last_heartbeat_at else None,
            "first_seen_at": device.first_seen_at.strftime('%Y-%m-%d %H:%M:%S') if device.first_seen_at else None,
            "mac_address": device.mac_address,
            "platform": device.platform
        }
    })


@agent_api_bp.route('/devices/<agent_id>', methods=['GET'])
@login_required
@require_permission('agent.view')
def get_device(agent_id):
    """获取设备详情"""
    device = AgentDevice.query.filter_by(agent_id=agent_id).first()
    if not device:
        return jsonify({"success": False, "message": "设备不存在"}), 404
    # 解析JSON字段
    disks = None
    if device.disks:
        try:
            disks = json.loads(device.disks)
        except (json.JSONDecodeError, TypeError):
            disks = device.disks
    network_interfaces = None
    if device.network_interfaces:
        try:
            network_interfaces = json.loads(device.network_interfaces)
        except (json.JSONDecodeError, TypeError):
            network_interfaces = device.network_interfaces
    result = {
        "agent_id": device.agent_id,
        "uuid": device.uuid,
        "device_fingerprint": device.device_fingerprint,
        "hostname": device.hostname,
        "os_name": device.os_name,
        "os_version": device.os_version,
        "os_arch": device.os_arch,
        "cpu_model": device.cpu_model,
        "cpu_cores": device.cpu_cores,
        "total_memory_mb": device.total_memory_mb,
        "available_memory_mb": device.available_memory_mb,
        "disks": disks,
        "mac_address": device.mac_address,
        "ip_address": mask_ip(device.ip_address),
        "network_interfaces": network_interfaces,
        "agent_version": device.agent_version,
        "logged_in_user": device.logged_in_user,
        "platform": device.platform,
        "asset_id": device.asset_id,
        "asset_number": device.asset_number,
        "location": device.location,
        "department": device.department,
        "responsible_person": device.responsible_person,
        "status": device.status,
        "last_heartbeat_at": device.last_heartbeat_at.strftime('%Y-%m-%d %H:%M:%S') if device.last_heartbeat_at else None,
        "first_seen_at": device.first_seen_at.strftime('%Y-%m-%d %H:%M:%S') if device.first_seen_at else None,
        "created_at": device.created_at.strftime('%Y-%m-%d %H:%M:%S') if device.created_at else None,
        "updated_at": device.updated_at.strftime('%Y-%m-%d %H:%M:%S') if device.updated_at else None,
    }
    # 关联资产信息
    if device.asset:
        result["asset_info"] = {
            "id": device.asset.id,
            "asset_number": device.asset.asset_number,
            "asset_name": device.asset.asset_name,
            "asset_category": device.asset.asset_category,
            "storage_location": device.asset.storage_location,
            "responsible_person": device.asset.responsible_person,
        }
    return jsonify({"success": True, "data": result})


# --- 客户端下载 ---

@agent_api_bp.route('/download', methods=['GET'])
@login_required
@require_permission('agent.manage')
def download_agent():
    """下载通用Agent客户端（动态注入server_url和api_key）

    生成config.json + asset-agent.exe打包为zip
    通用下载不含asset_number
    使用通用秘钥：inject_api_key为空时复用已有的"通用下载"Key
    """
    try:
        # 获取有效的服务器地址和API Key
        server_url = _get_effective_server_url()
        api_key = _get_effective_api_key(name='通用下载自动创建', remark='通用下载自动创建')
        # 构建config.json
        heartbeat_interval = AgentConfig.get_value('heartbeat_interval', default='120')
        config = {
            "server_url": server_url,
            "api_key": api_key,
            "heartbeat_interval": int(heartbeat_interval),
            "asset_number": ""
        }
        return _build_agent_zip(config, 'asset-agent-generic.zip')
    except Exception as e:
        logger.error(f"下载Agent客户端失败: {str(e)}", exc_info=True)
        return jsonify({"success": False, "message": "下载失败"}), 500


@agent_api_bp.route('/download/<asset_number>', methods=['GET'])
@login_required
@require_permission('agent.manage')
def download_agent_for_asset(asset_number):
    """下载资产关联Agent客户端（含asset_number和同步字段）

    仅允许asset_category为'电脑'的资产
    使用通用秘钥：inject_api_key为空时复用已有的"通用下载"Key
    """
    asset = FixedAsset.query.filter_by(asset_number=asset_number).first()
    if not asset:
        return jsonify({"success": False, "message": "资产不存在"}), 404
    if asset.asset_category != '电脑':
        return jsonify({"success": False, "message": "仅支持电脑类资产"}), 400
    try:
        # 获取有效的服务器地址和API Key
        server_url = _get_effective_server_url()
        api_key = _get_effective_api_key(name='通用下载自动创建', remark='通用下载自动创建')
        # 构建config.json（含asset_number和三字段）
        heartbeat_interval = AgentConfig.get_value('heartbeat_interval', default='120')
        dept_name = asset.dept_using.name if asset.dept_using else ''
        config = {
            "server_url": server_url,
            "api_key": api_key,
            "heartbeat_interval": int(heartbeat_interval),
            "asset_number": asset_number,
            "location": asset.storage_location or '',
            "department": dept_name,
            "responsible_person": asset.responsible_person or '',
        }
        filename = f'asset-agent-{asset_number}.zip'
        return _build_agent_zip(config, filename)
    except Exception as e:
        logger.error(f"下载资产关联Agent客户端失败: {str(e)}", exc_info=True)
        return jsonify({"success": False, "message": "下载失败"}), 500


def _build_agent_zip(config, zip_filename):
    """构建Agent客户端zip包（config.json + asset-agent.exe）"""
    exe_path = _get_agent_exe_path()
    if not os.path.exists(exe_path):
        return jsonify({"success": False, "message": "Agent客户端文件不存在"}), 404
    memory_zip = io.BytesIO()
    with zipfile.ZipFile(memory_zip, 'w', zipfile.ZIP_DEFLATED) as zf:
        # 写入config.json
        zf.writestr('config.json', json.dumps(config, ensure_ascii=False, indent=2))
        # 写入asset-agent.exe
        zf.write(exe_path, 'asset-agent.exe')
    memory_zip.seek(0)
    return send_file(
        memory_zip,
        mimetype='application/zip',
        as_attachment=True,
        download_name=zip_filename,
    )


# --- 脚本下载 ---

@agent_api_bp.route('/stop-script', methods=['GET'])
@login_required
@require_permission('agent.manage')
def download_stop_script():
    """下载停止Agent脚本（stop-agent.bat）"""
    agent_id = request.args.get('agent_id', '')
    agent_label = f' (Agent ID: {agent_id})' if agent_id else ''
    script = (
        '@echo off\r\n'
        'chcp 65001 >nul\r\n'
        f'echo 正在停止Asset Agent{agent_label}...\r\n'
        'taskkill /IM asset-agent.exe /F 2>nul\r\n'
        'if %errorlevel% equ 0 (\r\n'
        f'    echo Agent{agent_label}已停止\r\n'
        ') else (\r\n'
        f'    echo Agent{agent_label}未运行或停止失败\r\n'
        ')\r\n'
        'pause\r\n'
    )
    buf = io.BytesIO(script.encode('utf-8'))
    return send_file(buf, mimetype='application/bat',
                     as_attachment=True, download_name='stop-agent.bat')


@agent_api_bp.route('/uninstall-script', methods=['GET'])
@login_required
@require_permission('agent.manage')
def download_uninstall_script():
    """下载卸载Agent脚本（uninstall-agent.bat）"""
    agent_id = request.args.get('agent_id', '')
    agent_label = f' (Agent ID: {agent_id})' if agent_id else ''
    script = (
        '@echo off\r\n'
        'chcp 65001 >nul\r\n'
        f'echo 正在卸载Asset Agent{agent_label}...\r\n'
        ':: 停止Agent进程\r\n'
        'taskkill /IM asset-agent.exe /F 2>nul\r\n'
        ':: 删除开机自启注册表项\r\n'
        'reg delete "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run" /v AssetAgent /f 2>nul\r\n'
        ':: 删除程序数据目录\r\n'
        'rd /s /q "%ProgramData%\\AssetAgent" 2>nul\r\n'
        ':: 删除配置文件\r\n'
        'del /f /q "config.json" 2>nul\r\n'
        f'echo Agent{agent_label}卸载完成\r\n'
        'pause\r\n'
    )
    buf = io.BytesIO(script.encode('utf-8'))
    return send_file(buf, mimetype='application/bat',
                     as_attachment=True, download_name='uninstall-agent.bat')


@agent_api_bp.route('/edit-info-script', methods=['GET'])
@login_required
@require_permission('agent.manage')
def download_edit_info_script():
    """下载编辑配置脚本（edit-info-agent.bat）

    通过命名管道IPC通知运行中的Agent打开编辑窗口
    """
    agent_id = request.args.get('agent_id', '')
    agent_label = f' (Agent ID: {agent_id})' if agent_id else ''
    server_url = _get_effective_server_url()
    script = (
        '@echo off\r\n'
        'chcp 65001 >nul\r\n'
        f'echo 正在打开Agent{agent_label}配置编辑窗口...\r\n'
        ':: 通过命名管道IPC通知Agent打开编辑窗口\r\n'
        'echo edit_info>\\\\.\\pipe\\AssetAgent 2>nul\r\n'
        'if %errorlevel% equ 0 (\r\n'
        f'    echo 已发送编辑指令，Agent{agent_label}将打开编辑窗口\r\n'
        ') else (\r\n'
        f'    echo 发送失败，请确保Agent{agent_label}正在运行\r\n'
        ')\r\n'
        f'echo 服务器地址: {server_url}\r\n'
        'timeout /t 3 >nul\r\n'
    )
    buf = io.BytesIO(script.encode('utf-8'))
    return send_file(buf, mimetype='application/bat',
                     as_attachment=True, download_name='edit-info-agent.bat')


# --- 配置管理 ---

@agent_api_bp.route('/config', methods=['GET'])
@login_required
@require_permission('agent.manage')
def get_config():
    """获取Agent配置列表"""
    configs = AgentConfig.query.order_by(AgentConfig.id).all()
    result = []
    for c in configs:
        result.append({
            "key": c.config_key,
            "value": c.config_value,
            "description": c.description,
        })
    # 追加agent_enabled从SystemConfig读取（该配置项存储在SystemConfig表而非AgentConfig表）
    agent_enabled = SystemConfig.get_config('AGENT_ENABLED', default='true')
    result.append({
        "key": "agent_enabled",
        "value": str(agent_enabled).lower() if isinstance(agent_enabled, bool) else str(agent_enabled),
        "description": "Agent系统全局开关",
    })
    # 自动填充server_url默认值（当server_url为空时使用当前请求来源地址，支持反向代理）
    for item in result:
        if item['key'] == 'server_url' and not item['value']:
            # 优先检查X-Forwarded-Host（反向代理场景）
            forwarded_host = request.headers.get('X-Forwarded-Host', '')
            forwarded_proto = request.headers.get('X-Forwarded-Proto', '')
            if forwarded_host:
                scheme = forwarded_proto or request.scheme
                item['value'] = f"{scheme}://{forwarded_host}".rstrip('/')
            else:
                item['value'] = request.host_url.rstrip('/')
    return jsonify({"success": True, "data": result})


@agent_api_bp.route('/config', methods=['PUT'])
@login_required
@require_permission('agent.manage')
def update_config():
    """更新Agent配置（批量更新）"""
    data = request.get_json()
    if not data or 'configs' not in data:
        return jsonify({"success": False, "message": "请求数据无效"}), 400
    try:
        updated = []
        for item in data['configs']:
            key = item.get('key', '').strip().lower()
            value = item.get('value', '')
            if not key:
                continue
            # 白名单检查
            if key not in ALLOWED_CONFIG_KEYS:
                return jsonify({"success": False, "message": f"不允许的配置键: {key}"}), 400
            # 数值范围验证
            if key == 'heartbeat_interval':
                try:
                    val = int(value)
                    if val < 30 or val > 600:
                        return jsonify({"success": False, "message": "heartbeat_interval必须为30-600之间的整数"}), 400
                except (ValueError, TypeError):
                    return jsonify({"success": False, "message": "heartbeat_interval必须为整数"}), 400
            elif key == 'offline_threshold':
                try:
                    val = int(value)
                    if val < 60 or val > 86400:
                        return jsonify({"success": False, "message": "offline_threshold必须为60-86400之间的整数"}), 400
                except (ValueError, TypeError):
                    return jsonify({"success": False, "message": "offline_threshold必须为整数"}), 400
            elif key == 'heartbeat_log_retention_days':
                try:
                    val = int(value)
                    if val < 1 or val > 365:
                        return jsonify({"success": False, "message": "heartbeat_log_retention_days必须为1-365之间的整数"}), 400
                except (ValueError, TypeError):
                    return jsonify({"success": False, "message": "heartbeat_log_retention_days必须为整数"}), 400
            # 布尔值验证
            elif key in ('migration_enabled', 'allow_remote_stop', 'heartbeat_log_enabled'):
                if str(value).lower() not in ('true', 'false'):
                    return jsonify({"success": False, "message": f"{key}必须为true或false"}), 400
            # URL格式验证
            elif key in ('server_url', 'inject_server_url', 'migration_new_url'):
                if value and not (str(value).startswith('http://') or str(value).startswith('https://')):
                    return jsonify({"success": False, "message": f"{key}必须以http://或https://开头"}), 400
            AgentConfig.set_value(key, str(value))
            updated.append(key)
        log_operation(current_user.id if hasattr(current_user, 'id') else None,
                      f'更新配置: {", ".join(updated)}', module='资产代理')
        return jsonify({"success": True, "message": "配置更新成功", "data": {"updated": updated}})
    except Exception as e:
        db.session.rollback()
        logger.error(f"更新Agent配置失败: {str(e)}", exc_info=True)
        return jsonify({"success": False, "message": "更新失败"}), 500


# --- 全局开关 ---

@agent_api_bp.route('/toggle', methods=['POST'])
@login_required
@require_permission('agent.manage')
def toggle_agent():
    """切换Agent系统全局开关（AGENT_ENABLED）

    禁用后所有Agent API返回403，管理端不受影响
    """
    data = request.get_json() or {}
    enabled = data.get('enabled', True)
    try:
        user_id = current_user.id if hasattr(current_user, 'id') else None
        # 尝试更新配置，若配置项不存在则自动创建
        result = SystemConfig.update_config('AGENT_ENABLED', str(enabled), user_id=user_id)
        if not result:
            # 配置项不存在（已有安装未包含该默认配置），直接创建
            config = SystemConfig(
                config_key='AGENT_ENABLED',
                config_value='True' if enabled else 'False',
                config_type='bool',
                category='system.feature',
                description='Agent系统全局开关，禁用后所有Agent API返回403',
                is_editable=True,
                sort_order=170,
                updated_by=user_id
            )
            db.session.add(config)
            db.session.commit()
        status_text = '启用' if enabled else '禁用'
        log_operation(user_id, f'{status_text}Agent系统', module='资产代理')
        return jsonify({"success": True, "message": f"Agent系统已{status_text}"})
    except Exception as e:
        db.session.rollback()
        logger.error(f"切换Agent开关失败: {str(e)}", exc_info=True)
        return jsonify({"success": False, "message": "操作失败"}), 500


# --- 服务器迁移 ---

@agent_api_bp.route('/migrate', methods=['POST'])
@login_required
@require_permission('fixed_asset.manage')
def migrate_agent():
    """设置服务器迁移通知

    启用后Agent心跳响应中会包含config_update字段，
    通知Agent迁移到新服务器地址
    """
    data = request.get_json()
    if not data:
        return jsonify({"success": False, "message": "请求数据无效"}), 400
    new_url = data.get('new_server_url', '')
    # 验证URL协议（仅允许http://或https://）
    if new_url and not (new_url.startswith('http://') or new_url.startswith('https://')):
        return jsonify({"success": False, "message": "迁移URL必须以http://或https://开头"}), 400
    enabled = data.get('enabled', False)
    if enabled and not new_url:
        return jsonify({"success": False, "message": "启用迁移时必须提供新服务器地址"}), 400
    try:
        AgentConfig.set_value('migration_enabled', str(enabled).lower())
        AgentConfig.set_value('migration_new_url', new_url)
        status_text = '启用' if enabled else '禁用'
        log_operation(current_user.id if hasattr(current_user, 'id') else None,
                      f'{status_text}服务器迁移，目标: {new_url or "无"}', module='资产代理')
        return jsonify({"success": True, "message": f"迁移通知已{status_text}"})
    except Exception as e:
        db.session.rollback()
        logger.error(f"设置迁移通知失败: {str(e)}", exc_info=True)
        return jsonify({"success": False, "message": "操作失败"}), 500


# --- 设备手动字段更新 ---

@agent_api_bp.route('/devices/<agent_id>/manual-fields', methods=['PUT'])
@login_required
@require_permission('agent.manage')
def update_device_manual_fields(agent_id):
    """更新设备手动字段（location/department/responsible_person）

    管理端修改后同步到关联的固定资产
    """
    device = AgentDevice.query.filter_by(agent_id=agent_id).first()
    if not device:
        return jsonify({"success": False, "message": "设备不存在"}), 404
    data = request.get_json()
    if not data:
        return jsonify({"success": False, "message": "请求数据无效"}), 400
    try:
        changed = False
        for field in DEVICE_MANUAL_FIELDS:
            if field in data:
                new_val = data[field] or None
                old_val = getattr(device, field) or None
                if new_val != old_val:
                    setattr(device, field, new_val)
                    changed = True
        if changed:
            device.updated_at = datetime.utcnow()
            # 同步到关联的固定资产
            _sync_device_to_asset(device)
        db.session.commit()
        log_operation(current_user.id if hasattr(current_user, 'id') else None,
                      f'更新设备手动字段: {agent_id}', module='资产代理')
        return jsonify({"success": True, "message": "更新成功"})
    except Exception as e:
        db.session.rollback()
        logger.error(f"更新设备手动字段失败: {str(e)}", exc_info=True)
        return jsonify({"success": False, "message": "更新失败"}), 500


@agent_api_bp.route('/devices/<agent_id>/commands', methods=['POST'])
@login_required
@require_permission('agent.manage')
def send_device_command(agent_id):
    """向设备下发远程指令

    支持的指令类型：
      - report_now: 立即上报设备信息
      - stop: 停止Agent服务
      - update_interval: 更新心跳间隔（需带interval参数）

    指令将在下次心跳时下发给Agent客户端
    """
    device = AgentDevice.query.filter_by(agent_id=agent_id).first()
    if not device:
        return jsonify({"success": False, "message": "设备不存在"}), 404
    data = request.get_json()
    if not data or 'command' not in data:
        return jsonify({"success": False, "message": "缺少command参数"}), 400
    command = data.get('command', '')
    if command not in ('report_now', 'stop', 'update_interval', 'restart'):
        return jsonify({"success": False, "message": f"不支持的指令: {command}"}), 400
    # 检查allow_remote_stop配置：stop/restart指令需要该配置启用
    if command in ('stop', 'restart'):
        if not AgentConfig.get_value('allow_remote_stop', default='false').lower() == 'true':
            return jsonify({"success": False, "message": "远程停止功能未启用，请先在设置中开启allow_remote_stop"}), 400
    try:
        # 构建指令对象
        cmd_obj = {"command": command}
        if command == 'update_interval':
            interval = data.get('interval', 0)
            if not isinstance(interval, int) or interval < 30 or interval > 600:
                return jsonify({"success": False, "message": "interval必须为30-600之间的整数"}), 400
            cmd_obj["interval"] = interval
        # 追加到pending_commands
        existing = []
        if device.pending_commands:
            try:
                existing = json.loads(device.pending_commands)
                if not isinstance(existing, list):
                    existing = []
            except (json.JSONDecodeError, TypeError):
                existing = []
        existing.append(cmd_obj)
        device.pending_commands = json.dumps(existing)
        db.session.commit()
        log_operation(current_user.id if hasattr(current_user, 'id') else None,
                      f'向设备{agent_id}下发指令: {command}', module='资产代理')
        return jsonify({"success": True, "message": f"指令{command}已加入待下发队列"})
    except Exception as e:
        db.session.rollback()
        logger.error(f"下发设备指令失败: {str(e)}", exc_info=True)
        return jsonify({"success": False, "message": "操作失败"}), 500


# --- 从固定资产同步 ---

@agent_api_bp.route('/sync-from-asset/<int:asset_id>', methods=['POST'])
@login_required
@require_permission('fixed_asset.manage')
def sync_from_asset(asset_id):
    """从固定资产同步字段到关联的Agent设备

    将固定资产的 storage_location/dept_using.name/responsible_person
    同步到关联Agent设备的 location/department/responsible_person
    """
    asset = FixedAsset.query.get(asset_id)
    if not asset:
        return jsonify({"success": False, "message": "资产不存在"}), 404
    # 查找关联的Agent设备
    device = AgentDevice.query.filter_by(asset_id=asset_id).first()
    if not device:
        return jsonify({"success": False, "message": "该资产未关联Agent设备"}), 404
    try:
        _sync_asset_to_device(asset, device)
        db.session.commit()
        log_operation(current_user.id if hasattr(current_user, 'id') else None,
                      f'从资产{asset.asset_number}同步到设备{device.agent_id}',
                      module='资产代理')
        return jsonify({"success": True, "message": "同步成功"})
    except Exception as e:
        db.session.rollback()
        logger.error(f"从固定资产同步失败: {str(e)}", exc_info=True)
        return jsonify({"success": False, "message": "同步失败"}), 500