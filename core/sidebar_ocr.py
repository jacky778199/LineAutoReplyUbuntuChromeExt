"""
Sidebar OCR Pre-filter Module for LINE Auto-Reply Bot.
Performs Zero-Click Whitelist Verification using local Tesseract OCR
to prevent unintended 'Read' marking on non-whitelisted contacts.
"""

import os
import sys
import time
import logging
from typing import List, Tuple, Dict, Any, Optional

import cv2
import numpy as np

try:
    import pytesseract
    TESSERACT_AVAILABLE = True
except ImportError:
    TESSERACT_AVAILABLE = False

try:
    from rapidocr_onnxruntime import RapidOCR
    RAPID_OCR_AVAILABLE = True
except ImportError:
    RAPID_OCR_AVAILABLE = False

try:
    import opencc
    OPENCC_AVAILABLE = True
except ImportError:
    OPENCC_AVAILABLE = False

logger = logging.getLogger(__name__)


class SidebarOCR:
    """Zero-Click Whitelist Pre-filtering using RapidOCR (with Tesseract fallback) and Traditional Chinese normalization."""

    def __init__(self, cooldown_seconds: int = 30):
        self.cooldown_seconds = cooldown_seconds
        self._non_whitelisted_cache: Dict[Tuple[int, int], float] = {}
        self.rapid_ocr = RapidOCR() if RAPID_OCR_AVAILABLE else None
        self.s2t_converter = opencc.OpenCC('s2t') if OPENCC_AVAILABLE else None

    def clean_ocr_text(self, text: str) -> str:
        """Cleans whitespace, noisy OCR artifacts, and converts Simplified Chinese to Traditional Chinese."""
        if not text:
            return ""
        cleaned = "".join(text.split()).strip()
        if self.s2t_converter:
            try:
                cleaned = self.s2t_converter.convert(cleaned)
            except Exception:
                pass
        return cleaned

    def crop_sidebar_chat_item(
        self,
        screenshot_bgr: np.ndarray,
        dot_pos: Tuple[int, int]
    ) -> Optional[np.ndarray]:
        """
        Crops the text region (contact name + message preview) to the left of the green dot.
        """
        if screenshot_bgr is None:
            return None

        cx, cy = int(dot_pos[0]), int(dot_pos[1])
        s_h, s_w = screenshot_bgr.shape[:2]

        # Calculate bounding box for name & preview area (avoiding leftmost avatar)
        x_min = max(60, cx - 270)
        x_max = max(x_min + 30, cx - 15)
        y_min = max(0, cy - 32)
        y_max = min(s_h, cy + 28)

        if x_max <= x_min or y_max <= y_min:
            return None

        crop = screenshot_bgr[y_min:y_max, x_min:x_max]
        return crop

    def preprocess_for_ocr(self, crop_bgr: np.ndarray) -> np.ndarray:
        """Applies grayscale, contrast boost, and 2x enlargement for fallback OCR."""
        if crop_bgr is None or crop_bgr.size == 0:
            return None

        # Convert to grayscale
        gray = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2GRAY)

        # 2x enlargement for small font clarity
        resized = cv2.resize(gray, (0, 0), fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)

        # Normalize contrast
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(resized)

        return enhanced

    def recognize_chat_item_text(
        self,
        screenshot_bgr: np.ndarray,
        dot_pos: Tuple[int, int]
    ) -> str:
        """
        Runs local OCR (RapidOCR or Tesseract fallback) on the sidebar item at dot_pos.
        Returns recognized string.
        """
        crop = self.crop_sidebar_chat_item(screenshot_bgr, dot_pos)
        if crop is None:
            return ""

        # 1. Primary: RapidOCR (High-accuracy Deep Learning OCR with 2.5x cubic upscale)
        if self.rapid_ocr is not None:
            try:
                # 2.5x Bicubic upscale for small UI fonts (12-14px) to prevent stroke collapse
                upscaled_crop = cv2.resize(crop, (0, 0), fx=2.5, fy=2.5, interpolation=cv2.INTER_CUBIC)
                ocr_results, _ = self.rapid_ocr(upscaled_crop)
                if ocr_results:
                    recognized_lines = [item[1] for item in ocr_results if len(item) > 1 and item[1]]
                    full_text = "".join(recognized_lines)
                    clean = self.clean_ocr_text(full_text)
                    if clean:
                        return clean
            except Exception as e:
                logger.warning(f"RapidOCR 辨識側邊欄文字異常，降級為 Tesseract: {e}")

        # 2. Fallback: Local Tesseract OCR
        if TESSERACT_AVAILABLE:
            prep = self.preprocess_for_ocr(crop)
            if prep is not None:
                try:
                    raw_ocr = pytesseract.image_to_string(
                        prep,
                        lang="chi_tra+eng",
                        config="--psm 6"
                    )
                    clean = self.clean_ocr_text(raw_ocr)
                    if not clean:
                        raw_ocr_sparse = pytesseract.image_to_string(
                            prep,
                            lang="chi_tra+eng",
                            config="--psm 11"
                        )
                        clean = self.clean_ocr_text(raw_ocr_sparse)
                    return clean
                except Exception as e:
                    logger.warning(f"Tesseract OCR 辨識側邊欄文字時發生異常: {e}")

        return ""

    def is_dot_in_cooldown(self, dot_pos: Tuple[int, int]) -> bool:
        """Checks if a green dot coordinate is in non-whitelisted cooldown."""
        now = time.time()
        cx, cy = int(dot_pos[0]), int(dot_pos[1])
        # Grid snap cy to nearest 15px to account for minor 1-2px detection drift
        grid_key = (round(cx, -1), round(cy / 15.0) * 15)

        expire_time = self._non_whitelisted_cache.get(grid_key, 0)
        if now < expire_time:
            return True
        return False

    def mark_dot_non_whitelisted(self, dot_pos: Tuple[int, int]):
        """Caches dot position as non-whitelisted to prevent rapid repeat OCR."""
        cx, cy = int(dot_pos[0]), int(dot_pos[1])
        grid_key = (round(cx, -1), round(cy / 15.0) * 15)
        self._non_whitelisted_cache[grid_key] = time.time() + self.cooldown_seconds

    def check_whitelist_zero_click(
        self,
        screenshot_bgr: np.ndarray,
        dot_pos: Tuple[int, int],
        whitelist: List[str]
    ) -> Dict[str, Any]:
        """
        Zero-Click Whitelist Verifier:
        1. Checks cooldown cache.
        2. Crops item & runs Tesseract OCR.
        3. Matches recognized text with whitelist names.
        
        Returns dict:
            - is_whitelisted: bool
            - matched_contact: str or None
            - recognized_text: str
            - in_cooldown: bool
        """
        if not whitelist:
            # If whitelist is empty, all contacts are allowed
            return {
                "is_whitelisted": True,
                "matched_contact": None,
                "recognized_text": "",
                "in_cooldown": False
            }

        # 1. Cooldown check
        if self.is_dot_in_cooldown(dot_pos):
            return {
                "is_whitelisted": False,
                "matched_contact": None,
                "recognized_text": "(快取冷卻中 / Cooldown)",
                "in_cooldown": True
            }

        # 2. Run OCR
        recognized_text = self.recognize_chat_item_text(screenshot_bgr, dot_pos)

        # 3. Match with whitelist
        matched_contact = None
        for wl in whitelist:
            clean_wl = self.clean_ocr_text(wl)
            # Direct or substring match
            if clean_wl.lower() in recognized_text.lower() or recognized_text.lower() in clean_wl.lower():
                matched_contact = wl
                break
            # Partial prefix match for multi-character names (>= 2 chars)
            if len(clean_wl) >= 2 and (clean_wl[:2] in recognized_text or clean_wl[-2:] in recognized_text):
                matched_contact = wl
                break

        is_whitelisted = matched_contact is not None

        # 4. If not whitelisted, add to cooldown
        if not is_whitelisted:
            self.mark_dot_non_whitelisted(dot_pos)

        return {
            "is_whitelisted": is_whitelisted,
            "matched_contact": matched_contact,
            "recognized_text": recognized_text,
            "in_cooldown": False
        }
