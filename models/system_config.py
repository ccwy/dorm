from flask import current_app
from utils.db import db
from datetime import timedelta
import os, shutil
import logging
import json
from datetime import datetime, date  # 修正导入方式
import re
import traceback

class SystemConfig(db.Model):
    __tablename__ = 'system_configs'
    
    id = db.Column(db.Integer, primary_key=True)
    config_key = db.Column(db.String(50), unique=True, nullable=False, comment='配置项键名')
    config_value = db.Column(db.Text, nullable=False, comment='配置项值')
    config_type = db.Column(db.String(20), nullable=False, comment='配置项类型：string/int/bool/float/timedelta/path/list')
    category = db.Column(db.String(30), nullable=False, comment='配置项类别：system/user/room/dorm/fee/attendance/contract/log')
    description = db.Column(db.String(200), nullable=True, comment='配置项描述')
    is_system = db.Column(db.Boolean, default=False, comment='是否为系统级配置（不可删除）')
    is_editable = db.Column(db.Boolean, default=True, comment='是否允许编辑')
    sort_order = db.Column(db.Integer, default=999, nullable=False, comment='排序顺序，数字越小越靠前')
    updated_at = db.Column(db.DateTime, default=db.func.current_timestamp(), onupdate=db.func.current_timestamp(), comment='更新时间')
    updated_by = db.Column(db.Integer, nullable=True, comment='更新人ID')
    
    def __repr__(self):
        return f"<SystemConfig [{self.category}] {self.config_key}: {self.config_value}>"
    
    @classmethod
    def get_config(cls, key, default=None):
        """根据配置键获取配置值"""
        config = cls.query.filter_by(config_key=key).first()
        if not config:
            return default
        
        # 根据配置类型转换值
        if config.config_type == 'string':
            return config.config_value
        elif config.config_type == 'int':
            return int(config.config_value)
        elif config.config_type == 'bool':
            return config.config_value.lower() == 'true'
        elif config.config_type == 'float':
            return float(config.config_value)
        elif config.config_type == 'timedelta':
            return timedelta(seconds=int(config.config_value))
        elif config.config_type == 'path':
            return config.config_value
        elif config.config_type == 'list':
            return json.loads(config.config_value)
        return config.config_value
    
    @classmethod
    def _get_default_configs(cls):
        """获取所有默认配置列表（提取为独立方法以便复用）"""
        return [
            # 1. 系统核心配置 (category: system)        
            {
                'config_key': 'SYSTEM_TITLE',
                'config_value': '行政后勤管理系统',
                'config_type': 'string',
                'category': 'system',
                'description': '系统标题',
                'is_editable': True,
                'sort_order': 10  # 排序字段，数字越小越靠前
            },
            {
                'config_key': 'SERVER_MODE',
                'config_value': '客户端',
                'config_type': 'string',
                'category': 'system',
                'description': '启动类型，默认：客户端，可改成服务端（仅在windows系统上有效）',
                'sort_order': 20
            }, 
            {
                'config_key': 'SQL_TYPE',
                'config_value': 'SQLITE',
                'config_type': 'string',
                'category': 'system',
                'description': '数据库类型，默认： SQLITE ，可修改为： MYSQL ',
                'sort_order': 30
            },          
            {
                'config_key': 'SERVER_PORT',
                'config_value': '35168',
                'config_type': 'int',
                'category': 'system',
                'description': '服务器监听端口',
                'sort_order': 40
            },
            {
                'config_key': 'MYSQL_HOST',
                'config_value': '192.168.5.100',
                'config_type': 'string',
                'category': 'system',
                'description': 'MYSQL地址',
                'sort_order': 50
            },
            {
                'config_key': 'MYSQL_PORT',
                'config_value': '3306',
                'config_type': 'int',
                'category': 'system',
                'description': 'MYSQL监听端口',
                'sort_order': 60
            },
            
            {
                'config_key': 'MYSQL_DB',
                'config_value': 'test',
                'config_type': 'string',
                'category': 'system',
                'description': 'MYSQL数据库名称',
                'sort_order': 70
            },
            {
                'config_key': 'MYSQL_USER',
                'config_value': 'test',
                'config_type': 'string',
                'category': 'system',
                'description': 'MYSQL数据库用户名',
                'sort_order': 80
            },
            {
                'config_key': 'MYSQL_PASSWORD',
                'config_value': '123456',
                'config_type': 'string',
                'category': 'system',
                'description': 'MYSQL数据库密码',
                'sort_order': 90
            },
            # 2. 系统功能开关配置 (category: system.feature)
            {
                'config_key': 'FEATURE_USER_MANAGE_ENABLED',
                'config_value': 'true',
                'config_type': 'bool',
                'category': 'system.feature',
                'description': '用户管理功能开关',
                'is_editable': True,
                'sort_order': 10
            },
            {
                'config_key': 'FEATURE_DORM_MANAGE_ENABLED',
                'config_value': 'true',
                'config_type': 'bool',
                'category': 'system.feature',
                'description': '宿舍管理功能开关',
                'is_editable': True,
                'sort_order': 20
            },
            {
                'config_key': 'FEATURE_ROOM_MANAGE_ENABLED',
                'config_value': 'true',
                'config_type': 'bool',
                'category': 'system.feature',
                'description': '房间管理功能开关',
                'is_editable': True,
                'sort_order': 20
            },
            {
                'config_key': 'FEATURE_UTILITY_BILL_ENABLED',
                'config_value': 'true',
                'config_type': 'bool',
                'category': 'system.feature',
                'description': '水电费管理功能开关',
                'is_editable': True,
                'sort_order': 30
            },
            {
                'config_key': 'FEATURE_FEE_SUBSIDY_ENABLED',
                'config_value': 'true',
                'config_type': 'bool',
                'category': 'system.feature',
                'description': '补贴管理功能开关',
                'is_editable': True,
                'sort_order': 40
            },
            {
                'config_key': 'FEATURE_TODO_MANAGE_ENABLED',
                'config_value': 'true',
                'config_type': 'bool',
                'category': 'system.feature',
                'description': '待办事项管理功能开关',
                'is_editable': True,
                'sort_order': 50
            },
            {
                'config_key': 'FEATURE_TICKET_MANAGE_ENABLED',
                'config_value': 'true',
                'config_type': 'bool',
                'category': 'system.feature',
                'description': '留言管理功能开关',
                'is_editable': True,
                'sort_order': 60
            },
            {
                'config_key': 'FEATURE_FILE_SHARING_ENABLED',
                'config_value': 'true',
                'config_type': 'bool',
                'category': 'system.feature',
                'description': '文件共享功能开关',
                'is_editable': True,
                'sort_order': 70
            },
            {
                'config_key': 'FEATURE_CHAT_ENABLED',
                'config_value': 'true',
                'config_type': 'bool',
                'category': 'system.feature',
                'description': 'OA聊天功能开关',
                'is_editable': True,
                'sort_order': 80
            },
            {
                'config_key': 'FEATURE_SYSTEM_LOG_ENABLED',
                'config_value': 'true',
                'config_type': 'bool',
                'category': 'system.feature',
                'description': '系统日志功能开关',
                'is_editable': True,
                'sort_order': 90
            },
            {
                'config_key': 'FEATURE_FIXED_ASSET_MANAGE_ENABLED',
                'config_value': 'true',
                'config_type': 'bool',
                'category': 'system.feature',
                'description': '固定资产管理功能开关',
                'is_editable': True,
                'sort_order': 100
            },
            {
                'config_key': 'FEATURE_DEPARTMENT_ENABLED',
                'config_value': 'true',
                'config_type': 'bool',
                'category': 'system.feature',
                'description': '部门管理功能开关',
                'is_editable': True,
                'sort_order': 110
            },
            {
                'config_key': 'FEATURE_SUPPLY_MANAGE_ENABLED',
                'config_value': 'true',
                'config_type': 'bool',
                'category': 'system.feature',
                'description': '低值易耗品管理功能开关',
                'is_editable': True,
                'sort_order': 120
            },
            {
                'config_key': 'FEATURE_ROLE_MANAGE_ENABLED',
                'config_value': 'true',
                'config_type': 'bool',
                'category': 'system.feature',
                'description': '角色管理功能开关',
                'is_editable': True,
                'sort_order': 130
            },
            {
                'config_key': 'FEATURE_CONTRACT_MANAGE_ENABLED',
                'config_value': 'true',
                'config_type': 'bool',
                'category': 'system.feature',
                'description': '合同管理功能开关',
                'is_editable': True,
                'sort_order': 140
            },
            
            # 3. 用户管理配置 (category: user)
            {
                'config_key': 'USER_DEFAULT_BANNED',
                'config_value': 'False',
                'config_type': 'bool',
                'category': 'user',
                'description': '新增账号是否允许登录，默认是False',
                'sort_order': 10
            },
            {
                'config_key': 'USER_DEFAULT_ACTIVE',
                'config_value': 'True',
                'config_type': 'bool',
                'category': 'user',
                'description': '新增账号是否激活，默认是True',
                'sort_order': 20
            },
            {
                'config_key': 'USER_DEFAULT_PASSWORD',
                'config_value': '123456',
                'config_type': 'string',
                'category': 'user',
                'description': '新用户默认密码，默认是123456',
                'sort_order': 30
            },
            {
                'config_key': 'USER_DEFAULT_STATUS',
                'config_value': '在职',
                'config_type': 'string',
                'category': 'user',
                'description': '新用户默认状态',
                'sort_order': 50
            },
            {
                'config_key': 'USER_TYPES',
                'config_value': '员工,职员,高管',
                'config_type': 'list',
                'category': 'user',
                'description': '用户类型选项',
                'sort_order': 60
            },
            
            {
                'config_key': 'USER_STATUS_OPTIONS',
                'config_value': '在职,离职,自离,注销',
                'config_type': 'list',
                'category': 'user',
                'description': '用户状态选项',
                'sort_order': 80
            },
            
            {
                'config_key': 'USER_MARITAL_STATUS',
                'config_value': '未婚,已婚,离异,丧偶',
                'config_type': 'list',
                'category': 'user',
                'description': '用户婚姻状态选项',
                'sort_order': 90
            },
            # 留言分类配置
            {
                'config_key': 'MESSAGE_CATEGORIES',
                'config_value': '宿舍问题,设施维修,水电费问题,其他问题',
                'config_type': 'list',
                'category': 'user',
                'description': '用户提交留言的分类选项',
                'sort_order': 100
            },
            
            # 待办事项分类配置
            {
                'config_key': 'TODO_CATEGORIES',
                'config_value': '日常工作,项目任务,会议准备,学习培训,其他',
                'config_type': 'list',
                'category': 'user',
                'description': '待办事项的分类选项',
                'sort_order': 110
            },
            
            # 4. 房间管理配置 (category: room)
            {
                'config_key': 'ROOM_building',
                'config_value': 'A,B,C,D',
                'config_type': 'list',
                'category': 'room',
                'description': '房间楼栋选项',
                'sort_order': 10
            },
            {
                'config_key': 'ROOM_TYPES',
                'config_value': '单人间,双人间,三人间,四人间,五人间,六人间,七人间,八人间,豪华间,无障碍房间',
                'config_type': 'list',
                'category': 'room',
                'description': '房间类型选项（预设值，不建议删除，可以增加）',
                'sort_order': 20
            },
            {
                'config_key': 'ROOM_LEVELS',
                'config_value': '员工,职员,管理级,高管级',
                'config_type': 'list',
                'category': 'room',
                'description': '房间级别选项',
                'sort_order': 30
            },
            {
                'config_key': 'BASE_FACILITIES',
                'config_value': '空调,空调遥控器,暖气,热水器,洗衣机,冰箱,办公桌,衣柜,椅子,床,WiFi,电视,供电,供水,洗手间,阳台,水龙头,门锁,钥匙,木床,铁床',
                'config_type': 'list',
                'category': 'room',
                'description': '系统预设的基础房间设备类型（不可修改删除）',
                'is_system': True,
                'is_editable': False,
                'sort_order': 40
            },
            {
                'config_key': 'CUSTOM_FACILITIES',
                'config_value': '',  # 初始为空，允许用户动态添加
                'config_type': 'list',
                'category': 'room',
                'description': '用户自定义的房间设备类型（可动态增删）',
                'sort_order': 50
            },
            
            # 5. 宿舍管理配置 (category: dorm)
            {
                'config_key': 'ITEM_HANDOVER_CONFIG',
                'config_value': '钥匙:2,水卡:1,电卡:1,家具清单:1,设施确认表:1,其他:',
                'config_type': 'dict',
                'category': 'dorm',
                'description': '入住/退宿物品交接清单',
                'sort_order': 10
            },
            {
                'config_key': 'ITEM_DAMAGE_PENALTY',
                'config_value': '钥匙:50,水卡:30,电卡:30,桌椅:200,衣柜:300,空调:500',
                'config_type': 'dict',
                'category': 'dorm',
                'description': '物品损坏赔偿标准（元）',
                'sort_order': 20
            },
            {
                'config_key': 'dorm_type',
                'config_value': '分配宿舍,更换宿舍,互换宿舍,退宿',
                'config_type': 'list',
                'category': 'dorm',
                'description': '宿舍操作类型',
                'sort_order': 30
            },
            
            # 6. 水电费管理配置 (category: fee)
            {
                'config_key': 'ELECTRICITY_PRICE',
                'config_value': '1',
                'config_type': 'Decimal',
                'category': 'fee',
                'description': '电费单价（元/kWh）',
                'sort_order': 10
            },
            {
                'config_key': 'WATER_PRICE',
                'config_value': '5',
                'config_type': 'Decimal',
                'category': 'fee',
                'description': '水费单价（元/m³）',
                'sort_order': 20
            },
            {
                'config_key': 'FEE_METER_reduction',
                'config_value': 'True',
                'config_type': 'bool',
                'category': 'fee',
                'description': '是否启用房间水电按用量减免',
                'sort_order': 30
            },
            {
                'config_key': 'FEE_ROOM_FEE',
                'config_value': 'True',
                'config_type': 'bool',
                'category': 'fee',
                'description': '是否启用房间水电按金额减免',
                'sort_order': 40
            },
            {
                'config_key': 'FEE_USER_FEE',
                'config_value': 'True',
                'config_type': 'bool',
                'category': 'fee',
                'description': '是否启用住宿补贴',
                'sort_order': 50
            },
            {
                'config_key': 'lodging_allowance',
                'config_value': 'True',
                'config_type': 'bool',
                'category': 'fee',
                'description': '是否启用外宿补贴',
                'sort_order': 60
            },
            # 新增：特殊减免规则配置
            {
                'config_key': 'CHECKOUT_ENABLE_SPECIAL_REDUCTION_RULE',
                'config_value': 'True',
                'config_type': 'bool',
                'category': 'fee',
                'description': '退宿费用核算特殊减免规则是否启用，特殊规则：当房间实际入住人数小于标准值一半人数时，计算规则为房间容量的一半',
                'sort_order': 70
            },
            {
                'config_key': 'CHECKOUT_ROOM_CAPACITY_HALF_THRESHOLD',
                'config_value': '4',
                'config_type': 'int',
                'category': 'fee',
                'description': '退宿费用核算特殊减免规则标准值（人数）',
                'sort_order': 80
            },
            {
                'config_key': 'ENABLE_CUSTOM_METER_READING_DAY',
                'config_value': 'False',
                'config_type': 'bool',
                'category': 'fee',
                'description': '是否启用自定义抄表日，启用后将会以自定义的日期为起始日期，否则按自然月计算',
                'sort_order': 90
            },
            {
                'config_key': 'CUSTOM_METER_READING_DAY',
                'config_value': '1',
                'config_type': 'int',
                'category': 'fee',
                'description': '自定义抄表日（1-31），抄表日大于该月份的最大日期时使用该月份的最大日期',
                'sort_order': 100
            },
            {
                'config_key': 'ALLOWANCE_TYPES',
                'config_value': '外宿补贴,住宿补贴,房间水电按用量减免,房间水电按金额减免,话费补贴',
                'config_type': 'list',
                'category': 'fee',
                'description': '补贴类型选项',
                'sort_order': 110
            },

            # 7. 考勤管理配置 (category: attendance)
            {
                'config_key': 'ATTENDANCE_CHECKIN_TIME',
                'config_value': '08:00',
                'config_type': 'string',
                'category': 'attendance',
                'description': '考勤签到截止时间',
                'sort_order': 10
            },
            {
                'config_key': 'ATTENDANCE_CHECKOUT_TIME',
                'config_value': '22:30',
                'config_type': 'string',
                'category': 'attendance',
                'description': '考勤签退开始时间',
                'sort_order': 20
            },
            {
                'config_key': 'ATTENDANCE_ABSENCE_THRESHOLD',
                'config_value': '3',
                'config_type': 'int',
                'category': 'attendance',
                'description': '连续缺勤预警阈值（天）',
                'sort_order': 30
            },
            
            # 8. 合同管理配置 (category: contract) - 基础配置项已移至下方与CONTRACT_TYPES等统一管理
            
            # 9. 日志管理配置 (category: log)
            {
                'config_key': 'LOG_RETENTION_DAYS',
                'config_value': '90',
                'config_type': 'int',
                'category': 'log',
                'description': '日志保留天数',
                'sort_order': 10
            },
            {
                'config_key': 'LOG_LEVEL',
                'config_value': 'INFO',
                'config_type': 'string',
                'category': 'log',
                'description': '日志记录级别（DEBUG/INFO/WARNING/ERROR）',
                'sort_order': 20
            },
            {
                'config_key': 'LOG_PER_PAGE',
                'config_value': '20',
                'config_type': 'int',
                'category': 'log',
                'description': '每页显示日志数量',
                'sort_order': 30
            },
            {
                'config_key': 'LOG_LEVEL_VIEW_PERMISSION',
                'config_value': 'ADMIN:DEBUG,MANAGER:INFO,STAFF:WARNING,USER:ERROR',
                'config_type': 'dict',
                'category': 'log',
                'description': '不同角色可查看的日志级别',
                'sort_order': 40
            },
            
            # 10. 备份配置 (category: system.backup)
            {
                'config_key': 'BACKUP_INTERVAL',
                'config_value': '1440',  # 24*3600秒
                'config_type': 'int',
                'category': 'system.backup',
                'description': '自动备份间隔（分钟）',
                'sort_order': 10
            },
            {
                'config_key': 'BACKUP_RETENTION_COUNT',
                'config_value': '100',
                'config_type': 'int',
                'category': 'system.backup',
                'description': '保留备份文件的数量',
                'sort_order': 20
            },
            {
                'config_key': 'ENABLE_AUTO_BACKUP',
                'config_value': 'True',
                'config_type': 'bool',
                'category': 'system.backup',
                'description': '是否启用自动备份',
                'sort_order': 30
            },
            # 固定资产管理配置 (category: asset)
            {
                'config_key': 'ASSET_CATEGORIES',
                'config_value': '办公设备,家具,交通工具,电子设备,机械设备,其他',
                'config_type': 'list',
                'category': 'asset',
                'description': '固定资产分类列表',
                'is_editable': True,
                'sort_order': 10
            },
            {
                'config_key': 'ASSET_STATUSES',
                'config_value': '在用,闲置,维修中,已报废,已转移,已出售',
                'config_type': 'list',
                'category': 'asset',
                'description': '固定资产状态列表',
                'is_editable': True,
                'sort_order': 20
            },
            {
                'config_key': 'ASSET_SOURCES',
                'config_value': '采购,捐赠,调入,自建,其他',
                'config_type': 'list',
                'category': 'asset',
                'description': '资产来源选项列表',
                'is_editable': True,
                'sort_order': 30
            },
            {
                'config_key': 'asset_inventory_unapprove_enabled',
                'config_value': 'true',
                'config_type': 'bool',
                'category': 'asset',
                'description': '启用固定资产盘点反审核功能（允许已完成盘点单反审核回退到进行中）',
                'is_editable': True,
                'is_system': False,
                'sort_order': 40
            },

            # 低值易耗品进销存管理配置 (category: supply)
            {
                'config_key': 'supply_auto_number',
                'config_value': 'true',
                'config_type': 'bool',
                'category': 'supply',
                'description': '启用自动编号（物品/入库/出库/盘点单号）',
                'is_editable': True,
                'is_system': False,
                'sort_order': 20
            },
            {
                'config_key': 'supply_low_stock_alert',
                'config_value': 'true',
                'config_type': 'bool',
                'category': 'supply',
                'description': '启用低库存预警',
                'is_editable': True,
                'is_system': False,
                'sort_order': 30
            },
            {
                'config_key': 'supply_stock_out_check',
                'config_value': 'true',
                'config_type': 'bool',
                'category': 'supply',
                'description': '出库审核时检查库存充足性',
                'is_editable': True,
                'is_system': False,
                'sort_order': 40
            },
            {
                'config_key': 'STOCK_IN_APPROVAL_ENABLED',
                'config_value': 'true',
                'config_type': 'bool',
                'category': 'supply',
                'description': '入库单审核功能开关（关闭后保存即自动审核）',
                'is_editable': True,
                'sort_order': 50
            },
            {
                'config_key': 'STOCK_OUT_APPROVAL_ENABLED',
                'config_value': 'true',
                'config_type': 'bool',
                'category': 'supply',
                'description': '出库单审核功能开关（关闭后保存即自动审核）',
                'is_editable': True,
                'sort_order': 60
            },
            {
                'config_key': 'supply_default_min_stock',
                'config_value': '10',
                'config_type': 'int',
                'category': 'supply',
                'description': '默认最低库存数量',
                'is_editable': True,
                'is_system': False,
                'sort_order': 70
            },
            {
                'config_key': 'supply_units',
                'config_value': '个,件,箱,包,盒,瓶,支,本,张,套,台,把,条,块,卷,桶,袋,罐',
                'config_type': 'list',
                'category': 'supply',
                'description': '预设单位选项（逗号分隔）',
                'is_editable': True,
                'is_system': False,
                'sort_order': 80
            },
            {
                'config_key': 'supply_categories',
                'config_value': '文具,办公设备,耗材,清洁用品,其他',
                'config_type': 'list',
                'category': 'supply',
                'description': '物品分类选项（逗号分隔，第一个为默认值）',
                'is_editable': True,
                'is_system': False,
                'sort_order': 85
            },
            {
                'config_key': 'supply_number_prefix',
                'config_value': '{"item":"YP","stock_in":"RK","stock_out":"CK","inventory":"PD"}',
                'config_type': 'json',
                'category': 'supply',
                'description': '各单据编号前缀配置',
                'is_editable': True,
                'is_system': False,
                'sort_order': 90
            },
            
            {
                'config_key': 'stock_in_types',
                'config_value': '采购入库,其它入库',
                'config_type': 'list',
                'category': 'supply',
                'description': '入库类型选项（逗号分隔，第一个为默认值）',
                'is_editable': True,
                'is_system': False,
                'sort_order': 100
            },
            {
                'config_key': 'stock_out_types',
                'config_value': '正常领用,其他出库',
                'config_type': 'list',
                'category': 'supply',
                'description': '出库类型选项（逗号分隔，第一个为默认值）',
                'is_editable': True,
                'is_system': False,
                'sort_order': 110
            },
            {
                'config_key': 'storage_location_usage_types',
                'config_value': '低值易耗品,固定资产,合同管理',
                'config_type': 'list',
                'category': 'supply',
                'description': '存放位置使用类型选项（逗号分隔，第一个为默认值）',
                'is_editable': True,
                'is_system': False,
                'sort_order': 120
            },
            {
                'config_key': 'supply_inventory_unapprove_enabled',
                'config_value': 'true',
                'config_type': 'bool',
                'category': 'supply',
                'description': '启用低值易耗品盘点反审核功能（允许已完成盘点单反审核回退到进行中）',
                'is_editable': True,
                'is_system': False,
                'sort_order': 130
            },
    
            # 合同类型配置
            {
                'config_key': 'CONTRACT_TYPES',
                'config_value': '采购合同,服务合同,租赁合同,劳务合同,其他',
                'config_type': 'string',
                'category': 'contract',
                'description': '合同类型选项（逗号分隔）',
                'is_editable': True,
                'sort_order': 10
            },
            # 合同到期提醒天数
            {
                'config_key': 'CONTRACT_EXPIRY_WARNING_DAYS',
                'config_value': '30',
                'config_type': 'int',
                'category': 'contract',
                'description': '合同到期提前提醒天数',
                'is_editable': True,
                'sort_order': 20
            },
            # 合同分类配置
            {
                'config_key': 'CONTRACT_CATEGORIES',
                'config_value': '行政类,后勤类,IT类,其他',
                'config_type': 'string',
                'category': 'contract',
                'description': '合同分类选项（逗号分隔）',
                'is_editable': True,
                'sort_order': 30
            },

            # 后勤维修功能开关
            {
                'config_key': 'FEATURE_MAINTENANCE_MANAGE_ENABLED',
                'config_value': 'true',
                'config_type': 'bool',
                'category': 'system.feature',
                'description': '后勤维修功能开关',
                'is_editable': True,
                'sort_order': 150
            },

            # 维修类型列表
            {
                'config_key': 'MAINTENANCE_TYPES',
                'config_value': '水电维修,门窗维修,家具维修,空调维修,网络维修,其他',
                'config_type': 'list',
                'category': 'maintenance',
                'description': '维修类型列表（逗号分隔）',
                'is_editable': True,
                'sort_order': 10
            },

            # 自动分配开关
            {
                'config_key': 'MAINTENANCE_AUTO_ASSIGN_ENABLED',
                'config_value': 'true',
                'config_type': 'bool',
                'category': 'maintenance',
                'description': '维修工单自动分配开关（开启后新工单自动分配给空闲维修员）',
                'is_editable': True,
                'sort_order': 20
            },


        ]
    
    @classmethod
    def init_default_configs(cls, user_id=None, reset=False):
        """
        初始化所有模块的默认配置
        :param user_id: 操作用户ID
        :param reset: 是否重置（删除现有配置）
        :return: 是否成功
        """
        if cls.query.count() > 0 and not reset:
            logging.info("系统配置表已有数据，跳过全量初始化")
            return
        try:
            # 如果需要重置，先清空现有配置
            if reset:
                cls.query.delete()
                db.session.commit()
                logging.info("已清空所有现有配置")
            elif cls.query.count() > 0:
                logging.info("已有配置数据，跳过全量初始化")
                return True
                
            # 使用共享的默认配置列表
            default_configs = cls._get_default_configs()
            
            config_objects = []
            for config in default_configs:
                existing = cls.query.filter_by(config_key=config['config_key']).first()
                if not existing:
                    config_objects.append(cls(
                    config_key=config['config_key'],
                    config_value=config['config_value'],
                    config_type=config['config_type'],
                    category=config['category'],
                    description=config['description'],
                    is_system=config.get('is_system', False),
                    is_editable=config.get('is_editable', True),
                    sort_order=config.get('sort_order', 999),  # 使用配置中的排序值，默认为999
                    updated_by=user_id
                ))
            
            db.session.bulk_save_objects(config_objects)
            db.session.commit()
            logging.info(f"成功初始化 {len(default_configs)} 项默认配置")
            return True
        except Exception as e:
            db.session.rollback()
            logging.error(f"初始化默认配置失败: {str(e)}", exc_info=True)
            return False
    
    @classmethod
    def get_config_value(cls, key, default=None):
        """获取指定配置项的值（自动转换为对应类型）"""
        try:
            # 检查是否是系统模块配置项
            # 首先从本地JSON文件中获取系统核心配置
            if key in ['SYSTEM_TITLE', 'SERVER_MODE', 'SQL_TYPE', 'SERVER_PORT', 
                       'MYSQL_HOST', 'MYSQL_PORT', 'MYSQL_DB', 'MYSQL_USER', 'MYSQL_PASSWORD']:
                try:
                    from utils.db_config import DatabaseConfig
                    json_config = DatabaseConfig.load_config()
                    if key in json_config:
                        # 返回JSON配置中的值，保持与系统原有的类型转换逻辑一致
                        value = json_config[key]
                        # 这里不需要额外的类型转换，因为DatabaseConfig已经正确解析了JSON类型
                        return value
                except Exception as json_error:
                    logging.warning(f"从JSON文件获取配置项 {key} 失败: {str(json_error)}, 尝试从数据库获取")
            
            # 如果不是系统核心配置，或者从JSON文件获取失败，从数据库获取
            config = db.session.query(cls).filter_by(config_key=key).first()
            
            if not config:
                logging.warning(f"配置项 {key} 不存在，返回默认值")
                return default
                
            value = config.config_value
            
            try:
                if config.config_type == 'int':
                    return int(value)
                elif config.config_type == 'float':
                    return float(value)
                elif config.config_type == 'bool':
                    # 增强布尔值处理，确保能正确解析字符串形式的布尔值
                    if isinstance(value, str):
                        return value.lower() in ['true', '1', 'yes', 'y', 't']
                    return bool(value)
                elif config.config_type == 'timedelta':
                    return int(value)
                elif config.config_type == 'path':
                    return os.path.abspath(value)
                elif config.config_type == 'list':
                    return [item.strip() for item in value.split(',') if item.strip()]
                elif config.config_type == 'json':
                    return json.loads(value)
                elif config.config_type == 'dict':
                    result = {}
                    for item in value.replace(';', ',').split(','):
                        if ':' in item:
                            k, v = item.split(':', 1)
                            result[k.strip()] = v.strip()
                    return result
                # 对于string类型，直接返回原始字符串，不做自动拆分
                elif config.config_type == 'string':
                    return value
            except Exception as te:
                logging.error(f"配置项 {key} 类型转换失败: {str(te)}")
                return value
            
            return value
        except Exception as e:
            logging.error(f"获取配置项 {key} 失败: {str(e)}", exc_info=True)
            return default
            
    @classmethod
    def init_category_configs(cls, category, user_id=None, reset=False):
        """
        初始化指定类别的默认配置
        :param category: 配置类别
        :param user_id: 操作用户ID
        :param reset: 是否重置（删除现有配置）
        :return: 添加的配置数量
        """
        try:
            # 获取该类别的默认配置
            default_configs = [
                cfg for cfg in cls._get_default_configs() 
                if cfg['category'] == category
            ]
            
            if not default_configs:
                logging.info(f"类别 {category} 没有默认配置，跳过初始化")
                return 0
                
            added_count = 0
            
            # 如果需要重置，先删除该类别的现有配置
            if reset:
                cls.query.filter_by(category=category).delete()
                db.session.commit()
                logging.info(f"已删除 {category} 类别的现有配置")
                
            for config in default_configs:
                # 检查配置项是否已存在
                existing = cls.query.filter_by(config_key=config['config_key']).first()
                if not existing:
                    new_config = cls(
                        config_key=config['config_key'],
                        config_value=config['config_value'],
                        config_type=config['config_type'],
                        category=config['category'],
                        description=config['description'],
                        is_system=config.get('is_system', False),
                        is_editable=config.get('is_editable', True),
                        sort_order=config.get('sort_order', 999),  # 使用配置中的排序值，默认为999
                        updated_by=user_id
                    )
                    db.session.add(new_config)
                    added_count += 1
            
            if added_count > 0:
                db.session.commit()
                logging.info(f"成功为 {category} 类别初始化 {added_count} 项默认配置")
            else:
                logging.info(f"类别 {category} 的配置已存在，无需初始化")
                
            return added_count
        except Exception as e:
            db.session.rollback()
            logging.error(f"初始化 {category} 类别配置失败: {str(e)}", exc_info=True)
            return 0

    @classmethod
    def get_category_configs(cls, category):
        """获取指定类别的所有配置项，按照sort_order升序排序，相同时按config_key字母顺序排序"""
        try:
            if not category:
                logging.error("类别参数不能为空")
                return {}
                
            # 按照sort_order升序排序，如果sort_order相同则按config_key升序排序
            configs = db.session.query(cls).filter_by(category=category)
            configs = configs.order_by(cls.sort_order, cls.config_key).all()
            
            if not configs:
                logging.warning(f"类别 {category} 没有配置项")
                return {}
                
            result = {}
            for config in configs:
                try:
                    result[config.config_key] = cls.get_config_value(config.config_key)
                except Exception as e:
                    logging.error(f"处理配置项 {config.config_key} 时出错: {str(e)}")
                    result[config.config_key] = config.config_value
                
            logging.info(f"成功获取 {category} 类别 {len(result)} 项配置")
            return result
        except Exception as e:
            logging.error(f"获取类别 {category} 配置失败: {str(e)}", exc_info=True)
            return {}
    
    @classmethod
    def update_config(cls, key, value, user_id=None):
        """更新配置值"""
        try:
            config = cls.query.filter_by(config_key=key).first()
            if not config:
                logging.error(f"更新失败，配置项 {key} 不存在")
                return False
                
            if not config.is_editable:
                logging.warning(f"尝试更新不可编辑的配置项: {key}")
                return False
                
            try:
                if config.config_type == 'list' and isinstance(value, list):
                    config.config_value = ','.join(map(str, value))
                elif config.config_type == 'json' and isinstance(value, (dict, list)):
                    config.config_value = json.dumps(value)
                elif config.config_type == 'bool':
                    config.config_value = 'True' if value else 'False'
                else:
                    config.config_value = str(value)
            except Exception as te:
                logging.error(f"配置项 {key} 更新时类型转换失败: {str(te)}")
                return False
                
            config.updated_by = user_id
            db.session.commit()
            
            if current_app:
                current_app.config[key] = cls.get_config_value(key)
                
            return True
        except Exception as e:
            db.session.rollback()
            logging.error(f"更新配置项 {key} 失败: {str(e)}", exc_info=True)
            return False
    
    @classmethod
    def load_to_app(cls, app):
        """将所有配置加载到Flask应用实例"""
        try:
            configs = cls.query.all()
            for config in configs:
                try:
                    value = cls.get_config_value(config.config_key)
                    if value is not None:
                        app.config[config.config_key] = value
                except Exception as e:
                    logging.error(f"加载配置项 {config.config_key} 失败: {str(e)}")
            return True
        except Exception as e:
            logging.error(f"加载配置到应用失败: {str(e)}", exc_info=True)
            return False
    
    