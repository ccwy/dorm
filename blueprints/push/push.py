"""
Web推送通知蓝图

提供推送订阅管理API和测试推送功能。
"""
from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
from utils.db import db
from models.push.push_subscription import PushSubscription
from utils.push_notification import send_push_notification
import logging

logger = logging.getLogger(__name__)

# 创建推送通知蓝图
push_bp = Blueprint('push', __name__, url_prefix='/push')


@push_bp.route('/subscribe', methods=['POST'])
@login_required
def subscribe():
    """保存推送订阅"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'message': '请求数据无效'}), 400

        endpoint = data.get('endpoint', '').strip()
        keys = data.get('keys', {})
        p256dh = keys.get('p256dh', '').strip()
        auth_key = keys.get('auth', '').strip()

        if not endpoint or not p256dh or not auth_key:
            return jsonify({'success': False, 'message': '缺少必要的订阅参数'}), 400

        user_id = current_user.id

        # 查找是否已存在相同端点的订阅
        existing = PushSubscription.query.filter_by(
            user_id=user_id,
            endpoint=endpoint
        ).first()

        if existing:
            # 更新密钥
            existing.p256dh = p256dh
            existing.auth = auth_key
            logger.info(f"用户 {user_id} 更新推送订阅: {endpoint[:50]}")
        else:
            # 创建新订阅
            subscription = PushSubscription(
                user_id=user_id,
                endpoint=endpoint,
                p256dh=p256dh,
                auth=auth_key
            )
            db.session.add(subscription)
            logger.info(f"用户 {user_id} 新增推送订阅: {endpoint[:50]}")

        db.session.commit()
        return jsonify({'success': True})

    except Exception as e:
        db.session.rollback()
        logger.error(f"保存推送订阅失败: {e}")
        return jsonify({'success': False, 'message': '保存推送订阅失败'}), 500


@push_bp.route('/unsubscribe', methods=['POST'])
@login_required
def unsubscribe():
    """删除推送订阅"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'message': '请求数据无效'}), 400

        endpoint = data.get('endpoint', '').strip()
        if not endpoint:
            return jsonify({'success': False, 'message': '缺少端点参数'}), 400

        user_id = current_user.id

        # 删除指定端点的订阅
        subscription = PushSubscription.query.filter_by(
            user_id=user_id,
            endpoint=endpoint
        ).first()

        if subscription:
            db.session.delete(subscription)
            db.session.commit()
            logger.info(f"用户 {user_id} 删除推送订阅: {endpoint[:50]}")
        else:
            logger.debug(f"用户 {user_id} 未找到推送订阅: {endpoint[:50]}")

        return jsonify({'success': True})

    except Exception as e:
        db.session.rollback()
        logger.error(f"删除推送订阅失败: {e}")
        return jsonify({'success': False, 'message': '删除推送订阅失败'}), 500


@push_bp.route('/vapid-public-key', methods=['GET'])
@login_required
def vapid_public_key():
    """获取VAPID公钥"""
    try:
        from flask import current_app
        public_key = current_app.config.get('VAPID_PUBLIC_KEY', '')
        if not public_key:
            return jsonify({'success': False, 'message': 'VAPID公钥未配置'}), 404
        return jsonify({'success': True, 'publicKey': public_key})
    except Exception as e:
        logger.error(f"获取VAPID公钥失败: {e}")
        return jsonify({'success': False, 'message': '获取VAPID公钥失败'}), 500


@push_bp.route('/test', methods=['POST'])
@login_required
def test_push():
    """测试推送通知"""
    try:
        user_id = current_user.id
        result = send_push_notification(
            user_id=user_id,
            title='推送通知测试',
            body=f'这是一条来自宿舍管理系统的测试推送通知，发送给用户 {current_user.name}。',
            url='/'
        )

        if result:
            return jsonify({'success': True, 'message': '测试推送已发送'})
        else:
            # 检查是VAPID未配置还是没有订阅
            from flask import current_app
            if not current_app.config.get('VAPID_PRIVATE_KEY') or not current_app.config.get('VAPID_PUBLIC_KEY'):
                return jsonify({'success': False, 'message': 'VAPID密钥未配置，推送功能不可用'}), 400

            sub_count = PushSubscription.query.filter_by(user_id=user_id).count()
            if sub_count == 0:
                return jsonify({'success': False, 'message': '您还没有推送订阅，请先在浏览器中允许通知权限'}), 400

            return jsonify({'success': False, 'message': '推送发送失败，请检查VAPID配置'}), 500

    except Exception as e:
        logger.error(f"测试推送通知失败: {e}")
        return jsonify({'success': False, 'message': f'测试推送失败: {str(e)}'}), 500