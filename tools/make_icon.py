"""生成应用图标（多尺寸 .ico）。"""

import os

from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "assets")


def render(size: int) -> Image.Image:
    scale = 4
    s = size * scale
    image = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    radius = int(s * 0.26)
    # 纵向渐变
    for y in range(s):
        t = y / max(1, s - 1)
        r = int(0x6B + (0x3A - 0x6B) * t)
        g = int(0x86 + (0x54 - 0x86) * t)
        b = int(0xFF + (0xD6 - 0xFF) * t)
        draw.line([(0, y), (s, y)], fill=(r, g, b, 255))
    mask = Image.new("L", (s, s), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, s - 1, s - 1], radius=radius, fill=255)
    image.putalpha(mask)

    font_path = r"C:\Windows\Fonts\msyhbd.ttc"
    if not os.path.exists(font_path):
        font_path = r"C:\Windows\Fonts\msyh.ttc"
    font = ImageFont.truetype(font_path, int(s * 0.56))
    text = "译"
    box = draw.textbbox((0, 0), text, font=font)
    x = (s - (box[2] - box[0])) / 2 - box[0]
    y = (s - (box[3] - box[1])) / 2 - box[1] - s * 0.02
    draw.text((x, y), text, font=font, fill=(255, 255, 255, 245))
    return image.resize((size, size), Image.LANCZOS)


def main() -> None:
    os.makedirs(OUT, exist_ok=True)
    sizes = [16, 24, 32, 48, 64, 128, 256]
    images = [render(s) for s in sizes]
    path = os.path.join(OUT, "deepdict.ico")
    images[-1].save(path, format="ICO", sizes=[(s, s) for s in sizes])
    images[-1].save(os.path.join(OUT, "deepdict.png"))
    print("icon ->", path)


if __name__ == "__main__":
    main()
