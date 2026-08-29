"""
Fact and Preference Memory Manager Module.
Handles loading, saving, formatting, and updating long-term contact memories stored as JSON files.
"""

import os
import json
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

EXTRACTION_SYSTEM_PROMPT = """你是一個客觀且敏銳的情報與對話記憶分析專家。
你的任務是閱讀對話紀錄，並維護「關於談話對象（Contact）」的長遠記憶列表（Facts & Preferences）。

【規則與標準】：
1. 僅提取真正重要的「個人事實」、「明確偏好」、「重要習慣」、「未來重要日程/約定」或「人際關係狀態」。
2. 忽略無意義的問候、日常廢話、情緒發洩與短期動態。
3. 嚴禁編造或推測未提及的資訊。
4. 如果新對話與舊記憶有衝突（如：舊記憶「不喜歡咖啡」，新對話「最近迷上喝拿鐵」），請更新或取代舊記憶。
5. 保持每條事實簡短精準（控制在 15 字以內）。
6. 請直接輸出 JSON 陣列格式，嚴禁輸出 Markdown 標記或任何其他說明文字。

輸出格式範例：
[
  "喜歡泰式料理",
  "下週二有工作簡報",
  "偏好使用英文或泰文對話"
]
"""

class MemoryManager:
    """Manages reading, writing, and background updating of contact long-term memories."""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        memory_cfg = config.get("memory", {})
        self.enabled = memory_cfg.get("enabled", True)
        self.max_facts = memory_cfg.get("max_facts_per_contact", 20)
        self.storage_dir = memory_cfg.get("storage_dir", "logs/memories")

        if self.enabled:
            os.makedirs(self.storage_dir, exist_ok=True)

    def _get_filepath(self, contact_name: str) -> str:
        """Sanitizes contact name for safe filename usage."""
        safe_name = "".join(c for c in contact_name if c.isalnum() or c in (" ", "_", "-")).strip()
        if not safe_name:
            safe_name = "default_user"
        return os.path.join(self.storage_dir, f"{safe_name}.json")

    def load_memory(self, contact_name: str) -> Dict[str, Any]:
        """Loads memory dict for a specific contact."""
        if not self.enabled:
            return {"contact_name": contact_name, "facts": []}

        filepath = self._get_filepath(contact_name)
        if not os.path.exists(filepath):
            return {"contact_name": contact_name, "facts": [], "updated_at": None}

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
                if not isinstance(data, dict):
                    data = {"contact_name": contact_name, "facts": []}
                return data
        except Exception as e:
            logger.error(f"Failed to load memory file {filepath}: {e}")
            return {"contact_name": contact_name, "facts": []}

    def save_memory(self, contact_name: str, facts: List[str]):
        """Saves memory list to file."""
        if not self.enabled:
            return

        filepath = self._get_filepath(contact_name)
        # Deduplicate and limit size
        unique_facts = []
        for fact in facts:
            fact_clean = fact.strip()
            if fact_clean and fact_clean not in unique_facts:
                unique_facts.append(fact_clean)
        
        unique_facts = unique_facts[-self.max_facts:]

        data = {
            "contact_name": contact_name,
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "facts": unique_facts
        }

        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.info(f"Memory updated for [{contact_name}] ({len(unique_facts)} facts saved).")
        except Exception as e:
            logger.error(f"Failed to save memory for [{contact_name}]: {e}")

    def get_memory_prompt_block(self, contact_name: str) -> str:
        """Formats stored memories into a prompt section for LLM context."""
        if not self.enabled:
            return ""

        memory_data = self.load_memory(contact_name)
        facts = memory_data.get("facts", [])
        if not facts:
            return ""

        facts_formatted = "\n".join(f"- {fact}" for fact in facts)
        return f"\n【關於「{contact_name}」的長遠記憶與重要事實紀錄】：\n{facts_formatted}\n（請在溝通時自然參考上述背景資訊，切勿機械式複述。）\n"

    def update_memory_from_chat(self, contact_name: str, raw_chat_text: str, llm_service) -> List[str]:
        """
        Uses LLM to extract new facts from raw chat text and merges with existing memories.
        Should be invoked asynchronously or after response generation.
        """
        if not self.enabled or not raw_chat_text or not raw_chat_text.strip():
            return []

        existing_data = self.load_memory(contact_name)
        existing_facts = existing_data.get("facts", [])

        user_prompt = f"""當前舊有的記憶列表：
{json.dumps(existing_facts, ensure_ascii=False, indent=2)}

最新對話紀錄：
<chat_history>
{raw_chat_text}
</chat_history>

請分析上述對話，並輸出更新後的全量記憶 JSON 陣列："""

        try:
            # Generate response via primary LLM
            raw_result = llm_service._call_primary_llm(EXTRACTION_SYSTEM_PROMPT, user_prompt)
            cleaned_result = llm_service._clean_reply_text(raw_result)
            
            # Parse JSON
            if cleaned_result.startswith("```"):
                lines = cleaned_result.splitlines()
                if len(lines) >= 2:
                    cleaned_result = "\n".join(lines[1:-1]).strip()
            
            new_facts = json.loads(cleaned_result)
            if isinstance(new_facts, list):
                parsed_facts = [str(item).strip() for item in new_facts if str(item).strip()]
                self.save_memory(contact_name, parsed_facts)
                return parsed_facts
        except Exception as e:
            logger.warning(f"Memory extraction skipped or failed for [{contact_name}]: {e}")

        return existing_facts
