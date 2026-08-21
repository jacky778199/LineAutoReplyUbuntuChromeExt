"""
Test script to verify chat_logger archiving and rotating logs.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.chat_logger import ChatLogger

def test_chat_logger():
    logger = ChatLogger(log_dir="logs", debug_dir="debug")
    
    # 1. Test success log
    logger.log_reply_success(
        session_id="trace_test_001",
        contact_name="Eyeyupy~",
        latest_message="Can you hear me?",
        reply_text="Yes babe, I can hear you loud and clear! ❤️",
        duration_sec=2.15,
        provider="vertex_ai",
        model_name="gemini-3.6-flash"
    )
    assert os.path.exists("logs/reply_history.log")
    
    # 2. Test failure archive
    archive_dir = logger.archive_failure(
        reason_code="TEST_FAILURE",
        reason_desc="This is an automated test diagnostic archive",
        session_data={"session_id": "trace_test_001", "scan_count": 999},
        raw_text="Sample Raw Chat Line 1\nSample Raw Chat Line 2",
        llm_info={"prompt": "Test Prompt", "raw_reply": "[NO_REPLY]", "duration_sec": 1.2},
        dot_pos=(300, 200),
        safe_click_pos=(600, 400),
        save_screenshot=False
    )
    assert os.path.exists(archive_dir), f"Archive directory {archive_dir} should exist"
    assert os.path.exists(os.path.join(archive_dir, "summary.json"))
    assert os.path.exists(os.path.join(archive_dir, "raw_chat.txt"))
    assert os.path.exists(os.path.join(archive_dir, "prompt_and_llm.txt"))
    print("✅ ChatLogger test passed successfully!")

if __name__ == "__main__":
    test_chat_logger()
