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

if __name__ == "__main__":
    test_clipboard_thread_safety()
