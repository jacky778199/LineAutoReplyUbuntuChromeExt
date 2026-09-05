#!/usr/bin/env python3
"""
LINE Official Robot Webhook Server
用於接收來自 LINE 的訊息（例如 Android LINE 自動回覆發出的訊息），形成雙向測試對話。
支援自動透過 ngrok 穿透（若本機有設定 ngrok），或直接監聽本機 Port。
"""

import os
import sys
import argparse
from pathlib import Path
from flask import Flask, request, abort

from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.webhooks import MessageEvent, TextMessageContent
from linebot.v3.messaging import (
    Configuration,
    ApiClient,
    MessagingApi,
    ReplyMessageRequest,
    TextMessage
)

# Load environment
current_dir = Path(__file__).resolve().parent
sys.path.insert(0, str(current_dir))
from robot_client import LineOfficialRobot, load_environment

load_environment()

app = Flask(__name__)

# Config
channel_access_token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "").strip().strip("'\"")
channel_secret = os.getenv("LINE_CHANNEL_SECRET", "").strip().strip("'\"")

configuration = Configuration(access_token=channel_access_token)
handler = WebhookHandler(channel_secret) if channel_secret else None

# Global options
ENABLE_ECHO = False
ECHO_REPLY_PREFIX = "[Official AutoReply 收到]"


@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers.get("X-Line-Signature", "")
    body = request.get_data(as_text=True)

    if handler:
        try:
            handler.handle(body, signature)
        except InvalidSignatureError:
            print("❌ [Webhook] 簽章驗證失敗 (InvalidSignatureError)，請確認 LINE_CHANNEL_SECRET 是否正確。")
            abort(400)
    else:
        # If secret not provided, print warning but log request
        print("⚠️ [Webhook] 未設定 LINE_CHANNEL_SECRET，略過簽章驗證。")
        try:
            import json
            data = json.loads(body)
            events = data.get("events", [])
            for ev in events:
                if ev.get("type") == "message" and ev.get("message", {}).get("type") == "text":
                    user = ev.get("source", {}).get("userId", "Unknown")
                    text = ev.get("message", {}).get("text", "")
                    print(f"📥 [收到訊息] 來自 User: {user} | 內容: '{text}'")
        except Exception as e:
            print(f"❌ 解析事件失敗: {e}")

    return "OK"


if handler:
    @handler.add(MessageEvent, message=TextMessageContent)
    def handle_message(event):
        user_id = event.source.user_id
        text = event.message.text
        print(f"\n==================================================")
        print(f"📥 [Webhook 收到訊息]")
        print(f"  發送者 User ID: {user_id}")
        print(f"  訊息內容      : '{text}'")
        print(f"==================================================")

        if ENABLE_ECHO:
            reply_text = f"{ECHO_REPLY_PREFIX}: 收到你的訊息「{text}」，測試順暢！ Over~"
            with ApiClient(configuration) as api_client:
                line_bot_api = MessagingApi(api_client)
                line_bot_api.reply_message(
                    ReplyMessageRequest(
                        reply_token=event.reply_token,
                        messages=[TextMessage(text=reply_text)]
                    )
                )
            print(f"🤖 [已自動回覆] '{reply_text}'")


def main():
    global ENABLE_ECHO
    parser = argparse.ArgumentParser(description="LINE Official Robot Webhook Server")
    parser.add_argument("--port", "-p", type=int, default=5000, help="本機監聽 Port (預設 5000)")
    parser.add_argument("--ngrok", action="store_true", help="使用 pyngrok 自動建立公開公開網址")
    parser.add_argument("--echo", action="store_true", help="收到訊息時自動回覆 (雙向自動對話測試)")
    args = parser.parse_args()

    ENABLE_ECHO = args.echo

    if not channel_access_token:
        print("❌ 錯誤: 未設定 LINE_CHANNEL_ACCESS_TOKEN！請在 .env 中設定。")
        sys.exit(1)

    if not channel_secret:
        print("⚠️ 提醒: .env 中未設定 LINE_CHANNEL_SECRET，若要啟用正式 Webhook 簽章驗證，請在 .env 加入 LINE_CHANNEL_SECRET。")

    public_url = None
    if args.ngrok:
        try:
            from pyngrok import ngrok
            tunnel = ngrok.connect(args.port)
            public_url = tunnel.public_url
            print(f"\n🌐 [ngrok 隧道已建立]")
            print(f"👉 請至 LINE Developers Console -> Messaging API -> Webhook URL 設定為:")
            print(f"    {public_url}/callback")
            print(f"👉 並開啟 'Use webhook' 開關。\n")
        except Exception as e:
            print(f"❌ ngrok 建立失敗: {e}")

    print("==================================================")
    print(" 🚀 LINE Official Robot Webhook Server 啟動中...")
    print(f" 監聽 Port  : {args.port}")
    print(f" 自動 Echo  : {'開啟 (雙向互動)' if ENABLE_ECHO else '關閉 (僅記錄接收)'}")
    print("==================================================")

    try:
        app.run(host="0.0.0.0", port=args.port, debug=False)
    except KeyboardInterrupt:
        print("\n👋 Webhook Server 已停止。")


if __name__ == "__main__":
    main()
