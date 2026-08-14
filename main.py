"""
LINE Windows Desktop Auto-Reply Bot Main Script.
Integrates Green Dot Vision Detection, Dynamic Window Geometry, Safe Click Anchors,
Whitelist FIFO Queue, and Primary/Backup Dual LLM Auto-Response.
"""

import os
import sys
import time
import random
import argparse
import logging
import yaml
import pyautogui

from core.clipboard_manager import ClipboardManager
from core.vision_detector import GreenDotDetector
from core.llm_service import LLMService
from core.window_helper import LineWindowHelper
from core.environment_validator import EnvironmentValidator

# Setup default DISPLAY=:99 for Linux headless environment if not set
if sys.platform != "win32" and "DISPLAY" not in os.environ:
    os.environ["DISPLAY"] = ":99"

# Setup UTF-8 encoding for Windows console
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

# Setup Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("bot.log", encoding="utf-8")
    ]
)
logger = logging.getLogger("LineBot")


def load_config(config_path: str = "config.yaml") -> dict:
    """Loads configuration from YAML file."""
    if not os.path.exists(config_path):
        logger.error(f"Configuration file '{config_path}' not found!")
        sys.exit(1)
    
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def extract_contact_name_from_raw_text(raw_text: str, whitelist: list, default_name: str = "未知好友") -> str:
    """
    Attempts to identify which whitelisted contact is in the raw copied chat log text.
    Returns the matched contact name, or default_name.
    """
    if not raw_text:
        return default_name

    # Check if any whitelisted name appears in the first few lines of raw text
    for contact in whitelist:
        if contact in raw_text[:500]:
            return contact
            
    return default_name


def run_bot(config: dict, dry_run: bool = False, debug: bool = False):
    """Main execution loop for LINE Auto-Reply Bot."""
    bot_cfg = config.get("bot", {})
    ui_cfg = config.get("ui", {})
    
    whitelist = bot_cfg.get("whitelist", [])
    confidence = ui_cfg.get("green_dot_confidence", 0.65)
    template_path = ui_cfg.get("green_dot_template_path", "assets/green_dot_white_x.png")
    min_blob_area = ui_cfg.get("green_blob_min_area", 248)
    max_blob_area = ui_cfg.get("green_blob_max_area", 356)
    detection_mode = ui_cfg.get("detection_mode", "hybrid")
    delay_min = ui_cfg.get("response_delay_min", 1.5)
    delay_max = ui_cfg.get("response_delay_max", 3.0)

    logger.info("==================================================")
    logger.info(" Starting LINE Auto-Reply Bot ")
    logger.info(f" Whitelist: {whitelist}")
    logger.info(f" Dry Run Mode: {dry_run}")
    logger.info(f" Debug Mode: {debug}")
    logger.info(f" Detection Mode: {detection_mode}")
    logger.info(f" Green Blob Area: {min_blob_area}px ~ {max_blob_area}px")
    logger.info(f" Template Path: {template_path}")
    logger.info(f" Confidence Threshold: {confidence}")
    logger.info("==================================================")

    # Initialize components
    validator = EnvironmentValidator(left_roi_width=400, anchor_confidence_threshold=0.55)
    detector = GreenDotDetector(
        template_path=template_path,
        confidence=confidence,
        debug=debug,
        min_blob_area=min_blob_area,
        max_blob_area=max_blob_area,
        detection_mode=detection_mode
    )
    clipboard = ClipboardManager()
    llm = LLMService(config)
    win_helper = LineWindowHelper()

    # 0. Startup Environment Pre-flight Check (畫面左側 400px 基準檢測)
    logger.info("🔍 [環境檢測] 正在檢查畫面左側 (x < 400) 是否為正常 LINE 介面...")
    env_report = validator.validate_screen()
    if env_report["is_valid"]:
        logger.info(env_report["message"])
    else:
        logger.warning(env_report["message"])

    processed_signatures = set()
    scan_count = 0

    try:
        while True:
            scan_count += 1
            # 1. Detect unread green dots on screen
            unread_points = detector.find_unread_dots()

            if unread_points:
                logger.info(f"🎉 發現 {len(unread_points)} 個未讀訊息綠點標籤！開始處理 (FIFO 佇列)...")

                for (cx, cy) in unread_points:
                    logger.info(f"正在移動滑鼠點擊未讀聊天室標籤 ({cx}, {cy})...")
                    pyautogui.click(cx, cy)
                    time.sleep(0.5)

                    # Calculate safe focus coordinate in chat history pane (far right background, avoiding links/videos)
                    safe_chat_pos = win_helper.get_safe_chat_history_click_pos()

                    # 2. Extract chat history using safe focus click + Ctrl+A -> Ctrl+C
                    raw_text = clipboard.copy_selected_text(safe_click_pos=safe_chat_pos)
                    if not raw_text:
                        logger.warning("無法從剪貼簿讀取對話紀錄（可能點擊位置非對話區域）。自動解除焦點...")
                        if debug:
                            print(raw_text)
                        win_helper.unfocus_chat_room(detector)
                        continue

                    # 3. Identify contact name from raw text
                    contact_name = extract_contact_name_from_raw_text(raw_text, whitelist)
                    logger.info(f"偵測到聊天室對象：{contact_name}")

                    # 4. Check Whitelist
                    if whitelist and contact_name not in whitelist:
                        logger.info(f"對象 '{contact_name}' 不在白名單中，跳過不處理。自動切回聊天列表...")
                        win_helper.unfocus_chat_room(detector)
                        continue

                    # Prevent duplicate processing of identical recent raw text
                    text_sig = hash(raw_text[-300:])
                    if text_sig in processed_signatures:
                        logger.info("此對話內容近期已處理過，跳過防重複發送。自動解除焦點...")
                        win_helper.unfocus_chat_room(detector)
                        continue
                    processed_signatures.add(text_sig)
                    if len(processed_signatures) > 100:
                        processed_signatures.clear()

                    # 5. Generate LLM Reply
                    logger.info("正在請求 LLM 生成回覆文字...")
                    reply_text = llm.generate_reply(raw_text, contact_name)

                    if reply_text == "[NO_REPLY]":
                        logger.info("LLM 判斷最後一條訊息由自己發出或無須回覆。自動解除聊天室焦點...")
                        win_helper.unfocus_chat_room(detector)
                        continue

                    logger.info(f"LLM 生成回覆成功：'{reply_text}'")

                    # Calculate safe input box position
                    safe_input_pos = win_helper.get_input_box_click_pos()

                    # 6. Send Reply via Clipboard
                    if dry_run:
                        logger.info(f"[DRY-RUN 乾執行] 不發送真實訊息。預計回覆：{reply_text}")
                    else:
                        clipboard.send_message_via_clipboard(reply_text, safe_input_pos=safe_input_pos)

                    # 7. Unfocus active chat room (Click Message_icon.png + Press ESC) to ensure new messages show green dot
                    logger.info("點擊 Message Icon 並按下 ESC 解除聊天室焦點，確保新訊息可顯示綠點...")
                    win_helper.unfocus_chat_room(detector)

                    # 8. Random delay to simulate human typing & prevent rate limits
                    delay = random.uniform(delay_min, delay_max)
                    logger.info(f"隨機延遲 {delay:.2f} 秒，準備進行下一次掃描...")
                    time.sleep(delay)
            else:
                # 印出持續掃描訊息 (每 5 次掃描/10 秒印出一次，讓使用者知道程式運作中)
                if scan_count % 5 == 1:
                    logger.info("👀 正在持續掃描螢幕畫面，等待 LINE 新訊息綠點...（目前無未讀訊息）")

                # 每 30 次掃描 (約 60 秒) 進行一次畫面左側 (x < 400) 靜態健康檢查，防止 LINE 視窗被關閉或最小化
                if scan_count % 30 == 0:
                    chk = validator.validate_screen()
                    if not chk["is_valid"]:
                        logger.warning(f"⚠️ [環境監控警告] 畫面左側 (x < 400) LINE 介面異常: {'; '.join(chk['warnings'])}")

            # Sleep briefly before next scan iteration
            time.sleep(2.0)

    except KeyboardInterrupt:
        logger.info("Bot stopped by user (KeyboardInterrupt). Exiting...")
    except Exception as e:
        logger.critical(f"Unexpected error in bot main loop: {e}", exc_info=True)


def test_vision_diagnostics(config: dict):
    """Runs a one-shot vision diagnostic test to inspect screenshot & template match results."""
    from test_vision import run_vision_test
    print("\n🔍 正在執行影像辨識診斷分析...")
    run_vision_test(config)


def main():
    parser = argparse.ArgumentParser(description="LINE Windows Desktop Auto-Reply Bot")
    parser.add_argument("--config", default="config.yaml", help="Path to config.yaml file")
    parser.add_argument("--dry-run", action="store_true", help="Run without actually sending messages")
    parser.add_argument("--debug", action="store_true", help="Enable verbose debug logging and image dumping")
    parser.add_argument("--test-vision", action="store_true", help="Diagnose screen capture, template matching scores & save debug images")
    parser.add_argument("--generate-template", action="store_true", help="Generate default green dot template image")
    parser.add_argument("--test-llm", action="store_true", help="Test LLM connection with dummy chat history")

    args = parser.parse_args()

    if args.generate_template:
        detector = GreenDotDetector(template_path="assets/green_dot_template.png")
        print("Template generated at 'assets/green_dot_template.png'.")
        return

    config = load_config(args.config)

    if args.test_vision:
        test_vision_diagnostics(config)
        return

    if args.test_llm:
        print("\n==================================================")
        print(" 🧪 正在獨立測試雙 LLM 引擎連線狀態...")
        print("==================================================")
        llm = LLMService(config)
        results = llm.test_connection()
        
        print("\n==================================================")
        print(" 📊 雙 LLM 連線測試總結報表")
        print("==================================================")
        for key in ["primary", "backup"]:
            res = results.get(key, {})
            name = "主要模型 (Primary)" if key == "primary" else "備用模型 (Backup)"
            status = res.get("status", "UNKNOWN")
            prov = res.get("provider", "")
            
            if status == "SUCCESS":
                sec = res.get("duration_sec", 0)
                reply = res.get("reply", "")
                print(f"✅ {name}: 【{status}】 ({sec}s) - {prov}")
                print(f"   💬 回覆範例: {reply}")
            else:
                err = res.get("error", "未知錯誤")
                print(f"❌ {name}: 【{status}】 - {prov}")
                print(f"   ⚠️ 失敗原因: {err}")
        print("==================================================\n")
        return

    run_bot(config, dry_run=args.dry_run, debug=args.debug)


if __name__ == "__main__":
    main()
