"""
PWA 路由测试脚本
验证 /manifest.json 和 /sw.js 路由是否正常工作
"""
import sys
import os
import json

# 确保项目根目录在 path 中
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_pwa_routes():
    """测试 PWA 相关路由"""
    from main import init_flask_app

    print("=" * 60)
    print("PWA 路由测试")
    print("=" * 60)

    # 初始化 Flask 应用（不启动服务器）
    print("\n[1] 初始化 Flask 应用...")
    try:
        app, _ = init_flask_app()
        print("    ✓ Flask 应用初始化成功")
    except Exception as e:
        print(f"    ✗ Flask 应用初始化失败: {e}")
        return False

    # 使用测试客户端
    client = app.test_client()

    # 测试 /manifest.json
    print("\n[2] 测试 /manifest.json 路由...")
    try:
        response = client.get('/manifest.json')
        print(f"    状态码: {response.status_code}")
        print(f"    Content-Type: {response.content_type}")

        if response.status_code != 200:
            print(f"    ✗ 请求失败，状态码: {response.status_code}")
            return False

        data = json.loads(response.data)
        print(f"    name: {data.get('name')}")
        print(f"    short_name: {data.get('short_name')}")
        print(f"    start_url: {data.get('start_url')}")
        print(f"    scope: {data.get('scope')}")
        print(f"    display: {data.get('display')}")
        print(f"    theme_color: {data.get('theme_color')}")
        print(f"    icons 数量: {len(data.get('icons', []))}")

        # 验证关键字段
        assert data['start_url'] == '/', f"start_url 应为 '/'，实际为 '{data['start_url']}'"
        assert data['scope'] == '/', f"scope 应为 '/'，实际为 '{data['scope']}'"
        assert data['display'] == 'standalone', f"display 应为 'standalone'"
        assert len(data['icons']) == 8, f"icons 应有 8 个，实际 {len(data['icons'])}"

        # 验证图标路径都是根相对路径
        for icon in data['icons']:
            assert icon['src'].startswith('/static/'), f"图标路径应为根相对路径，实际为 '{icon['src']}'"

        print("    ✓ /manifest.json 验证通过")
    except Exception as e:
        print(f"    ✗ /manifest.json 测试失败: {e}")
        return False

    # 测试 /sw.js
    print("\n[3] 测试 /sw.js 路由...")
    try:
        response = client.get('/sw.js')
        print(f"    状态码: {response.status_code}")
        print(f"    Content-Type: {response.content_type}")

        if response.status_code != 200:
            print(f"    ✗ 请求失败，状态码: {response.status_code}")
            return False

        content = response.data.decode('utf-8')
        print(f"    内容长度: {len(content)} 字节")
        print(f"    Cache-Control: {response.headers.get('Cache-Control', '未设置')}")

        # 验证 SW 关键内容
        assert 'install' in content, "SW 应包含 install 事件"
        assert 'activate' in content, "SW 应包含 activate 事件"
        assert 'skipWaiting' in content, "SW 应包含 skipWaiting"
        assert 'clients.claim' in content, "SW 应包含 clients.claim"

        print("    ✓ /sw.js 验证通过")
    except Exception as e:
        print(f"    ✗ /sw.js 测试失败: {e}")
        return False

    # 测试 PWA 图标文件是否存在
    print("\n[4] 测试 PWA 图标文件...")
    icon_sizes = [72, 96, 128, 144, 152, 192, 384, 512]
    all_icons_ok = True
    for size in icon_sizes:
        icon_path = f'static/images/pwa/icon-{size}x{size}.png'
        full_path = os.path.join(os.path.dirname(__file__), icon_path)
        if os.path.exists(full_path):
            file_size = os.path.getsize(full_path)
            print(f"    ✓ {icon_path} ({file_size} bytes)")
        else:
            print(f"    ✗ {icon_path} 不存在")
            all_icons_ok = False

    if not all_icons_ok:
        return False

    # 测试模板中是否包含 PWA 标签
    print("\n[5] 测试模板 PWA 标签...")
    try:
        static_html_path = os.path.join(os.path.dirname(__file__), 'templates', 'static.html')
        with open(static_html_path, 'r', encoding='utf-8') as f:
            static_content = f.read()

        checks = [
            ('manifest link', 'rel="manifest"'),
            ('theme-color meta', 'name="theme-color"'),
            ('apple-mobile-web-app-capable', 'name="apple-mobile-web-app-capable"'),
            ('apple-touch-icon', 'rel="apple-touch-icon"'),
        ]
        for name, pattern in checks:
            if pattern in static_content:
                print(f"    ✓ {name} 存在")
            else:
                print(f"    ✗ {name} 缺失")
                return False

        # 检查 footer.html 中的 pwa-register.js
        footer_path = os.path.join(os.path.dirname(__file__), 'templates', 'footer.html')
        with open(footer_path, 'r', encoding='utf-8') as f:
            footer_content = f.read()

        if 'pwa-register.js' in footer_content:
            print(f"    ✓ footer 中 pwa-register.js 引用存在")
        else:
            print(f"    ✗ footer 中 pwa-register.js 引用缺失")
            return False

    except Exception as e:
        print(f"    ✗ 模板测试失败: {e}")
        return False

    print("\n" + "=" * 60)
    print("所有 PWA 测试通过！ ✓")
    print("=" * 60)
    return True


if __name__ == '__main__':
    success = test_pwa_routes()
    sys.exit(0 if success else 1)