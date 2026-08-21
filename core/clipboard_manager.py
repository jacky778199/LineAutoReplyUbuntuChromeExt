"""
Clipboard and Keyboard Automation Manager.
Handles thread-safe clipboard operations, Ctrl+A/C text extraction, and Ctrl+V message sending
with multi-encoding fallback support (UTF-8, CP950/Big5, GB18030, Latin1).
"""

import os
import sys
import time
import logging
import threading
import subprocess
import pyperclip

if sys.platform != "win32" and "DISPLAY" not in os.environ:
    os.environ["DISPLAY"] = ":99"

import pyautogui

logger = logging.getLogger(__name__)

# Configure PyAutoGUI safety pauses
pyautogui.PAUSE = 0.3
pyautogui.FAILSAFE = False  # Disable fail-safe in headless/background automation


def robust_paste() -> str:
    """
    Safely reads text from system clipboard with multi-encoding fallback.
    Prevents UnicodeDecodeError when clipboard contains Big5/CP950 or non-UTF8 bytes from xclip.
    """
    if sys.platform != "win32":
        # 1. On Linux, try direct xclip with multi-encoding decode
        try:
            p = subprocess.run(["xclip", "-selection", "clipboard", "-o"], capture_output=True, timeout=2)
            if p.returncode == 0 and p.stdout:
                raw_bytes = p.stdout
                for enc in ["utf-8", "cp950", "big5", "gb18030", "utf-16", "latin1"]:
                    try:
                        return raw_bytes.decode(enc)
                    except UnicodeDecodeError:
                        continue
                return raw_bytes.decode("utf-8", errors="replace")
        except Exception:
            pass

    # 2. Try standard pyperclip.paste()
    try:
        return pyperclip.paste()
    except UnicodeDecodeError:
        # Fallback if pyperclip throws UnicodeDecodeError
        try:
            p = subprocess.run(["xclip", "-selection", "clipboard", "-o"], capture_output=True, timeout=2)
            return p.stdout.decode("utf-8", errors="replace")
        except Exception:
            return ""
    except Exception as e:
        logger.debug(f"pyperclip.paste exception: {e}")
        return ""


def robust_copy(text: str) -> bool:
    """Safely writes text into system clipboard with xclip fallback."""
    try:
        pyperclip.copy(text)
        return True
    except Exception as e:
        logger.debug(f"pyperclip.copy error: {e}")
        if sys.platform != "win32":
            try:
                p = subprocess.Popen(["xclip", "-selection", "clipboard"], stdin=subprocess.PIPE)
                p.communicate(input=text.encode("utf-8"), timeout=2)
                return True
            except Exception as e2:
                logger.error(f"Fallback xclip copy error: {e2}")
        return False


class ClipboardManager:
    """Thread-safe manager for system clipboard interactions and key simulation."""
    
    def __init__(self):
        self._lock = threading.Lock()
        self.last_diagnostics = {}

    def get_last_diagnostics(self) -> dict:
        """Returns diagnostic details from the most recent copy/paste operation."""
        return dict(self.last_diagnostics)

    def get_clipboard_text(self) -> str:
        """Safely fetch current text from clipboard with lock."""
        with self._lock:
            try:
                return robust_paste()
            except Exception as e:
                logger.error(f"Failed to read from clipboard: {e}")
                return ""

    def set_clipboard_text(self, text: str) -> bool:
        """Safely copy text into system clipboard with lock."""
        with self._lock:
            try:
                return robust_copy(text)
            except Exception as e:
                logger.error(f"Failed to write to clipboard: {e}")
                return False

    def copy_selected_text(self, safe_click_pos: tuple = None, max_retries: int = 2) -> str:
        """
        Clicks safe empty background region in chat history area to focus pane (avoiding links/videos),
        then simulates Ctrl+A -> Ctrl+C to copy chat log with multi-stage retry & diagnostics tracking.
        """
        with self._lock:
            diag = {
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "safe_click_pos": safe_click_pos,
                "attempts": [],
                "success": False,
                "text_length": 0,
                "error": None
            }
            self.last_diagnostics = diag

            try:
                old_clip = robust_paste()

                for attempt_idx in range(1, max_retries + 2):
                    attempt_info = {
                        "attempt": attempt_idx,
                        "click_pos": safe_click_pos,
                        "method": "pyautogui" if attempt_idx == 1 else "xdotool_fallback",
                        "clipboard_len": 0,
                        "primary_len": 0
                    }

                    # Determine click coordinates (Attempt 1: given pos; Attempt 2+: slight offset to ensure focus)
                    click_target = safe_click_pos
                    if attempt_idx > 1 and safe_click_pos:
                        # Offset by 20px horizontally or vertically to re-activate pane
                        offset_x = safe_click_pos[0] - 25 if safe_click_pos[0] > 100 else safe_click_pos[0]
                        offset_y = safe_click_pos[1] + 15
                        click_target = (offset_x, offset_y)
                        attempt_info["click_pos"] = click_target

                    if click_target:
                        logger.info(f"Clicking chat coordinate {click_target} (Attempt {attempt_idx}) to focus history pane...")
                        pyautogui.click(click_target[0], click_target[1])
                        time.sleep(0.35)

                    # Clear clipboard first
                    robust_copy("")
                    time.sleep(0.1)

                    if sys.platform != "win32" and attempt_idx > 1:
                        # Linux: Use xdotool with --clearmodifiers for reliable key sending
                        try:
                            subprocess.run(["xdotool", "key", "--clearmodifiers", "ctrl+a"], check=False, timeout=2)
                            time.sleep(0.25)
                            subprocess.run(["xdotool", "key", "--clearmodifiers", "ctrl+c"], check=False, timeout=2)
                            time.sleep(0.35)
                        except Exception as xdotool_err:
                            attempt_info["xdotool_err"] = str(xdotool_err)
                            pyautogui.hotkey('ctrl', 'a')
                            time.sleep(0.2)
                            pyautogui.hotkey('ctrl', 'c')
                            time.sleep(0.3)
                    else:
                        # Standard PyAutoGUI key hotkeys
                        pyautogui.hotkey('ctrl', 'a')
                        time.sleep(0.25)
                        pyautogui.hotkey('ctrl', 'c')
                        time.sleep(0.35)

                    # Read standard clipboard
                    copied_text = robust_paste()
                    attempt_info["clipboard_len"] = len(copied_text) if copied_text else 0

                    # Fallback: check X11 primary selection on Linux if clipboard selection is empty
                    if not copied_text and sys.platform != "win32":
                        try:
                            p_prim = subprocess.run(["xclip", "-selection", "primary", "-o"], capture_output=True, timeout=2)
                            if p_prim.returncode == 0 and p_prim.stdout:
                                prim_text = p_prim.stdout.decode("utf-8", errors="replace")
                                attempt_info["primary_len"] = len(prim_text)
                                if prim_text and len(prim_text.strip()) > 0:
                                    copied_text = prim_text
                        except Exception as prim_err:
                            attempt_info["primary_err"] = str(prim_err)

                    diag["attempts"].append(attempt_info)

                    if copied_text and len(copied_text.strip()) > 0:
                        diag["success"] = True
                        diag["text_length"] = len(copied_text)
                        logger.info(f"✅ 對話紀錄複製成功 (第 {attempt_idx} 次嘗試，字數: {len(copied_text)})")
                        return copied_text

                    logger.warning(f"⚠️ 第 {attempt_idx} 次複製未取得對話文字 (剪貼簿為空)，準備重試...")
                    time.sleep(0.4)

                # If nothing copied after all attempts, restore old clipboard text
                if old_clip:
                    robust_copy(old_clip)

                diag["success"] = False
                logger.error("❌ 所有複製嘗試均未取得對話文字 (剪貼簿為空)。")
                return ""

            except Exception as e:
                diag["error"] = str(e)
                logger.error(f"Error copying chat history: {e}", exc_info=True)
                return ""

    def send_message_via_clipboard(self, message: str, safe_input_pos: tuple = None) -> bool:
        """
        Clicks input box, copies message to clipboard, pastes (Ctrl+V) and sends (Enter).
        """
        if not message or message.strip() == "[NO_REPLY]":
            logger.info("No message to send.")
            return False

        with self._lock:
            try:
                if safe_input_pos:
                    logger.info(f"Clicking safe input box coordinate ({safe_input_pos[0]}, {safe_input_pos[1]})...")
                    pyautogui.click(safe_input_pos[0], safe_input_pos[1])
                    time.sleep(0.3)

                # Save existing clipboard content
                prev_content = robust_paste()

                # Set new message into clipboard
                robust_copy(message)
                time.sleep(0.2)

                # Paste into input box
                pyautogui.hotkey('ctrl', 'v')
                time.sleep(0.2)

                # Send Enter
                pyautogui.press('enter')
                logger.info(f"Message sent via clipboard: {message[:30]}...")

                # Restore previous clipboard after a short delay
                time.sleep(0.5)
                if prev_content:
                    robust_copy(prev_content)
                return True

            except Exception as e:
                logger.error(f"Error sending message via clipboard: {e}", exc_info=True)
                return False
