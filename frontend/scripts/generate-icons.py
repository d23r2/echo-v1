"""Generates PWA/Android app icons matching the EchoPresence orb visual
identity (radial-gradient blue sphere + soft glow) — there is no tear-drop
glyph anywhere in this codebase to reuse, so this builds on the orb design
already shipped in EchoPresence.tsx instead. Run once; outputs are committed
as static assets, not regenerated at build time.
"""
import math
from PIL import Image, ImageDraw, ImageFilter

BG = (9, 9, 11, 255)  # zinc-950
CORE_LIGHT = (199, 213, 255)
CORE_MID = (124, 158, 255)
CORE_DARK = (75, 95, 168)


def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(len(a)))


def draw_orb(size, margin_ratio):
    """margin_ratio: fraction of size left as background margin around the
    orb. 0 for regular icons (orb fills most of the frame), larger for
    maskable icons (must stay within the ~80% safe zone circle)."""
    img = Image.new("RGBA", (size, size), BG)
    draw = ImageDraw.Draw(img)

    radius = size * (0.5 - margin_ratio)
    cx = cy = size / 2
    # Radial gradient via concentric circles, light source offset up-left
    # (matches the orb's `radial-gradient(circle at 35% 30%, ...)` in CSS).
    light_cx = cx - radius * 0.3
    light_cy = cy - radius * 0.4
    steps = 160
    for i in range(steps, 0, -1):
        t = i / steps
        r = radius * t
        if t > 0.55:
            color = lerp(CORE_MID, CORE_DARK, (t - 0.55) / 0.45)
        else:
            color = lerp(CORE_LIGHT, CORE_MID, t / 0.55)
        bbox = [light_cx - r, light_cy - r, light_cx + r, light_cy + r]
        draw.ellipse(bbox, fill=color + (255,))

    # Soft outer glow: blurred larger halo underneath, composited behind.
    glow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    gdraw = ImageDraw.Draw(glow)
    glow_r = radius * 1.35
    gdraw.ellipse([cx - glow_r, cy - glow_r, cx + glow_r, cy + glow_r], fill=CORE_MID + (110,))
    glow = glow.filter(ImageFilter.GaussianBlur(radius=size * 0.06))

    base = Image.new("RGBA", (size, size), BG)
    base.alpha_composite(glow)
    base.alpha_composite(img)
    return base


OUT_DIR = "C:/Users/newte/echo v1/frontend/public/icons"

for size in (192, 512):
    draw_orb(size, margin_ratio=0.08).save(f"{OUT_DIR}/icon-{size}.png")
    # Maskable: keep orb within the ~80% safe zone so OS masking (circle/
    # squircle/rounded-square) never clips the important content.
    draw_orb(size, margin_ratio=0.22).save(f"{OUT_DIR}/icon-{size}-maskable.png")

# Favicon-ish small size for index.html + apple-touch-icon.
draw_orb(180, margin_ratio=0.08).save(f"{OUT_DIR}/apple-touch-icon.png")
draw_orb(32, margin_ratio=0.05).save(f"{OUT_DIR}/favicon-32.png")

print("done")
