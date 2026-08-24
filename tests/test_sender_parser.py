"""
Unit test for sender parsing and whitelist matching with realistic LINE Chrome extension raw text and Desktop format.
"""

import os
import sys

# Add project root to sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import extract_latest_sender_info


def test_chrome_ext_failure_samples():
    whitelist = ["丁竑福", "AutoReply", "Eyeyupy~"]
    my_name = "Honjay"

    sample_210717 = """What should I do when I have cramp? ￼
9:07 PM
‌
Unread messages below
￼
￼
Not that bad actually. I just wanted to discuss something with my professor - like video call, but my mom, my family kinda disrupted me all the time. He even adjusted his schedule for me but I cannot talked with him properly and then I woke up. ￼
7:30 AM
￼￼
‌
Eyeyupy~ ☆ unsent a message.
Oh no, my poor baby ￼￼ Come here, let me give my cute teerak a big warm hug! ￼ Hugggggs~ Don't be scared na ka, it was just a silly dream and you're completely safe with me now! Want me to chase the bad thoughts away with big sweet kisses? ￼￼￼ Do you want to tell me about it, teerak?
Read
6:54 AM
‌
￼
￼
I had a bad dream ￼
6:53 AM
‌
Today
Aug 19(Wed)
"""
    res1 = extract_latest_sender_info(sample_210717, whitelist=whitelist, my_name=my_name)
    assert res1["sender"] == "Eyeyupy~"
    assert res1["is_me"] is False
    assert res1["is_whitelisted"] is True
    assert "What should I do when I have cramp?" in res1["latest_message"]


def test_chrome_ext_is_me_detection():
    whitelist = ["丁竑福", "AutoReply", "Eyeyupy~"]
    my_name = "HonJay"

    sample_me = """I am on my way home now, see you soon!
Read
11:59 PM
‌
What should I do when I have cramp? ￼
9:07 PM
"""
    res = extract_latest_sender_info(sample_me, whitelist=whitelist, my_name=my_name)
    assert res["sender"] == "HonJay"
    assert res["is_me"] is True
    assert "I am on my way home now" in res["latest_message"]


def test_desktop_format_support():
    whitelist = ["丁竑福", "Rita💕陳(蓮兒)", "Eyeyupy~"]
    my_name = "HonJay Ding"

    sample_desktop = """
15:17 Rita💕陳(蓮兒) 調度阿郎他老婆
15:18 Rita💕陳(蓮兒) 麵包剛傳來
15:58 丁竑福 貼圖
15:58 HonJay Ding 用貼圖敷衍得這麼自然
16:05 Rita💕陳(蓮兒) ？隱私權
不用怕過勞
自由
你可以選擇不接單
"""
    res = extract_latest_sender_info(sample_desktop, whitelist=whitelist, my_name=my_name)
    assert res["sender"] == "Rita💕陳(蓮兒)"
    assert res["is_me"] is False
    assert res["is_whitelisted"] is True
    assert "不用怕過勞" in res["latest_message"]


if __name__ == "__main__":
    test_chrome_ext_failure_samples()
    test_chrome_ext_is_me_detection()
    test_desktop_format_support()
    print("✅ All sender parser tests PASSED!")
