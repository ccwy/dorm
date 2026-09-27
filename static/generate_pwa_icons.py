"""
PWA 图标生成脚本
使用 Pillow 从 favicon.svg 的设计重新绘制多尺寸 PNG 图标
依赖: pip install Pillow
"""
import os
import math
from PIL import Image, ImageDraw


def draw_icon(size):
    """根据 favicon.svg 的设计绘制指定尺寸的图标"""
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # 比例系数（基于64x64原始SVG）
    s = size / 64.0

    # 圆角背景 (#165DFF)
    rx = int(8 * s)
    draw.rounded_rectangle([0, 0, size - 1, size - 1], radius=rx, fill=(22, 93, 255))

    # 建筑主体 (白色圆角矩形) x:16-48, y:20-44, rx:2
    x1, y1, x2, y2 = int(16*s), int(20*s), int(48*s), int(44*s)
    draw.rounded_rectangle([x1, y1, x2, y2], radius=max(1, int(2*s)), fill=(255, 255, 255))

    # 底座 (白色) x:24-40, y:44-52, rx:1
    bx1, by1, bx2, by2 = int(24*s), int(44*s), int(40*s), int(52*s)
    draw.rounded_rectangle([bx1, by1, bx2, by2], radius=max(1, int(1*s)), fill=(255, 255, 255))

    # 窗户和门 (#165DFF 蓝色)
    blue = (22, 93, 255)

    # 左窗 x:20-28, y:28-40
    draw.rectangle([int(20*s), int(28*s), int(28*s), int(40*s)], fill=blue)
    # 右窗 x:36-44, y:28-40
    draw.rectangle([int(36*s), int(28*s), int(44*s), int(40*s)], fill=blue)
    # 门 x:28-36, y:36-40
    draw.rectangle([int(28*s), int(36*s), int(36*s), int(40*s)], fill=blue)
    # 顶部左小窗 x:22-26, y:24-28
    draw.rectangle([int(22*s), int(24*s), int(26*s), int(28*s)], fill=blue)
    # 顶部中窗 x:28-36, y:24-28
    draw.rectangle([int(28*s), int(24*s), int(36*s), int(28*s)], fill=blue)
    # 顶部右小窗 x:38-42, y:24-28
    draw.rectangle([int(38*s), int(24*s), int(42*s), int(28*s)], fill=blue)

    return img


def generate_icons():
    output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'images')
    os.makedirs(output_dir, exist_ok=True)

    sizes = [72, 96, 128, 144, 152, 192, 384, 512]

    for size in sizes:
        img = draw_icon(size)
        output_path = os.path.join(output_dir, f'icon-{size}x{size}.png')
        img.save(output_path, 'PNG')
        print(f"已生成: {output_path} ({size}x{size})")

    print("\n所有 PWA 图标生成完成！")


if __name__ == '__main__':
    generate_icons()