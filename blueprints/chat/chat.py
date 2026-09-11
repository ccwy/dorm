from flask import Blueprint, render_template, redirect, url_for, request, jsonify, flash
from flask_login import login_required, current_user
from utils.auth import require_permission
from sqlalchemy.exc import SQLAlchemyError
from datetime import datetime
import logging
from utils.db import db
from models.chat.chat_session import ChatSession
from models.chat.chat_participant import ChatParticipant
from models.chat.chat_message import ChatMessage
from models.user.user import User
from models.department.department import Department

# 创建聊天功能蓝图
chat_bp = Blueprint('chat', __name__, url_prefix='/chat')

def _get_chat_sessions_data(include_hidden=False):
    """获取聊天会话数据（共享函数）"""
    # 获取当前用户参与的所有未隐藏的聊天会话
    if include_hidden:
        chat_sessions = current_user.chat_sessions
    else:
        # 查询未隐藏的会话（包括is_hidden为False或NULL的情况）
        from sqlalchemy import and_, or_
        chat_sessions = ChatSession.query.join(ChatParticipant).filter(
            and_(
                ChatParticipant.user_id == current_user.id,
                or_(
                    ChatParticipant.is_hidden == False,
                    ChatParticipant.is_hidden.is_(None)
                )
            )
        ).all()
    
    # 处理每个会话的最新消息和未读消息数量
    sessions_with_latest_msg = []
    for session in chat_sessions:
        latest_message = ChatMessage.query.filter_by(chat_session_id=session.id) \
                                      .order_by(ChatMessage.created_at.desc()) \
                                      .first()
        
        # 计算未读消息数量
        unread_count = ChatMessage.query.filter_by(chat_session_id=session.id, is_read=False) \
                                        .filter(ChatMessage.sender_id != current_user.id) \
                                        .count()
        
        # 获取会话参与者（不包括当前用户）
        other_participants = [p for p in session.participants if p.id != current_user.id]
        
        sessions_with_latest_msg.append({
            'session': session,
            'latest_message': latest_message,
            'unread_count': unread_count,
            'other_participants': other_participants
        })
    
    # 按最新消息时间排序
    sessions_with_latest_msg.sort(key=lambda x: 
        x['latest_message'].created_at if x['latest_message'] else datetime.min, 
        reverse=True
    )
    
    return sessions_with_latest_msg

@chat_bp.route('/')
@login_required
@require_permission('chat.manage')
def chat_index():
    """聊天功能首页，显示所有聊天会话"""
    logging.info(f"用户 {current_user.id} - {current_user.name} 访问聊天首页")
    logging.info(f"请求参数: {request.args.to_dict()}")
    
    try:
        logging.info(f"获取当前用户参与的所有聊天会话")
        # 使用共享函数获取会话数据
        sessions_with_latest_msg = _get_chat_sessions_data()
        
        logging.info(f"找到 {len(sessions_with_latest_msg)} 个聊天会话，会话列表处理完成，准备渲染模板")
        return render_template('chat/chat_index.html', title="OA聊天",
                             sessions_with_latest_msg=sessions_with_latest_msg)
    except Exception as e:
        logging.error(f"获取聊天会话列表失败: {str(e)}")
        logging.error(f"错误类型: {type(e).__name__}")
        import traceback
        logging.error(f"错误堆栈: {traceback.format_exc()}")
        flash('获取聊天会话列表失败', 'danger')
        return redirect(url_for('index'))

@chat_bp.route('/start_chat/<int:user_id>')
@login_required
@require_permission('chat.manage')
def start_chat(user_id):
    """开始与指定用户的聊天"""
    logging.info(f"用户 {current_user.id} - {current_user.name} 请求开始聊天，目标用户ID: {user_id}")
    logging.info(f"请求参数: {request.args.to_dict()}")
    
    try:
        if user_id == current_user.id:
            logging.warning(f"用户 {current_user.id} 尝试与自己聊天")
            return jsonify({
                'success': False,
                'message': '不能与自己聊天'
            })
            
        # 再次验证user_id的有效性
        logging.info(f"验证用户ID: {user_id} 类型: {type(user_id)}")
        if not isinstance(user_id, int) or user_id <= 0:
            logging.error(f"无效的用户ID: {user_id}")
            return jsonify({
                'success': False,
                'message': '无效的用户ID'
            })
            
        # 检查是否已存在与该用户的私聊会话
        logging.info(f"查询所有私聊会话")
        existing_sessions = ChatSession.query.filter(ChatSession.is_group_chat == False).all()
        logging.info(f"找到 {len(existing_sessions)} 个私聊会话")
        
        logging.info(f"查询目标用户信息，用户ID: {user_id}")
        target_user = User.query.get(user_id)
        
        if not target_user:
            logging.error(f"用户不存在，用户ID: {user_id}")
            return jsonify({
                'success': False,
                'message': '用户不存在'
            })
        
        logging.info(f"找到目标用户: {target_user.id} - {target_user.name}")
        
        # 查找现有会话
        logging.info(f"开始查找与用户 {user_id} 的现有会话")
        existing_session = None
        for session in existing_sessions:
            participants = [p.id for p in session.participants]
            logging.debug(f"会话 {session.id} 参与者: {participants}")
            if current_user.id in participants and user_id in participants and len(participants) == 2:
                existing_session = session
                break
        
        if existing_session:
            # 如果存在现有会话，确保将其设置为不隐藏状态
            logging.info(f"找到现有会话: {existing_session.id}")
            
            # 获取当前用户在这个会话中的参与者记录
            current_participant = ChatParticipant.query.filter_by(
                chat_session_id=existing_session.id,
                user_id=current_user.id
            ).first()
            
            # 如果参与者记录存在且is_hidden为True，则将其设置为False
            if current_participant and current_participant.is_hidden:
                current_participant.is_hidden = False
                db.session.commit()
                logging.info(f"已将会话 {existing_session.id} 的is_hidden状态设置为False")
            
            return jsonify({
                'success': True,
                'session_id': existing_session.id
            })
        else:
            # 创建新的私聊会话
            logging.info(f"未找到现有会话，创建新的私聊会话")
            new_session = ChatSession(
                is_group_chat=False,
                created_at=datetime.now()
            )
            db.session.add(new_session)
            db.session.flush()  # 获取session_id
            logging.info(f"新会话创建成功，会话ID: {new_session.id}")
            
            # 添加参与者
            logging.info(f"添加参与者到会话: 用户 {current_user.id} 和用户 {user_id}")
            current_participant = ChatParticipant(
                chat_session_id=new_session.id,
                user_id=current_user.id,
                joined_at=datetime.now(),
                is_hidden=False  # 显式设置为不隐藏
            )
            target_participant = ChatParticipant(
                chat_session_id=new_session.id,
                user_id=user_id,
                joined_at=datetime.now(),
                is_hidden=False  # 显式设置为不隐藏
            )
            
            db.session.add_all([current_participant, target_participant])
            db.session.commit()
            logging.info(f"参与者添加成功，会话初始化完成")
            
            return jsonify({
                'success': True,
                'session_id': new_session.id
            })
    except Exception as e:
        db.session.rollback()
        logging.error(f"开始聊天失败: {str(e)}")
        logging.error(f"错误类型: {type(e).__name__}")
        import traceback
        logging.error(f"错误堆栈: {traceback.format_exc()}")
        return jsonify({
                'success': False,
                'message': str(e)
            })

@chat_bp.route('/create_group_chat', methods=['POST'])
@login_required
@require_permission('chat.manage')
def create_group_chat():
    """创建群聊"""
    logging.info(f"用户 {current_user.id} - {current_user.name} 请求创建群聊")
    logging.info(f"表单参数: {request.form.to_dict()}")
    logging.info(f"原始参与者ID列表: {request.form.getlist('participants')}")
    
    try:
        group_name = request.form.get('group_name', '').strip()
        participant_ids = request.form.getlist('participants')
        
        if not participant_ids:
            logging.warning(f"未选择任何群聊成员")
            return jsonify({
                'success': False,
                'message': '请至少选择一个群聊成员'
            })
        
        # 转换参与者ID为整数并添加当前用户
        # 先过滤掉空字符串和非数字，然后再转换为整数
        logging.info(f"开始处理参与者ID列表")
        valid_participant_ids = []
        for pid in participant_ids:
            logging.debug(f"处理参与者ID: '{pid}', 类型: {type(pid)}, 是否为空: {not pid}, 是否为数字: {pid.isdigit() if isinstance(pid, str) else 'N/A'}")
            if pid and isinstance(pid, str) and pid.isdigit():
                try:
                    valid_id = int(pid)
                    valid_participant_ids.append(valid_id)
                    logging.debug(f"成功转换ID '{pid}' 为整数 {valid_id}")
                except ValueError as ve:
                    logging.error(f"转换ID '{pid}' 为整数失败: {str(ve)}")
        
        logging.info(f"过滤后有效的参与者ID数量: {len(valid_participant_ids)}")
        
        if current_user.id not in valid_participant_ids:
            logging.info(f"添加当前用户 {current_user.id} 到参与者列表")
            valid_participant_ids.append(current_user.id)
        
        # 去重
        valid_participant_ids = list(set(valid_participant_ids))
        logging.info(f"去重后最终参与者ID列表: {valid_participant_ids}")
        
        # 创建群聊会话
        logging.info(f"创建群聊会话，群聊名称: '{group_name}'")
        # 只保存原始群聊名称，不添加人数信息
        final_name = group_name if group_name else "群聊"
        new_session = ChatSession(
            name=final_name,
            is_group_chat=True,
            created_at=datetime.now(),
            participant_count=len(valid_participant_ids)
        )
        db.session.add(new_session)
        db.session.flush()  # 获取session_id
        logging.info(f"群聊会话创建成功，会话ID: {new_session.id}")
        
        # 添加所有参与者
        logging.info(f"开始添加 {len(valid_participant_ids)} 个参与者到会话")
        participants = []
        for user_id in valid_participant_ids:
            logging.debug(f"添加参与者 {user_id} 到会话 {new_session.id}")
            participant = ChatParticipant(
                chat_session_id=new_session.id,
                user_id=user_id,
                joined_at=datetime.now()
            )
            participants.append(participant)
        
        db.session.add_all(participants)
        db.session.commit()
        logging.info(f"所有参与者添加成功，群聊创建完成")
        
        return jsonify({
                'success': True,
                'session_id': new_session.id
            })
    except Exception as e:
        db.session.rollback()
        logging.error(f"创建群聊失败: {str(e)}")
        logging.error(f"错误类型: {type(e).__name__}")
        import traceback
        logging.error(f"错误堆栈: {traceback.format_exc()}")
        return jsonify({
            'success': False,
            'message': '创建群聊失败'
        })


@chat_bp.route('/send_message', methods=['POST'])
@login_required
@require_permission('chat.manage')
def send_message():
    """发送消息"""
    logging.info(f"用户 {current_user.id} - {current_user.name} 请求发送消息")
    logging.info(f"表单参数: {request.form.to_dict()}")
    
    try:
        session_id = request.form.get('session_id')
        content = request.form.get('content', '').strip()
        
        logging.info(f"接收到的参数 - session_id: '{session_id}' 类型: {type(session_id)}, content: '{content}' 长度: {len(content)}")
        
        if not session_id or not content:
            logging.error(f"参数错误 - session_id: {session_id is not None}, content: {content is not None}")
            return jsonify({'success': False, 'message': '参数错误'})
        
        # 验证session_id是否为有效的整数
        try:
            session_id_int = int(session_id)
            logging.info(f"成功将会话ID '{session_id}' 转换为整数 {session_id_int}")
        except ValueError:
            logging.error(f"无效的会话ID: '{session_id}'")
            return jsonify({'success': False, 'message': '无效的会话ID'})
        
        # 检查会话是否存在且当前用户是参与者
        logging.info(f"查询会话信息，会话ID: {session_id_int}")
        session = ChatSession.query.get(session_id_int)
        
        if not session:
            logging.error(f"会话不存在，会话ID: {session_id_int}")
            return jsonify({'success': False, 'message': '会话不存在'})
        
        logging.info(f"找到会话: {session.id} - {session.name or '私聊会话'}")
        
        logging.info(f"检查用户是否为会话参与者")
        is_participant = any(p.id == current_user.id for p in session.participants)
        if not is_participant:
            logging.error(f"用户 {current_user.id} 不是会话 {session_id_int} 的参与者")
            return jsonify({'success': False, 'message': '您无权发送消息'})
        
        # 创建新消息
        logging.info(f"创建新消息，内容长度: {len(content)}")
        new_message = ChatMessage(
            chat_session_id=session_id_int,
            sender_id=current_user.id,
            content=content,
            created_at=datetime.now()
        )
        
        db.session.add(new_message)
        db.session.commit()
        logging.info(f"消息发送成功，消息ID: {new_message.id}")
        
        # 格式化返回的消息时间
        formatted_time = new_message.created_at.strftime('%Y-%m-%d %H:%M:%S')
        logging.info(f"消息格式化完成，准备返回响应")
        
        # 关键修改：当发送新消息时，确保所有接收者的会话都不隐藏
        # 获取会话中所有参与者（除了发送者自己）
        other_participants = [p for p in session.participants if p.id != current_user.id]
        
        if other_participants:
            logging.info(f"更新 {len(other_participants)} 个接收者的会话隐藏状态")
            # 查询这些参与者的ChatParticipant记录并更新is_hidden状态
            for participant in other_participants:
                chat_participant = ChatParticipant.query.filter_by(
                    chat_session_id=session_id_int,
                    user_id=participant.id
                ).first()
                
                if chat_participant and chat_participant.is_hidden:
                    logging.info(f"将会话 {session_id_int} 对用户 {participant.id} 的隐藏状态设置为False")
                    chat_participant.is_hidden = False
            
            # 提交所有更改
            db.session.commit()
        
        return jsonify({
            'success': True,
            'message': {
                'id': new_message.id,
                'content': new_message.content,
                'created_at': formatted_time,
                'sender_name': current_user.name,
                'sender_id': current_user.id
            }
        })
    except Exception as e:
        db.session.rollback()
        logging.error(f"发送消息失败: {str(e)}")
        logging.error(f"错误类型: {type(e).__name__}")
        import traceback
        logging.error(f"错误堆栈: {traceback.format_exc()}")
        return jsonify({'success': False, 'message': '发送消息失败'})

@chat_bp.route('/get_users_for_chat')
@login_required
@require_permission('chat.manage')
def get_users_for_chat():
    """获取用户列表用于聊天选择（API），支持部门、性别、公司筛选和分页"""
    try:
        # 获取筛选参数
        department = request.args.get('department', '').strip()
        gender = request.args.get('gender', '').strip()
        company = request.args.get('company', '').strip()
        search_term = request.args.get('search_term', '').strip()
        
        # 获取分页参数
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 10))
        
        # 构建查询 - 关联Department表以确保公司和部门数据源统一
        query = User.query.filter(User.is_active == True, User.status == '在职', User.id != current_user.id)\
            .outerjoin(Department, User.department_id == Department.id)
        
        # 应用筛选条件
        if department:
            query = query.filter(Department.name == department)
        if gender:
            query = query.filter(User.gender == gender)
        if company:
            query = query.filter(Department.company == company)
        if search_term:
            search_pattern = f"%{search_term}%"
            query = query.filter(
                (User.name.like(search_pattern)) |
                (Department.name.like(search_pattern)) |
                (User.position.like(search_pattern))
            )
        
        # 执行分页查询
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        users = pagination.items
        total_count = pagination.total
        
        # 获取所有可选的部门、性别、公司值（用于前端筛选下拉框）
        all_departments = Department.query.filter_by(status='正常').with_entities(Department.name).order_by(Department.name).all()
        all_genders = db.session.query(User.gender).filter(User.gender.isnot(None), User.gender != '').distinct().all()
        all_companies = Department.get_all_companies()
        
        # 格式化用户数据和筛选选项
        users_data = [{
            'id': user.id,
            'name': user.name,
            'department': user.department or '未设置部门',
            'position': user.position or '未设置职位',
            'gender': user.gender,
            'company': user.company or '未设置公司'
        } for user in users]
        
        departments_data = [d[0] for d in all_departments]
        genders_data = [g[0] for g in all_genders]
        companies_data = all_companies  # Department.get_all_companies()已返回字符串列表
        
        return jsonify({
            'success': True,
            'users': users_data,
            'total_count': total_count,
            'departments': departments_data,
            'genders': genders_data,
            'companies': companies_data,
            'current_page': page,
            'per_page': per_page,
            'total_pages': pagination.pages
        })
    except Exception as e:
        logging.error(f"获取用户列表失败: {str(e)}")
        return jsonify({
            'success': False,
            'message': '获取用户列表失败'
        })

@chat_bp.route('/get_filter_options')
@login_required
@require_permission('chat.manage')
def get_filter_options():
    """获取筛选选项（部门、性别、公司）"""
    try:
        # 获取所有可选的部门、性别、公司值
        all_departments = Department.query.filter_by(status='正常').with_entities(Department.name).order_by(Department.name).all()
        all_genders = db.session.query(User.gender).filter(User.gender.isnot(None), User.gender != '').distinct().all()
        all_companies = Department.get_all_companies()
        
        # 格式化数据
        departments_data = [d[0] for d in all_departments]
        genders_data = [g[0] for g in all_genders]
        companies_data = all_companies  # Department.get_all_companies()已返回字符串列表
        
        return jsonify({
            'success': True,
            'departments': departments_data,
            'genders': genders_data,
            'companies': companies_data
        })
    except Exception as e:
        logging.error(f"获取筛选选项失败: {str(e)}")
        return jsonify({
            'success': False,
            'message': '获取筛选选项失败'
        })

@chat_bp.route('/get_chat_sessions')
@login_required
@require_permission('chat.manage')
def get_chat_sessions():
    """获取聊天会话列表（API）"""
    try:
        # 使用共享函数获取会话数据
        sessions_with_latest_msg = _get_chat_sessions_data()
        
        # 格式化数据为JSON格式
        sessions_data = []
        for item in sessions_with_latest_msg:
            session = item['session']
            latest_message = item['latest_message']
            unread_count = item['unread_count']
            other_participants = item['other_participants']
            
            # 格式化最新消息
            latest_message_data = None
            if latest_message:
                latest_message_data = {
                    'id': latest_message.id,
                    'content': latest_message.content,
                    'created_at': latest_message.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                    'sender_id': latest_message.sender_id,
                    'sender_name': latest_message.sender.name
                }
            
            # 格式化参与者数据
            participants_data = [{
                'id': p.id,
                'name': p.name,
                'gender': p.gender,
                'company': p.company,
                'department': p.department,
                'position': p.position
            } for p in other_participants]
            
            sessions_data.append({
                'id': session.id,
                'name': session.name if session.is_group_chat else (participants_data[0]['name'] if participants_data else '未知用户'),
                'is_group_chat': session.is_group_chat,
                'latest_message': latest_message_data,
                'unread_count': unread_count,
                'participants': participants_data,
                'participant_count': session.participant_count  # 添加participant_count字段
            })
        
        return jsonify({
            'success': True,
            'sessions': sessions_data
        })
    except Exception as e:
        logging.error(f"获取聊天会话列表失败: {str(e)}")
        return jsonify({
            'success': False,
            'message': '获取聊天会话列表失败'
        })

@chat_bp.route('/hide_session/<int:session_id>', methods=['POST'])
@login_required
@require_permission('chat.manage')
def hide_session(session_id):
    """隐藏聊天会话"""
    try:
        # 检查会话是否存在，并且用户是否为参与者
        chat_participant = ChatParticipant.query.filter_by(
            chat_session_id=session_id,
            user_id=current_user.id
        ).first()
        
        if not chat_participant:
            return jsonify({
                'success': False,
                'message': '会话不存在或您不是该会话的参与者'
            })
        
        # 切换隐藏状态
        chat_participant.is_hidden = not chat_participant.is_hidden
        db.session.commit()
        
        return jsonify({
            'success': True,
            'is_hidden': chat_participant.is_hidden,
            'message': f"会话已{'隐藏' if chat_participant.is_hidden else '取消隐藏'}"
        })
    except Exception as e:
        db.session.rollback()
        logging.error(f"隐藏会话失败: {str(e)}")
        return jsonify({
            'success': False,
            'message': '操作失败，请重试'
        })

@chat_bp.route('/get_new_messages/<int:session_id>/<int:last_message_id>')
@login_required
@require_permission('chat.manage')
def get_new_messages(session_id, last_message_id):
    """获取新消息（用于简单轮询）"""
    logging.info(f"用户 {current_user.id} - {current_user.name} 请求获取新消息")
    logging.info(f"请求参数 - session_id: {session_id} 类型: {type(session_id)}, last_message_id: {last_message_id} 类型: {type(last_message_id)}")
    logging.info(f"请求路径: {request.path}")
    
    try:
        # 检查会话是否存在且当前用户是参与者
        logging.info(f"查询会话信息，会话ID: {session_id}")
        session = ChatSession.query.get(session_id)
        
        if not session:
            logging.error(f"会话不存在，会话ID: {session_id}")
            return jsonify({'success': False, 'message': '会话不存在'})
        
        logging.info(f"找到会话: {session.id} - {session.name or '私聊会话'}")
        
        logging.info(f"检查用户是否为会话参与者")
        is_participant = any(p.id == current_user.id for p in session.participants)
        if not is_participant:
            logging.error(f"用户 {current_user.id} 不是会话 {session_id} 的参与者")
            return jsonify({'success': False, 'message': '您无权获取消息'})
        
        logging.info(f"用户是会话参与者，继续获取新消息")
        
        # 获取新消息
        logging.info(f"查询新消息，条件: chat_session_id={session_id}, id>{last_message_id}")
        new_messages = ChatMessage.query.filter(
            ChatMessage.chat_session_id == session_id,
            ChatMessage.id > last_message_id
        ).order_by(ChatMessage.created_at).all()
        
        logging.info(f"找到 {len(new_messages)} 条新消息")
        
        # 将未读消息标记为已读
        unread_count = 0
        for msg in new_messages:
            if msg.sender_id != current_user.id and not msg.is_read:
                msg.is_read = True
                unread_count += 1
        
        if unread_count > 0:
            logging.info(f"已将 {unread_count} 条未读消息标记为已读")
            db.session.commit()
        
        # 格式化消息数据
        logging.info(f"开始格式化消息数据")
        formatted_messages = []
        for msg in new_messages:
            try:
                formatted_messages.append({
                    'id': msg.id,
                    'content': msg.content,
                    'created_at': msg.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                    'sender_name': msg.sender.name,
                    'sender_id': msg.sender.id
                })
            except Exception as msg_err:
                logging.error(f"格式化消息 {msg.id} 失败: {str(msg_err)}")
        
        logging.info(f"消息格式化完成，共 {len(formatted_messages)} 条消息")
        
        return jsonify({
            'success': True,
            'messages': formatted_messages
        })
    except Exception as e:
        logging.error(f"获取新消息失败: {str(e)}")
        logging.error(f"错误类型: {type(e).__name__}")
        import traceback
        logging.error(f"错误堆栈: {traceback.format_exc()}")
        return jsonify({'success': False, 'message': '获取新消息失败'})

@chat_bp.route('/get_messages/<int:session_id>')
@login_required
@require_permission('chat.manage')
def get_messages(session_id):
    """获取特定会话的所有消息"""
    logging.info(f"用户 {current_user.id} - {current_user.name} 请求获取会话消息")
    logging.info(f"请求参数 - session_id: {session_id} 类型: {type(session_id)}")
    logging.info(f"请求路径: {request.path}")
    
    try:
        # 检查会话是否存在且当前用户是参与者
        logging.info(f"查询会话信息，会话ID: {session_id}")
        session = ChatSession.query.get(session_id)
        
        if not session:
            logging.error(f"会话不存在，会话ID: {session_id}")
            return jsonify({'success': False, 'message': '会话不存在'})
        
        logging.info(f"找到会话: {session.id} - {session.name or '私聊会话'}")
        
        logging.info(f"检查用户是否为会话参与者")
        is_participant = any(p.id == current_user.id for p in session.participants)
        if not is_participant:
            logging.error(f"用户 {current_user.id} 不是会话 {session_id} 的参与者")
            return jsonify({'success': False, 'message': '您无权获取消息'})
        
        logging.info(f"用户是会话参与者，继续获取所有消息")
        
        # 获取该会话的所有消息，按时间排序
        logging.info(f"查询会话所有消息，条件: chat_session_id={session_id}")
        messages = ChatMessage.query.filter_by(chat_session_id=session_id) \
                                   .order_by(ChatMessage.created_at).all()
        
        logging.info(f"找到 {len(messages)} 条消息")
        
        # 将未读消息标记为已读
        unread_count = 0
        for msg in messages:
            if msg.sender_id != current_user.id and not msg.is_read:
                msg.is_read = True
                unread_count += 1
        
        if unread_count > 0:
            logging.info(f"已将 {unread_count} 条未读消息标记为已读")
            db.session.commit()
        
        # 格式化消息数据
        logging.info(f"开始格式化消息数据")
        formatted_messages = []
        for msg in messages:
            try:
                formatted_messages.append({
                    'id': msg.id,
                    'content': msg.content,
                    'created_at': msg.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                    'sender_name': msg.sender.name,
                    'sender_id': msg.sender.id
                })
            except Exception as msg_err:
                logging.error(f"格式化消息 {msg.id} 失败: {str(msg_err)}")
        
        logging.info(f"消息格式化完成，共 {len(formatted_messages)} 条消息")
        
        # 获取会话名称
        session_name = session.name
        if not session_name and len(session.participants) > 1:
            # 如果是私聊，则将会话名称设为对方的用户名
            other_participants = [p for p in session.participants if p.id != current_user.id]
            if other_participants:
                session_name = other_participants[0].name
        
        return jsonify({
            'success': True,
            'messages': formatted_messages,
            'session_name': session_name or '聊天会话'
        })
    except Exception as e:
        logging.error(f"获取会话消息失败: {str(e)}")
        logging.error(f"错误类型: {type(e).__name__}")
        import traceback
        logging.error(f"错误堆栈: {traceback.format_exc()}")
        return jsonify({'success': False, 'message': '获取会话消息失败'})

