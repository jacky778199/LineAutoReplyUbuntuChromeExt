"""
Test for Configuration and Persona Prompt Lookup.
"""

import os
import sys
import yaml

if sys.platform != "win32" and "DISPLAY" not in os.environ:
    os.environ["DISPLAY"] = ":99"

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from main import load_config
from core.llm_service import LLMService

def test_config_loading():
    config = load_config("config.yaml")
    assert "llm" in config
    assert "bot" in config
    assert "ui" in config
    assert "provider" in config["llm"]["primary"]
    assert "provider" in config["llm"]["backup"]
    print("test_config_loading PASSED!")

def test_persona_prompt_resolution():
    config = load_config("config.yaml")
    llm = LLMService(config)

    # Test default prompt resolution
    default_prompt = llm._get_system_prompt_for_contact("RandomFriend")
    assert len(default_prompt) > 0

    print("test_persona_prompt_resolution PASSED!")

if __name__ == "__main__":
    test_config_loading()
    test_persona_prompt_resolution()
