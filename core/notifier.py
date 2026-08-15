"""
Telegram Notification Service for LINE Auto-Reply Bot.
Handles sending alerts, status updates, and PC verification screenshots to Telegram.
"""

import os
import logging
import requests

logger = logging.getLogger(__name__)


class TelegramNotifier:
    """Sends messages and image alerts to Telegram Bot."""

    def __init__(self, config: dict = None):
        self.config = config or {}
        notify_cfg = self.config.get("notification", {})

        self.enabled = notify_cfg.get("enabled", True)
        self.bot_token = os.environ.get("TELEGRAM_BOT_TOKEN") or notify_cfg.get("telegram_bot_token", "")
        self.chat_id = str(os.environ.get("TELEGRAM_CHAT_ID") or notify_cfg.get("telegram_chat_id", ""))
        self.verification_timeout = notify_cfg.get("verification_timeout", 90)

    def is_configured(self) -> bool:
        """Returns True if both bot_token and chat_id are present."""
        return bool(self.bot_token and self.chat_id)

    def send_message(self, text: str) -> bool:
        """Sends a text message to Telegram chat."""
        if not self.enabled:
            logger.debug("Telegram 通知已停用。")
            return False

        if not self.is_configured():
            logger.debug("Telegram Bot Token 或 Chat ID 未設定，略過傳送。")
            return False

        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "HTML"
        }

        try:
            res = requests.post(url, json=payload, timeout=10)
            if res.status_code == 200:
                logger.info("📤 Telegram 文字通知發送成功！")
                return True
            else:
                logger.error(f"❌ Telegram 發送失敗: HTTP {res.status_code} - {res.text}")
                return False
        except Exception as e:
            logger.error(f"❌ Telegram 連線異常: {e}")
            return False

    def send_photo(self, photo_path: str, caption: str = "") -> bool:
        """Sends a photo file to Telegram chat with optional caption."""
        if not self.enabled:
            logger.debug("Telegram 通知已停用。")
            return False

        if not self.is_configured():
            logger.warning("⚠️ Telegram Bot Token 或 Chat ID 未設定，無法發送截圖通知！")
            return False

        if not os.path.exists(photo_path):
            logger.error(f"❌ 欲發送之截圖檔案不存在: {photo_path}")
            return False

        url = f"https://api.telegram.org/bot{self.bot_token}/sendPhoto"
        data = {
            "chat_id": self.chat_id,
            "caption": caption
        }

        try:
            with open(photo_path, "rb") as f:
                files = {"photo": f}
                res = requests.post(url, data=data, files=files, timeout=20)

            if res.status_code == 200:
                logger.info(f"📸 Telegram 截圖通知發送成功: {photo_path}")
                return True
            else:
                logger.error(f"❌ Telegram 圖片發送失敗: HTTP {res.status_code} - {res.text}")
                return False
        except Exception as e:
            logger.error(f"❌ Telegram 發送圖片異常: {e}")
            return False

    def test_connection(self) -> dict:
        """Tests Telegram Bot connection by querying getMe and sending a test message."""
        result = {"status": "FAILED", "bot_name": "", "error": ""}

        if not self.is_configured():
            result["error"] = "未設定 TELEGRAM_BOT_TOKEN 或 TELEGRAM_CHAT_ID"
            return result

        url = f"https://api.telegram.org/bot{self.bot_token}/getMe"
        try:
            res = requests.get(url, timeout=10)
            if res.status_code == 200:
                data = res.json()
                result["bot_name"] = data.get("result", {}).get("username", "")
                
                # Send test message
                msg_ok = self.send_message("🔔 <b>LINE Bot Telegram 通知測試連線成功！</b>")
                if msg_ok:
                    result["status"] = "SUCCESS"
                else:
                    result["error"] = "getMe 成功，但發送測試訊息失敗 (請確認 Chat ID 是否正確)"
            else:
                result["error"] = f"HTTP {res.status_code} - {res.text}"
        except Exception as e:
            result["error"] = str(e)

        return result
