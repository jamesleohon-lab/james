"""Regenerate the PWA icons in web/icons (needs Pillow: pip install pillow)."""

from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parent.parent / "web" / "icons"
BG = (15, 18, 22)
BARS = [((229, 72, 77), 0.85), ((240, 140, 46), 0.6), ((230, 200, 74), 0.38)]


def draw(size: int, padding: float) -> Image.Image:
    img = Image.new("RGB", (size, size), BG)
    d = ImageDraw.Draw(img)
    inner = size * (1 - 2 * padding)
    bar_w = inner / 5
    gap = bar_w / 2
    left = (size - (3 * bar_w + 2 * gap)) / 2
    bottom = size * (1 - padding) - inner * 0.05
    for i, (colour, height) in enumerate(BARS):
        x = left + i * (bar_w + gap)
        d.rounded_rectangle([x, bottom - inner * height, x + bar_w, bottom],
                            radius=bar_w * 0.18, fill=colour)
    return img


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    draw(192, 0.16).save(OUT / "icon-192.png")
    draw(512, 0.16).save(OUT / "icon-512.png")
    draw(512, 0.26).save(OUT / "icon-512-maskable.png")  # safe zone for Android masks
    draw(180, 0.14).save(OUT / "apple-touch-icon.png")
    print("icons written to", OUT)
