"""
Tray Icon Rendering and Dynamic Tinting Engine for Blackboard Sentinel.
Provides state-driven tinting, real-time animations on a base silhouette,
and automatic or explicit Windows Light / Dark taskbar adaptation.
"""
import os
import sys
import math
import time
from PIL import Image, ImageDraw

# Color Palette - Dark Taskbar (Default in Windows 11)
DARK_WHITE = (255, 255, 255)
DARK_SYNCED_GREEN = (16, 185, 129)       # #10B981
DARK_WORKING_CYAN = (56, 189, 248)       # #38BDF8 Sky blue
DARK_NOT_CONFIGURED = (245, 158, 11)     # #F59E0B Amber
DARK_ERROR_RED = (239, 68, 68)           # #EF4444 Crimson

# Color Palette - Light Taskbar (Contrast against white/light taskbar)
LIGHT_DARK_SLATE = (15, 23, 42)          # #0F172A
LIGHT_SYNCED_GREEN = (5, 150, 105)       # #059669
LIGHT_WORKING_BLUE = (37, 99, 235)       # #2563EB Royal Blue
LIGHT_NOT_CONFIGURED = (217, 119, 6)     # #D97706 Deep Amber
LIGHT_ERROR_RED = (220, 38, 38)          # #DC2626 Deep Red


def is_windows_taskbar_light():
    """Detect if Windows taskbar is configured in Light Theme."""
    if sys.platform != "win32":
        return False
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize")
        val, _ = winreg.QueryValueEx(key, "SystemUsesLightTheme")
        winreg.CloseKey(key)
        return val == 1
    except Exception:
        return False


class TrayIconTheme:
    STATE_SYNCED = "synced"
    STATE_WORKING = "working"
    STATE_NOT_CONFIGURED = "not_configured"
    STATE_ERROR = "error"
    STATE_NEW_NOTIFICATION = "new_notification"

    def __init__(self, base_png_path=None, target_size=64, theme_mode=None):
        self.target_size = target_size
        self.theme_mode = theme_mode

        if base_png_path and os.path.exists(base_png_path):
            self.base_image = Image.open(base_png_path).convert("RGBA")
        else:
            base_dir = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
            default_path = os.path.join(base_dir, "assets", "icon_base.png")
            if not os.path.exists(default_path):
                exe_dir = os.path.dirname(sys.executable)
                default_path = os.path.join(exe_dir, "assets", "icon_base.png")

            if os.path.exists(default_path):
                self.base_image = Image.open(default_path).convert("RGBA")
            else:
                from scripts.generate_icon_png import render_base_icon
                self.base_image = render_base_icon(512)

        # Cache resized base image and extract alpha mask
        self.cached_base = self.base_image.resize((target_size, target_size), Image.Resampling.LANCZOS)
        _, _, _, self.alpha_mask = self.cached_base.split()

    def is_light(self):
        pref = (self.theme_mode or os.getenv("TRAY_THEME") or "auto").lower().strip()
        if pref == "light":
            return True
        elif pref == "dark":
            return False
        return is_windows_taskbar_light()

    def tint_base(self, rgb_color, alpha_factor=1.0):
        """Tint base image to specific RGB color with optional alpha factor."""
        solid = Image.new("RGBA", (self.target_size, self.target_size), rgb_color + (255,))
        if alpha_factor < 1.0:
            mask = self.alpha_mask.point(lambda a: int(a * alpha_factor))
        else:
            mask = self.alpha_mask
        solid.putalpha(mask)
        return solid

    @staticmethod
    def lerp_color(c1, c2, t):
        """Linear interpolation between two RGB tuples where t in [0.0, 1.0]."""
        return (
            int(c1[0] + (c2[0] - c1[0]) * t),
            int(c1[1] + (c2[1] - c1[1]) * t),
            int(c1[2] + (c2[2] - c1[2]) * t)
        )

    def get_image(self, state, elapsed_time=0.0):
        """
        Returns the PIL RGBA image for the given state and animation timestamp.
        elapsed_time: seconds into current state animation.
        """
        light = self.is_light()

        if state == self.STATE_SYNCED:
            return self.tint_base(LIGHT_DARK_SLATE if light else DARK_WHITE)

        elif state == self.STATE_WORKING:
            # 1.5 Hz smooth breathing pulse
            pulse = 0.5 + 0.5 * math.sin(elapsed_time * 2.0 * math.pi * 1.5)
            if light:
                color = self.lerp_color(LIGHT_WORKING_BLUE, LIGHT_DARK_SLATE, pulse)
            else:
                color = self.lerp_color(DARK_WORKING_CYAN, DARK_WHITE, pulse)
            return self.tint_base(color)

        elif state == self.STATE_NOT_CONFIGURED:
            return self.tint_base(LIGHT_NOT_CONFIGURED if light else DARK_NOT_CONFIGURED)

        elif state == self.STATE_ERROR:
            # 1.2 Hz smooth breathing pulse between bright crimson and deep red
            pulse = 0.5 + 0.5 * math.sin(elapsed_time * 2.0 * math.pi * 1.2)
            base_red = LIGHT_ERROR_RED if light else DARK_ERROR_RED
            dim_red = (150, 25, 25) if light else (90, 15, 15)
            color = self.lerp_color(base_red, dim_red, pulse)
            return self.tint_base(color)

        elif state == self.STATE_NEW_NOTIFICATION:
            t = min(max(elapsed_time, 0.0), 1.0)
            pulse = math.sin(t * math.pi * 2.0) ** 2
            if light:
                color = self.lerp_color(LIGHT_DARK_SLATE, LIGHT_SYNCED_GREEN, pulse)
            else:
                color = self.lerp_color(DARK_WHITE, DARK_SYNCED_GREEN, pulse)
            return self.tint_base(color)

        # Default fallback
        return self.tint_base(LIGHT_DARK_SLATE if light else DARK_WHITE)
