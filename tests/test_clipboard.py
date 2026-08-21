"""
Unit test for ClipboardManager thread locking mechanism.
"""

import os
import sys
import threading
import time

if sys.platform != "win32" and "DISPLAY" not in os.environ:
    os.environ["DISPLAY"] = ":99"

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.clipboard_manager import ClipboardManager

def test_clipboard_thread_safety():
    clipboard = ClipboardManager()
    results = []

    def worker(worker_id: int, message: str):
        clipboard.set_clipboard_text(f"Worker {worker_id}: {message}")
        time.sleep(0.05)
        text = clipboard.get_clipboard_text()
        results.append(text)

    threads = []
    for i in range(5):
        t = threading.Thread(target=worker, args=(i, f"Message_{i}"))
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    assert len(results) == 5
    print("test_clipboard_thread_safety PASSED!")


def test_clipboard_diagnostics_and_failure_save():
    from main import save_copy_failure_debug
    from core.window_helper import LineWindowHelper

    clipboard = ClipboardManager()
    win_helper = LineWindowHelper()

    # Simulate copy attempt to populate diagnostics
    clipboard.last_diagnostics = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "safe_click_pos": (850, 350),
        "attempts": [
            {"attempt": 1, "method": "pyautogui", "click_pos": (850, 350), "clipboard_len": 0, "primary_len": 0},
            {"attempt": 2, "method": "xdotool_fallback", "click_pos": (825, 365), "clipboard_len": 0, "primary_len": 0}
        ],
        "success": False,
        "text_length": 0,
        "error": None
    }

    test_debug_dir = "/home/dinghonjay/AutoReplyMessage/debug"
    save_copy_failure_debug(
        scan_count=99999,
        dot_pos=(100, 200),
        safe_chat_pos=(850, 350),
        clipboard_mgr=clipboard,
        win_helper=win_helper,
        debug_dir=test_debug_dir,
        is_test=True
    )

    # Verify report file exists and has diagnostic content
    report_file = os.path.join(test_debug_dir, "test_raw_text_99999.txt")
    assert os.path.exists(report_file), "Debug raw text report was not created!"

    with open(report_file, "r", encoding="utf-8") as f:
        content = f.read()

    assert "LINE 訊息複製失敗詳細診斷報告" in content
    assert "99999" in content
    assert "Unread Dot" in content or "(100, 200)" in content
    print("test_clipboard_diagnostics_and_failure_save PASSED!")

    # Clean up test artifact
    if os.path.exists(report_file):
        os.remove(report_file)
    copy_fail_file = os.path.join(test_debug_dir, "test_copy_fail_99999.txt")
    if os.path.exists(copy_fail_file):
        os.remove(copy_fail_file)
    png_file = os.path.join(test_debug_dir, "test_copy_fail_99999.png")
    if os.path.exists(png_file):
        os.remove(png_file)
    latest_test_png = os.path.join(test_debug_dir, "test_latest_copy_fail.png")
    if os.path.exists(latest_test_png):
        os.remove(latest_test_png)


if __name__ == "__main__":
    test_clipboard_thread_safety()
    test_clipboard_diagnostics_and_failure_save()

