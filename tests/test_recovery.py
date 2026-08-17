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


def test_locate_login_anchors_with_prefilled_text():
    import numpy as np
    import cv2

    mgr = RecoveryManager()

    # Create a synthetic 1080x1920 screenshot with LINE Logo, pre-filled email text, and Log in button
    img = np.full((1080, 1920, 3), 255, dtype=np.uint8)

    # 1. Place LINE Logo at (x: 900~1000, y: 300~336) -> Center: (950, 318)
    tpl_logo = cv2.imread(mgr.login_logo_template_path)
    if tpl_logo is not None:
        lh, lw = tpl_logo.shape[:2]
        img[300:300+lh, 900:900+lw] = tpl_logo

    # 2. Place random/prefilled email text at email field position (y: 360~400)
    cv2.putText(img, "ting825030@gmail.com", (870, 390), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (50, 50, 50), 1)

    # 3. Place Log in button at (x: 870~1030, y: 480~522) -> Center: (950, 501)
    tpl_btn = cv2.imread(mgr.login_button_template_path)
    if tpl_btn is not None:
        bh, bw = tpl_btn.shape[:2]
        img[480:480+bh, 870:870+bw] = tpl_btn

    anchors = mgr.locate_login_anchors(confidence=0.50, screenshot_bgr=img)
    assert anchors["is_found"] is True, "Should detect anchors even when email is prefilled"
    assert anchors["anchor_type"] in ["dual_anchor", "logo_anchor"]
    assert anchors["email_field"] is not None
    assert anchors["password_field"] is not None
    assert anchors["login_button"] is not None

    # Check calculated X is close to 950
    assert abs(anchors["email_field"][0] - 950) < 15
    # Check calculated Y for email is between logo and button
    assert 330 < anchors["email_field"][1] < 450
    assert 400 < anchors["password_field"][1] < 500


def test_window_singleton_methods():
    mgr = RecoveryManager()
    # Test methods execute safely and return correct types
    line_wids = mgr.find_all_line_windows()
    assert isinstance(line_wids, list)

    non_line_wids = mgr.find_all_non_line_chrome_windows()
    assert isinstance(non_line_wids, list)

    # Test duplicate cleanup executes cleanly
    closed = mgr.cleanup_duplicate_windows(keep_latest=True)
    assert isinstance(closed, int)
    assert closed >= 0


def test_sidebar_dual_anchor_validation():
    import numpy as np
    import cv2
    from core.environment_validator import EnvironmentValidator

    val = EnvironmentValidator()
    # Create synthetic screen with dark blue sidebar (x: 0~50)
    img = np.full((1080, 1920, 3), 245, dtype=np.uint8)
    img[:, :50] = (43, 31, 35)  # Dark sidebar background

    # 1. Place Friend icon at (x: 8~46, y: 22~50) -> Center: (27, 36)
    f_tpl = cv2.imread("assets/sidebar_friend_icon.png")
    if f_tpl is not None:
        fh, fw = f_tpl.shape[:2]
        img[22:22+fh, 8:8+fw] = f_tpl

    # 2. Place VOOM icon at (x: 8~46, y: 184~210) -> Center: (27, 197)
    v_tpl = cv2.imread("assets/sidebar_voom_icon.png")
    if v_tpl is not None:
        vh, vw = v_tpl.shape[:2]
        img[184:184+vh, 8:8+vw] = v_tpl

    report = val.validate_screen(screenshot_bgr=img, save_debug_image_on_fail=False)
    assert report["is_valid"] is True
    assert report["anchor_found"] is True
    assert report["anchor_type"] == "dual_anchor"
    assert report["anchor_location"] is not None
    # Check Message icon Y is calculated near 89~90
    msg_x, msg_y = report["anchor_location"]
    assert abs(msg_x - 27) <= 2
    assert abs(msg_y - 90) <= 2


if __name__ == "__main__":
    test_recovery_manager_config_defaults()
    test_recovery_manager_env_var_precedence()
    test_config_example_environment_keys()
    test_locate_login_anchors_with_prefilled_text()
    test_window_singleton_methods()
    test_sidebar_dual_anchor_validation()
    print("All recovery & dual-anchor unit tests PASSED!")
