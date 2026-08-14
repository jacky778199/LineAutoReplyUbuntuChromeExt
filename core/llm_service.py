"""
Dual LLM Service Module.
Primary: Vertex AI / Gemini API
Backup: OpenAI API
Includes automatic failover and contact-specific prompt persona resolution.
"""

import os
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class LLMService:
    """LLM Manager with Vertex AI / Gemini primary and OpenAI backup fallback."""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.llm_config = config.get("llm", {})
        self.bot_config = config.get("bot", {})
        
        self.my_name = self.bot_config.get("my_name", "我")
        self.default_prompt = self.bot_config.get("default_system_prompt", "")
        self.contact_prompts = self.bot_config.get("contact_prompts", {})

        # Clients lazily initialized
        self._gemini_client = None
        self._openai_client = None

    def _get_system_prompt_for_contact(self, contact_name: str) -> str:
        """Resolves system prompt persona for a specific contact or defaults."""
        custom_prompt = self.contact_prompts.get(contact_name)
        if custom_prompt:
            prompt = custom_prompt
        else:
            prompt = self.default_prompt

        # Replace placeholder if present
        return prompt.replace("[MY_NAME]", self.my_name)

    def generate_reply(self, raw_chat_text: str, contact_name: str) -> str:
        """
        Main entry point for generating a response.
        Tries Primary (Vertex AI / Gemini) first. If it fails, falls back to Backup (OpenAI).
        """
        if not raw_chat_text or not raw_chat_text.strip():
            logger.warning("Empty raw chat text received. Skipping LLM generation.")
            return "[NO_REPLY]"

        system_prompt = self._get_system_prompt_for_contact(contact_name)
        full_user_prompt = f"""
你現在正在處理 LINE 聊天室中與【{contact_name}】的對話。
我的名稱是：「{self.my_name}」。

以下是從 LINE 桌面版全選複製出來的原始對話紀錄 (Raw Text)：
==================================================
{raw_chat_text}
==================================================

【處理規則】：
1. 請仔細檢視對話紀錄最下方的最新訊息。
2. 如果最新發出的訊息是我本人（{self.my_name}）發送的，或者該訊息不需要回覆，請**僅回傳** "[NO_REPLY]"。
3. 如果最新訊息是對方（{contact_name}）發出的，請根據上述的系統指示風格，生成一句合適的回覆。
4. 請直接輸出要回覆的純文字，嚴禁包含引號、註解或任何 Markdown 標記。
"""

        # 1. Try Primary LLM (Vertex AI / Gemini)
        try:
            logger.info(f"Attempting reply generation via Primary LLM ({self.llm_config.get('primary', {}).get('provider', 'vertex_ai')})...")
            reply = self._call_primary_llm(system_prompt, full_user_prompt)
            if reply:
                return reply.strip()
        except Exception as e:
            logger.warning(f"Primary LLM failed: {e}. Switching to Backup LLM (OpenAI)...")

        # 2. Try Backup LLM (OpenAI API)
        try:
            logger.info("Attempting reply generation via Backup LLM (OpenAI)...")
            reply = self._call_backup_llm(system_prompt, full_user_prompt)
            if reply:
                return reply.strip()
        except Exception as e:
            logger.error(f"Backup LLM also failed: {e}")

        return "[NO_REPLY]"

    def _call_primary_llm(self, system_prompt: str, user_prompt: str) -> str:
        """Calls Primary LLM (Vertex AI / Gemini API)."""
        primary_cfg = self.llm_config.get("primary", {})
        provider = primary_cfg.get("provider", "vertex_ai")
        model_name = primary_cfg.get("model_name", "gemini-2.0-flash-001")

        # Use google-genai SDK if available
        try:
            from google import genai
            from google.genai import types

            project_id = primary_cfg.get("project_id")
            location = primary_cfg.get("location", "us-central1")

            # Initialize client for Vertex AI or Gemini Developer API
            if provider == "vertex_ai" and project_id and project_id != "YOUR_GCP_PROJECT_ID":
                client = genai.Client(vertexai=True, project=project_id, location=location)
            else:
                # Fallback to standard GEMINI_API_KEY environment variable
                client = genai.Client()

            response = client.models.generate_content(
                model=model_name,
                contents=user_prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    temperature=0.7,
                )
            )
            return response.text if response.text else "[NO_REPLY]"

        except ImportError:
            # Alternative: google-cloud-aiplatform / legacy SDK fallback
            logger.warning("google-genai library not found, attempting google.generativeai fallback...")
            import google.generativeai as ggi
            api_key = os.getenv("GEMINI_API_KEY")
            if api_key:
                ggi.configure(api_key=api_key)
                model = ggi.GenerativeModel(model_name=model_name, system_instruction=system_prompt)
                resp = model.generate_content(user_prompt)
                return resp.text
            raise RuntimeError("Gemini / Vertex AI credentials not configured.")

    def test_connection(self) -> dict:
        """
        Independently tests both Primary and Backup LLM models and reports results.
        Returns a dict with test status and responses for both providers.
        """
        import time
        results = {}
        sample_prompt = "請回覆一句簡短的問候語。"
        system_prompt = "你是一個親切的 LINE 助理。"

        # 1. Test Primary LLM
        primary_cfg = self.llm_config.get("primary", {})
        primary_name = f"{primary_cfg.get('provider', 'vertex_ai')} ({primary_cfg.get('model_name', 'default')})"
        logger.info(f"🧪 [1/2] 正在測試主要模型 (Primary LLM): {primary_name}...")
        try:
            t0 = time.time()
            p_reply = self._call_primary_llm(system_prompt, sample_prompt)
            duration = time.time() - t0
            results["primary"] = {
                "status": "SUCCESS",
                "provider": primary_name,
                "duration_sec": round(duration, 2),
                "reply": p_reply.strip()
            }
            logger.info(f"✅ 主要模型連線成功 ({duration:.2f}s)！回覆: {p_reply.strip()[:60]}")
        except Exception as e:
            results["primary"] = {
                "status": "FAILED",
                "provider": primary_name,
                "error": str(e)
            }
            logger.error(f"❌ 主要模型連線失敗: {e}")

        # 2. Test Backup LLM
        backup_cfg = self.llm_config.get("backup", {})
        backup_name = f"{backup_cfg.get('provider', 'openai')} ({backup_cfg.get('model_name', 'default')})"
        logger.info(f"🧪 [2/2] 正在測試備用模型 (Backup LLM): {backup_name}...")
        try:
            t0 = time.time()
            b_reply = self._call_backup_llm(system_prompt, sample_prompt)
            duration = time.time() - t0
            results["backup"] = {
                "status": "SUCCESS",
                "provider": backup_name,
                "duration_sec": round(duration, 2),
                "reply": b_reply.strip()
            }
            logger.info(f"✅ 備用模型連線成功 ({duration:.2f}s)！回覆: {b_reply.strip()[:60]}")
        except Exception as e:
            results["backup"] = {
                "status": "FAILED",
                "provider": backup_name,
                "error": str(e)
            }
        return results

    def _call_backup_llm(self, system_prompt: str, user_prompt: str) -> str:
        """Calls Backup LLM (OpenAI / Compatible API)."""
        backup_cfg = self.llm_config.get("backup", {})
        api_key = backup_cfg.get("api_key") or os.getenv("OPENAI_API_KEY")
        model_name = backup_cfg.get("model_name", "gpt-4o-mini")

        if not api_key or api_key == "YOUR_OPENAI_API_KEY":
            raise ValueError("OpenAI / Backup API Key is missing in config or environment.")

        from openai import OpenAI
        client = OpenAI(api_key=api_key, base_url=backup_cfg.get("base_url"))

        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.7
        )

        content = response.choices[0].message.content
        return content if content else "[NO_REPLY]"
