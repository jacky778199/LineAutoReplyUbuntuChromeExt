"""
Chat Logger and Diagnostic Archiver for LINE Auto-Reply Bot.
Provides rotating log files, reply history logging, and automated diagnostic
archiving for failures and skipped reply events.
"""

import os
import sys
import time
import json
import logging
from logging.handlers import RotatingFileHandler
from typing import Dict, Any, Optional

import cv2
import numpy as np

if sys.platform != "win32" and "DISPLAY" not in os.environ:
    os.environ["DISPLAY"] = ":99"

import pyautogui


class ChatLogger:
    """Manages application logging and failure diagnostic packet archiving."""

    def __init__(self, log_dir: str = "logs", debug_dir: str = "debug", max_failures_to_keep: int = 100):
        self.log_dir = log_dir
        self.debug_dir = debug_dir
        self.failures_dir = os.path.join(log_dir, "failures")
        self.max_failures_to_keep = max_failures_to_keep

        os.makedirs(self.log_dir, exist_ok=True)
        os.makedirs(self.debug_dir, exist_ok=True)
        os.makedirs(self.failures_dir, exist_ok=True)

        self._setup_logging()
        self._setup_reply_history_logger()

    def _setup_logging(self):
        """Sets up rotating file logger for general bot execution."""
        log_file = os.path.join(self.log_dir, "bot.log")
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.INFO)

        # Clear existing file handlers to prevent duplicate lines
        for handler in list(root_logger.handlers):
            if isinstance(handler, (logging.FileHandler, RotatingFileHandler)):
                root_logger.removeHandler(handler)

        formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

        # Rotating file handler: 5MB max size, 5 backups
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=5 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8"
        )
        file_handler.setFormatter(formatter)
        file_handler.setLevel(logging.INFO)
        root_logger.addHandler(file_handler)

        # Ensure StreamHandler exists
        has_stream = any(
            isinstance(h, logging.StreamHandler) and not isinstance(h, (logging.FileHandler, RotatingFileHandler))
            for h in root_logger.handlers
        )
        if not has_stream:
            stream_handler = logging.StreamHandler(sys.stdout)
            stream_handler.setFormatter(formatter)
            stream_handler.setLevel(logging.INFO)
            root_logger.addHandler(stream_handler)

    def _setup_reply_history_logger(self):
        """Sets up dedicated logger for successful auto-replies."""
        history_file = os.path.join(self.log_dir, "reply_history.log")
        self.reply_logger = logging.getLogger("ReplyHistory")
        self.reply_logger.setLevel(logging.INFO)
        self.reply_logger.propagate = False

        formatter = logging.Formatter("%(asctime)s | %(message)s")
        handler = RotatingFileHandler(
            history_file,
            maxBytes=5 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8"
        )
        handler.setFormatter(formatter)
        self.reply_logger.addHandler(handler)

    def log_reply_success(
        self,
        session_id: str,
        contact_name: str,
        latest_message: str,
        reply_text: str,
        duration_sec: float,
        provider: str = "",
        model_name: str = ""
    ):
        """Records a successful auto-reply to reply_history.log."""
        clean_msg = latest_message.replace("\n", " ")[:60]
        clean_reply = reply_text.replace("\n", " ")
        log_line = (
            f"[SUCCESS] ID:{session_id} | 對象:【{contact_name}】 | "
            f"最新訊息: '{clean_msg}' | "
            f"回覆內容: '{clean_reply}' | "
            f"模型: {provider}({model_name}) | 耗時: {duration_sec:.2f}s"
        )
        self.reply_logger.info(log_line)
        logging.getLogger("LineBot").info(f"💾 已記錄回覆歷程至: {os.path.join(self.log_dir, 'reply_history.log')}")

    def capture_annotated_screenshot(
        self,
        dot_pos: tuple = None,
        safe_click_pos: tuple = None,
        banner_text: str = ""
    ) -> Optional[np.ndarray]:
        """Captures screen and draws annotated markers for dot and click positions."""
        try:
            pil_img = pyautogui.screenshot()
            img_cv = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
            annotated = img_cv.copy()
            h, w = annotated.shape[:2]

            # Mark unread dot (Red)
            if dot_pos and len(dot_pos) == 2:
                dx, dy = int(dot_pos[0]), int(dot_pos[1])
                cv2.circle(annotated, (dx, dy), 16, (0, 0, 255), 2)
                cv2.circle(annotated, (dx, dy), 3, (0, 0, 255), -1)
                cv2.putText(annotated, f"Dot: ({dx},{dy})", (dx + 18, dy - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)

            # Mark safe click position (Orange)
            if safe_click_pos and len(safe_click_pos) == 2:
                sx, sy = int(safe_click_pos[0]), int(safe_click_pos[1])
                cv2.circle(annotated, (sx, sy), 16, (0, 140, 255), 2)
                cv2.drawMarker(annotated, (sx, sy), (0, 140, 255), markerType=cv2.MARKER_CROSS, markerSize=24, thickness=2)
                cv2.putText(annotated, f"Focus: ({sx},{sy})", (max(10, sx - 130), max(20, sy - 15)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 140, 255), 2)

            # Draw banner header
            if banner_text:
                cv2.rectangle(annotated, (0, 0), (w, 40), (0, 0, 180), -1)
                cv2.putText(annotated, banner_text[:80], (15, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 2)

            return annotated
        except Exception as e:
            logging.getLogger("LineBot").warning(f"截圖與標註發生異常: {e}")
            return None

    def archive_failure(
        self,
        reason_code: str,
        reason_desc: str,
        session_data: Dict[str, Any],
        raw_text: str = "",
        llm_info: Dict[str, Any] = None,
        dot_pos: tuple = None,
        safe_click_pos: tuple = None,
        save_screenshot: bool = True
    ) -> str:
        """
        Creates a dedicated timestamped failure archive folder containing:
        - summary.json: Full structured diagnostics
        - raw_chat.txt: Complete raw copied text
        - prompt_and_llm.txt: LLM prompt, responses, errors (if any)
        - screenshot.png: Annotated screen capture
        """
        logger = logging.getLogger("LineBot")
        timestamp_slug = time.strftime("%Y%m%d_%H%M%S")
        safe_reason = reason_code.replace(" ", "_").upper()
        folder_name = f"{timestamp_slug}_{safe_reason}"
        archive_path = os.path.join(self.failures_dir, folder_name)

        try:
            os.makedirs(archive_path, exist_ok=True)

            # 1. Prepare Summary JSON
            summary = {
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "failure_reason_code": reason_code,
                "failure_description": reason_desc,
                "session": session_data,
                "dot_position": dot_pos,
                "safe_click_position": safe_click_pos,
                "raw_text_length": len(raw_text) if raw_text else 0,
                "llm_summary": {
                    "provider": llm_info.get("provider") if llm_info else None,
                    "model": llm_info.get("model") if llm_info else None,
                    "raw_reply": llm_info.get("raw_reply") if llm_info else None,
                    "error": llm_info.get("error") if llm_info else None,
                    "duration_sec": llm_info.get("duration_sec") if llm_info else None
                } if llm_info else None
            }

            with open(os.path.join(archive_path, "summary.json"), "w", encoding="utf-8") as f:
                json.dump(summary, f, ensure_ascii=False, indent=2)

            # 2. Save Raw Chat Text
            with open(os.path.join(archive_path, "raw_chat.txt"), "w", encoding="utf-8") as f:
                f.write(raw_text if raw_text else "(剪貼簿未取得對話文字 / Empty Text)")

            # Also update debug/latest_raw_text.txt
            try:
                with open(os.path.join(self.debug_dir, "latest_raw_text.txt"), "w", encoding="utf-8") as f_latest:
                    f_latest.write(f"Timestamp: {summary['timestamp']}\n")
                    f_latest.write(f"Reason: {reason_code} - {reason_desc}\n")
                    f_latest.write(f"Dot Pos: {dot_pos}\n")
                    f_latest.write(f"Raw Text:\n{raw_text}\n")
            except Exception:
                pass

            # 3. Save Prompt and LLM details if available
            if llm_info and (llm_info.get("prompt") or llm_info.get("raw_reply") or llm_info.get("error")):
                llm_log_path = os.path.join(archive_path, "prompt_and_llm.txt")
                with open(llm_log_path, "w", encoding="utf-8") as f:
                    f.write("=" * 80 + "\n")
                    f.write("LLM PROMPT & DIAGNOSTICS\n")
                    f.write("=" * 80 + "\n\n")
                    f.write(f"Provider: {llm_info.get('provider')}\n")
                    f.write(f"Model: {llm_info.get('model')}\n")
                    f.write(f"Duration: {llm_info.get('duration_sec')}s\n")
                    if llm_info.get("error"):
                        f.write(f"Error: {llm_info.get('error')}\n\n")
                    f.write("--- [SYSTEM & USER PROMPT] ---\n")
                    f.write(str(llm_info.get("prompt", "")) + "\n\n")
                    f.write("--- [MODEL RESPONSE] ---\n")
                    f.write(str(llm_info.get("raw_reply", "")) + "\n")

            # 4. Save Annotated Screenshot
            if save_screenshot:
                banner = f"[{reason_code}] {reason_desc} ({summary['timestamp']})"
                img = self.capture_annotated_screenshot(
                    dot_pos=dot_pos,
                    safe_click_pos=safe_click_pos,
                    banner_text=banner
                )
                if img is not None:
                    img_path = os.path.join(archive_path, "screenshot.png")
                    cv2.imwrite(img_path, img)
                    # Update debug/latest_failure.png
                    cv2.imwrite(os.path.join(self.debug_dir, "latest_failure.png"), img)

            logger.info(f"📁 診斷報告與除錯檔案已自動歸檔至: {archive_path}")

            # 5. Clean older failure archives if exceeding limit
            self._cleanup_old_archives()

            return archive_path

        except Exception as e:
            logger.error(f"歸檔失敗資訊時發生例外: {e}", exc_info=True)
            return ""

    def _cleanup_old_archives(self):
        """Keeps failures directory tidy by keeping only the most recent N archives."""
        try:
            entries = [
                os.path.join(self.failures_dir, d)
                for d in os.listdir(self.failures_dir)
                if os.path.isdir(os.path.join(self.failures_dir, d))
            ]
            if len(entries) > self.max_failures_to_keep:
                entries.sort(key=os.path.getmtime)
                to_delete = entries[:-self.max_failures_to_keep]
                for p in to_delete:
                    import shutil
                    shutil.rmtree(p, ignore_errors=True)
        except Exception:
            pass
