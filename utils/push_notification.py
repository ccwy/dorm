"""
Web推送通知工具模块

提供推送通知的发送功能，使用pywebpush库实现。
推送通知是辅助功能，发送失败不影响主业务流程。
"""
import logging
import json

logger = logging.getLogger(__name__)


def _get_vapid_config():
    """获取VAPID配置，未配置时返回None"""
    try:
        from flask import current_app
        private_key = current_app.config.get('VAPID_PRIVATE_KEY', '')
        public_key = current_app.config.get('VAPID_PUBLIC_KEY', '')
        claim_email = current_app.config.get('VAPID_CLAIM_EMAIL', 'admin@dorm.local')
        if not private_key or not public_key:
            return None
        return {
            'private_key': private_key,
            'public_key': public_key,
            'claim_email': claim_email,
            'claim_domain': current_app.config.get('VAPID_CLAIM_DOMAIN', ''),
        }
    except Exception:
        return None


def send_push_notification(user_id, title, body, url=None):
    """
    向指定用户发送推送通知。

    推送通知是辅助功能，发送失败仅记录日志，不影响主业务流程。
    同一用户可能有多个订阅（不同设备/浏览器），会逐一发送。
    发送失败的订阅（410 Gone等）会自动清理。

    Args:
        user_id: 目标用户ID
        title: 通知标题
        body: 通知内容
        url: 点击通知后打开的URL（可选）

    Returns:
        bool: 是否至少成功发送给一个订阅
    """
    try:
        vapid_config = _get_vapid_config()
        if not vapid_config:
            logger.warning("VAPID密钥未配置，跳过推送通知发送")
            return False

        from models.push.push_subscription import PushSubscription
        from utils.db import db

        # 查询用户所有活跃订阅
        subscriptions = PushSubscription.query.filter_by(user_id=user_id).all()
        if not subscriptions:
            logger.debug(f"用户 {user_id} 没有推送订阅，跳过发送")
            return False

        # 构建推送数据
        payload = json.dumps({
            'title': title,
            'body': body,
            'url': url or '/',
        })

        # VAPID认证信息
        vapid_claims = {
            'sub': f'mailto:{vapid_config["claim_email"]}',
        }
        # aud域名将在循环内根据每个订阅的endpoint动态设置

        success_count = 0
        failed_subscriptions = []

        for sub in subscriptions:
            try:
                subscription_info = {
                    'endpoint': sub.endpoint,
                    'keys': {
                        'p256dh': sub.p256dh,
                        'auth': sub.auth,
                    }
                }

                from pywebpush import webpush
                from urllib.parse import urlparse

                # 动态设置aud：从订阅endpoint提取推送服务origin
                if vapid_config.get('claim_domain'):
                    vapid_claims['aud'] = f'https://{vapid_config["claim_domain"]}'
                else:
                    parsed = urlparse(sub.endpoint)
                    vapid_claims['aud'] = f'{parsed.scheme}://{parsed.netloc}'

                # 诊断日志：记录VAPID私钥格式和endpoint域名
                private_key = vapid_config['private_key']
                logger.info(f"[Push诊断] VAPID私钥长度={len(private_key)}, 前20字符={private_key[:20]}")
                try:
                    endpoint_domain = urlparse(sub.endpoint).netloc
                    logger.info(f"[Push诊断] endpoint域名={endpoint_domain}, aud={vapid_claims.get('aud')}")
                except Exception:
                    logger.info(f"[Push诊断] endpoint解析失败: {sub.endpoint[:50]}")
                # PEM格式私钥需要用Vapid.from_pem()构造实例，from_string()无法正确解析PEM
                vapid_private_key = private_key
                if '-----BEGIN' in private_key:
                    from py_vapid import Vapid
                    vapid_private_key = Vapid.from_pem(private_key.encode('utf-8'))
                webpush(
                    subscription_info=subscription_info,
                    data=payload,
                    vapid_private_key=vapid_private_key,
                    vapid_claims=vapid_claims,
                    ttl=86400,  # 消息有效期24小时
                )
                success_count += 1
                logger.info(f"推送通知发送成功: 用户={user_id}, 端点={sub.endpoint[:50]}")

            except Exception as e:
                error_str = str(e)
                # 410 Gone 或 404 表示订阅已失效，需要清理
                if '410' in error_str or '404' in error_str or 'ExpiredSubscription' in error_str:
                    logger.info(f"推送订阅已失效，将删除: 用户={user_id}, 端点={sub.endpoint[:50]}")
                    failed_subscriptions.append(sub)
                else:
                    logger.warning(f"推送通知发送失败: 用户={user_id}, 端点={sub.endpoint[:50]}, 错误={error_str}")

        # 清理失效的订阅
        if failed_subscriptions:
            try:
                for sub in failed_subscriptions:
                    db.session.delete(sub)
                db.session.commit()
                logger.info(f"已清理 {len(failed_subscriptions)} 个失效推送订阅")
            except Exception as cleanup_err:
                logger.error(f"清理失效推送订阅失败: {cleanup_err}")
                db.session.rollback()

        return success_count > 0

    except Exception as e:
        logger.error(f"发送推送通知异常: {e}")
        return False


def send_push_notification_to_users(user_ids, title, body, url=None):
    """
    向多个用户发送推送通知。

    Args:
        user_ids: 目标用户ID列表
        title: 通知标题
        body: 通知内容
        url: 点击通知后打开的URL（可选）
    """
    for uid in user_ids:
        try:
            send_push_notification(uid, title, body, url)
        except Exception as e:
            logger.error(f"向用户 {uid} 发送推送通知失败: {e}")