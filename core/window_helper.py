"""
LINE Window Geometry & Safe Coordinates Helper.
Calculates exact safe click targets to avoid opening links, images, or videos.
Supports both Windows (pygetwindow) and Linux/X11 (xdotool / xwininfo / screen fallback).
"""

import sys
import subprocess
import logging
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

    def get_safe_chat_history_click_pos(self) -> tuple:
        """
        Returns (x, y) coordinates for a SAFE blank space inside the chat history area.
        Uses the far-right margin background (92% width, 40% height) to avoid clicking message bubbles, links, videos or images.
        """
        win = self.get_line_window()
        if not win:
            logger.warning("LINE window not found. Falling back to default screen ratio.")
            return (850, 350)

        # Far right margin background of the chat pane
        safe_x = int(win.left + win.width * 0.92)
        safe_y = int(win.top + win.height * 0.40)
        logger.info(f"Calculated safe chat history focus coordinate: ({safe_x}, {safe_y})")
        return (safe_x, safe_y)

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
            icon_pos = detector.find_message_icon(template_path="assets/Message_icon.png", confidence=0.55)

        win = self.get_line_window()

        if icon_pos:
            click_x, click_y = icon_pos
            logger.info(f"🎯 [圖案比對成功] 點擊 Message_icon.png 座標 ({click_x}, {click_y}) + 按下 ESC...")
        elif win:
            click_x = int(win.left + 30)
            click_y = int(win.top + 45)
            logger.info(f"Unfocusing active chat room (比例備用算法): 點擊 ({click_x}, {click_y}) + 按下 ESC...")
        else:
            logger.warning("LINE window not found. Skipping unfocus action.")
            return

        pyautogui.click(click_x, click_y)
        time.sleep(0.3)
        pyautogui.press('escape')
        time.sleep(0.3)



