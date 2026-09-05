#!/usr/bin/env python3
"""
LINE Official Robot CLI & Push Message Sender
方便隨時發送測試訊息給 LINE 帳號，以測試自動回覆機器人 (main_android.py)。
"""

import sys
import time
import random
import argparse
from robot_client import LineOfficialRobot

PRESET_TEST_MESSAGES = [
    "嗨，在忙嗎？今天過得如何？",
    "想問一下上次說的那個專案進度怎麼樣了？",
    "晚上要不要一起吃個飯？",
    "記得看一下稍早寄給你的信件喔！",
    "哈囉！這是一條自動測試訊息，收到請回答 Over~",
    "明天下午兩點開會別忘了喔！",
    "今天天氣真不錯，週末有什麼安排嗎？"
]


def print_bot_info(robot: LineOfficialRobot):
    print("==================================================")
    print(" 🤖 LINE Official Robot 資訊檢查")
    print("==================================================")
    try:
        info = robot.get_bot_info()
        print(f"  名稱 (Display Name): {info.get('display_name')}")
        print(f"  Basic ID          : @{info.get('basic_id')}")
        print(f"  Bot User ID       : {info.get('user_id')}")
        print(f"  聊天模式 (ChatMode): {info.get('chat_mode')}")
        print(f"  頭像連結 (Picture) : {info.get('picture_url')}")
        print("==================================================")
        print("✅ 機器人 API Token 驗證成功！可正常連線。")
    except Exception as e:
        print(f"❌ 取得機器人資訊失敗: {e}")


def interactive_mode(robot: LineOfficialRobot, user_id: str):
    print("==================================================")
    print(" 💬 進入互動式測試推播模式")
    print(f" 目標 User ID: {user_id or robot.default_user_id}")
    print(" 輸入訊息後按 Enter 即會推播至手機 LINE。")
    print(" 輸入 'exit' 或 'quit' 或按 Ctrl+C 可離開。")
    print("==================================================")

    while True:
        try:
            text = input("\n[輸入測試訊息] > ").strip()
            if not text:
                continue
            if text.lower() in ("exit", "quit", "q"):
                print("👋 離開互動模式。")
                break

            robot.send_push(text=text, user_id=user_id)
            print(f"🚀 已推播: '{text}'")
        except KeyboardInterrupt:
            print("\n👋 接收到中斷訊號，離開互動模式。")
            break
        except Exception as e:
            print(f"❌ 發送失敗: {e}")


def auto_simulate_mode(robot: LineOfficialRobot, interval: int, count: int, user_id: str):
    print("==================================================")
    print(" 🔄 進入自動模擬對話測試模式")
    print(f" 目標 User ID: {user_id or robot.default_user_id}")
    print(f" 間隔秒數    : {interval} 秒")
    print(f" 發送次數    : {'無限' if count <= 0 else count} 次")
    print(" 按 Ctrl+C 可隨時中止。")
    print("==================================================")

    sent = 0
    try:
        while True:
            msg = random.choice(PRESET_TEST_MESSAGES)
            sent += 1
            print(f"\n[{sent}] 正在發送: {msg}")
            robot.send_push(text=msg, user_id=user_id)
            print(f"✅ 發送成功！等待 {interval} 秒...")

            if count > 0 and sent >= count:
                print("🎉 已達到指定發送次數，測試結束。")
                break

            time.sleep(interval)
    except KeyboardInterrupt:
        print("\n👋 自動模擬測試已中止。")


def main():
    parser = argparse.ArgumentParser(description="LINE Official Robot (AutoReply) 測試發訊工具")
    parser.add_argument("--message", "-m", type=str, default=None, help="發送單則指定文字訊息")
    parser.add_argument("--info", action="store_true", help="僅檢查並印出官方機器人資訊")
    parser.add_argument("--interactive", "-i", action="store_true", help="進入互動式輸入發送模式")
    parser.add_argument("--auto", type=int, nargs="?", const=15, default=None, help="自動每隔 N 秒隨機發送測試語句 (預設 15 秒)")
    parser.add_argument("--count", type=int, default=0, help="配合 --auto 時的總發送次數 (0 為無限循環)")
    parser.add_argument("--token", type=str, default=None, help="覆蓋 LINE_CHANNEL_ACCESS_TOKEN")
    parser.add_argument("--user-id", type=str, default=None, help="覆蓋目標 LINE_USER_ID")

    args = parser.parse_args()

    try:
        robot = LineOfficialRobot(channel_access_token=args.token, default_user_id=args.user_id)
    except Exception as e:
        print(f"❌ 初始化失敗: {e}")
        sys.exit(1)

    if args.info:
        print_bot_info(robot)
        return

    if args.message:
        print(f"正在發送測試訊息至 {args.user_id or robot.default_user_id}...")
        try:
            robot.send_push(args.message, user_id=args.user_id)
            print(f"✅ 成功發送: '{args.message}'")
        except Exception as e:
            print(f"❌ 發送失敗: {e}")
            sys.exit(1)
        return

    if args.auto is not None:
        auto_simulate_mode(robot, interval=args.auto, count=args.count, user_id=args.user_id)
        return

    # 預設或指定 -i 進入互動模式
    print_bot_info(robot)
    interactive_mode(robot, user_id=args.user_id)


if __name__ == "__main__":
    main()
