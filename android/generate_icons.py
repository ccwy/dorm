#!/usr/bin/env python3
"""
从 static/favicon.ico 自动生成 Android Adaptive Icon 前景图。

在 Gradle preBuild 阶段自动调用，确保 Android 图标与 Web 端 favicon 保持同步。
需要 Pillow: pip install Pillow
"""
import os
import sys

try:
    from PIL import Image
except ImportError:
    print("Pillow not installed, skipping icon generation")
    print("Install with: pip install Pillow")
    sys.exit(0)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
FAVICON_PATH = os.path.join(SCRIPT_DIR, '..', 'static', 'favicon.ico')
RES_DIR = os.path.join(SCRIPT_DIR, 'app', 'src', 'main', 'res')

# Adaptive Icon 前景尺寸 (108dp 在各密度的像素值)
FOREGROUND_SIZES = {
    'drawable-mdpi': 108,
    'drawable-hdpi': 162,
    'drawable-xhdpi': 216,
    'drawable-xxhdpi': 324,
    'drawable-xxxhdpi': 432,
}


def main():
    if not os.path.exists(FAVICON_PATH):
        print(f"favicon.ico not found: {FAVICON_PATH}")
        sys.exit(0)

    # 打开 ICO，Pillow 默认打开最大帧
    img = Image.open(FAVICON_PATH).convert('RGBA')

    print(f"Source icon: {img.size[0]}x{img.size[1]}px")

    for density, size_px in FOREGROUND_SIZES.items():
        target_dir = os.path.join(RES_DIR, density)
        os.makedirs(target_dir, exist_ok=True)

        # 缩放到目标尺寸
        resized = img.resize((size_px, size_px), Image.LANCZOS)

        output = os.path.join(target_dir, 'ic_launcher_foreground.png')
        resized.save(output, 'PNG')
        print(f"  {density}/ic_launcher_foreground.png ({size_px}px)")

    print("Android icons generated from favicon.ico!")


if __name__ == '__main__':
    main()