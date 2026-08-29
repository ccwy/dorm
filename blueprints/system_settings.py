from flask import Blueprint, current_app, flash, redirect, url_for, render_template, request, jsonify
from flask_login import login_required, current_user
import logging
from utils.db import db, init_db  # 导入init_db用于数据库初始化
from sqlalchemy import text
import os
import json
import time
import shutil
import datetime
from datetime import timedelta
from models.user import User
from models.room import Room
from models.utility_room_meter import UtilityMeterReading
from models.system_config import SystemConfig  # 系统配置模型
from utils.log import log_operation
from utils.auth import require_permission  # 从独立模块导入权限装饰器
from config import Config
from utils.db_config import DatabaseConfig  # 导入DatabaseConfig类用于读取本地JSON配置


system_config_bp = Blueprint('system_settings', __name__, url_prefix='/system')

# 模块配置列表 - 与SystemConfig模型中的category严格匹配
MODULES = [
    {"name": "系统核心配置", "category": "system", "icon": "cogs"},
    {"name": "系统功能开关", "category": "system.feature", "icon": "toggle-on"},
    #{"name": "数据库配置", "category": "system.db", "icon": "database"},
    {"name": "用户管理配置", "category": "user", "icon": "users"},
    {"name": "房间管理配置", "category": "room", "icon": "bed"},
    #{"name": "宿舍管理配置", "category": "dorm", "icon": "building"},
    {"name": "水电费管理配置", "category": "fee", "icon": "money"},
    {"name": "固定资产管理配置", "category": "asset", "icon": "cube"},
    {"name": "低值易耗品管理配置", "category": "supply", "icon": "cubes"},

    #{"name": "考勤管理配置", "category": "attendance", "icon": "calendar-check-o"},
    #{"name": "合同管理配置", "category": "contract", "icon": "file-text-o"},
    #{"name": "日志管理配置", "category": "log", "icon": "history"},
    {"name": "备份配置", "category": "system.backup", "icon": "history"}
]

from . import system_settings_backup  # 数据备份模块
from . import system_settings_initialize  # 数据初始化模块

@system_config_bp.route('/api/by_configs_key/<string:key>', methods=['GET'])
@login_required
def get_config_by_key(key):
    """根据配置键获取配置值的API接口 - 优先从本地JSON文件获取system模块配置"""
    try:
        # 定义需要从本地JSON文件获取的配置项列表
        json_config_keys = [
            'SQL_TYPE', 'MYSQL_HOST', 'MYSQL_PORT', 'MYSQL_DB', 'MYSQL_USER', 'MYSQL_PASSWORD',
            'SERVER_PORT', 'SERVER_MODE', 'SYSTEM_TITLE'
        ]
        
        # 检查是否是需要从JSON文件获取的配置项
        if key in json_config_keys:
            # 从本地JSON文件获取配置
            local_config = DatabaseConfig.load_config()
            if key in local_config:
                config_value = local_config[key]

                logging.info(f"从本地JSON文件查询配置项 {key}")
                # 获取配置的额外信息（仍然从数据库获取元数据）
                db_config = SystemConfig.query.filter_by(config_key=key).first()
                
                return jsonify({
                    "success": True,
                    "message": "配置项获取成功（本地JSON文件）",
                    "data": {
                        "key": key,
                        "value": config_value,
                        "type": db_config.config_type if db_config else 'string',
                        "description": db_config.description if db_config else f"本地配置项 {key}",
                        "category": 'system',
                        "is_editable": db_config.is_editable if db_config else True
                    }
                })
        
        # 如果不是指定的JSON配置项，或者在JSON中未找到，则从数据库获取
        config_value = SystemConfig.get_config_value(key)
        
        # 检查配置是否存在
        if config_value is None:
            logging.error(f"查询配置项 {key},失败：配置项不存在")
            return jsonify({
                "success": False,
                "message": f"配置项 {key} 不存在",
                "data": None
            }), 404
        
        
        # 返回成功响应
        return jsonify({
            "success": True,
            "message": "配置项获取成功",
            "data": {
                "key": key,
                "value": config_value,
                # 获取配置项的额外信息
                "type": SystemConfig.query.filter_by(config_key=key).first().config_type,
                "description": SystemConfig.query.filter_by(config_key=key).first().description,
                "category": SystemConfig.query.filter_by(config_key=key).first().category,
                "is_editable": SystemConfig.query.filter_by(config_key=key).first().is_editable
            }
        })
        
    except Exception as e:
        # 记录错误日志
        logging.error(f"获取配置项 {key} 时发生错误: {str(e)}", exc_info=True)
        # 返回错误响应
        return jsonify({
            "success": False,
            "message": f"获取配置项时发生错误: {str(e)}",
            "data": None
        }), 500

@system_config_bp.route('/settings')
@login_required
@require_permission('system_settings.view')
def settings():
    # 根据用户权限过滤模块列表
    filtered_modules = []
    for module in MODULES:
        # 对于system模块，只对超级管理员显示
        if module['category'] == 'system' and not (current_user.user_role and current_user.user_role.code == 'super_admin'):
            continue
        filtered_modules.append(module)
    
    # 记录访问日志
    log_operation(
            user_id=current_user.id,
            module='system',
            operation_type='records',
            action="访问系统设置页面",
            result="成功"
    )
    return render_template('system_settings/system_settings.html', modules=filtered_modules,title=f"系统设置")

@system_config_bp.route('/api/modules', methods=['GET'])
@login_required
@require_permission('system_settings.view')
def get_modules():
    try:
        # 根据用户权限过滤模块列表
        filtered_modules = []
        for module in MODULES:
            # 对于system模块，只对超级管理员显示
            if module['category'] == 'system' and not (current_user.user_role and current_user.user_role.code == 'super_admin'):
                continue
            
            category = module['category']
            config_count = SystemConfig.query.filter_by(category=category).count()
            module_copy = module.copy()  # 复制模块对象，避免修改原始数据
            module_copy['has_config'] = config_count > 0
            filtered_modules.append(module_copy)
            
        return jsonify({
            "success": True,
            "data": filtered_modules
        })
    except Exception as e:
        logging.error(f"获取模块列表失败: {str(e)}")
        return jsonify({
            "success": False,
            "message": f"获取模块列表失败: {str(e)}"
        }), 500

@system_config_bp.route('/api/configs/<category>', methods=['GET'])
@login_required
@require_permission('system_settings.view')
def get_module_configs(category):
    try:
        # 转换category格式，确保与模型匹配
        normalized_category = category.replace('-', '.')
        
        # 验证模块是否存在
        if not any(m['category'] == normalized_category for m in MODULES):
            
            logging.error(f"模块 {category} 不存在或未授权访问")
            return jsonify({
                "success": False,
                "message": f"模块 {category} 不存在或未授权访问"
            }), 404
        
        # 从模型获取配置，包含类型转换
        configs = SystemConfig.get_category_configs(normalized_category)
        
        # 获取原始配置信息（包含类型等元数据）
        raw_configs = SystemConfig.query.filter_by(category=normalized_category).all()
        config_metadata = {
            item.config_key: {
                'config_type': item.config_type,
                'is_editable': item.is_editable,
                'description': item.description,
                'sort_order': item.sort_order
            } for item in raw_configs
        }
        
        # 如果是system模块，优先从本地JSON文件获取指定配置项的值
        if normalized_category == 'system':
            # 定义需要从本地JSON文件获取的配置项列表
            json_config_keys = [
                'SQL_TYPE', 'MYSQL_HOST', 'MYSQL_PORT', 'MYSQL_DB', 'MYSQL_USER', 'MYSQL_PASSWORD',
                'SERVER_PORT', 'SERVER_MODE', 'SYSTEM_TITLE'
            ]
            
            # 从本地JSON文件获取配置
            local_config = DatabaseConfig.load_config()
            
            # 更新配置值为本地JSON文件中的值
            for key in json_config_keys:
                if key in local_config:
                    configs[key] = local_config[key]
                    


        return jsonify({
            "success": True,
            "data": configs,
            "metadata": config_metadata,
            "module": next(m for m in MODULES if m['category'] == normalized_category)
        })
    except Exception as e:
        logging.error(f"获取{category}模块配置失败: {str(e)}")

        return jsonify({
            "success": False,
            "message": f"获取配置失败: {str(e)}"
        }), 500

@system_config_bp.route('/api/configs/update', methods=['POST'])
@login_required
@require_permission('system_settings.manage')
def update_configs():
    try:
        data = request.get_json()
        category = data.get('category', '').replace('-', '.')
        configs = data.get('configs', {})
        
        if not category or not configs:
            logging.warning(f"尝试更新模块配置: {category}, 缺少必要参数")
            return jsonify({
                "success": False,
                "message": "缺少必要参数"
            }), 400
        
        if not any(m['category'] == category for m in MODULES):
            logging.warning(f"尝试更新不存在的模块配置: {category}")
            return jsonify({
                "success": False,
                "message": f"模块 {category} 不存在"
            }), 404
        
        # 对于system模块，需要超级管理员权限
        if category == 'system' and not (current_user.user_role and current_user.user_role.code == 'super_admin'):
            logging.warning(f"非超级管理员用户{current_user.username}尝试修改系统核心配置失败")
            return jsonify({
                "success": False,
                "message": "需要超级管理员权限才能修改系统核心配置"
            }), 403
        
        # 检查是否在Docker环境中且尝试将SERVER_MODE修改为服务端
        from utils.system_detector import is_docker
        if is_docker() and category == 'system' and 'SERVER_MODE' in configs and str(configs['SERVER_MODE']) == '服务端':
            logging.warning("在Docker环境中不允许将SERVER_MODE修改为服务端")
            return jsonify({
                "success": False,
                "message": "在Docker环境中不允许修改启动类型(SERVER_MODE)"
            }), 403
        
        updated_keys = []
        db_config_updates = {}      #数据库更新
        backup_config_updates = {}  #自动备份
        fee_config_updates = {}     #自定义抄表日期和开启开关
       
        is_db_config = category == 'system'             # 检查是否是数据库配置更新
        is_backup_config = category == 'system.backup'  #检查是否是自动备份更新
        is_fee_config = category == 'fee'         #自定义抄表日期和开启开关

        for key, value in configs.items():
            config_item = SystemConfig.query.filter_by(
                config_key=key, 
                category=category
            ).first()
            
            if config_item:
                # 检查是否可编辑
                if not config_item.is_editable:
                    logging.warning(f"尝试更新不可编辑的配置项: {key}")
                    continue
                # 对于数据库配置项，记录需要更新到外部文件的内容
                if is_db_config :
                    # 转换值为合适的类型
                    if key == 'MYSQL_PORT':
                        try:
                            db_config_updates[key] = int(value)
                        except ValueError:
                            db_config_updates[key] = 3306  # MySQL端口默认值
                    elif key == 'SERVER_PORT':
                        try:
                            db_config_updates[key] = int(value)
                        except ValueError:
                            db_config_updates[key] = 35168  # 服务器端口默认值
                    elif key == 'SQL_TYPE':
                        try:
                            db_config_updates[key] = str(value).strip().upper() # 自动转换为大写
                        except ValueError:
                            db_config_updates[key] = 'SQLITE'  # 默认数据库类型
                    elif key == 'SERVER_MODE':
                        try:
                            db_config_updates[key] = str(value) # 设置默认启动模式值
                        except ValueError:
                            db_config_updates[key] = '客户端'  # 默认启动模式值
                    elif key == 'SYSTEM_TITLE':
                        try:
                            db_config_updates[key] = str(value) # 设置系统标题值
                        except ValueError:
                            db_config_updates[key] = '宿舍管理系统'  # 默认系统标题值
                    else:
                        db_config_updates[key] = value
                        
                #自动备份
                if is_backup_config :
                    if key == 'BACKUP_RETENTION_COUNT':
                        try:
                            backup_config_updates[key] = int(value)
                        except ValueError:
                            backup_config_updates[key] = 30  # 自动备份数量默认值
                    elif key == 'BACKUP_INTERVAL':  # 修复重复定义的问题
                        try:
                            backup_config_updates[key] = int(value)
                        except ValueError:
                            backup_config_updates[key] = 86400  # 自动备份间隔时间默认值
                    elif key == 'ENABLE_AUTO_BACKUP':  # 添加布尔类型处理
                        # 确保ENABLE_AUTO_BACKUP被正确转换为布尔值
                        backup_config_updates[key] = str(value).lower() == 'true' or value is True
                    else:
                        backup_config_updates[key] = value

                # 自定义抄表日期和开启开关
                if is_fee_config :
                    if key == 'ENABLE_CUSTOM_METER_READING_DAY':
                            fee_config_updates[key] = str(value).lower() == 'true' or value is True
                    elif key == 'CUSTOM_METER_READING_DAY':
                        try:
                            fee_config_updates[key] = int(value)
                        except ValueError:
                            fee_config_updates[key] = 1  # 日期默认值
                    # 移除else分支，只保存特定的配置项，避免整个模块被保存进去

                
                # 根据配置类型进行值转换，与模型保持一致
                try:
                    converted_value = value
                    if config_item.config_type == 'bool':
                        # 修复：保持布尔值类型，不要转换为字符串
                        # 正确处理前端可能传递的字符串形式的布尔值
                        if isinstance(value, str):
                            converted_value = value.lower() == 'true'
                        else:
                            converted_value = bool(value)
                    elif config_item.config_type in ['int', 'float']:
                        converted_value = str(value)
                    elif config_item.config_type == 'list' and isinstance(value, list):
                        converted_value = ','.join(map(str, value))
                    elif config_item.config_type == 'dict' and isinstance(value, dict):
                        converted_value = ';'.join([f"{k}:{v}" for k, v in value.items()])
                    elif config_item.config_type == 'json':
                        converted_value = json.dumps(value)
                        
                    if SystemConfig.update_config(key, converted_value, current_user.id):
                        updated_keys.append(key)
                except Exception as te:
                    logging.error(f"配置项 {key} 类型转换失败: {str(te)}")
            else:
                # 新增配置时需要指定类型，默认为string
                new_config = SystemConfig(
                    config_key=key,
                    config_value=str(value),
                    config_type='string',  # 默认类型
                    category='config_update',
                    description=f'新增配置项 {key}',
                    updated_by=current_user.id
                )
                db.session.add(new_config)
                updated_keys.append(key)
                
            message = f"更新{category}模块配置,成功更新{len(updated_keys)}项配置"

         #费用主表自动生成月度记录
        if is_fee_config and fee_config_updates:
            from utils.db_config import DatabaseConfig    
            # 保存到外部配置文件
            DatabaseConfig.update_config(fee_config_updates)
            logging.info(f"自定义抄表日期和开启开关设置已更新: {fee_config_updates}")
            db.session.commit()
            message = f"更新{category}模块配置,成功更新{len(updated_keys)}项配置，自定义抄表日期和开启开关设置已更新"

        #自动备份配置
        if is_backup_config and backup_config_updates:
            from utils.db_config import DatabaseConfig    
            # 保存到外部配置文件
            DatabaseConfig.update_config(backup_config_updates)
            logging.info(f"自动备份配置已更新: {backup_config_updates}")
            db.session.commit()
            message = f"更新{category}模块配置,成功更新{len(updated_keys)}项配置，自动备份配置已更新"

        # 如果是数据库配置更新，同步更新外部配置文件
        if is_db_config and db_config_updates:
            from utils.db_config import DatabaseConfig    
            # 保存到外部配置文件
            DatabaseConfig.update_config(db_config_updates)
            logging.info("数据库配置已更新，需要重启应用生效")
            db.session.commit()
            message = f"更新{category}模块配置,成功更新{len(updated_keys)}项配置，数据库配置已更新"
            
        # 系统类型判断与动态导入重载服务
        if is_db_config and db_config_updates:
            # 系统类型判断与动态导入重载服务
            from utils.system_detector import SystemDetector
            logging.info("数据库类型配置已更改，触发系统重载")
            # 优先判断Docker环境
            if SystemDetector.is_docker():
                from utils.reload_docker_service import reload_service
                logging.info("使用Docker环境重载服务")
                message = f"更新{category}模块配置,成功更新{len(updated_keys)}项配置，数据库配置已更新，当前是Docker环境，需要你手动重启Docker生效"
            # 其次判断Windows系统
            elif SystemDetector.is_windows():
                from utils.reload_windows_service import reload_service
                logging.info("使用Windows系统重载服务")
                message = f"更新{category}模块配置,成功更新{len(updated_keys)}项配置，数据库配置已更新，当前是Windows环境，触发自动重载，请等待系统自动重启完成"
            # 移除其他系统处理，仅保留Docker和Windows
            else:
                # 理论上不会执行到这里，可根据实际需求添加异常处理
                logging.error("不支持的系统环境，无法执行重载")
            reload_service() #重载触发
            
            
        log_operation(
            user_id=current_user.id,
            action=message,
            module='system',
            operation_type='config_update',
            result="成功"
        )

        return jsonify({
            "success": True,
            "message": message,
            "updated": updated_keys
        })
        
    except Exception as e:
        db.session.rollback()
        logging.error(f"更新配置失败: {str(e)}")
        log_operation(
            user_id=current_user.id if current_user.is_authenticated else 0,
            action=f"更新{category}模块配置失败,{str(e)}",
            module='system',
            operation_type='config_update',
            result="失败 "
        )
        return jsonify({
            "success": False,
            "message": f"更新配置失败: {str(e)}"
        }), 500

# 在初始化模块配置路由中添加reset参数
@system_config_bp.route('/api/configs/initialize/<category>', methods=['POST'])
@login_required
@require_permission('system_settings.initialize')
def initialize_module_configs(category):
    try:
        data = request.get_json() or {}
        reset = data.get('reset', False)  # 获取是否重置的参数
        normalized_category = category.replace('-', '.')
        
        if not any(m['category'] == normalized_category for m in MODULES):
            logging.error(f"模块 {category} 不存在")
            return jsonify({
                "success": False,
                "message": f"模块 {category} 不存在"
            }), 404
        
        # 对于system模块，需要超级管理员权限
        if normalized_category == 'system' and not (current_user.user_role and current_user.user_role.code == 'super_admin'):
            logging.warning(f"非超级管理员用户{current_user.username}尝试初始化系统核心配置失败")
            return jsonify({
                "success": False,
                "message": "需要超级管理员权限才能初始化系统核心配置"
            }), 403
        
        # 先保存当前配置数量
        prev_count = SystemConfig.query.filter_by(category=normalized_category).count()
        
        # 调用模型初始化方法，传入reset参数
        initialized = SystemConfig.init_category_configs(
            normalized_category, 
            current_user.id,
            reset=reset
        )
        
        # 计算新增配置数量
        new_count = SystemConfig.query.filter_by(category=normalized_category).count()
        
        log_operation(
            user_id=current_user.id,
            action=f"初始化{normalized_category}模块默认配置,初始化{initialized}项配置",
            module='system',
            operation_type='initialize',
            result="成功"
        )

        return jsonify({
            "success": True,
            "message":f"初始化{normalized_category}模块默认配置,初始化{initialized}项配置",
            "initialized": initialized
        })
    except Exception as e:
        db.session.rollback()
        logging.error(f"初始化{category}模块配置失败: {str(e)}")
        log_operation(
            user_id=current_user.id if current_user.is_authenticated else 0,
            action=f"初始化{category}模块配置失败,{str(e)}",
            module='system',
            operation_type='initialize',
            result="失败"
        )
        return jsonify({
            "success": False,
            "message": f"初始化配置失败: {str(e)}"
        }), 500


# 在初始化所有配置路由中添加reset参数
@system_config_bp.route('/api/configs/initialize-all', methods=['POST'])
@login_required
@require_permission('system_settings.initialize')
def initialize_all_configs():
    try:
        data = request.get_json() or {}
        reset = data.get('reset', False)  # 获取是否重置的参数
        
        # 初始化所有配置需要超级管理员权限，因为包含system模块
        if not (current_user.user_role and current_user.user_role.code == 'super_admin'):
            logging.warning(f"非超级管理员用户{current_user.username}尝试初始化所有模块配置失败")
            return jsonify({
                "success": False,
                "message": "需要超级管理员权限才能初始化所有模块配置"
            }), 403
        
        # 记录初始化前的配置数量
        prev_total = SystemConfig.query.count()
        
        # 调用模型的初始化方法，传入reset参数
        success = SystemConfig.init_default_configs(current_user.id, reset=reset)
        
        # 计算总配置数量变化
        new_total = SystemConfig.query.count()
        initialized = new_total - prev_total if not reset else new_total
        
        log_operation(
            user_id=current_user.id,
            action=f"初始化所有模块默认配置,成功初始化{initialized}项配置，当前共{new_total}项配置",
            module="system",
            operation_type="initialize",
            result="成功"
        )


        return jsonify({
            "success": success,
            "message": f"初始化所有模块默认配置,成功初始化{initialized}项配置，当前共{new_total}项配置",
            "total_initialized": initialized,
            "total_configs": new_total
        })
    except Exception as e:
        logging.error(f"初始化所有模块配置失败: {str(e)}")
        log_operation(
            user_id=current_user.id if current_user.is_authenticated else 0,
            action=f"初始化所有模块默认配置失败,{str(e)}",
            module="system",
            operation_type="initialize",
            result="失败"
        )
        return jsonify({
            "success": False,
            "message": f"初始化配置失败: {str(e)}"
        }), 500

@system_config_bp.route('/api/db/info', methods=['GET'])
@login_required
def get_database_info():
    """获取当前数据库连接信息并返回给前端"""
    try:
        from sqlalchemy.engine.url import make_url  # 用于解析数据库连接字符串
        
        # 获取数据库连接URI
        db_uri = current_app.config.get('SQLALCHEMY_DATABASE_URI', '')
        if not db_uri:
            return jsonify({
                "success": False,
                "message": "未配置数据库连接信息"
            }), 500
        
        # 解析连接字符串
        parsed_url = make_url(db_uri)
        db_info = {
            "db_type": parsed_url.drivername.split('+')[0],  # 提取基础数据库类型
            "host": parsed_url.host,
            "port": parsed_url.port,
            "database": parsed_url.database,
            "username": parsed_url.username,
            # 不返回密码，只返回是否存在密码
            "has_password": bool(parsed_url.password),
            "uri_masked": f"{parsed_url.drivername}://{parsed_url.username}:{'***' if parsed_url.password else ''}@{parsed_url.host}:{parsed_url.port or ''}/{parsed_url.database}"
        }
        
        # 针对SQLite特殊处理（没有host和port，显示文件路径）
        if db_info["db_type"] == "sqlite":
            db_info["file_path"] = parsed_url.database
            db_info["host"] = "本地文件系统"
            db_info["port"] = "N/A"
        
        log_operation(
            user_id=current_user.id,
            action="查询当前数据库信息",
            module="system",
            operation_type="system_api",
            result="成功"
        )
        
        return jsonify({
            "success": True,
            "data": db_info
        })
        
    except Exception as e:
        logging.error(f"获取数据库信息失败: {str(e)}")
        log_operation(
            user_id=current_user.id if current_user.is_authenticated else 0,
            action=f"查询数据库信息失败: {str(e)}",
            module="system",
            operation_type="system_api",
            result="失败"
        )
        return jsonify({
            "success": False,
            "message": f"获取数据库信息失败: {str(e)}"
        }), 500