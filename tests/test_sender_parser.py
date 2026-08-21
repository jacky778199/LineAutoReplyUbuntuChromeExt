"""
Unit test for sender parsing and whitelist matching with realistic LINE Chrome extension raw text.
"""

import os
import sys
import re

# Add project root to sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

TIME_HEADER_PATTERN = re.compile(
    r"^(?:(?:(?:上午|下午|AM|PM)\s*)?\b\d{1,2}:\d{2}(?::\d{2})?(?:\s*(?:AM|PM|上午|下午))?)\s+(.*)$",
    re.IGNORECASE
)

DATE_HEADER_PATTERN = re.compile(
    r"^(?:\d{4}[./年-]\d{1,2}[./月-]\d{1,2}(?:日)?(?:\s*星期[一二三四五六日天]|\s*\(?[一二三四五六日天]\)?)?|昨天|今天)$"
)

NOISE_PATTERNS = [
    "Your OS version doesn't support this feature.",
    "Save as...",
    "Save",
    "Share",
    "Read",
    "已讀",
    "未讀",
]

FILE_SIZE_PATTERN = re.compile(r"^(?:Size:\s*\d+(?:\.\d+)?\s*(?:KB|MB|GB)|Until:\s*)$", re.IGNORECASE)


def clean_raw_line(line: str) -> str:
    """Removes invisible zero-width unicode chars and object replacement chars."""
    if not line:
        return ""
    return (
        line.replace("\u200c", "")
        .replace("\u200b", "")
        .replace("\ufeff", "")
        .replace("\ufffc", "")
        .strip()
    )


def is_noise_line(line: str) -> bool:
    """Returns True if a line contains only placeholder symbols, file buttons, or system notices."""
    cleaned = clean_raw_line(line)
    if not cleaned:
        return True
    if cleaned in NOISE_PATTERNS:
        return True
    if FILE_SIZE_PATTERN.match(cleaned):
        return True
    if cleaned.endswith(".pdf") or cleaned.endswith(".png") or cleaned.endswith(".jpg"):
        return True
    return False


def extract_latest_sender_info(
    raw_text: str,
    whitelist: list = None,
    my_name: str = "我",
    default_name: str = "未知好友"
) -> dict:
    if not raw_text or not raw_text.strip():
        return {
            "sender": default_name,
            "is_me": False,
            "is_whitelisted": False,
            "latest_message": "",
            "matched_whitelist_item": None
        }

    raw_lines = raw_text.splitlines()
    cleaned_lines = []
    for line in raw_lines:
        c = clean_raw_line(line)
        if c and not is_noise_line(c):
            cleaned_lines.append(c)

    # 1. Global whitelist match across the full text (not restricted to [:500])
    matched_wl = None
    if whitelist:
        top_text = "\n".join(raw_lines[:100])
        for wl in whitelist:
            if wl in top_text or (len(wl) > 1 and wl.lower() in top_text.lower()):
                matched_wl = wl
                break
        if not matched_wl:
            for wl in whitelist:
                if wl in raw_text or (len(wl) > 1 and wl.lower() in raw_text.lower()):
                    matched_wl = wl
                    break

    # 2. Scan lines bottom-up to find timestamps or messages
    latest_sender = None
    is_me = False
    latest_msg_lines = []

    for i in range(len(raw_lines) - 1, -1, -1):
        line = clean_raw_line(raw_lines[i])
        if not line or is_noise_line(line):
            continue
        if DATE_HEADER_PATTERN.match(line):
            continue

        m = TIME_HEADER_PATTERN.match(line)
        if m:
            rest = m.group(1).strip()
            sender_name = None
            msg_part = ""

            if my_name and (rest == my_name or rest.startswith(my_name + " ") or rest.startswith(my_name + "\t") or rest.startswith(my_name)):
                sender_name = my_name
                msg_part = rest[len(my_name):].strip()
            else:
                for wl in (whitelist or []):
                    if rest == wl or rest.startswith(wl + " ") or rest.startswith(wl + "\t") or rest.startswith(wl):
                        sender_name = wl
                        msg_part = rest[len(wl):].strip()
                        break

            if not sender_name:
                parts = rest.split(None, 1)
                sender_name = parts[0]
                msg_part = parts[1] if len(parts) > 1 else ""

            latest_sender = sender_name
            if my_name and (sender_name == my_name or (my_name in sender_name)):
                is_me = True

            if msg_part and not is_noise_line(msg_part):
                latest_msg_lines.insert(0, msg_part)
            break
        else:
            latest_msg_lines.insert(0, line)
            if len(latest_msg_lines) >= 3:
                break

    # 3. Fallback when no standard timestamp header exists
    if not latest_sender:
        if matched_wl:
            latest_sender = matched_wl
        else:
            latest_sender = default_name

    # Determine whitelist status
    if matched_wl:
        is_whitelisted = True
    elif whitelist:
        is_whitelisted = (latest_sender in whitelist)
    else:
        is_whitelisted = True

    latest_msg_text = "\n".join(latest_msg_lines).strip()
    if not latest_msg_text and cleaned_lines:
        latest_msg_text = cleaned_lines[-1]

    if my_name and latest_msg_text.startswith(my_name + ":"):
        is_me = True

    return {
        "sender": latest_sender,
        "is_me": is_me,
        "is_whitelisted": is_whitelisted,
        "latest_message": latest_msg_text,
        "matched_whitelist_item": matched_wl
    }


def test_latest_raw_text():
    sample_path = "debug/latest_raw_text.txt"
    if not os.path.exists(sample_path):
        print(f"Sample file {sample_path} not found.")
        return

    with open(sample_path, "r", encoding="utf-8") as f:
        text = f.read()

    whitelist = ["丁竑福", "AutoReply", "Eyeyupy~"]
    res = extract_latest_sender_info(text, whitelist=whitelist, my_name="Honjay")
    print("\n================ TEST RESULT ================")
    print(f"Sender: {res['sender']}")
    print(f"Is Me: {res['is_me']}")
    print(f"Is Whitelisted: {res['is_whitelisted']}")
    print(f"Matched Whitelist Item: {res['matched_whitelist_item']}")
    print(f"Latest Message Snippet: '{res['latest_message']}'")
    print("=============================================\n")

    assert res["sender"] == "Eyeyupy~", f"Expected 'Eyeyupy~', got '{res['sender']}'"
    assert res["is_whitelisted"] is True, "Expected is_whitelisted to be True"
    assert res["is_me"] is False, "Expected is_me to be False"
    assert "Can you hear me?" in res["latest_message"], f"Expected 'Can you hear me?' in '{res['latest_message']}'"
    print("✅ All test assertions passed successfully!")


if __name__ == "__main__":
    test_latest_raw_text()
