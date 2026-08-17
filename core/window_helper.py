"""
LINE Window Geometry & Safe Coordinates Helper.
Calculates exact safe click targets to avoid opening links, images, or videos.
Supports both Windows (pygetwindow) and Linux/X11 (xdotool / xwininfo / screen fallback).
"""

import os
import sys
import subprocess
import logging

if sys.platform != "win32" and "DISPLAY" not in os.environ:
    os.environ["DISPLAY"] = ":99"

import pyautogui

logger = logging.getLogger(__name__)

class SimpleWindow:
    def __init__(self, left: int, top: int, width: int, height: int, title: str = "LINE"):
        self.left = left
        self.top = top
        self.width = width
        self.height = height
        self.title = title

class LineWindowHelper:
    """Helper to locate LINE window and calculate safe click targets."""

    def __init__(self, title_keyword: str = "LINE"):
        self.title_keyword = title_keyword

    def get_line_window(self):
        """Finds the active LINE desktop window on Windows or Linux."""
        if sys.platform == "win32":
            try:
                import pygetwindow as gw
                windows = gw.getWindowsWithTitle(self.title_keyword)
                for w in windows:
                    if "LINE" in w.title.upper() and w.width > 400 and w.height > 400:
                        return w
            except Exception as e:
                logger.error(f"Error finding LINE window on Windows: {e}")
        else:
            # Linux X11 / Xvfb detection using xdotool / xwininfo
            try:
                res = subprocess.run(["xdotool", "search", "--name", self.title_keyword], capture_output=True, text=True)
                if res.returncode == 0 and res.stdout.strip():
                    win_ids = res.stdout.strip().splitlines()
                    for wid in win_ids:
                        info_res = subprocess.run(["xwininfo", "-id", wid], capture_output=True, text=True)
                        if info_res.returncode == 0:
                            lines = info_res.stdout.splitlines()
                            x, y, w, h = 0, 0, 0, 0
                            for line in lines:
                                if "Absolute upper-left X:" in line:
                                    x = int(line.split(":")[-1].strip())
                                elif "Absolute upper-left Y:" in line:
                                    y = int(line.split(":")[-1].strip())
                                elif "Width:" in line:
                                    w = int(line.split(":")[-1].strip())
                                elif "Height:" in line:
                                    h = int(line.split(":")[-1].strip())
                            if w > 400 and h > 400:
                                return SimpleWindow(x, y, w, h, "LINE")
            except Exception as e:
                logger.debug(f"Linux window detection via xdotool failed: {e}")

            # Fallback to screen resolution
            sw, sh = pyautogui.size()
            return SimpleWindow(0, 0, sw, sh, "LINE")

        return None

    def get_safe_chat_history_click_pos(self, detector=None) -> tuple:
        """
        Returns (x, y) coordinates for a SAFE blank space inside the chat history area.
        Combines:
        1. Scheme A: Vision-based White Background Spot Finder (if detector is provided).
        2. Scheme B: Structural safe margin / gutter coordinates fallback (95% width, 35% height).
        """
        win = self.get_line_window()
        if not win:
            logger.warning("LINE window not found. Falling back to default screen ratio.")
            if detector:
                safe_spot = detector.find_safe_white_background_spot()
                if safe_spot:
                    return safe_spot
            return (850, 350)

        # Calculate search bounding box on the right side of the chat pane (x: 72%~96%, y: 20%~75%)
        search_x = int(win.left + win.width * 0.72)
        search_y = int(win.top + win.height * 0.20)
        search_w = int(win.width * 0.24)
        search_h = int(win.height * 0.55)
        search_region = (search_x, search_y, search_w, search_h)

        # Structural safe margin position (far-right margin gutter, avoiding bubbles)
        fallback_safe_x = int(win.left + win.width * 0.95)
        fallback_safe_y = int(win.top + win.height * 0.35)

        if detector:
            safe_spot = detector.find_safe_white_background_spot(
                search_region=search_region,
                preferred_pos=(fallback_safe_x, fallback_safe_y)
            )
            if safe_spot:
                logger.info(f"🎯 [純白安全點] 視覺動態鎖定純白背景座標: {safe_spot}")
                return safe_spot
            else:
                logger.warning("⚠️ [純白安全點] 視覺辨識未找到足夠純白區塊，採用結構性安全邊界備援。")

        logger.info(f"Using structural safe chat history coordinate: ({fallback_safe_x}, {fallback_safe_y})")
        return (fallback_safe_x, fallback_safe_y)

    def get_input_box_click_pos(self) -> tuple:
        """
        Returns (x, y) coordinates for the bottom message input text box.
        """
        win = self.get_line_window()
        if not win:
            return (700, 650)

        input_x = int(win.left + win.width * 0.60)
        input_y = int(win.top + win.height - 95)
        logger.info(f"Calculated safe input box focus coordinate: ({input_x}, {input_y})")
        return (input_x, input_y)

    def unfocus_chat_room(self, detector=None):
        """
        Locates Message_icon.png on screen using OpenCV template matching via detector (with window ratio fallback),
        clicks the icon, and sends ESC key to unfocus/close active chat room.
        """
        import time
        import pyautogui

        icon_pos = None
        if detector:
            icon_pos = detector.find_message_icon(template_path="assets/Message_icon.png", confidence=0.65)

        win = self.get_line_window()

        if icon_pos:
            click_x, click_y = icon_pos
            logger.info(f"🎯 [圖案比對成功] 點擊 Message_icon.png 座標 ({click_x}, {click_y}) + 按下 ESC...")
        elif win:
            click_x = int(win.left + 30)
            click_y = int(win.top + 89)
            logger.info(f"Unfocusing active chat room (側邊欄備用座標): 點擊 ({click_x}, {click_y}) + 按下 ESC...")
        else:
            logger.warning("LINE window not found. Skipping unfocus action.")
            return

        pyautogui.click(click_x, click_y)
        logger.info("⏳ 點擊 Message 分頁後等待 5 秒 (確保對話列表載入完成)...")
        time.sleep(5.0)
        pyautogui.press('escape')
        time.sleep(0.3)



