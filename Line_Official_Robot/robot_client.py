"""
LINE Official Robot Client Wrapper (Messaging API v3)
"""

import os
from pathlib import Path
from typing import Optional, Dict, Any

from linebot.v3.messaging import (
    Configuration,
    ApiClient,
    MessagingApi,
    PushMessageRequest,
    TextMessage
)
from linebot.v3.messaging.rest import ApiException

def load_environment():
    """Load .env from current folder or parent project root."""
    current_dir = Path(__file__).resolve().parent
    root_dir = current_dir.parent

    for env_file in [current_dir / ".env", root_dir / ".env"]:
        if env_file.exists():
            try:
                with open(env_file, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith("#") or "=" not in line:
                            continue
                        k, v = line.split("=", 1)
                        k = k.strip()
                        v = v.strip().strip("'\"")
                        if k and k not in os.environ:
                            os.environ[k] = v
            except Exception:
                pass


load_environment()


class LineOfficialRobot:
    """Official LINE Robot client for sending push messages and inspecting bot status."""

    def __init__(self, channel_access_token: Optional[str] = None, default_user_id: Optional[str] = None):
        self.channel_access_token = (
            channel_access_token
            or os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
            or os.getenv("line_channel_access_token")
            or ""
        ).strip().strip("'\"")

        self.default_user_id = (
            default_user_id
            or os.getenv("LINE_USER_ID")
            or os.getenv("line_user_id")
            or ""
        ).strip().strip("'\"")

        self.channel_secret = (
            os.getenv("LINE_CHANNEL_SECRET")
            or os.getenv("line_channel_secret")
            or ""
        ).strip().strip("'\"")

        if not self.channel_access_token:
            raise ValueError(
                "找不到 LINE_CHANNEL_ACCESS_TOKEN！請確保專案根目錄或本目錄下的 .env 已設定 LINE_CHANNEL_ACCESS_TOKEN。"
            )

        self.configuration = Configuration(access_token=self.channel_access_token)

    def get_bot_info(self) -> Dict[str, Any]:
        """Fetches the official bot profile information (display name, basic ID, etc.)."""
        with ApiClient(self.configuration) as api_client:
            line_bot_api = MessagingApi(api_client)
            info = line_bot_api.get_bot_info()
            return {
                "user_id": info.user_id,
                "basic_id": info.basic_id,
                "display_name": info.display_name,
                "picture_url": info.picture_url,
                "chat_mode": info.chat_mode,
                "mark_as_read_mode": info.mark_as_read_mode
            }

    def send_push(self, text: str, user_id: Optional[str] = None) -> bool:
        """
        Sends a push message to a specific user.
        If user_id is not specified, uses default_user_id from .env.
        """
        target_user = user_id or self.default_user_id
        if not target_user:
            raise ValueError(
                "未指定目標 user_id，且 .env 中沒有設定 LINE_USER_ID！"
            )

        with ApiClient(self.configuration) as api_client:
            line_bot_api = MessagingApi(api_client)
            push_request = PushMessageRequest(
                to=target_user,
                messages=[TextMessage(text=text)]
            )
            try:
                line_bot_api.push_message(push_request)
                return True
            except ApiException as e:
                print(f"❌ [LINE API 錯誤] HTTP {e.status}: {e.body}")
                raise
            except Exception as e:
                print(f"❌ [發送失敗]: {e}")
                raise
