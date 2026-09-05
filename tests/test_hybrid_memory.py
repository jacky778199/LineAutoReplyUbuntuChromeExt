"""
Unit tests for Dual-Layer Hybrid Memory (EpisodicVectorStore, MemoryManager, and History Importer).
"""

import os
import shutil
import tempfile
import unittest
from datetime import datetime

from core.vector_store import EpisodicVectorStore, cosine_similarity
from core.memory_manager import MemoryManager
from scripts.import_history import parse_line_txt_export, import_from_reply_logs


class TestEpisodicVectorStore(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.config = {
            "memory": {
                "enabled": True,
                "storage_dir": os.path.join(self.test_dir, "memories"),
                "episodic": {
                    "enabled": True,
                    "top_k": 2,
                    "storage_dir": os.path.join(self.test_dir, "vector_db")
                }
            },
            "llm": {
                "primary": {"provider": "local", "project_id": ""},
                "backup": {"api_key": ""}
            }
        }
        self.store = EpisodicVectorStore(self.config)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_cosine_similarity(self):
        v1 = [1.0, 0.0, 0.0]
        v2 = [1.0, 0.0, 0.0]
        v3 = [0.0, 1.0, 0.0]
        self.assertAlmostEqual(cosine_similarity(v1, v2), 1.0, places=4)
        self.assertAlmostEqual(cosine_similarity(v1, v3), 0.0, places=4)

    def test_local_hash_embedding(self):
        vec1 = self.store._local_hash_embedding("陽明山喝咖啡", dim=1024)
        vec2 = self.store._local_hash_embedding("陽明山喝咖啡", dim=1024)
        vec3 = self.store._local_hash_embedding("完全不相關的內容討論韌體", dim=1024)

        self.assertEqual(len(vec1), 1024)
        # Deterministic
        self.assertEqual(vec1, vec2)
        # Similarity of identical should be ~1.0
        self.assertAlmostEqual(cosine_similarity(vec1, vec2), 1.0, places=4)
        # Similarity of different should be significantly lower
        self.assertLess(cosine_similarity(vec1, vec3), 0.5)

    def test_add_and_search_with_contact_isolation(self):
        # Add episode for Alice
        self.store.add_episode(
            contact_name="Alice",
            timestamp="2026-08-15 14:00:00",
            content="Alice: 上次推薦的竹子湖繡球花咖啡廳超讚，下次想再去！"
        )

        # Add episode for Bob
        self.store.add_episode(
            contact_name="Bob",
            timestamp="2026-08-16 10:00:00",
            content="Bob: 伺服器 BMC 韌體的 OpenBMC porting 進度如何？"
        )

        # Search Alice for "咖啡廳"
        alice_results = self.store.search(query="咖啡廳", contact_name="Alice")
        self.assertTrue(len(alice_results) >= 1)
        self.assertIn("竹子湖", alice_results[0]["content"])

        # Contact isolation: Searching Bob for "咖啡廳" should return NO results
        bob_coffee_results = self.store.search(query="咖啡廳", contact_name="Bob")
        self.assertEqual(len(bob_coffee_results), 0)

        # Searching Bob for "BMC 韌體" should return Bob's episode
        bob_bmc_results = self.store.search(query="BMC 韌體", contact_name="Bob")
        self.assertTrue(len(bob_bmc_results) >= 1)
        self.assertIn("OpenBMC", bob_bmc_results[0]["content"])

        # Episode count check
        self.assertEqual(self.store.get_contact_episodes_count("Alice"), 1)
        self.assertEqual(self.store.get_contact_episodes_count("Bob"), 1)
        self.assertEqual(self.store.get_contact_episodes_count("Charlie"), 0)


class TestMemoryManagerToolCalling(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.config = {
            "memory": {
                "enabled": True,
                "max_facts_per_contact": 10,
                "storage_dir": os.path.join(self.test_dir, "memories"),
                "episodic": {
                    "enabled": True,
                    "top_k": 3,
                    "storage_dir": os.path.join(self.test_dir, "vector_db")
                }
            },
            "llm": {
                "primary": {"provider": "local", "project_id": ""},
                "backup": {"api_key": ""}
            }
        }
        self.mgr = MemoryManager(self.config)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_search_past_memory_formatting(self):
        # Insert test episode into vector store
        self.mgr.vector_store.add_episode(
            contact_name="丁竑福",
            timestamp="2026-08-10 19:30:00",
            content="丁竑福: 我上週去日本吃了道地的沾麵跟拉麵，湯頭很濃郁！"
        )

        # Test search tool
        result_str = self.mgr.search_past_memory(query="日本沾麵拉麵", contact_name="丁竑福")
        self.assertIn("【歷史對話片段 1】", result_str)
        self.assertIn("沾麵跟拉麵", result_str)
        self.assertIn("2026-08-10 19:30:00", result_str)

        # Test empty query / no result
        empty_str = self.mgr.search_past_memory(query="外星人太空船", contact_name="丁竑福")
        self.assertIn("未檢索到", empty_str)


class TestHistoryImporter(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_parse_line_txt_export(self):
        sample_txt = os.path.join(self.test_dir, "line_chat.txt")
        with open(sample_txt, "w", encoding="utf-8") as f:
            f.write("""[LINE] 與丁小弟的聊天記錄
儲存日期：2026/09/06 01:00

2026/08/20（四）
14:10\t丁小弟\t今天下班要不要一起去健身房？
14:12\t我\t好啊，大概晚上七點。
14:15\t丁小弟\tOK！

2026/08/21（五）
10:00\t丁小弟\t昨天的深蹲好累！
10:01\t我\t多吃蛋白質補充。
""")

        episodes = parse_line_txt_export(sample_txt)
        self.assertEqual(len(episodes), 2)
        self.assertIn("2026/08/20", episodes[0]["timestamp"])
        self.assertIn("健身房", episodes[0]["content"])
        self.assertIn("2026/08/21", episodes[1]["timestamp"])
        self.assertIn("深蹲好累", episodes[1]["content"])

    def test_import_from_reply_logs(self):
        sample_log = os.path.join(self.test_dir, "reply_history.log")
        with open(sample_log, "w", encoding="utf-8") as f:
            f.write("2026-09-05 18:24:10,997 | [SUCCESS] 自動回覆成功 | 對象:【AutoReply】 | 最新訊息: '你好在嗎' | 回覆內容: '在的，請問有什麼事嗎？' | 耗時: 1.25秒\n")
            f.write("2026-09-05 18:25:00,100 | [SUCCESS] 自動回覆成功 | 對象:【丁小弟】 | 最新訊息: '出發了嗎' | 回覆內容: '剛出門了！' | 耗時: 0.95秒\n")

        items = import_from_reply_logs(sample_log, target_contact="AutoReply")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["contact_name"], "AutoReply")
        self.assertIn("你好在嗎", items[0]["content"])

        all_items = import_from_reply_logs(sample_log, target_contact=None)
        self.assertEqual(len(all_items), 2)


if __name__ == "__main__":
    unittest.main()
