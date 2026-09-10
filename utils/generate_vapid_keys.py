#!/usr/bin/env python3
"""
VAPID 密钥对生成脚本

用于生成 Web Push 推送通知所需的 VAPID 密钥对。
生成的密钥对需要配置到 config.py 或 .env 文件中，推送功能才能正常工作。

使用方法：
    python utils/generate_vapid_keys.py

输出格式为环境变量格式，可直接复制到 .env 文件或 config.py 中：
    VAPID_PRIVATE_KEY=xxxxx
    VAPID_PUBLIC_KEY=xxxxx
    VAPID_CLAIM_EMAIL=mailto:your-email@example.com

依赖：
    pip install pywebpush

说明：
    - VAPID (Voluntary Application Server Identification) 用于标识推送通知的发送方
    - 私钥必须保密，仅在服务端使用
    - 公钥会分发给客户端浏览器，用于订阅推送
    - 如果未配置 VAPID 密钥，推送功能将静默跳过（不影响主业务）
    - 每次运行会生成新的密钥对，旧密钥对应的订阅将失效
"""
import sys


def main():
    try:
        from pywebpush import generate_vapid_key_pair
    except ImportError:
        print("错误：pywebpush 未安装")
        print("请先安装依赖：pip install pywebpush")
        sys.exit(1)

    key_pair = generate_vapid_key_pair()

    # generate_vapid_key_pair() 返回字典，包含 private_key 和 public_key
    private_key = key_pair.get('private_key', '')
    public_key = key_pair.get('public_key', '')

    if not private_key or not public_key:
        print("错误：密钥生成失败")
        sys.exit(1)

    print("=" * 60)
    print("VAPID 密钥对已生成")
    print("=" * 60)
    print()
    print("请将以下配置添加到 .env 文件或 config.py 中：")
    print()
    print(f"VAPID_PRIVATE_KEY={private_key}")
    print(f"VAPID_PUBLIC_KEY={public_key}")
    print("VAPID_CLAIM_EMAIL=mailto:your-email@example.com")
    print()
    print("-" * 60)
    print("注意事项：")
    print("  1. 私钥 (VAPID_PRIVATE_KEY) 必须保密，不要提交到版本控制")
    print("  2. 公钥 (VAPID_PUBLIC_KEY) 可安全分发给客户端")
    print("  3. VAPID_CLAIM_EMAIL 替换为你的实际邮箱")
    print("  4. 更换密钥后，已有的推送订阅将失效，用户需重新订阅")
    print("=" * 60)


if __name__ == '__main__':
    main()