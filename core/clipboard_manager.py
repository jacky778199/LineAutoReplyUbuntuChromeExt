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

    def copy_selected_text(self, safe_click_pos: tuple = None) -> str:
        """
        Clicks safe empty background region in chat history area to focus pane (avoiding links/videos),
        then simulates Ctrl+A -> Ctrl+C to copy chat log.
        """
        with self._lock:
            try:
                if safe_click_pos:
                    logger.info(f"Clicking safe chat background coordinate ({safe_click_pos[0]}, {safe_click_pos[1]}) to focus history pane...")
                    pyautogui.click(safe_click_pos[0], safe_click_pos[1])
                    time.sleep(0.3)

                # Save old clipboard content (safely with robust_paste)
                old_clip = robust_paste()
                robust_copy("")
                
                # Perform Ctrl+A then Ctrl+C
                pyautogui.hotkey('ctrl', 'a')
                time.sleep(0.2)
                pyautogui.hotkey('ctrl', 'c')
                time.sleep(0.3)

                copied_text = robust_paste()
                
                # If nothing copied, restore old clipboard text
                if not copied_text and old_clip:
                    robust_copy(old_clip)
                    
                return copied_text
            except Exception as e:
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
