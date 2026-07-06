"""
make_icon.py - generate click_later.ico (+ a PNG preview).

Design: a gold targeting reticle on a warm-charcoal rounded tile - reads as
"click a precise point", matching the app's gold/dark theme. Pure Pillow.
Run:  python make_icon.py
"""
from PIL import Image, ImageDraw

S = 256
GOLD    = (245, 200, 66, 255)
GOLD_HI = (255, 221, 110, 255)
GOLD_DK = (138, 114, 32, 255)

top, bot = (0x1b, 0x16, 0x0e), (0x0c, 0x0a, 0x07)
bg = Image.new("RGB", (S, S))
px = bg.load()
for y in range(S):
    t = y / (S - 1)
    row = tuple(int(top[i] + (bot[i] - top[i]) * t) for i in range(3))
    for x in range(S):
        px[x, y] = row

mask = Image.new("L", (S, S), 0)
ImageDraw.Draw(mask).rounded_rectangle([0, 0, S - 1, S - 1], radius=58, fill=255)

img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
img.paste(bg, (0, 0), mask)
d = ImageDraw.Draw(img)
d.rounded_rectangle([2, 2, S - 3, S - 3], radius=56, outline=(58, 48, 29, 120), width=2)

cx = cy = S // 2
d.ellipse([cx - 96, cy - 96, cx + 96, cy + 96], outline=GOLD_DK, width=6)
d.ellipse([cx - 70, cy - 70, cx + 70, cy + 70], outline=GOLD, width=15)
d.ellipse([cx - 14, cy - 14, cx + 14, cy + 14], fill=GOLD_HI)
for x0, y0, x1, y1 in [
    (cx, cy - 100, cx, cy - 42), (cx, cy + 42, cx, cy + 100),
    (cx - 100, cy, cx - 42, cy), (cx + 42, cy, cx + 100, cy),
]:
    d.line([x0, y0, x1, y1], fill=GOLD, width=13)

img.save("click_later_icon.png")
img.save("click_later.ico",
         sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])
print("wrote click_later.ico + click_later_icon.png")
