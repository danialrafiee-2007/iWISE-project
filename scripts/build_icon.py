"""Draw deploy/portable/truth-guardian.ico, the icon of the desktop shortcut that Get-Truth-Guardian.bat offers (D-217).

It is the site's own shield (the rail's logo in static_html/index.html: the same outline, green face and white tick),
drawn here with Pillow so that no picture from elsewhere is needed:

    .venv/Scripts/python.exe scripts/build_icon.py
"""

from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "deploy" / "portable" / "truth-guardian.ico"
SIZE = 1024  # drawn large, then scaled down, for smooth edges
SIZES = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
# The rail's viewBox is 3 1.5 19 21.5; the shield's outline in that box: M12 3 l7 3 v5 c0 4.5 -3 8.3 -7 10 c-4 -1.7 -7 -5.5 -7 -10 V6 z
BOX = (3.0, 1.5, 19.0, 21.5)


def bezier(p0, p1, p2, p3, steps=40):
    return [
        tuple((1 - t) ** 3 * a + 3 * (1 - t) ** 2 * t * b + 3 * (1 - t) * t**2 * c + t**3 * d for a, b, c, d in zip(p0, p1, p2, p3))
        for t in (i / steps for i in range(1, steps + 1))
    ]


def outline():
    points = [(12, 3), (19, 6), (19, 11)]
    points += bezier((19, 11), (19, 15.5), (16, 19.3), (12, 21))
    points += bezier((12, 21), (8, 19.3), (5, 15.5), (5, 11))
    points += [(5, 6)]
    return points


def to_pixels(points, dx=0.0, dy=0.0):
    x0, y0, w, h = BOX
    scale = SIZE / max(w, h)
    left = (SIZE - w * scale) / 2
    top = (SIZE - h * scale) / 2
    return [(left + (x + dx - x0) * scale, top + (y + dy - y0) * scale) for x, y in points], scale


def gradient(top_left, bottom_right, stops):
    """A diagonal gradient the size of the icon, like the rail's linearGradient."""
    layer = Image.new("RGBA", (SIZE, SIZE))
    pixels = layer.load()
    (x1, y1), (x2, y2) = top_left, bottom_right
    span = (x2 - x1) ** 2 + (y2 - y1) ** 2
    for y in range(SIZE):
        for x in range(SIZE):
            t = max(0.0, min(1.0, ((x - x1) * (x2 - x1) + (y - y1) * (y2 - y1)) / span))
            for (a, ca), (b, cb) in zip(stops, stops[1:]):
                if a <= t <= b:
                    f = (t - a) / (b - a) if b > a else 0
                    pixels[x, y] = tuple(round(ca[i] + (cb[i] - ca[i]) * f) for i in range(3)) + (255,)
                    break
    return layer


def shape_mask(points):
    mask = Image.new("L", (SIZE, SIZE), 0)
    ImageDraw.Draw(mask).polygon(points, fill=255)
    return mask


def main() -> None:
    icon = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    edge, scale = to_pixels(outline(), 0.9, 1.1)
    face, _ = to_pixels(outline())
    dark = (6, 48, 27)
    icon.paste(gradient((0, 0), (0, SIZE), [(0, (20, 92, 55)), (1, dark)]), mask=shape_mask(edge))
    icon.paste(gradient((0.15 * SIZE, 0), (0.85 * SIZE, SIZE), [(0, (157, 255, 196)), (0.45, (47, 179, 106)), (1, (15, 90, 52))]), mask=shape_mask(face))
    draw = ImageDraw.Draw(icon)
    draw.line(face + face[:1], fill=(217, 255, 233, 180), width=max(1, round(0.7 * scale)), joint="curve")
    tick, _ = to_pixels([(8.5, 12), (11, 14.5), (15.5, 9.5)])
    shadow, _ = to_pixels([(8.5, 12), (11, 14.5), (15.5, 9.5)], 0.35, 0.5)
    draw.line(shadow, fill=dark + (140,), width=round(2.2 * scale), joint="curve")
    draw.line(tick, fill=(243, 255, 248, 255), width=round(2.0 * scale), joint="curve")
    for end in (tick[0], tick[-1]):  # round caps
        r = scale
        draw.ellipse((end[0] - r, end[1] - r, end[0] + r, end[1] + r), fill=(243, 255, 248, 255))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    icon.resize((256, 256), Image.LANCZOS).save(OUT, sizes=SIZES)
    print(OUT, OUT.stat().st_size, "bytes")


if __name__ == "__main__":
    main()
