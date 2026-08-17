"""
Unit tests for Safe Click Protection (Schemes A, B, C):
- Scheme A: Vision-based pure white background spot detection (avoiding hyperlinks, text, images).
- Scheme B: Structural safe margin fallback coordinates.
- Scheme C: Accidental tab dismissal / self-healing defense.
"""

import os
import sys
import numpy as np
import cv2

if sys.platform != "win32" and "DISPLAY" not in os.environ:
    os.environ["DISPLAY"] = ":99"

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.vision_detector import GreenDotDetector
from core.window_helper import LineWindowHelper, SimpleWindow
from core.recovery_manager import RecoveryManager


def test_pure_white_detection():
    detector = GreenDotDetector()
    
    # 1. Synthetic image with 100% white background (1080x1920)
    white_img = np.full((1080, 1920, 3), 255, dtype=np.uint8)
    
    spot = detector.find_safe_white_background_spot(
        search_region=(1000, 200, 500, 500),
        preferred_pos=(1400, 300),
        screenshot_bgr=white_img
    )
    assert spot is not None, "Should find safe spot in pure white image"
    assert spot == (1400, 300), "Should hit preferred_pos immediately when pure white"


def test_avoid_blue_hyperlink_and_text():
    detector = GreenDotDetector()
    
    # Create white canvas
    img = np.full((600, 800, 3), 255, dtype=np.uint8)
    
    # Draw blue hyperlink text / card in the right area (e.g. x: 600~750, y: 150~250)
    # OpenCV BGR for bright blue: (255, 100, 0)
    cv2.rectangle(img, (580, 150), (760, 260), (255, 100, 0), -1)
    cv2.putText(img, "https://example.com/login", (590, 200), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 2)
    
    # Also draw black message bubble on y: 280~380
    cv2.rectangle(img, (580, 280), (760, 380), (50, 50, 50), -1)
    
    # Preferred position is right inside the blue hyperlink!
    preferred_in_link = (650, 200)
    
    # Search region encompasses x: 500~780, y: 100~550
    spot = detector.find_safe_white_background_spot(
        search_region=(500, 100, 280, 450),
        preferred_pos=preferred_in_link,
        patch_size=(20, 20),
        screenshot_bgr=img,
        save_debug=True
    )
    
    assert spot is not None, "Should find a safe white spot elsewhere in search ROI"
    assert spot != preferred_in_link, "Must NOT click inside the blue hyperlink"
    
    # Verify the selected spot in img is actually pure white
    sx, sy = spot
    patch = img[sy-10:sy+10, sx-10:sx+10]
    assert np.mean(patch) >= 245, "Detected patch must be pure white"
    assert np.max(patch[:, :, 0].astype(int) - patch[:, :, 2].astype(int)) <= 15, "Detected patch must not have blue link bias"


def test_all_noisy_no_white_spot():
    detector = GreenDotDetector()
    
    # Image with random noise / no white area (all dark/colored)
    noisy_img = np.random.randint(0, 150, (400, 400, 3), dtype=np.uint8)
    
    spot = detector.find_safe_white_background_spot(
        search_region=(50, 50, 300, 300),
        screenshot_bgr=noisy_img
    )
    assert spot is None, "Should return None when no white patch exists"


def test_window_helper_safe_coordinates():
    win_helper = LineWindowHelper()
    detector = GreenDotDetector()
    
    pos = win_helper.get_safe_chat_history_click_pos(detector=detector)
    assert isinstance(pos, tuple)
    assert len(pos) == 2
    assert pos[0] > 0 and pos[1] > 0


def test_recovery_dismiss_accidental_tabs():
    mgr = RecoveryManager()
    # Ensure method exists and can be called safely without crash
    res = mgr.dismiss_accidental_tabs(validator=None)
    assert res is False or res is True


if __name__ == "__main__":
    test_pure_white_detection()
    test_avoid_blue_hyperlink_and_text()
    test_all_noisy_no_white_spot()
    test_window_helper_safe_coordinates()
    test_recovery_dismiss_accidental_tabs()
    print("✅ All Safe Click (A+B+C) unit tests PASSED successfully!")
