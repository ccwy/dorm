#!/usr/bin/env python3
"""
从 static/favicon.svg 或 static/favicon.ico 自动生成 PWA 所需的各种尺寸图标。

生成的图标文件放置在本脚本所在目录 (static/images/pwa/)，
与 manifest.json 中声明的路径一致。

使用方法：
    python static/images/pwa/generate_pwa_icons.py

依赖：
    必需：Pillow (pip install Pillow)
    可选：cairosvg (pip install cairosvg) — 用于从 SVG 源文件生成高清图标

图标源优先级：
    1. favicon.svg（矢量图，需要 cairosvg）— 推荐，可无损缩放
    2. favicon.ico（位图）— 回退方案，从最大帧缩放

参考：android/generate_icons.py（Android Adaptive Icon 生成脚本）
"""
import os
import sys

try:
    from PIL import Image
except ImportError:
    print("Pillow 未安装，跳过 PWA 图标生成")
    print("请安装依赖：pip install Pillow")
    sys.exit(0)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.normpath(os.path.join(SCRIPT_DIR, '..', '..'))
OUTPUT_DIR = SCRIPT_DIR

# 优先使用 SVG，回退到 ICO
SVG_PATH = os.path.join(STATIC_DIR, 'favicon.svg')
ICO_PATH = os.path.join(STATIC_DIR, 'favicon.ico')

# PWA 所需的图标尺寸（与 manifest.json 中的 icons 列表一致）
ICON_SIZES = [72, 96, 128, 144, 152, 192, 384, 512]


def load_source_image():
    """加载源图标，优先 SVG，回退 ICO。

    Returns:
        PIL.Image.Image: 加载后的 RGBA 图像

    Exits:
        如果没有找到任何源文件，打印提示后退出
    """
    # 尝试从 SVG 加载（需要 cairosvg）
    if os.path.exists(SVG_PATH):
        try:
            import cairosvg
            from io import BytesIO
            # 将 SVG 转为 PNG 字节流（以最大尺寸 512px 渲染），再用 Pillow 打开
            png_data = cairosvg.svg2png(url=SVG_PATH, output_width=512, output_height=512)
            img = Image.open(BytesIO(png_data)).convert('RGBA')
            print(f"源图标: favicon.svg ({img.size[0]}x{img.size[1]}px)")
            return img
        except ImportError:
            print("cairosvg 未安装，无法从 SVG 生成高清图标，将回退到 favicon.ico")
            print("如需 SVG 支持，请安装：pip install cairosvg")
        except Exception as e:
            print(f"SVG 加载失败: {e}，将回退到 favicon.ico")

    # 回退到 ICO
    if os.path.exists(ICO_PATH):
        try:
            img = Image.open(ICO_PATH).convert('RGBA')
            print(f"源图标: favicon.ico ({img.size[0]}x{img.size[1]}px)")
            if img.size[0] < 256:
                print(f"  注意: 源图标尺寸较小 ({img.size[0]}px)，放大后可能模糊，建议使用 SVG 源文件")
            return img
        except Exception as e:
            print(f"ICO 加载失败: {e}")
            sys.exit(1)

    # 两个源文件都不存在
    print(f"未找到源图标文件，已尝试以下路径：")
    print(f"  1. {SVG_PATH}")
    print(f"  2. {ICO_PATH}")
    print("请确保项目中存在 favicon.svg 或 favicon.ico 文件")
    sys.exit(1)


def main():
    img = load_source_image()

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    generated = 0
    failed = 0

    for size in ICON_SIZES:
        try:
            resized = img.resize((size, size), Image.LANCZOS)
            output = os.path.join(OUTPUT_DIR, f'icon-{size}x{size}.png')
            resized.save(output, 'PNG')
            print(f"  icon-{size}x{size}.png")
            generated += 1
        except Exception as e:
            print(f"  icon-{size}x{size}.png — 生成失败: {e}")
            failed += 1

    if failed == 0:
        print(f"PWA 图标生成完成！共生成 {generated} 个图标")
    else:
        print(f"PWA 图标生成完成（{generated} 成功, {failed} 失败）")
        sys.exit(1)


if __name__ == '__main__':
    main()