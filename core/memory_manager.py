"""
Fact and Preference Memory Manager Module.
Handles loading, saving, formatting, and updating long-term contact memories stored as JSON files.
"""

import os
import json
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional
from core.vector_store import EpisodicVectorStore

logger = logging.getLogger(__name__)

EXTRACTION_SYSTEM_PROMPT = """你是一個客觀且敏銳的情報與對話記憶分析專家。
你的任務是閱讀對話紀錄，並維護「關於談話對象（Contact）」的長遠記憶列表（Facts & Preferences）。

【規則與標準】：
1. 僅提取真正重要的「個人事實」、「明確偏好」、「重要習慣」、「未來重要日程/約定/面試等事件」或「人際關係狀態」。
2. 【時間絕對化轉換規則（極重要）】：
   - 系統會在輸入中提供【當前對話基準時間】（包含年月日與星期）。
   - 對話中若出現任何時間表達（例如「今天」、「明天」、「後天」、「下週四」、「下個月」、「9月6號」等）：
     * 嚴禁使用模糊或相對時間詞彙（如「下週四」、「明天」）。
     * 必須根據基準時間推算出「具體的絕對日期與時間」，例如：「預計於 2026-09-10 (四) 至 Supermicro 面試 BMC 職位」、「預計於 2026-09-06 (日) 23:00 去看大象遊街」。
   - 若對話中過去的某個約定或事件已經完成或過期，請將事實更新為已完成狀態，或適度移除過期事件。
3. 忽略無意義的問候、日常廢話、情緒發洩與短期動態。
4. 嚴禁編造或推測對話中未提及的資訊。
5. 如果新對話與舊記憶有衝突或狀態更新（如：舊記憶「不喜歡咖啡」，新對話「最近迷上喝拿鐵」），請更新或取代舊記憶。
6. 保持每條事實精準且資訊完整，單條事實長度建議控制在 35 字以內，包含必要的人事時地物。
7. 請直接輸出 JSON 陣列格式，嚴禁輸出 Markdown 代碼塊或任何其他說明文字。

輸出格式範例：
[
  "喜歡泰式料理與黑咖啡",
  "預計於 2026-09-10 (四) 至 Supermicro 面試 BMC 相關職位",
  "偏好使用底片相機拍照"
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
            self.vector_store = EpisodicVectorStore(config)
        else:
            self.vector_store = None

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
        """Formats stored memories into a prompt section for LLM context with current timestamp."""
        if not self.enabled:
            return ""

        memory_data = self.load_memory(contact_name)
        facts = memory_data.get("facts", [])
        if not facts:
            return ""

        now = datetime.now()
        weekday_map = {0: "一", 1: "二", 2: "三", 3: "四", 4: "五", 5: "六", 6: "日"}
        now_str = f"{now.strftime('%Y-%m-%d')} 星期{weekday_map[now.weekday()]}"

        facts_formatted = "\n".join(f"- {fact}" for fact in facts)
        return f"\n【關於「{contact_name}」的長遠記憶與重要事實紀錄】（當前參考時間：{now_str}）：\n{facts_formatted}\n（請在溝通時自然參考上述背景資訊，若記憶中有具體日期，請比對當前參考時間自然表達，切勿機械式複述。）\n"

    def search_past_memory(self, query: str, contact_name: str) -> str:
        """
        Tool interface for LLM: Searches historical episodic vector memory for a contact.
        Returns formatted context string for LLM response synthesis.
        """
        if not self.enabled or not self.vector_store:
            return "情節記憶庫未啟用。"
        if not query or not query.strip():
            return "查詢關鍵字為空，未檢索歷史紀錄。"

        results = self.vector_store.search(query=query.strip(), contact_name=contact_name)
        if not results:
            return f"歷史對話紀錄中未檢索到與「{query}」直接相關的詳細內容。"

        formatted_episodes = []
        for i, ep in enumerate(results, 1):
            ts = ep.get("timestamp", "未知時間")
            content = ep.get("content", "").strip()
            # Truncate content to avoid blowing up prompt
            if len(content) > 500:
                content = content[:500] + "... (內容過長截斷)"
            formatted_episodes.append(f"【歷史對話片段 {i}】(時間: {ts}):\n{content}")

        return (
            f"【關於「{contact_name}」的歷史情節記憶檢索結果 (關鍵字: {query})】：\n"
            + "\n\n".join(formatted_episodes)
            + "\n（請依據上述檢索到的歷史情報，自然且親切地回覆對方，若細節依然不足可誠實表達。）"
        )

    def update_memory_from_chat(self, contact_name: str, raw_chat_text: str, llm_service) -> List[str]:
        """
        Uses LLM to extract new facts from raw chat text (Layer 1) and saves episodic chunk (Layer 2).
        Should be invoked asynchronously or after response generation.
        """
        if not self.enabled or not raw_chat_text or not raw_chat_text.strip():
            return []

        now = datetime.now()
        weekday_map = {0: "一", 1: "二", 2: "三", 3: "四", 4: "五", 5: "六", 6: "日"}
        now_str = f"{now.strftime('%Y-%m-%d %H:%M:%S')} (星期{weekday_map[now.weekday()]})"

        # Dual-Write Layer 2: Save to Episodic Vector Store
        if self.vector_store:
            try:
                self.vector_store.add_episode(
                    contact_name=contact_name,
                    timestamp=now.strftime("%Y-%m-%d %H:%M:%S"),
                    content=raw_chat_text
                )
            except Exception as e:
                logger.warning(f"Failed to write episodic memory for [{contact_name}]: {e}")

        # Dual-Write Layer 1: Extract and Save Key Facts
        existing_data = self.load_memory(contact_name)
        existing_facts = existing_data.get("facts", [])

        user_prompt = f"""【當前對話基準時間】：{now_str}

當前舊有的記憶列表：
{json.dumps(existing_facts, ensure_ascii=False, indent=2)}

最新對話紀錄：
<chat_history>
{raw_chat_text}
</chat_history>

請根據【當前對話基準時間】嚴格將所有涉及時間的事實推算並轉換為具體絕對日期（格式如 YYYY-MM-DD (星期X)），分析上述對話，並輸出更新後的全量記憶 JSON 陣列："""

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
