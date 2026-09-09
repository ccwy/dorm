# -*- coding: utf-8 -*-
"""轻量级内存速率限制器 - 基于IP的滑动窗口实现

不依赖Flask-Limiter，使用threading.Lock保证线程安全，
自动清理过期记录防止内存泄漏。
"""
import logging
import threading
import time
from collections import defaultdict

logger = logging.getLogger(__name__)


class SlidingWindowRateLimiter:
    """基于IP的滑动窗口速率限制器

    使用滑动窗口算法记录每个IP的请求时间戳，
    支持独立的多组限制策略（如普通请求和认证失败请求）。

    Attributes:
        limits: dict, 限制策略配置 {name: (max_requests, window_seconds)}
        _records: dict, 存储各策略的请求记录 {name: {ip: [timestamps]}}
        _locks: dict, 各策略的线程锁 {name: Lock}
        _cleanup_interval: int, 清理间隔（秒）
        _last_cleanup: float, 上次清理时间戳
        _global_lock: Lock, 清理操作的全局锁
    """

    def __init__(self, limits=None, cleanup_interval=300):
        """初始化速率限制器

        Args:
            limits: dict, 限制策略 {name: (max_requests, window_seconds)}
                    默认包含 'default' (60次/分) 和 'auth_failure' (10次/分)
            cleanup_interval: int, 自动清理过期记录的间隔秒数，默认300秒
        """
        if limits is None:
            limits = {
                'default': (60, 60),       # 每IP每分钟60次请求
                'auth_failure': (10, 60),  # 每IP每分钟10次认证失败
            }
        self.limits = limits
        self._records = {name: defaultdict(list) for name in limits}
        self._locks = {name: threading.Lock() for name in limits}
        self._cleanup_interval = cleanup_interval
        self._last_cleanup = time.time()
        self._global_lock = threading.Lock()

    def is_rate_limited(self, ip, limit_name='default'):
        """检查指定IP是否触发速率限制

        Args:
            ip: str, 客户端IP地址
            limit_name: str, 限制策略名称，默认为 'default'

        Returns:
            bool: True表示已触发速率限制，False表示允许请求
        """
        if limit_name not in self.limits:
            logger.warning("未知的速率限制策略: %s", limit_name)
            return False

        max_requests, window_seconds = self.limits[limit_name]
        now = time.time()
        cutoff = now - window_seconds

        with self._locks[limit_name]:
            timestamps = self._records[limit_name][ip]
            # 移除窗口外的旧记录
            self._records[limit_name][ip] = [t for t in timestamps if t > cutoff]
            timestamps = self._records[limit_name][ip]

            if len(timestamps) >= max_requests:
                logger.warning(
                    "速率限制触发: IP=%s, 策略=%s, 已请求%d次/%ds, 限制%d次/%ds",
                    ip, limit_name, len(timestamps), window_seconds,
                    max_requests, window_seconds
                )
                return True

            # 记录本次请求时间戳
            timestamps.append(now)
            return False

    def record_auth_failure(self, ip):
        """记录认证失败事件并检查是否触发更严格的速率限制

        Args:
            ip: str, 客户端IP地址

        Returns:
            bool: True表示已触发认证失败速率限制，False表示允许继续
        """
        return self.is_rate_limited(ip, limit_name='auth_failure')

    def _cleanup_expired(self):
        """清理所有策略中过期的记录，防止内存泄漏

        仅在距上次清理超过cleanup_interval秒后执行，
        使用全局锁保证清理操作不会并发执行。
        """
        with self._global_lock:
            now = time.time()
            if now - self._last_cleanup < self._cleanup_interval:
                return

            for name, (max_requests, window_seconds) in self.limits.items():
                cutoff = now - window_seconds
                with self._locks[name]:
                    ips_to_remove = []
                    for ip, timestamps in self._records[name].items():
                        # 过滤掉过期时间戳
                        filtered = [t for t in timestamps if t > cutoff]
                        if filtered:
                            self._records[name][ip] = filtered
                        else:
                            ips_to_remove.append(ip)
                    # 移除没有记录的IP
                    for ip in ips_to_remove:
                        del self._records[name][ip]

            self._last_cleanup = now
            logger.debug("速率限制器过期记录清理完成")

    def check_and_cleanup(self, ip, limit_name='default'):
        """检查速率限制并顺便触发过期记录清理

        Args:
            ip: str, 客户端IP地址
            limit_name: str, 限制策略名称

        Returns:
            bool: True表示已触发速率限制，False表示允许请求
        """
        result = self.is_rate_limited(ip, limit_name)
        self._cleanup_expired()
        return result

    def get_stats(self):
        """获取当前速率限制器状态统计（用于调试）

        Returns:
            dict: 各策略的活跃IP数和总请求数
        """
        stats = {}
        for name in self.limits:
            with self._locks[name]:
                stats[name] = {
                    'active_ips': len(self._records[name]),
                    'total_requests': sum(len(ts) for ts in self._records[name].values())
                }
        return stats


# 全局速率限制器实例
agent_limiter = SlidingWindowRateLimiter(
    limits={
        'default': (60, 60),       # Agent API: 每IP每分钟60次请求
        'auth_failure': (10, 60),  # 认证失败: 每IP每分钟10次
    },
    cleanup_interval=300
)