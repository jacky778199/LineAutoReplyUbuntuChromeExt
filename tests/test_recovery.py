"""
Unit tests for Environment Recovery Manager (core/recovery_manager.py).
"""

import os
import sys

if sys.platform != "win32" and "DISPLAY" not in os.environ:
    os.environ["DISPLAY"] = ":99"

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.recovery_manager import RecoveryManager
from main import load_config


def test_recovery_manager_config_defaults():
    config = {
        "environment": {
            "auto_recover": True,
            "max_recover_attempts": 3,
            "recover_cooldown_sec": 5.0,
            "display": ":99",
            "chrome_bin": "google-chrome",
            "line_extension_id": "ophjlpahpchlmihnnnihgmmeilfjmjjc",
            "line_password": "test_yaml_password",
            "fullscreen": True
        }
    }
    mgr = RecoveryManager(config)
    assert mgr.auto_recover is True
    assert mgr.max_recover_attempts == 3
    assert mgr.recover_cooldown_sec == 5.0
    assert mgr.display == ":99"
    assert mgr.fullscreen is True
    assert mgr.get_password() == "test_yaml_password"


def test_recovery_manager_env_var_precedence():
    config = {
        "environment": {
            "line_password": "yaml_password"
        }
    }
    os.environ["LINE_PASSWORD"] = "env_secret_password"
    try:
        mgr = RecoveryManager(config)
        assert mgr.get_password() == "env_secret_password"
    finally:
        del os.environ["LINE_PASSWORD"]


def test_config_example_environment_keys():
    config = load_config("config.example.yaml")
    assert "environment" in config
    env_cfg = config["environment"]
    assert env_cfg.get("auto_recover") is True
    assert env_cfg.get("line_extension_id") == "ophjlpahpchlmihnnnihgmmeilfjmjjc"
    assert env_cfg.get("fullscreen") is True


if __name__ == "__main__":
    test_recovery_manager_config_defaults()
    test_recovery_manager_env_var_precedence()
    test_config_example_environment_keys()
    print("All recovery unit tests PASSED!")
