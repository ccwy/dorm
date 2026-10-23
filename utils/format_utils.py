"""通用格式化工具函数"""


def format_stay_days(days, convert_enabled=None):
    """格式化住宿天数显示。

    当系统配置 STAY_DAYS_FORMAT_CONVERT_ENABLED 开启时，
    将天数转换为年月日格式（如 2400天 -> 6年7个月）。
    关闭时返回原始天数格式（如 2400天）。

    Args:
        days: 天数（整数）
        convert_enabled: 是否开启转换。为None时自动读取系统配置。
    """
    if convert_enabled is None:
        try:
            from models.system_config.system_config import SystemConfig
            convert_enabled = SystemConfig.get_config_value('STAY_DAYS_FORMAT_CONVERT_ENABLED', False)
        except Exception:
            convert_enabled = False

    if not convert_enabled:
        return f'{days}天'

    if not days or days <= 0:
        return '0天'

    years = days // 365
    remaining = days % 365
    months = remaining // 30
    day_part = remaining % 30

    parts = []
    if years:
        parts.append(f'{years}年')
    if months:
        parts.append(f'{months}个月')
    if day_part:
        parts.append(f'{day_part}天')
    return ''.join(parts) if parts else '0天'