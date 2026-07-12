"""Generates the source assets @capacitor/assets needs to produce Android
launcher icons (legacy + adaptive) at all mipmap densities, reusing the same
orb visual identity as the PWA icons (see generate-icons.py).
"""
from PIL import Image, ImageDraw, ImageFilter

BG = (9, 9, 11, 255)  # zinc-950
CORE_LIGHT = (199, 213, 255)
CORE_MID = (124, 158, 255)
CORE_DARK = (75, 95, 168)


def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(len(a)))


def draw_orb(size, margin_ratio, transparent_bg=False):
    bg = (0, 0, 0, 0) if transparent_bg else BG
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    radius = size * (0.5 - margin_ratio)
    cx = cy = size / 2
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

    glow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    gdraw = ImageDraw.Draw(glow)
    glow_r = radius * 1.35
    gdraw.ellipse([cx - glow_r, cy - glow_r, cx + glow_r, cy + glow_r], fill=CORE_MID + (110,))
    glow = glow.filter(ImageFilter.GaussianBlur(radius=size * 0.06))

    base = Image.new("RGBA", (size, size), bg)
    base.alpha_composite(glow)
    base.alpha_composite(img)
    return base


OUT_DIR = "C:/Users/newte/echo v1/frontend/resources"

# Legacy launcher icon: orb fills most of the frame, opaque background.
draw_orb(1024, margin_ratio=0.08, transparent_bg=False).save(f"{OUT_DIR}/icon.png")

# Adaptive icon foreground: orb kept within the ~66% safe zone (adaptive
# icons crop more aggressively than PWA maskable icons), transparent bg so
# it layers over the background color.
draw_orb(1024, margin_ratio=0.30, transparent_bg=True).save(f"{OUT_DIR}/icon-foreground.png")

# Adaptive icon background: flat fill matching the app's dark background.
solid = Image.new("RGBA", (1024, 1024), BG)
solid.save(f"{OUT_DIR}/icon-background.png")

print("done")
