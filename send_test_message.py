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

# LINE Channel Access Token
CHANNEL_ACCESS_TOKEN = 'qcRwFHXZRhnnqG43DWyBwqdQCscn2IlUXrG65uAZEZ3gHQDFP4Hw89jgCzpg75cMVu2OjPeiKXplFOk7QxfM5z2sFnSHR7uPqBQDEdO8Iq+mrBWAD9hAfhKswVM/T7R5jeV/WKTn4zZftjO/Mk8dvgdB04t89/1O/w1cDnyilFU='
DEFAULT_USER_ID = 'U645e7f3d2ddf26bda322be963bea689a'

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

def send_push_message(user_id: str, text: str):
    """Sends a proactive push message using LINE Messaging API v3."""
    print(f"==================================================")
    print(f" 正在發送 Push Message ")
    print(f" Target User ID : {user_id}")
    print(f" Message Content: {text}")
    print(f"==================================================")

    configuration = Configuration(access_token=CHANNEL_ACCESS_TOKEN)

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
    parser.add_argument("--user-id", default=DEFAULT_USER_ID, help="目標 LINE User ID (格式如 Uxxxx...)")
    parser.add_argument("--message", default="🤖 這是一條來自 LINE AutoReplyBot 的測試主動推播訊息 (Push Message)！", help="測試發送內容")

    args = parser.parse_args()
    send_push_message(args.user_id, args.message)
