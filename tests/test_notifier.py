"""
Unit tests for Telegram Notifier (core/notifier.py).
"""

import os
import sys

if sys.platform != "win32" and "DISPLAY" not in os.environ:
    os.environ["DISPLAY"] = ":99"

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.notifier import TelegramNotifier
from main import load_config


def test_notifier_initialization_defaults():
    config = {
        "notification": {
            "enabled": True,
            "telegram_bot_token": "test_bot_token",
            "telegram_chat_id": "12345678",
            "verification_timeout": 60
        }
    }
    notifier = TelegramNotifier(config)
    assert notifier.enabled is True
    assert notifier.bot_token == "test_bot_token"
    assert notifier.chat_id == "12345678"
    assert notifier.verification_timeout == 60
    assert notifier.is_configured() is True


def test_notifier_env_var_precedence():
    config = {
        "notification": {
            "telegram_bot_token": "yaml_token",
            "telegram_chat_id": "yaml_chat_id"
        }
    }
    os.environ["TELEGRAM_BOT_TOKEN"] = "env_token"
    os.environ["TELEGRAM_CHAT_ID"] = "env_chat_id"
    try:
        notifier = TelegramNotifier(config)
        assert notifier.bot_token == "env_token"
        assert notifier.chat_id == "env_chat_id"
    finally:
        del os.environ["TELEGRAM_BOT_TOKEN"]
        del os.environ["TELEGRAM_CHAT_ID"]


def test_config_example_notification_keys():
    config = load_config("config.example.yaml")
    assert "notification" in config
    notify_cfg = config["notification"]
    assert notify_cfg.get("enabled") is True
    assert "telegram_bot_token" in notify_cfg
    assert "telegram_chat_id" in notify_cfg


if __name__ == "__main__":
    test_notifier_initialization_defaults()
    test_notifier_env_var_precedence()
    test_config_example_notification_keys()
    print("All Telegram Notifier unit tests PASSED!")
