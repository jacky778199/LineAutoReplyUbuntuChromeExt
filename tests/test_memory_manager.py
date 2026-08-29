"""
Unit tests for MemoryManager module.
"""

import os
import json
import shutil
import unittest
from core.memory_manager import MemoryManager

class TestMemoryManager(unittest.TestCase):

    def setUp(self):
        self.test_dir = "tests/temp_memories"
        self.config = {
            "memory": {
                "enabled": True,
                "max_facts_per_contact": 5,
                "storage_dir": self.test_dir
            }
        }
        self.manager = MemoryManager(self.config)

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_save_and_load_memory(self):
        contact = "TestUser"
        facts = ["喜歡珍珠奶茶", "住在台北", "下個月生日"]

        self.manager.save_memory(contact, facts)

        memory_data = self.manager.load_memory(contact)
        self.assertEqual(memory_data["contact_name"], contact)
        self.assertEqual(len(memory_data["facts"]), 3)
        self.assertIn("喜歡珍珠奶茶", memory_data["facts"])

    def test_get_memory_prompt_block(self):
        contact = "Eyeyupy~"
        facts = ["喜歡泰式料理", "不吃香菜"]

        self.manager.save_memory(contact, facts)
        prompt_block = self.manager.get_memory_prompt_block(contact)

        self.assertIn("【關於「Eyeyupy~」的長遠記憶與重要事實紀錄】", prompt_block)
        self.assertIn("- 喜歡泰式料理", prompt_block)
        self.assertIn("- 不吃香菜", prompt_block)

    def test_max_facts_limit(self):
        contact = "LimitUser"
        facts = [f"事實 {i}" for i in range(10)]

        self.manager.save_memory(contact, facts)
        memory_data = self.manager.load_memory(contact)

        # Max facts configured is 5
        self.assertEqual(len(memory_data["facts"]), 5)
        self.assertEqual(memory_data["facts"][-1], "事實 9")

if __name__ == "__main__":
    unittest.main()
