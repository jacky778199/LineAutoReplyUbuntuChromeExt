#!/usr/bin/env bash
"""
Batch Historical Chat Importer.
Imports past chat history (.txt exports from LINE or existing log files)
into the Episodic Vector Database.
"""

import os
import re
import sys
import yaml
import argparse
from datetime import datetime
from typing import List, Dict, Any

# Ensure project root is in sys.path
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from core.vector_store import EpisodicVectorStore


def parse_line_txt_export(file_path: str) -> List[Dict[str, str]]:
    """
    Parses a LINE exported chat history .txt file.
    Splits into session episodes by date header or message bursts.
    Returns list of dicts: {"timestamp": ..., "content": ...}
    """
    if not os.path.exists(file_path):
        print(f"❌ 找不到指定的檔案: {file_path}")
        return []

    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        lines = f.readlines()

    episodes = []
    current_date = "未知日期"
    current_chunk = []

    # Regex patterns for LINE date headers
    # e.g., 2026/08/15（六）, 2026.08.15 Saturday, 2026-08-15
    date_header_pattern = re.compile(r"^(\d{4}[/.-]\d{1,2}[/.-]\d{1,2})")
    time_msg_pattern = re.compile(r"^(\d{1,2}:\d{2})\s+([^\t]+)\t(.*)$|^(\d{1,2}:\d{2})\s+(.*?)\s*:\s*(.*)$")

    for line in lines:
        line_str = line.strip()
        if not line_str:
            continue

        # Check for Date Header
        date_match = date_header_pattern.match(line_str)
        if date_match:
            # If we had buffered messages, commit previous episode
            if current_chunk:
                episodes.append({
                    "timestamp": current_date,
                    "content": "\n".join(current_chunk)
                })
                current_chunk = []
            current_date = line_str
            continue

        # Skip LINE system header lines
        if line_str.startswith("[LINE]") or line_str.startswith("儲存日期") or line_str.startswith("Saved"):
            continue

        # Append message line
        current_chunk.append(line_str)

        # Chunk if buffer reaches 12 messages to keep search granularity high
        if len(current_chunk) >= 12:
            episodes.append({
                "timestamp": current_date,
                "content": "\n".join(current_chunk)
            })
            current_chunk = []

    # Commit remaining chunk
    if current_chunk:
        episodes.append({
            "timestamp": current_date,
            "content": "\n".join(current_chunk)
        })

    return episodes


def import_from_reply_logs(log_path: str, target_contact: str = None) -> List[Dict[str, Any]]:
    """
    Parses logs/reply_history.log into episode chunks.
    Format: 2026-09-05 18:24:10,997 | [SUCCESS] ... | 對象:【AutoReply】 | 最新訊息: '...' | 回覆內容: '...'
    """
    if not os.path.exists(log_path):
        print(f"❌ 找不到日誌檔案: {log_path}")
        return []

    episodes_by_contact = []
    with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            if "[SUCCESS]" not in line:
                continue

            match = re.search(r"^([\d\-]+ [\d:]+).*?對象:【(.*?)】.*?最新訊息: '(.*?)' \| 回覆內容: '(.*?)'", line)
            if match:
                ts, contact, user_msg, bot_reply = match.groups()
                if target_contact and contact != target_contact:
                    continue
                content = f"{contact}: {user_msg}\n我: {bot_reply}"
                episodes_by_contact.append({
                    "contact_name": contact,
                    "timestamp": ts,
                    "content": content
                })

    return episodes_by_contact


def main():
    parser = argparse.ArgumentParser(description="LINE Historical Conversation Importer for Episodic Vector DB")
    parser.add_argument("--contact", help="聯絡人/好友名稱 (例如: 丁竑福, AutoReply)")
    parser.add_argument("--file", help="LINE 匯出的聊天文字檔路徑 (.txt)")
    parser.add_argument("--from-logs", action="store_true", help="自動由 logs/reply_history.log 匯入已記錄之對話")
    parser.add_argument("--config", default="config.yaml", help="設定檔路徑 (預設 config.yaml)")

    args = parser.parse_args()

    # Load configuration
    config_path = os.path.join(PROJECT_ROOT, args.config)
    if not os.path.exists(config_path):
        print(f"❌ 找不到設定檔: {config_path}")
        sys.exit(1)

    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    vector_store = EpisodicVectorStore(config)
    if not vector_store.enabled:
        print("⚠️ 向量記憶功能尚未啟用 (config.yaml memory.episodic.enabled = false)")
        sys.exit(1)

    # Mode 1: Import from reply_history.log
    if args.from_logs:
        log_file = os.path.join(PROJECT_ROOT, "logs", "reply_history.log")
        print(f"📖 正在讀取回覆歷程日誌: {log_file}...")
        log_items = import_from_reply_logs(log_file, target_contact=args.contact)
        print(f"🔍 找到 {len(log_items)} 筆成功對話紀錄，開始計算向量並匯入...")

        success_count = 0
        for item in log_items:
            c_name = item["contact_name"]
            ok = vector_store.add_episode(
                contact_name=c_name,
                timestamp=item["timestamp"],
                content=item["content"]
            )
            if ok:
                success_count += 1

        print(f"🎉 成功匯入 {success_count} 筆情節記憶！")
        return

    # Mode 2: Import from .txt export file
    if not args.contact or not args.file:
        print("❌ 請指定 --contact <好友名稱> 與 --file <檔案路徑>，或使用 --from-logs")
        parser.print_help()
        sys.exit(1)

    file_path = os.path.abspath(args.file)
    print(f"📖 正在解析好友 【{args.contact}】 的對話紀錄檔: {file_path}...")
    episodes = parse_line_txt_export(file_path)

    if not episodes:
        print("⚠️ 未解析出任何有效的對話切片。")
        return

    print(f"✂️ 共切分成 {len(episodes)} 個情節區塊，正在計算向量並寫入向量資料庫...")

    success_count = 0
    for ep in episodes:
        ok = vector_store.add_episode(
            contact_name=args.contact,
            timestamp=ep["timestamp"],
            content=ep["content"]
        )
        if ok:
            success_count += 1

    total_in_db = vector_store.get_contact_episodes_count(args.contact)
    print("=" * 50)
    print(f"✅ 匯入完成！成功寫入 {success_count} 筆紀錄至 【{args.contact}】 的情節向量庫。")
    print(f"📚 目前該好友在向量庫中的情節存根總數: {total_in_db} 筆")
    print("=" * 50)


if __name__ == "__main__":
    main()
