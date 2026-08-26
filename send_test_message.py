import os
import sys
import argparse
from linebot.v3.messaging import (
    Configuration,
    ApiClient,
    MessagingApi,
    PushMessageRequest,
    TextMessage
)
from linebot.v3.messaging.rest import ApiException

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

def load_dotenv_if_exists(dotenv_path: str = ".env"):
    """Lightweight .env loader without external dependencies."""
    if os.path.exists(dotenv_path):
        try:
            with open(dotenv_path, "r", encoding="utf-8") as f:
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

load_dotenv_if_exists()

def send_push_message(access_token: str, user_id: str, text: str):
    """Sends a proactive push message using LINE Messaging API v3."""
    if not access_token:
        print("❌ [錯誤] 未提供 LINE Channel Access Token！")
        print("💡 請設定環境變數 LINE_CHANNEL_ACCESS_TOKEN，或透過參數 --token 指定。")
        sys.exit(1)

    if not user_id:
        print("❌ [錯誤] 未提供目標 LINE User ID！")
        print("💡 請設定環境變數 LINE_USER_ID，或透過參數 --user-id 指定。")
        sys.exit(1)

    print(f"==================================================")
    print(f" 正在發送 Push Message ")
    print(f" Target User ID : {user_id}")
    print(f" Message Content: {text}")
    print(f"==================================================")

    configuration = Configuration(access_token=access_token)

    try:
        with ApiClient(configuration) as api_client:
            line_bot_api = MessagingApi(api_client)
            push_message_request = PushMessageRequest(
                to=user_id,
                messages=[TextMessage(text=text)]
            )
            response = line_bot_api.push_message(push_message_request)
            print("\n✅ [成功] Push Message 已成功發送！請檢查您的手機 LINE 聊天室。")
            return True
    except ApiException as e:
        print(f"\n❌ [失敗] LINE API 錯誤 (HTTP {e.status}):")
        print(f"    {e.body}")
        return False
    except Exception as e:
        print(f"\n❌ [失敗] 發生未預期的錯誤: {e}")
        return False

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="LINE Push Message 測試腳本")
    parser.add_argument(
        "--token",
        default=os.environ.get("LINE_CHANNEL_ACCESS_TOKEN") or os.environ.get("line_channel_access_token", ""),
        help="LINE Channel Access Token (或由環境變數 LINE_CHANNEL_ACCESS_TOKEN 提供)"
    )
    parser.add_argument(
        "--user-id",
        default=os.environ.get("LINE_USER_ID") or os.environ.get("line_user_id", ""),
        help="目標 LINE User ID (格式如 Uxxxx... 或由環境變數 LINE_USER_ID 提供)"
    )
    parser.add_argument(
        "--message",
        default="🤖 這是一條來自 LINE AutoReplyBot 的測試主動推播訊息 (Push Message)！",
        help="測試發送內容"
    )

    args = parser.parse_args()
    send_push_message(args.token, args.user_id, args.message)

