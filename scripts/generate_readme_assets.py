#!/usr/bin/env python3
"""
Generate visual assets for README.md:
1. assets/tray_animations.gif: Animated preview of all dynamic tray icon states.
2. assets/screenshot_setup.png: Crisp rendering of the configuration dialog with generic example credentials.
3. assets/screenshot_tray_menu.png: Crisp rendering of the system tray quick menu.
"""

import os
import sys
import math
from PIL import Image, ImageDraw, ImageFont

# Add repo root to sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from tray_icon import TrayIconTheme


def get_font(size, bold=False):
    """Attempt to load Segoe UI or fallback to default."""
    names = ["segoeuib.ttf" if bold else "segoeui.ttf", "arialbd.ttf" if bold else "arial.ttf"]
    for n in names:
        try:
            return ImageFont.truetype(n, size)
        except Exception:
            pass
    return ImageFont.load_default()


def generate_tray_animations_gif(output_path, num_frames=40, fps=25):
    """Generate an animated GIF showing all 5 tray states in action."""
    theme = TrayIconTheme(target_size=48, theme_mode="dark")
    
    states = [
        ("Synced / Up to Date", TrayIconTheme.STATE_SYNCED, "Idle"),
        ("Active Syncing", TrayIconTheme.STATE_WORKING, "Pulsing (1.5 Hz)"),
        ("New Updates Found", TrayIconTheme.STATE_NEW_NOTIFICATION, "Emerald Alert"),
        ("Missing Credentials", TrayIconTheme.STATE_NOT_CONFIGURED, "Amber Warning"),
        ("Network / Auth Error", TrayIconTheme.STATE_ERROR, "Crimson Pulse")
    ]
    
    card_w = 170
    card_h = 130
    padding = 16
    total_w = len(states) * card_w + (len(states) + 1) * padding
    total_h = card_h + padding * 2
    
    font_title = get_font(12, bold=True)
    font_sub = get_font(11, bold=False)
    
    frames = []
    duration_per_frame = int(1000 / fps)
    
    for frame_idx in range(num_frames):
        elapsed = frame_idx * (1.0 / fps)
        
        # GitHub Dark Theme Canvas Background (#0d1117)
        img = Image.new("RGBA", (total_w, total_h), (13, 17, 23, 255))
        draw = ImageDraw.Draw(img)
        
        for i, (label, state_key, subtext) in enumerate(states):
            x = padding + i * (card_w + padding)
            y = padding
            
            # GitHub Dark Surface Card (#161b22) with subtle border (#30363d)
            draw.rounded_rectangle(
                [x, y, x + card_w, y + card_h],
                radius=10,
                fill=(22, 27, 34, 255),
                outline=(48, 54, 61, 255),
                width=1
            )
            
            # Get animated state frame
            icon_img = theme.get_image(state_key, elapsed_time=elapsed)
            icon_x = x + (card_w - icon_img.width) // 2
            icon_y = y + 16
            img.paste(icon_img, (icon_x, icon_y), icon_img)
            
            # Label (#f0f6fc)
            bbox = draw.textbbox((0, 0), label, font=font_title)
            tw = bbox[2] - bbox[0]
            draw.text((x + (card_w - tw) // 2, y + 74), label, fill=(240, 246, 252), font=font_title)
            
            # Subtitle (#8b949e)
            bbox_sub = draw.textbbox((0, 0), subtext, font=font_sub)
            sw = bbox_sub[2] - bbox_sub[0]
            draw.text((x + (card_w - sw) // 2, y + 96), subtext, fill=(139, 148, 158), font=font_sub)
        
        frames.append(img)
    
    # Save as looping animated GIF
    frames[0].save(
        output_path,
        save_all=True,
        append_images=frames[1:],
        duration=duration_per_frame,
        loop=0,
        optimize=True
    )
    print(f"Saved tray animation GIF: {output_path}")


def generate_setup_screenshot(output_path):
    """Render a clean, high-resolution mockup of the Configuration window with generic placeholders."""
    w, h = 640, 590
    img = Image.new("RGBA", (w, h), (15, 23, 42, 255))
    draw = ImageDraw.Draw(img)

    font_win_title = get_font(12, bold=False)
    font_h1 = get_font(18, bold=True)
    font_desc = get_font(12, bold=False)
    font_label = get_font(12, bold=True)
    font_input = get_font(12, bold=False)
    font_btn = get_font(12, bold=True)
    font_small = get_font(11, bold=False)

    # Window Title Bar
    draw.rectangle([0, 0, w, 36], fill=(30, 41, 59, 255))
    draw.text((16, 9), "Blackboard Sentinel - Setup", fill=(203, 213, 225), font=font_win_title)
    draw.text((w - 70, 9), "—   □   ✕", fill=(148, 163, 184), font=font_win_title)

    # Main Card
    draw.rounded_rectangle([30, 60, w - 30, h - 30], radius=12, fill=(30, 41, 59, 255), outline=(51, 65, 85, 255), width=1)

    # Header
    draw.text((55, 80), "Blackboard Sentinel Configuration", fill=(248, 250, 252), font=font_h1)
    draw.text((55, 110), "Enter your portal credentials and choose your local course storage folder.", fill=(148, 163, 184), font=font_desc)

    fields = [
        ("Blackboard LMS Base URL", "https://lms.university.edu"),
        ("Username / Student ID", "student_id"),
        ("Password", "••••••••••••"),
        ("Course Files Storage Folder", "C:\\Users\\Student\\Documents\\University"),
    ]

    cur_y = 150
    for label, val in fields:
        draw.text((55, cur_y), label, fill=(226, 232, 240), font=font_label)
        cur_y += 24
        # Input Box
        draw.rounded_rectangle([55, cur_y, w - 55, cur_y + 36], radius=6, fill=(15, 23, 42, 255), outline=(71, 85, 105, 255), width=1)
        draw.text((67, cur_y + 9), val, fill=(241, 245, 249) if val.startswith("http") or val.startswith("C:") else (148, 163, 184), font=font_input)
        cur_y += 48

    # Checkbox
    chk_x, chk_y = 55, cur_y + 4
    draw.rounded_rectangle([chk_x, chk_y, chk_x + 18, chk_y + 18], radius=4, fill=(59, 130, 246, 255))
    draw.line([(chk_x + 4, chk_y + 9), (chk_x + 8, chk_y + 13), (chk_x + 14, chk_y + 5)], fill=(255, 255, 255), width=2)
    draw.text((82, cur_y + 4), "Keep all lecturer announcements (.docx)", fill=(241, 245, 249), font=font_label)
    cur_y += 26
    draw.text((82, cur_y), "Create an Announcements folder in each subject that keeps track of all announcements\nand converts them to word documents (.docx)", fill=(148, 163, 184), font=font_small)

    # Connect Button
    btn_w, btn_h = 220, 40
    btn_x = w - 55 - btn_w
    btn_y = h - 85
    draw.rounded_rectangle([btn_x, btn_y, btn_x + btn_w, btn_y + btn_h], radius=6, fill=(37, 99, 235, 255))
    draw.text((btn_x + 24, btn_y + 11), "Connect & Choose Subjects ->", fill=(255, 255, 255), font=font_btn)

    img.save(output_path)
    print(f"Saved setup screenshot: {output_path}")


def generate_tray_menu_screenshot(output_path):
    """Render a clean, high-resolution mockup of the Windows 11 System Tray Popup Menu."""
    menu_w, menu_h = 320, 270
    img = Image.new("RGBA", (menu_w, menu_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Windows 11 Acrylic / Dark Menu Style
    draw.rounded_rectangle(
        [4, 4, menu_w - 4, menu_h - 4],
        radius=10,
        fill=(32, 32, 32, 245),
        outline=(60, 60, 60, 255),
        width=1
    )

    font_default = get_font(12, bold=True)
    font_normal = get_font(12, bold=False)
    font_dim = get_font(11, bold=False)

    items = [
        ("Open Course Folder", True, False, "Default (Single Click)"),
        ("Check for Updates Now", False, False, ""),
        ("Upcoming Deadlines", False, False, ""),
        ("Grades & Feedback", False, False, ""),
        ("— separator —", False, True, ""),
        ("Settings...", False, False, ""),
        ("Exit", False, False, "")
    ]

    cur_y = 12
    for title, is_bold, is_sep, hint in items:
        if is_sep:
            draw.line([16, cur_y + 4, menu_w - 16, cur_y + 4], fill=(60, 60, 60, 255), width=1)
            cur_y += 10
            continue

        item_h = 32
        # Highlight first item gently
        if is_bold:
            draw.rounded_rectangle([10, cur_y, menu_w - 10, cur_y + item_h], radius=6, fill=(48, 48, 48, 200))

        font = font_default if is_bold else font_normal
        draw.text((22, cur_y + 7), title, fill=(255, 255, 255) if is_bold else (225, 225, 225), font=font)
        
        if hint:
            bbox = draw.textbbox((0, 0), hint, font=font_dim)
            hw = bbox[2] - bbox[0]
            draw.text((menu_w - 22 - hw, cur_y + 9), hint, fill=(150, 150, 150), font=font_dim)

        cur_y += item_h + 2

    img.save(output_path)
    print(f"Saved tray menu screenshot: {output_path}")


def main():
    assets_dir = os.path.join(BASE_DIR, "assets")
    os.makedirs(assets_dir, exist_ok=True)

    gif_path = os.path.join(assets_dir, "tray_animations.gif")
    setup_path = os.path.join(assets_dir, "screenshot_setup.png")
    menu_path = os.path.join(assets_dir, "screenshot_tray_menu.png")

    generate_tray_animations_gif(gif_path)
    generate_setup_screenshot(setup_path)
    generate_tray_menu_screenshot(menu_path)


if __name__ == "__main__":
    main()
