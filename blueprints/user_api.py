from flask import Blueprint, jsonify, request, abort
from utils.db import db
from models.user import User
from models.dorm import Dorm
from models.room import Room
from flask_login import login_required, current_user
from utils.log import log_operation
import datetime
from sqlalchemy import or_
# 导入admin_required装饰器
from utils.auth import admin_required
# 移除从蓝图导入的函数（已迁移到g工具）
from utils.user_utils import process_field_value
import logging


# 蓝图变量名保持不变
user_api_bp = Blueprint('user_api', __name__, url_prefix='/api/users')

@user_api_bp.route('/<int:user_id>', methods=['GET'])
@login_required
@admin_required
def get_user(user_id):
    """获取指定ID的用户详细信息（JSON接口）"""
    try:
        # 查询指定ID的用户
        user = User.query.get(user_id)
        if not user:
            log_operation(
                user_id=current_user.id,
                module='user',
                operation_type='user_api',
                action=f"尝试获取用户信息 [ID: {user_id}]，失败: 用户不存在",
                result="失败"
            )
            logging.error(f"获取用户信息操作失败，用户ID: {user_id}，异常信息: 用户不存在")
            return jsonify({
                'success': False,
                'message': f'ID为{user_id}的用户不存在'
            }), 404
        
        # 获取住宿信息
        current_dorm = Dorm.query.filter_by(
            user_id=user.id,
            status='active'
        ).first()
        # 房间号
        room_full_identifier = None
        if current_dorm and current_dorm.room:
            room_full_identifier = f"{current_dorm.room.building}{current_dorm.room.room_number}"
        
        # 使用模型方法替代原蓝图函数
        birth_date = user.get_birth_date_from_id()
        age = user.get_age()
        native_place = user.extract_native_place()
        
        # 构造返回数据
        user_data = {
            'id': user.id,
            'student_id': user.student_id,
            'name': user.name,
            'gender': user.gender,
            'age': str(age) if age else '',
            'birthday': birth_date.strftime('%Y-%m-%d') if birth_date else '',
            'native_place': native_place or '',
            'id_card': user.id_card,
            'id_address': user.id_address,
            'phone': user.phone,
            'department': user.department,
            'position': user.position,
            'emergency_contact': user.emergency_contact,
            'emergency_phone': user.emergency_phone,
            'remarks': user.remarks,
            'status': user.status,
            'status_code': user.status,
            'room_full_identifier': room_full_identifier,
            'created_at': process_field_value('created_at', user.created_at),
            'updated_at': process_field_value('updated_at', user.updated_at)
        }
        
        log_operation(
            user_id=current_user.id,
            module='user',
            operation_type='user_api',
            action=f"获取用户信息 [ID: {user_id}, 姓名: {user.name}]",
            result="成功"
        )
        logging.info(f"获取用户信息操作成功，用户ID: {user_id}，姓名: {user.name}")
        return jsonify({
            'success': True,
            'data': user_data
        })
        
    except Exception as e:
        log_operation(
            user_id=current_user.id,
            module='user',
            operation_type='user_api',
            action=f"尝试获取用户信息 [ID: {user_id}]，失败: {str(e)}",
            result="失败"
        )
        logging.error(f"获取用户信息操作失败，用户ID: {user_id}，异常信息: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'获取用户信息失败: {str(e)}'
        }), 500

@user_api_bp.route('/search', methods=['GET'])
@login_required
@admin_required
def search_users():
    """搜索用户信息的API接口（支持分页）"""
    try:
        search_query = request.args.get('query', '').strip()
        
        # 获取分页参数
        use_pagination = True
        try:
            page = int(request.args.get('page', 0))
            if page < 1:
                use_pagination = False
        except ValueError:
            use_pagination = False
        
        try:
            per_page = int(request.args.get('per_page', 20))
            if per_page < 1 or per_page > 100:
                per_page = 20
        except ValueError:
            per_page = 20
        
        # 基础查询：默认返回所有用户
        query = User.query
        
        # 只有当查询词不为空时，才添加过滤条件
        if search_query:
            query = query.filter(
                or_(
                    User.name.ilike(f'%{search_query}%'),
                    User.department.ilike(f'%{search_query}%'),
                    User.position.ilike(f'%{search_query}%'),
                    User.phone.ilike(f'%{search_query}%'),
                    User.student_id.ilike(f'%{search_query}%')
                )
            )
        
        # 获取总记录数
        total_count = query.count()
        
        # 执行查询（根据是否启用分页）
        if use_pagination:
            offset = (page - 1) * per_page
            users = query.offset(offset).limit(per_page).all()
        else:
            users = query.all()
            page = 1
            per_page = total_count
        
        # 处理返回数据
        result = []
        for user in users:
            current_dorm = Dorm.query.filter_by(
                user_id=user.id,
                status='active'
            ).first()
            #房间号
            room_full_identifier = None
            if current_dorm and current_dorm.room:
                room_full_identifier = f"{current_dorm.room.building}{current_dorm.room.room_number}"
                
            # 使用模型方法获取年龄
            age = user.get_age()
            
            result.append({
                'id': user.id,
                'name': user.name,
                'gender': user.gender,
                'age': str(age) if age else '',
                'department': user.department,
                'position': user.position,
                'phone': user.phone,
                'room_full_identifier': room_full_identifier,
                'status': user.status,
                'lodging_allowance': user.lodging_allowance,
                'reduction_fee': user.reduction_fee,
            })
        
        # 日志记录（根据是否使用分页）
        if use_pagination:
            action_desc = f"搜索用户信息 [查询词: {search_query}]，页码: {page}，每页数量: {per_page}"
            log_info = f"搜索用户信息操作成功，查询词: {search_query}，页码: {page}，每页数量: {per_page}，返回用户数: {len(result)}"
        else:
            action_desc = f"搜索用户信息 [查询词: {search_query}]，返回全部结果"
            log_info = f"搜索用户信息操作成功，查询词: {search_query}，返回全部用户数: {len(result)}"
        
        log_operation(
            user_id=current_user.id,
            module='user',
            operation_type='user_api',
            action=action_desc,
            result="成功"
        )
        logging.info(log_info)
        return jsonify({
            'success': True,
            'data': {
                'count': total_count,
                'users': result
            }
        })
        
    except Exception as e:
        log_operation(
            user_id=current_user.id,
            module='user',
            operation_type='user_api',
            action=f"尝试搜索用户信息 [查询词: {search_query}]，失败: {str(e)}",
            result="失败"
        )
        logging.error(f"搜索用户信息操作失败，查询词: {search_query}，异常信息: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'搜索失败: {str(e)}'
        }), 500
    