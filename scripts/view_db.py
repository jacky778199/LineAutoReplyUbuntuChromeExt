#!/usr/bin/env python3
"""
Episodic Vector DB Viewer & Query Tool.
Inspect stored episodes, contact statistics, and test semantic search without cluttering the terminal with raw vector embeddings.
"""

import os
import sys
import sqlite3
import argparse

# Ensure project root is in sys.path
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
DB_PATH = os.path.join(PROJECT_ROOT, "logs", "vector_db", "episodes.db")


def show_stats():
    """Prints total episodes count grouped by contact."""
    if not os.path.exists(DB_PATH):
        print(f"❌ 找不到資料庫檔案: {DB_PATH}")
        return

    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT contact_name, COUNT(*) FROM episodes GROUP BY contact_name ORDER BY COUNT(*) DESC")
        rows = cursor.fetchall()
        cursor.execute("SELECT COUNT(*) FROM episodes")
        total = cursor.fetchone()[0]

    print("\n" + "=" * 55)
    print(" 📊 情節向量資料庫 (episodes.db) 儲存概況")
    print("=" * 55)
    print(f"總存檔切片數: {total} 筆\n")
    print(f"{'好友 / 談話對象':<25} {'已儲存情節數':<15}")
    print("-" * 55)
    for contact, count in rows:
        print(f"{contact:<25} {count:<15}")
    print("=" * 55 + "\n")


def view_episodes(contact_name: str = None, limit: int = 5, keyword: str = None):
    """Prints episode records without raw embedding numbers."""
    if not os.path.exists(DB_PATH):
        print(f"❌ 找不到資料庫檔案: {DB_PATH}")
        return

    query = "SELECT id, contact_name, timestamp, content, created_at FROM episodes WHERE 1=1"
    params = []

    if contact_name:
        query += " AND contact_name = ?"
        params.append(contact_name)
    if keyword:
        query += " AND content LIKE ?"
        params.append(f"%{keyword}%")

    query += " ORDER BY id DESC LIMIT ?"
    params.append(limit)

    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        rows = cursor.fetchall()

    if not rows:
        print(f"⚠️ 未找到符合條件的紀錄 (對象: {contact_name or '全部'}, 關鍵字: {keyword or '無'})")
        return

    print(f"\n🔍 查詢到 {len(rows)} 筆情節紀錄 (顯示最新 {limit} 筆)：\n")
    for r_id, c_name, ts, content, created_at in rows:
        print(f"【ID: {r_id} | 對象: {c_name} | 對話時間: {ts} | 入庫時間: {created_at}】")
        # Indent content
        for line in content.strip().splitlines():
            print(f"  {line}")
        print("-" * 60)


def main():
    parser = argparse.ArgumentParser(description="View & Inspect Episodic Vector DB")
    parser.add_argument("--stats", action="store_true", help="顯示資料庫各好友的情節總數統計")
    parser.add_argument("--contact", help="指定查看特定聯絡人/好友 (例如: 丁竑福, Eyeyupy)")
    parser.add_argument("--keyword", help="內容文字關鍵字篩選 (例如: 機車, 咖啡)")
    parser.add_argument("--limit", type=int, default=5, help="顯示筆數上限 (預設 5 筆)")

    args = parser.parse_args()

    if args.stats or (not args.contact and not args.keyword):
        show_stats()

    if args.contact or args.keyword:
        view_episodes(contact_name=args.contact, limit=args.limit, keyword=args.keyword)


if __name__ == "__main__":
    main()
