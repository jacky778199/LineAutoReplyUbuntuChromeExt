"""
Test for Configuration and Persona Prompt Lookup.
"""

import os
import sys
import yaml

if sys.platform != "win32" and "DISPLAY" not in os.environ:
    os.environ["DISPLAY"] = ":99"

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from main import load_config
from core.llm_service import LLMService

def test_config_loading():
    config = load_config("config.yaml")
    assert "llm" in config
    assert "bot" in config
    assert "ui" in config
    assert "provider" in config["llm"]["primary"]
    assert "provider" in config["llm"]["backup"]
    print("test_config_loading PASSED!")

def test_persona_prompt_resolution():
    config = load_config("config.yaml")
    llm = LLMService(config)

    # Test default prompt resolution
    default_prompt = llm._get_system_prompt_for_contact("RandomFriend")
    assert len(default_prompt) > 0

    # Test specific contact prompt resolution if defined
    ding_prompt = llm._get_system_prompt_for_contact("丁竑福")
    assert len(ding_prompt) > 0

    eye_prompt = llm._get_system_prompt_for_contact("Eyeyupy~")
    assert len(eye_prompt) > 0

    print("test_persona_prompt_resolution PASSED!")


def test_extract_latest_sender_info():
    from main import extract_latest_sender_info, extract_contact_name_from_raw_text

    raw_sample = """
15:17 Rita💕陳(蓮兒) 調度阿郎他老婆
現在是借R牌
她自己買車
因為她還沒有拿到營業登記證
15:18 Rita💕陳(蓮兒) 圖片
15:18 Rita💕陳(蓮兒) 麵包剛傳來
15:58 丁竑福 貼圖
15:58 HonJay Ding 用貼圖敷衍得這麼自然，看來你已經做好月入八萬然後過勞死的準備了。
16:05 Rita💕陳(蓮兒) ？隱私權
不用怕過勞
自由
你可以選擇不接單
2026.08.19 星期三
14:20 HonJay Ding 咦 有bug 我回去看看情況
"""
    whitelist = ["丁竑福", "Rita💕陳(蓮兒)", "Eyeyupy~"]
    my_name = "HonJay Ding"

    # 1. Test when latest is me (HonJay Ding)
    info1 = extract_latest_sender_info(raw_sample, whitelist=whitelist, my_name=my_name)
    assert info1["sender"] == "HonJay Ding"
    assert info1["is_me"] is True
    assert "咦 有bug" in info1["latest_message"]

    # 2. Test when latest is Rita (multi-line)
    sample2 = """
15:58 HonJay Ding 哈哈
16:05 Rita💕陳(蓮兒) ？隱私權
不用怕過勞
自由
你可以選擇不接單
"""
    info2 = extract_latest_sender_info(sample2, whitelist=whitelist, my_name=my_name)
    assert info2["sender"] == "Rita💕陳(蓮兒)"
    assert info2["is_me"] is False
    assert info2["is_whitelisted"] is True
    assert "不用怕過勞" in info2["latest_message"]

    # 3. Test when latest is 丁竑福
    sample3 = """
15:58 HonJay Ding 哈哈
16:05 丁竑福 晚上去吃火鍋嗎？
"""
    info3 = extract_latest_sender_info(sample3, whitelist=whitelist, my_name=my_name)
    assert info3["sender"] == "丁竑福"
    assert info3["is_me"] is False
    assert info3["is_whitelisted"] is True
    assert info3["latest_message"] == "晚上去吃火鍋嗎？"

    # 4. Test when latest is non-whitelisted user (張三)
    sample4 = """
15:58 HonJay Ding 哈哈
16:05 張三 這是其他人的發言
"""
    info4 = extract_latest_sender_info(sample4, whitelist=whitelist, my_name=my_name)
    assert info4["sender"] == "張三"
    assert info4["is_me"] is False
    assert info4["is_whitelisted"] is False

    # 5. Test legacy compatibility helper
    contact = extract_contact_name_from_raw_text(sample3, whitelist=whitelist)
    assert contact == "丁竑福"

    print("test_extract_latest_sender_info PASSED!")


if __name__ == "__main__":
    test_config_loading()
    test_persona_prompt_resolution()
    test_extract_latest_sender_info()
