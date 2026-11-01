"""
Generate high-resolution 512x512 master PNG and multi-resolution .ico
from pure mathematical vector primitives with 4x supersampling.
Produces:
  1. assets/icon_base.png & icon_base.ico: Pure white silhouette for system tray tinting.
  2. assets/icon_app.png & icon_app.ico: High-contrast dark shield with white insignia
     for window title bars, task switcher, and application shortcuts.
"""
from PIL import Image, ImageDraw
import os

def get_shield_and_insignia_paths(dim):
    def s(val):
        return val * (dim / 512.0)

    shield_pts = []
    steps = 40
    shield_pts.append((s(128), s(64)))
    shield_pts.append((s(384), s(64)))

    for i in range(steps + 1):
        t = i / steps
        x = (1-t)**2 * 384 + 2*(1-t)*t * 440 + t**2 * 440
        y = (1-t)**2 * 64 + 2*(1-t)*t * 76 + t**2 * 128
        shield_pts.append((s(x), s(y)))

    for i in range(1, steps + 1):
        t = i / steps
        x = (1-t)**2 * 440 + 2*(1-t)*t * 440 + t**2 * 256
        y = (1-t)**2 * 128 + 2*(1-t)*t * 376 + t**2 * 456
        shield_pts.append((s(x), s(y)))

    for i in range(1, steps + 1):
        t = i / steps
        x = (1-t)**2 * 256 + 2*(1-t)*t * 72 + t**2 * 72
        y = (1-t)**2 * 456 + 2*(1-t)*t * 376 + t**2 * 128
        shield_pts.append((s(x), s(y)))

    for i in range(1, steps + 1):
        t = i / steps
        x = (1-t)**2 * 72 + 2*(1-t)*t * 72 + t**2 * 128
        y = (1-t)**2 * 128 + 2*(1-t)*t * 76 + t**2 * 64
        shield_pts.append((s(x), s(y)))

    cap_top = [
        (s(256), s(142)),
        (s(374), s(204)),
        (s(256), s(266)),
        (s(138), s(204))
    ]

    chev_pts = []
    chev_pts.append((s(158), s(244)))
    chev_pts.append((s(256), s(296)))
    chev_pts.append((s(354), s(244)))
    chev_pts.append((s(354), s(308)))

    for i in range(steps + 1):
        t = i / steps
        x = (1-t)**2 * 354 + 2*(1-t)*t * 298 + t**2 * 256
        y = (1-t)**2 * 308 + 2*(1-t)*t * 364 + t**2 * 392
        chev_pts.append((s(x), s(y)))
    for i in range(1, steps + 1):
        t = i / steps
        x = (1-t)**2 * 256 + 2*(1-t)*t * 214 + t**2 * 158
        y = (1-t)**2 * 392 + 2*(1-t)*t * 364 + t**2 * 308
        chev_pts.append((s(x), s(y)))

    return shield_pts, cap_top, chev_pts


def render_base_icon(size=512):
    """Pure white silhouette with transparent cutouts (for tray tinting)."""
    scale = 4
    dim = size * scale
    img = Image.new("RGBA", (dim, dim), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    shield_pts, cap_top, chev_pts = get_shield_and_insignia_paths(dim)
    draw.polygon(shield_pts, fill=(255, 255, 255, 255))
    draw.polygon(cap_top, fill=(0, 0, 0, 0))
    draw.polygon(chev_pts, fill=(0, 0, 0, 0))

    return img.resize((size, size), Image.Resampling.LANCZOS)


def render_app_icon(size=512):
    """High-contrast dark shield with white insignia (for window headers and desktop shortcuts)."""
    scale = 4
    dim = size * scale
    img = Image.new("RGBA", (dim, dim), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    shield_pts, cap_top, chev_pts = get_shield_and_insignia_paths(dim)
    # Dark slate shield body
    draw.polygon(shield_pts, fill=(15, 23, 42, 255))
    # Subtle crisp outline
    draw.line(shield_pts + [shield_pts[0]], fill=(71, 85, 105, 255), width=max(2, int(6 * (dim / 512.0))))
    # Crisp white insignia inside
    draw.polygon(cap_top, fill=(255, 255, 255, 255))
    draw.polygon(chev_pts, fill=(255, 255, 255, 255))

    return img.resize((size, size), Image.Resampling.LANCZOS)


if __name__ == "__main__":
    os.makedirs("assets", exist_ok=True)
    sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]

    # 1. White base icon for tray
    icon_base = render_base_icon(512)
    icon_base.save("assets/icon_base.png", "PNG")
    icon_base.save("assets/icon_base.ico", format="ICO", sizes=sizes)
    print("Generated assets/icon_base.png & assets/icon_base.ico")

    # 2. High-contrast app icon for windows and shortcuts
    icon_app = render_app_icon(512)
    icon_app.save("assets/icon_app.png", "PNG")
    icon_app.save("assets/icon_app.ico", format="ICO", sizes=sizes)
    print("Generated assets/icon_app.png & assets/icon_app.ico")
