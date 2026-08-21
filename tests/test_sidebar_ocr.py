"""
Unit tests for SidebarOCR module.
"""

import os
import sys
import numpy as np
import cv2

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.sidebar_ocr import SidebarOCR


def test_sidebar_ocr_synthetic():
    ocr = SidebarOCR(cooldown_seconds=10)

    # Create a synthetic 1920x1080 sidebar image with text and a green dot
    img = np.full((1080, 1920, 3), 255, dtype=np.uint8)

    # Draw contact name "Eyeyupy~" at y=200
    cv2.putText(img, "Eyeyupy~", (120, 195), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 2)
    # Draw green dot at (346, 195)
    cv2.circle(img, (346, 195), 8, (6, 197, 46), -1)

    # Draw non-whitelisted contact "Stranger John" at y=300
    cv2.putText(img, "Stranger John", (120, 295), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 2)
    # Draw green dot at (346, 295)
    cv2.circle(img, (346, 295), 8, (6, 197, 46), -1)

    whitelist = ["丁竑福", "AutoReply", "Eyeyupy~"]

    # 1. Test whitelist match on Eyeyupy~
    res_wl = ocr.check_whitelist_zero_click(img, (346, 195), whitelist=whitelist)
    print("\n--- Test Whitelist Item ---")
    print(f"Recognized: '{res_wl['recognized_text']}'")
    print(f"Matched Contact: {res_wl['matched_contact']}")
    print(f"Is Whitelisted: {res_wl['is_whitelisted']}")
    assert res_wl["is_whitelisted"] is True, "Expected Eyeyupy~ to be whitelisted"
    assert res_wl["matched_contact"] == "Eyeyupy~"

    # 2. Test non-whitelisted item
    res_non_wl = ocr.check_whitelist_zero_click(img, (346, 295), whitelist=whitelist)
    print("\n--- Test Non-Whitelist Item ---")
    print(f"Recognized: '{res_non_wl['recognized_text']}'")
    print(f"Matched Contact: {res_non_wl['matched_contact']}")
    print(f"Is Whitelisted: {res_non_wl['is_whitelisted']}")
    assert res_non_wl["is_whitelisted"] is False, "Expected Stranger John to NOT be whitelisted"

    # 3. Test Cooldown cache
    res_cooldown = ocr.check_whitelist_zero_click(img, (346, 295), whitelist=whitelist)
    assert res_cooldown["in_cooldown"] is True, "Second check should be in cooldown"
    print("✅ All SidebarOCR test assertions passed successfully!")


if __name__ == "__main__":
    test_sidebar_ocr_synthetic()
