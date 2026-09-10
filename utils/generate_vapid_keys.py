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


def _get_vapid_key_path():
    """获取VAPID密钥持久化文件路径

    根据运行环境返回不同的存储路径：
    - Docker环境: /data/vapid_keys.json（持久化数据卷）
    - Android环境: APP_DATA_DIR/vapid_keys.json
    - 打包环境(frozen): 可执行文件目录/data/vapid_keys.json
    - 开发环境: 项目根目录/data/vapid_keys.json

    Returns:
        str: VAPID密钥文件的绝对路径
    """
    import os
    import sys

    # Docker环境 - 使用持久化数据卷
    if os.environ.get('DOCKER_ENV', 'false').lower() == 'true':
        data_dir = '/data'
    # Android环境
    elif os.environ.get('ANDROID_ENV', 'false').lower() == 'true':
        data_dir = os.environ.get('APP_DATA_DIR', os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
    # 打包环境
    elif getattr(sys, 'frozen', False):
        data_dir = os.path.join(os.path.dirname(sys.executable), 'data')
    # 开发环境
    else:
        data_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'data'))

    os.makedirs(data_dir, exist_ok=True)
    return os.path.join(data_dir, 'vapid_keys.json')


def ensure_vapid_keys():
    """确保VAPID密钥已配置，未配置则自动生成并持久化。

    此函数可安全地在每次启动时调用：
    - 如果环境变量已配置VAPID_PRIVATE_KEY，直接返回（不覆盖）
    - 如果持久化文件存在，从中加载并设置环境变量
    - 如果都没有，自动生成新密钥对并持久化

    Returns:
        bool: True表示密钥已就绪（已存在或新生成），False表示生成失败
    """
    import os
    import json

    # 1. 检查环境变量是否已配置
    if os.environ.get('VAPID_PRIVATE_KEY') and os.environ.get('VAPID_PUBLIC_KEY'):
        print("[VAPID] 密钥已通过环境变量配置，跳过自动生成")
        return True

    # 2. 检查持久化文件
    key_path = _get_vapid_key_path()
    if os.path.exists(key_path):
        try:
            with open(key_path, 'r', encoding='utf-8') as f:
                keys = json.load(f)
            private_key = keys.get('private_key', '')
            public_key = keys.get('public_key', '')
            if private_key and public_key:
                os.environ['VAPID_PRIVATE_KEY'] = private_key
                os.environ['VAPID_PUBLIC_KEY'] = public_key
                if keys.get('claim_email'):
                    os.environ['VAPID_CLAIM_EMAIL'] = keys['claim_email']
                print(f"[VAPID] 从持久化文件加载密钥: {key_path}")
                return True
        except Exception as e:
            print(f"[VAPID] 读取持久化密钥失败: {e}，将重新生成")

    # 3. 自动生成新密钥对
    try:
        from pywebpush import generate_vapid_key_pair
    except ImportError:
        print("[VAPID] pywebpush 未安装，跳过VAPID密钥自动生成")
        print("[VAPID] 推送通知功能将不可用，如需启用请安装：pip install pywebpush")
        return False

    try:
        key_pair = generate_vapid_key_pair()
        private_key = key_pair.get('private_key', '')
        public_key = key_pair.get('public_key', '')

        if not private_key or not public_key:
            print("[VAPID] 密钥生成失败：返回值为空")
            return False

        # 设置环境变量（必须在config.py导入后生效，此处设置供后续读取）
        os.environ['VAPID_PRIVATE_KEY'] = private_key
        os.environ['VAPID_PUBLIC_KEY'] = public_key
        claim_email = os.environ.get('VAPID_CLAIM_EMAIL', 'admin@dorm.local')
        os.environ['VAPID_CLAIM_EMAIL'] = claim_email

        # 持久化到文件
        try:
            keys_data = {
                'private_key': private_key,
                'public_key': public_key,
                'claim_email': claim_email
            }
            with open(key_path, 'w', encoding='utf-8') as f:
                json.dump(keys_data, f, indent=2, ensure_ascii=False)
            print(f"[VAPID] 新密钥对已生成并持久化到: {key_path}")
        except Exception as e:
            print(f"[VAPID] 密钥持久化失败: {e}（密钥已设置到环境变量，但重启后需重新生成）")

        print("[VAPID] 注意：新生成的密钥会使已有的推送订阅失效，用户需重新订阅")
        return True

    except Exception as e:
        print(f"[VAPID] 密钥生成异常: {e}")
        return False


if __name__ == '__main__':
    main()