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
    pip install pywebpush（或直接使用 cryptography 库）

说明：
    - VAPID (Voluntary Application Server Identification) 用于标识推送通知的发送方
    - 私钥必须保密，仅在服务端使用
    - 公钥会分发给客户端浏览器，用于订阅推送
    - 如果未配置 VAPID 密钥，推送功能将静默跳过（不影响主业务）
    - 每次运行会生成新的密钥对，旧密钥对应的订阅将失效
    - 兼容 pywebpush 2.x（Vapid 类，优先）和 1.x（generate_vapid_key_pair，回退）
    - 如果 pywebpush 不可用，回退到 cryptography 库直接生成
"""
import sys
import base64


def _generate_keys_cryptography():
    """使用 cryptography 库直接生成 VAPID 密钥对（不依赖 pywebpush）。

    Returns:
        dict: {'private_key': str(PEM), 'public_key': str(base64url)} 或 None
    """
    try:
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.hazmat.primitives import serialization

        # 生成 P-256 (SECP256R1) 密钥对
        private_key = ec.generate_private_key(ec.SECP256R1())

        # 私钥导出为 PEM 格式
        private_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        ).decode('utf-8')

        # 公钥导出为未压缩点格式，再 base64url 编码（浏览器推送所需的格式）
        public_key_raw = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.X962,
            format=serialization.PublicFormat.UncompressedPoint
        )
        public_key_b64 = base64.urlsafe_b64encode(public_key_raw).decode('utf-8').rstrip('=')

        return {
            'private_key': private_pem,
            'public_key': public_key_b64
        }
    except Exception as e:
        print(f"[VAPID] cryptography 库生成密钥失败: {e}")
        return None


def _generate_keys_pywebpush_v1():
    """使用 pywebpush 1.x 的 generate_vapid_key_pair() 生成密钥。

    Returns:
        dict: {'private_key': str, 'public_key': str} 或 None
    """
    try:
        from pywebpush import generate_vapid_key_pair
        key_pair = generate_vapid_key_pair()
        private_key = key_pair.get('private_key', '')
        public_key = key_pair.get('public_key', '')
        if private_key and public_key:
            return {
                'private_key': private_key,
                'public_key': public_key
            }
        print(f"[VAPID] pywebpush v1 generate_vapid_key_pair() 返回值为空: {key_pair}")
        return None
    except ImportError:
        return None
    except Exception as e:
        print(f"[VAPID] pywebpush v1 generate_vapid_key_pair() 失败: {e}")
        return None


def _generate_keys_pywebpush_v2():
    """使用 pywebpush 2.x 的 Vapid 类生成密钥。

    Returns:
        dict: {'private_key': str(PEM), 'public_key': str(base64url)} 或 None
    """
    try:
        from pywebpush import Vapid
        v = Vapid()
        v.generate_keys()

        # 获取私钥 PEM
        private_pem_result = v.private_pem()
        if isinstance(private_pem_result, bytes):
            private_pem = private_pem_result.decode('utf-8')
        elif isinstance(private_pem_result, str):
            private_pem = private_pem_result
        else:
            private_pem = private_pem_result  # 可能已经是 str

        # 获取公钥并转换为浏览器所需的 base64url 格式
        pub_key_obj = v.public_key
        if pub_key_obj is not None:
            from cryptography.hazmat.primitives import serialization
            public_key_raw = pub_key_obj.public_bytes(
                encoding=serialization.Encoding.X962,
                format=serialization.PublicFormat.UncompressedPoint
            )
            public_key_b64 = base64.urlsafe_b64encode(public_key_raw).decode('utf-8').rstrip('=')
        else:
            print("[VAPID] pywebpush v2 Vapid.public_key 为 None")
            return None

        if private_pem and public_key_b64:
            return {
                'private_key': private_pem,
                'public_key': public_key_b64
            }
        print(f"[VAPID] pywebpush v2 Vapid 生成密钥为空")
        return None
    except ImportError:
        return None
    except Exception as e:
        print(f"[VAPID] pywebpush v2 Vapid 生成密钥失败: {e}")
        return None


def generate_vapid_keypair():
    """生成 VAPID 密钥对，按优先级尝试多种方法。

    尝试顺序（优先使用cryptography直接生成，避免pywebpush内部使用ec.SECP256R1类引用触发CryptographyDeprecationWarning）：
    1. cryptography 库直接生成（避免CryptographyDeprecationWarning）
    2. pywebpush 2.x: Vapid 类（当前主流版本2.5.0+）
    3. pywebpush 1.x: generate_vapid_key_pair()（旧版本兼容）

    Returns:
        dict: {'private_key': str, 'public_key': str} 或 None
    """
    # 方法1: cryptography 直接生成（优先，避免pywebpush触发的CryptographyDeprecationWarning）
    result = _generate_keys_cryptography()
    if result:
        print("[VAPID] 使用 cryptography 库直接生成密钥")
        return result

    # 方法2: pywebpush 2.x（当前主流版本）
    result = _generate_keys_pywebpush_v2()
    if result:
        print("[VAPID] 使用 pywebpush v2 (Vapid 类) 生成密钥")
        return result

    # 方法3: pywebpush 1.x（旧版本兼容）
    result = _generate_keys_pywebpush_v1()
    if result:
        print("[VAPID] 使用 pywebpush v1 (generate_vapid_key_pair) 生成密钥")
        return result

    print("[VAPID] 所有密钥生成方法均失败，请安装 pywebpush 或 cryptography")
    return None


def main():
    key_pair = generate_vapid_keypair()
    if not key_pair:
        print("错误：密钥生成失败")
        print("请安装依赖：pip install pywebpush")
        sys.exit(1)

    private_key = key_pair.get('private_key', '')
    public_key = key_pair.get('public_key', '')

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

    密钥生成按优先级尝试多种方法：
    1. cryptography 库直接生成（避免CryptographyDeprecationWarning）
    2. pywebpush 2.x: Vapid 类（当前主流版本）
    3. pywebpush 1.x: generate_vapid_key_pair()（旧版本兼容）

    Returns:
        bool: True表示密钥已就绪（已存在或新生成），False表示生成失败
    """
    import os
    import json

    # 确保VAPID_AVAILABLE默认为true（仅在明确失败时设为false）
    os.environ.setdefault('VAPID_AVAILABLE', 'true')

    # 1. 检查环境变量是否已配置
    if os.environ.get('VAPID_PRIVATE_KEY') and os.environ.get('VAPID_PUBLIC_KEY'):
        print("[VAPID] 密钥已通过环境变量配置，跳过自动生成")
        os.environ['VAPID_AVAILABLE'] = 'true'
        return True

    # 2. 检查持久化文件
    key_path = _get_vapid_key_path()
    if os.path.exists(key_path):
        try:
            file_size = os.path.getsize(key_path)
            print(f"[VAPID] 持久化文件存在: {key_path} (大小: {file_size} 字节)")
            with open(key_path, 'r', encoding='utf-8') as f:
                keys = json.load(f)
            private_key = keys.get('private_key', '')
            public_key = keys.get('public_key', '')
            if private_key and public_key:
                # 脱敏日志：仅显示密钥前8位
                pk_preview = private_key[:8] + '...' if len(private_key) > 8 else '***'
                pub_preview = public_key[:8] + '...' if len(public_key) > 8 else '***'
                print(f"[VAPID] 持久化文件加载成功: private_key={pk_preview}, public_key={pub_preview}")
                os.environ['VAPID_PRIVATE_KEY'] = private_key
                os.environ['VAPID_PUBLIC_KEY'] = public_key
                if keys.get('claim_email'):
                    os.environ['VAPID_CLAIM_EMAIL'] = keys['claim_email']
                print(f"[VAPID] 从持久化文件加载密钥: {key_path}")
                os.environ['VAPID_AVAILABLE'] = 'true'
                return True
            else:
                print(f"[VAPID] 持久化文件中密钥为空，将重新生成: {key_path}")
                print(f"[VAPID] 文件内容: private_key={'有值' if private_key else '空'}, public_key={'有值' if public_key else '空'}")
        except json.JSONDecodeError as e:
            print(f"[VAPID] 持久化文件JSON解析失败: {e}，文件路径: {key_path}，将重新生成")
        except Exception as e:
            print(f"[VAPID] 读取持久化密钥失败: {type(e).__name__}: {e}，文件路径: {key_path}，将重新生成")

    # 3. 自动生成新密钥对（使用兼容多版本的生成函数）
    key_pair = generate_vapid_keypair()

    if not key_pair:
        print("[VAPID] 密钥生成失败，推送通知功能将不可用")
        print("[VAPID] 请安装依赖：pip install pywebpush（或 pip install cryptography）")
        os.environ['VAPID_AVAILABLE'] = 'false'
        return False

    private_key = key_pair.get('private_key', '')
    public_key = key_pair.get('public_key', '')

    if not private_key or not public_key:
        print("[VAPID] 密钥生成失败：返回值为空")
        os.environ['VAPID_AVAILABLE'] = 'false'
        return False

    # 设置环境变量（必须在config.py导入后生效，此处设置供后续读取）
    os.environ['VAPID_PRIVATE_KEY'] = private_key
    os.environ['VAPID_PUBLIC_KEY'] = public_key
    claim_email = os.environ.get('VAPID_CLAIM_EMAIL', 'admin@dorm.local')
    os.environ['VAPID_CLAIM_EMAIL'] = claim_email
    os.environ['VAPID_AVAILABLE'] = 'true'

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


if __name__ == '__main__':
    main()