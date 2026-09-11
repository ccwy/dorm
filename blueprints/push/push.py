"""
Web推送通知蓝图

提供推送订阅管理API和测试推送功能。
"""
from flask import Blueprint, request, jsonify, Response
from flask_login import login_required, current_user
from utils.db import db
from models.push.push_subscription import PushSubscription
from utils.push_notification import send_push_notification
import os
import logging

logger = logging.getLogger(__name__)

# 创建推送通知蓝图
push_bp = Blueprint('push', __name__, url_prefix='/push')


@push_bp.route('/manifest.json')
def manifest():
    """动态生成PWA manifest.json，使用系统配置的标题"""
    from utils.db_config import DatabaseConfig
    config = DatabaseConfig.load_config()
    system_title = config.get('SYSTEM_TITLE', '行政后勤管理系统')
    short_name = system_title[:12] if len(system_title) > 12 else system_title

    manifest_data = {
        "name": system_title,
        "short_name": short_name,
        "description": system_title,
        "start_url": "/",
        "display": "standalone",
        "background_color": "#ffffff",
        "theme_color": "#3b82f6",
        "orientation": "any",
        "icons": [
            {"src": "/static/images/pwa/icon-72x72.png", "sizes": "72x72", "type": "image/png"},
            {"src": "/static/images/pwa/icon-96x96.png", "sizes": "96x96", "type": "image/png"},
            {"src": "/static/images/pwa/icon-128x128.png", "sizes": "128x128", "type": "image/png"},
            {"src": "/static/images/pwa/icon-144x144.png", "sizes": "144x144", "type": "image/png"},
            {"src": "/static/images/pwa/icon-152x152.png", "sizes": "152x152", "type": "image/png"},
            {"src": "/static/images/pwa/icon-192x192.png", "sizes": "192x192", "type": "image/png"},
            {"src": "/static/images/pwa/icon-384x384.png", "sizes": "384x384", "type": "image/png"},
            {"src": "/static/images/pwa/icon-512x512.png", "sizes": "512x512", "type": "image/png"}
        ]
    }
    import json
    return Response(json.dumps(manifest_data, ensure_ascii=False), mimetype='application/manifest+json')


@push_bp.route('/sw.js')
def service_worker():
    """提供Service Worker脚本，通过Service-Worker-Allowed头允许scope为/"""
    from flask import current_app
    import os

    sw_path = os.path.join(current_app.root_path, 'static', 'js', 'sw.js')
    try:
        with open(sw_path, 'r', encoding='utf-8') as f:
            sw_content = f.read()
    except FileNotFoundError:
        return Response('/* SW file not found */', mimetype='application/javascript', status=404)

    response = Response(sw_content, mimetype='application/javascript')
    response.headers['Service-Worker-Allowed'] = '/'
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    return response


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
        # 获取订阅时的页面域名（优先使用前端传递，回退到request.host）
        subscribed_domain = data.get('subscribedDomain', '').strip() or request.host

        if not endpoint or not p256dh or not auth_key:
            return jsonify({'success': False, 'message': '缺少必要的订阅参数'}), 400

        user_id = current_user.id

        # 查找是否已存在相同端点的订阅
        existing = PushSubscription.query.filter_by(
            user_id=user_id,
            endpoint=endpoint
        ).first()

        if existing:
            # 更新密钥和域名
            existing.p256dh = p256dh
            existing.auth = auth_key
            existing.subscribed_domain = subscribed_domain
            logger.info(f"用户 {user_id} 更新推送订阅: {endpoint[:50]}, domain={subscribed_domain}")
        else:
            # 创建新订阅
            subscription = PushSubscription(
                user_id=user_id,
                endpoint=endpoint,
                p256dh=p256dh,
                auth=auth_key,
                subscribed_domain=subscribed_domain
            )
            db.session.add(subscription)
            logger.info(f"用户 {user_id} 新增推送订阅: {endpoint[:50]}, domain={subscribed_domain}")

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


def _recover_vapid_keys(app):
    """尝试从持久化文件恢复VAPID密钥到Flask配置。
    
    当Flask配置中VAPID密钥为空时（如进程重启后env vars未继承），
    从vapid_keys.json文件重新加载密钥，避免永久503。
    
    Returns:
        bool: True表示恢复成功，False表示恢复失败
    """
    if app.config.get('VAPID_PUBLIC_KEY'):
        return True  # 密钥已存在，无需恢复

    try:
        # 尝试从环境变量恢复（可能ensure_vapid_keys已设置但Flask config未更新）
        env_public = os.environ.get('VAPID_PUBLIC_KEY', '')
        env_private = os.environ.get('VAPID_PRIVATE_KEY', '')
        if env_public and env_private:
            app.config['VAPID_PUBLIC_KEY'] = env_public
            app.config['VAPID_PRIVATE_KEY'] = env_private
            app.config['VAPID_CLAIM_EMAIL'] = os.environ.get('VAPID_CLAIM_EMAIL', 'admin@dorm.local')
            logger.info("[VAPID] 从环境变量恢复密钥到Flask配置成功")
            return True

        # 环境变量也为空，尝试从持久化文件恢复
        from utils.generate_vapid_keys import ensure_vapid_keys
        result = ensure_vapid_keys()
        if result:
            env_public = os.environ.get('VAPID_PUBLIC_KEY', '')
            env_private = os.environ.get('VAPID_PRIVATE_KEY', '')
            if env_public and env_private:
                app.config['VAPID_PUBLIC_KEY'] = env_public
                app.config['VAPID_PRIVATE_KEY'] = env_private
                app.config['VAPID_CLAIM_EMAIL'] = os.environ.get('VAPID_CLAIM_EMAIL', 'admin@dorm.local')
                logger.info("[VAPID] 从持久化文件恢复密钥到Flask配置成功")
                return True

        logger.warning("[VAPID] 密钥恢复失败：环境变量和持久化文件均无有效密钥")
    except Exception as e:
        logger.error(f"[VAPID] 密钥恢复异常: {e}")

    return False


@push_bp.route('/vapid-public-key', methods=['GET'])
def vapid_public_key():
    """获取VAPID公钥"""
    try:
        from flask import current_app
        public_key = current_app.config.get('VAPID_PUBLIC_KEY', '')
        if not public_key:
            # 尝试运行时恢复密钥（从环境变量或持久化文件）
            _recovered = _recover_vapid_keys(current_app)
            if _recovered:
                public_key = current_app.config.get('VAPID_PUBLIC_KEY', '')
        if not public_key:
            # 收集详细诊断信息，帮助前端和调试定位503原因
            vapid_available = os.environ.get('VAPID_AVAILABLE', 'true')
            vapid_private_key_set = bool(os.environ.get('VAPID_PRIVATE_KEY', ''))
            vapid_public_key_env = bool(os.environ.get('VAPID_PUBLIC_KEY', ''))
            app_private_key = bool(current_app.config.get('VAPID_PRIVATE_KEY', ''))
            app_public_key = bool(current_app.config.get('VAPID_PUBLIC_KEY', ''))

            # 检查 pywebpush 是否可导入
            pywebpush_available = False
            pywebpush_version = 'unknown'
            try:
                import pywebpush as _pw
                pywebpush_available = True
                pywebpush_version = getattr(_pw, '__version__', 'installed')
            except ImportError:
                pass

            # 检查 cryptography 是否可用
            crypto_available = False
            try:
                from cryptography.hazmat.primitives.asymmetric import ec  # noqa: F401
                crypto_available = True
            except ImportError:
                pass

            # 构建诊断信息
            diagnostics = {
                'vapid_available_env': vapid_available,
                'env_private_key_set': vapid_private_key_set,
                'env_public_key_set': vapid_public_key_env,
                'app_private_key_set': app_private_key,
                'app_public_key_set': app_public_key,
                'pywebpush_available': pywebpush_available,
                'pywebpush_version': pywebpush_version,
                'crypto_available': crypto_available,
            }

            # 确定具体原因
            if vapid_available == 'false':
                reason = 'VAPID密钥生成失败（pywebpush或cryptography不可用），推送功能不可用'
                suggestion = '请安装依赖：pip install pywebpush（或 pip install cryptography）'
            elif not pywebpush_available and not crypto_available:
                reason = 'pywebpush和cryptography均未安装，无法生成VAPID密钥'
                suggestion = '请安装依赖：pip install pywebpush'
            elif vapid_public_key_env and not app_public_key:
                reason = '环境变量中存在VAPID公钥但未正确加载到Flask配置'
                suggestion = '请检查config.py和main.py中的VAPID配置加载逻辑'
            else:
                reason = 'VAPID密钥未生成，推送功能不可用'
                suggestion = '请检查服务端日志中的[VAPID]标记信息'

            logger.warning(f"VAPID公钥为空，返回503: {reason}, diagnostics={diagnostics}")
            return jsonify({
                'success': False,
                'message': reason,
                'suggestion': suggestion,
                'diagnostics': diagnostics,
            }), 503
        return jsonify({'success': True, 'publicKey': public_key, 'currentDomain': request.host})
    except Exception as e:
        logger.error(f"获取VAPID公钥失败: {e}")
        return jsonify({'success': False, 'message': f'获取VAPID公钥失败: {str(e)}'}), 500


@push_bp.route('/test', methods=['POST'])
@login_required
def test_push():
    """测试推送通知，返回详细诊断信息"""
    from flask import current_app
    from utils.db_config import DatabaseConfig
    system_title = '宿舍管理系统'
    try:
        config = DatabaseConfig.load_config()
        system_title = config.get('SYSTEM_TITLE', '宿舍管理系统')
    except Exception:
        pass

    diagnostics = {
        'vapid_configured': False,
        'vapid_private_key_set': False,
        'vapid_public_key_set': False,
        'subscription_count': 0,
        'push_sent': False,
        'push_error': None,
    }

    # 检查VAPID配置
    private_key = current_app.config.get('VAPID_PRIVATE_KEY', '')
    public_key = current_app.config.get('VAPID_PUBLIC_KEY', '')
    diagnostics['vapid_private_key_set'] = bool(private_key)
    diagnostics['vapid_public_key_set'] = bool(public_key)
    diagnostics['vapid_configured'] = bool(private_key and public_key)

    # 检查订阅
    user_id = current_user.id
    sub_count = PushSubscription.query.filter_by(user_id=user_id).count()
    diagnostics['subscription_count'] = sub_count

    if not diagnostics['vapid_configured']:
        diagnostics['push_error'] = 'VAPID密钥未配置'
        return jsonify({'success': False, 'diagnostics': diagnostics}), 200

    if sub_count == 0:
        diagnostics['push_error'] = '当前用户没有推送订阅'
        return jsonify({'success': False, 'diagnostics': diagnostics}), 200

    # 尝试发送
    try:
        result = send_push_notification(
            user_id=user_id,
            title=f'{system_title} - 测试通知',
            body=f'这是一条来自{system_title}的测试推送通知，发送给用户 {current_user.name}。',
            url='/'
        )
        diagnostics['push_sent'] = result
        if not result:
            diagnostics['push_error'] = 'send_push_notification返回False（可能webpush调用失败，请检查服务器日志）'
    except Exception as e:
        diagnostics['push_error'] = str(e)

    return jsonify({'success': diagnostics['push_sent'], 'diagnostics': diagnostics}), 200