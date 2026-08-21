"""
LINE Windows Desktop Auto-Reply Bot Main Script.
Integrates Green Dot Vision Detection, Dynamic Window Geometry, Safe Click Anchors,
Whitelist FIFO Queue, and Primary/Backup Dual LLM Auto-Response.
"""

import re
import os
import sys
import time
import random
import argparse
import logging
import yaml

# Setup default DISPLAY=:99 for Linux headless environment if not set
if sys.platform != "win32" and "DISPLAY" not in os.environ:
    os.environ["DISPLAY"] = ":99"

import pyautogui

import cv2
import numpy as np

from core.clipboard_manager import ClipboardManager
from core.vision_detector import GreenDotDetector
from core.llm_service import LLMService
from core.window_helper import LineWindowHelper
from core.environment_validator import EnvironmentValidator
from core.recovery_manager import RecoveryManager
from core.chat_logger import ChatLogger
from core.sidebar_ocr import SidebarOCR
from core.notifier import TelegramNotifier


# Setup UTF-8 encoding for Windows console
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

# Initialize Global Logger & ChatLogger
chat_logger = ChatLogger(log_dir="logs", debug_dir="debug")
logger = logging.getLogger("LineBot")


def load_config(config_path: str = "config.yaml") -> dict:
    """Loads configuration from YAML file."""
    if not os.path.exists(config_path):
        logger.error(f"Configuration file '{config_path}' not found!")
        sys.exit(1)
    
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def save_copy_failure_debug(
    scan_count: int,
    dot_pos: tuple,
    safe_chat_pos: tuple,
    clipboard_mgr: ClipboardManager,
    win_helper: LineWindowHelper,
    debug_dir: str = "debug",
    is_test: bool = False
):
    """Legacy helper: delegates diagnostic archiving to ChatLogger."""
    session_data = {
        "scan_count": scan_count,
        "is_test": is_test,
        "clipboard_diagnostics": clipboard_mgr.get_last_diagnostics() if clipboard_mgr else {},
    }
    return chat_logger.archive_failure(
        reason_code="COPY_EMPTY",
        reason_desc="無法從剪貼簿讀取對話紀錄（剪貼簿為空）",
        session_data=session_data,
        raw_text="",
        dot_pos=dot_pos,
        safe_click_pos=safe_chat_pos,
        save_screenshot=True
    )


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
    """
    Enhanced sender and message parser for LINE Desktop & Chrome Extension.
    Supports global whitelist search, noise line filtering, and bottom-up
    substantive message extraction.
    """
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

    # 3. Fallback when no standard timestamp header exists (common in Chrome extension 1-on-1 chat)
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


def extract_contact_name_from_raw_text(raw_text: str, whitelist: list, default_name: str = "未知好友") -> str:
    """Legacy compatibility helper: returns sender name using latest sender info."""
    info = extract_latest_sender_info(raw_text, whitelist=whitelist, default_name=default_name)
    return info["sender"]


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
    recovery_mgr = RecoveryManager(config)
    sidebar_ocr = SidebarOCR(cooldown_seconds=30)
    notifier = TelegramNotifier(config)

    # 0. Startup Environment Pre-flight Check
    logger.info("🔍 [環境檢測] 正在檢查畫面左側 (x < 400) 是否為正常 LINE 介面並清理多餘重複視窗...")
    recovery_mgr.cleanup_duplicate_windows(keep_latest=True)
    env_report = validator.validate_screen()
    if env_report["is_valid"]:
        logger.info(env_report["message"])
        recovery_mgr.switch_to_chat_tab()
    else:
        logger.warning(env_report["message"])
        if recovery_mgr.auto_recover:
            logger.info("🛠️ [啟動自動修復] 畫面異常，正在自動重啟 Chrome LINE 並就緒環境...")
            recovered = recovery_mgr.recover_environment(validator)
            if recovered:
                logger.info("✅ 啟動階段環境自動恢復成功！")
            else:
                logger.warning("⚠️ 啟動階段環境自動恢復失敗，將持續在背景監控重試。")

    processed_signatures = set()
    scan_count = 0
    consecutive_invalid_env = 0

    try:
        while True:
            scan_count += 1
            # 1. Detect unread green dots on screen
            unread_points = detector.find_unread_dots()

            if unread_points:
                consecutive_invalid_env = 0
                logger.info(f"🎉 發現 {len(unread_points)} 個未讀訊息綠點標籤！開始處理 (FIFO 佇列)...")

                # Capture full screen once for sidebar Zero-Click OCR pre-filtering
                screenshot_bgr, _ = detector.capture_screen()

                for (cx, cy) in unread_points:
                    session_id = f"trace_{time.strftime('%Y%m%d_%H%M%S')}_{random.randint(100, 999)}"

                    # 1.5 ZERO-CLICK WHITELIST PRE-FILTERING (點擊前 OCR 視覺白名單預判)
                    if screenshot_bgr is not None and whitelist:
                        ocr_res = sidebar_ocr.check_whitelist_zero_click(screenshot_bgr, (cx, cy), whitelist=whitelist)
                        if not ocr_res["is_whitelisted"]:
                            if not ocr_res.get("in_cooldown"):
                                rec_text = ocr_res.get('recognized_text') or '(無文字)'
                                logger.info(
                                    f"🚫 [{session_id}] [點前 OCR 攔截] 側邊欄文字: '{rec_text}' 不在白名單中！"
                                    f"【絕不點擊進入，永久保持未讀綠點/手機紅點】"
                                )
                                chat_logger.archive_failure(
                                    reason_code="ZERO_CLICK_NON_WHITELIST",
                                    reason_desc=f"點前 OCR 辨識非白名單 ('{rec_text}')，保持未讀",
                                    session_data={"session_id": session_id, "dot_pos": (cx, cy), "recognized_text": rec_text},
                                    dot_pos=(cx, cy),
                                    save_screenshot=False
                                )
                            continue
                        else:
                            logger.info(
                                f"[{session_id}] ✅ [點前 OCR 通過] 辨識出白名單對象【{ocr_res['matched_contact']}】"
                                f" (側邊欄文字: '{ocr_res['recognized_text']}'), 準備進入聊天室..."
                            )

                    logger.info(f"[{session_id}] 正在移動滑鼠點擊未讀聊天室標籤 ({cx}, {cy})...")
                    pyautogui.click(cx, cy)
                    time.sleep(2)

                    # Calculate safe focus coordinate in chat history pane
                    safe_chat_pos = win_helper.get_safe_chat_history_click_pos(detector=detector)

                    # 2. Extract chat history using safe focus click + Ctrl+A -> Ctrl+C
                    raw_text = clipboard.copy_selected_text(safe_click_pos=safe_chat_pos)
                    if not raw_text:
                        logger.warning(f"⚠️ [{session_id}] 無法從剪貼簿讀取對話紀錄（剪貼簿為空）。已儲存診斷報告與截圖，自動解除焦點...")
                        chat_logger.archive_failure(
                            reason_code="COPY_EMPTY",
                            reason_desc="無法從剪貼簿讀取對話紀錄（剪貼簿為空）",
                            session_data={"session_id": session_id, "scan_count": scan_count},
                            raw_text="",
                            dot_pos=(cx, cy),
                            safe_click_pos=safe_chat_pos
                        )
                        recovery_mgr.dismiss_accidental_tabs(validator)
                        win_helper.unfocus_chat_room(detector)
                        continue

                    # 3. Identify latest message sender & info from raw text
                    my_name = bot_cfg.get("my_name", "我")
                    sender_info = extract_latest_sender_info(raw_text, whitelist=whitelist, my_name=my_name)
                    sender_info["session_id"] = session_id
                    sender_info["scan_count"] = scan_count
                    
                    latest_sender = sender_info["sender"]
                    is_me = sender_info["is_me"]
                    is_whitelisted = sender_info["is_whitelisted"]
                    latest_msg_snippet = sender_info["latest_message"].replace("\n", " ")[:50]

                    logger.info(f"[{session_id}] 🎯 鎖定對象：【{latest_sender}】(最新訊息：'{latest_msg_snippet}') | 白名單={is_whitelisted} | 本人發言={is_me}")

                    # 4. Check if latest message was sent by myself
                    if is_me:
                        logger.info(f"[{session_id}] 最後一則訊息由自己 ({my_name}) 發出，無須回覆。自動切回聊天列表...")
                        chat_logger.archive_failure(
                            reason_code="LAST_MSG_IS_ME",
                            reason_desc=f"最後一則訊息由自己 ({my_name}) 發出，無須回覆",
                            session_data=sender_info,
                            raw_text=raw_text,
                            dot_pos=(cx, cy),
                            safe_click_pos=safe_chat_pos,
                            save_screenshot=False
                        )
                        # Telegram 手動處理通知 (已讀但自己最後一句)
                        notifier.notify_manual_action_needed(
                            contact_name=latest_sender,
                            latest_message=sender_info.get("latest_message", ""),
                            reason=f"最後一則訊息為自己 ({my_name}) 發出"
                        )
                        win_helper.unfocus_chat_room(detector)
                        continue

                    # 5. Check Whitelist (雙重保險防護)
                    if whitelist and not is_whitelisted:
                        logger.warning(f"[{session_id}] ⚠️ 對象 '{latest_sender}' 不在白名單中，跳過不處理。自動切回聊天列表...")
                        chat_logger.archive_failure(
                            reason_code="NOT_WHITELISTED",
                            reason_desc=f"對象 '{latest_sender}' 不在白名單中",
                            session_data=sender_info,
                            raw_text=raw_text,
                            dot_pos=(cx, cy),
                            safe_click_pos=safe_chat_pos,
                            save_screenshot=True
                        )
                        notifier.notify_manual_action_needed(
                            contact_name=latest_sender,
                            latest_message=sender_info.get("latest_message", ""),
                            reason="非白名單聯絡人，已開啟但未回覆"
                        )
                        win_helper.unfocus_chat_room(detector)
                        continue

                    # Prevent duplicate processing of identical recent raw text
                    text_sig = hash(raw_text[-300:])
                    if text_sig in processed_signatures:
                        logger.info(f"[{session_id}] 此對話內容近期已處理過，跳過防重複發送。自動解除焦點...")
                        chat_logger.archive_failure(
                            reason_code="DUPLICATE_TEXT",
                            reason_desc="此對話內容近期已處理過，跳過防重複發送",
                            session_data=sender_info,
                            raw_text=raw_text,
                            dot_pos=(cx, cy),
                            safe_click_pos=safe_chat_pos,
                            save_screenshot=False
                        )
                        win_helper.unfocus_chat_room(detector)
                        continue
                    processed_signatures.add(text_sig)
                    if len(processed_signatures) > 100:
                        processed_signatures.clear()

                    # 6. Generate LLM Reply targeted at latest sender
                    logger.info(f"[{session_id}] 正在針對【{latest_sender}】請求 LLM 生成回覆文字...")
                    reply_text = llm.generate_reply(raw_text, contact_name=latest_sender, sender_name=latest_sender)
                    llm_diag = llm.get_last_diagnostics()

                    if reply_text == "[NO_REPLY]":
                        logger.info(f"[{session_id}] LLM 判斷無須回覆或最後一條由自己發出。自動解除聊天室焦點...")
                        chat_logger.archive_failure(
                            reason_code="LLM_NO_REPLY",
                            reason_desc="LLM 判斷無須回覆或最後一則訊息由自己發出",
                            session_data=sender_info,
                            raw_text=raw_text,
                            llm_info=llm_diag,
                            dot_pos=(cx, cy),
                            safe_click_pos=safe_chat_pos,
                            save_screenshot=False
                        )
                        # Telegram 手動處理通知 (LLM 判斷不需回覆)
                        notifier.notify_manual_action_needed(
                            contact_name=latest_sender,
                            latest_message=sender_info.get("latest_message", ""),
                            reason="AI 判斷此訊息無須回覆或話題已結束"
                        )
                        win_helper.unfocus_chat_room(detector)
                        continue

                    logger.info(f"[{session_id}] ✨ LLM 生成回覆成功：'{reply_text}' (耗時: {llm_diag.get('duration_sec', 0)}s)")

                    # Calculate safe input box position
                    safe_input_pos = win_helper.get_input_box_click_pos()

                    # 7. Send Reply via Clipboard
                    send_success = False
                    if dry_run:
                        logger.info(f"[{session_id}] [DRY-RUN 乾執行] 不發送真實訊息。預計回覆：{reply_text}")
                        send_success = True
                    else:
                        send_success = clipboard.send_message_via_clipboard(reply_text, safe_input_pos=safe_input_pos)

                    if send_success:
                        chat_logger.log_reply_success(
                            session_id=session_id,
                            contact_name=latest_sender,
                            latest_message=sender_info.get("latest_message", ""),
                            reply_text=reply_text,
                            duration_sec=llm_diag.get("duration_sec", 0.0),
                            provider=llm_diag.get("provider", ""),
                            model_name=llm_diag.get("model", "")
                        )
                    else:
                        logger.error(f"[{session_id}] ❌ 訊息貼上與送出失敗！")
                        chat_logger.archive_failure(
                            reason_code="SEND_FAILED",
                            reason_desc="訊息貼上或 Enter 發送失敗",
                            session_data=sender_info,
                            raw_text=raw_text,
                            llm_info=llm_diag,
                            dot_pos=(cx, cy),
                            safe_click_pos=safe_input_pos,
                            save_screenshot=True
                        )
                        notifier.notify_error_alert(
                            reason_code="SEND_FAILED",
                            details=f"回覆對象【{latest_sender}】時訊息發送失敗！"
                        )

                    # 8. Unfocus active chat room
                    logger.info(f"[{session_id}] 點擊 Message Icon 並按下 ESC 解除聊天室焦點，確保新訊息可顯示綠點...")
                    win_helper.unfocus_chat_room(detector)

                    # 9. Random delay to simulate human typing & prevent rate limits
                    delay = random.uniform(delay_min, delay_max)
                    logger.info(f"隨機延遲 {delay:.2f} 秒，準備進行下一次掃描...")
                    time.sleep(delay)
            else:
                # 印出持續掃描訊息 (每 5 次掃描/10 秒印出一次)
                if scan_count % 5 == 1:
                    logger.info("👀 正在持續掃描螢幕畫面，等待 LINE 新訊息綠點...（目前無未讀訊息）")

                # 每 15 次掃描 (約 30 秒) 進行一次畫面健康檢查與視窗去重
                if scan_count % 15 == 0:
                    recovery_mgr.cleanup_duplicate_windows(keep_latest=True)
                    chk = validator.validate_screen()
                    if not chk["is_valid"]:
                        consecutive_invalid_env += 1
                        logger.warning(
                            f"⚠️ [環境監控警告 (連續 {consecutive_invalid_env} 次)] "
                            f"畫面左側 (x < 400) LINE 介面異常: {'; '.join(chk['warnings'])}"
                        )

                        if recovery_mgr.auto_recover and (consecutive_invalid_env >= 2 or not chk.get("is_non_blank", True)):
                            logger.info("🚨 偵測到環境持續異常或黑畫面，立即觸發自動恢復 (Auto-Recovery)...")
                            if recovery_mgr.recover_environment(validator):
                                logger.info("🎉 環境自動恢復完成！繼續監控綠點...")
                                consecutive_invalid_env = 0
                            else:
                                logger.error("⚠️ 本次環境自動恢復未能成功，將於下個週期繼續重試。")
                    else:
                        consecutive_invalid_env = 0

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


def test_environment_recovery(config: dict):
    """Runs a one-shot environment recovery test."""
    print("\n==================================================")
    print(" 🛠️ 正在執行 Chrome LINE 環境自動恢復與全螢幕測試...")
    print("==================================================")
    validator = EnvironmentValidator(left_roi_width=400, anchor_confidence_threshold=0.55)
    recovery_mgr = RecoveryManager(config)
    success = recovery_mgr.recover_environment(validator)
    if success:
        print("\n✅ 環境恢復與全螢幕測試成功！")
    else:
        print("\n❌ 環境恢復測試失敗，請檢查日誌與 VNC 畫面。")
    print("==================================================\n")


def test_telegram_notification(config: dict):
    """Tests Telegram Bot notification connection."""
    from core.notifier import TelegramNotifier
    print("\n==================================================")
    print(" 📱 正在測試 Telegram Bot 連線與通知發送...")
    print("==================================================")
    notifier = TelegramNotifier(config)
    res = notifier.test_connection()
    if res.get("status") == "SUCCESS":
        print(f"✅ Telegram 連線測試成功！Bot 名稱: @{res.get('bot_name')}")
        print("   💬 已向您的 Telegram 帳號發送測試訊息。")
    else:
        print(f"❌ Telegram 連線測試失敗: {res.get('error')}")
    print("==================================================\n")


def main():
    parser = argparse.ArgumentParser(description="LINE Windows Desktop Auto-Reply Bot")
    parser.add_argument("--config", default="config.yaml", help="Path to config.yaml file")
    parser.add_argument("--dry-run", action="store_true", help="Run without actually sending messages")
    parser.add_argument("--debug", action="store_true", help="Enable verbose debug logging and image dumping")
    parser.add_argument("--test-vision", action="store_true", help="Diagnose screen capture, template matching scores & save debug images")
    parser.add_argument("--test-recover", action="store_true", help="Test Chrome LINE extension auto-recovery, login & fullscreen")
    parser.add_argument("--test-notify", action="store_true", help="Test Telegram Bot notification connection")
    parser.add_argument("--generate-template", action="store_true", help="Generate default green dot template image")
    parser.add_argument("--test-llm", action="store_true", help="Test LLM connection with dummy chat history")

    args = parser.parse_args()

    if args.generate_template:
        detector = GreenDotDetector(template_path="assets/green_dot_template.png")
        print("Template generated at 'assets/green_dot_template.png'.")
        return

    config = load_config(args.config)

    if args.test_notify:
        test_telegram_notification(config)
        return

    if args.test_recover:
        test_environment_recovery(config)
        return


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

