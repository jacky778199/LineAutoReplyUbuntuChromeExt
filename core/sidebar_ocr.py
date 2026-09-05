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

    def crop_sidebar_regions(
        self,
        screenshot_bgr: np.ndarray,
        dot_pos: Tuple[int, int]
    ) -> Tuple[Optional[np.ndarray], Optional[np.ndarray]]:
        """
        Crops separated regions:
        1. Name crop (Upper half, single line)
        2. Message preview crop (Lower half)
        """
        if screenshot_bgr is None:
            return None, None

        cx, cy = int(dot_pos[0]), int(dot_pos[1])
        s_h, s_w = screenshot_bgr.shape[:2]

        # Calculate horizontal text span avoiding left avatar
        x_min = max(60, cx - 270)
        x_max = max(x_min + 30, cx - 15)

        # 1. Contact Name region (Upper half: cy - 32 to cy - 2)
        y_name_min = max(0, cy - 32)
        y_name_max = max(0, cy - 2)
        name_crop = screenshot_bgr[y_name_min:y_name_max, x_min:x_max] if y_name_max > y_name_min else None

        # 2. Message Preview region (Lower half: cy - 2 to cy + 28)
        y_msg_min = max(0, cy - 2)
        y_msg_max = min(s_h, cy + 28)
        msg_crop = screenshot_bgr[y_msg_min:y_msg_max, x_min:x_max] if y_msg_max > y_msg_min else None

        return name_crop, msg_crop

    def crop_sidebar_chat_item(
        self,
        screenshot_bgr: np.ndarray,
        dot_pos: Tuple[int, int]
    ) -> Optional[np.ndarray]:
        """Crops full text region (name + preview) with generous vertical bounds."""
        if screenshot_bgr is None:
            return None
        cx, cy = int(dot_pos[0]), int(dot_pos[1])
        s_h, s_w = screenshot_bgr.shape[:2]
        x_min = max(60, cx - 270)
        x_max = max(x_min + 30, cx - 15)
        # Generous vertical bounds (42px above green dot to ensure top name is never clipped)
        y_min = max(0, cy - 42)
        y_max = min(s_h, cy + 32)
        crop = screenshot_bgr[y_min:y_max, x_min:x_max] if (x_max > x_min and y_max > y_min) else None
        
        # Save debug image for verification
        if crop is not None and crop.size > 0:
            try:
                cv2.imwrite("debug/sidebar_preview.png", crop)
            except Exception:
                pass

        return crop

    def preprocess_for_ocr(self, crop_bgr: np.ndarray) -> np.ndarray:
        """
        Applies high-resolution 3.5x bicubic upscaling, unsharp mask sharpening,
        CLAHE contrast normalization, and Otsu adaptive binarization to prevent stroke collapse.
        """
        if crop_bgr is None or crop_bgr.size == 0:
            return None

        # Convert to grayscale
        gray = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2GRAY)

        # 1. 3.5x Bicubic enlargement for fine strokes clarity
        resized = cv2.resize(gray, (0, 0), fx=3.5, fy=3.5, interpolation=cv2.INTER_CUBIC)

        # 2. Unsharp Masking to sharpen character edges
        gaussian = cv2.GaussianBlur(resized, (0, 0), 2.0)
        sharpened = cv2.addWeighted(resized, 1.6, gaussian, -0.6, 0)

        # 3. CLAHE local contrast enhancement
        clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
        enhanced = clahe.apply(sharpened)

        # 4. Otsu Adaptive Binarization
        _, binary = cv2.threshold(enhanced, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

        return binary

    def recognize_single_line_text(self, crop_bgr: np.ndarray) -> str:
        """Runs single-line optimized OCR (PSM 7) on a single horizontal line crop."""
        if crop_bgr is None or crop_bgr.size == 0 or not TESSERACT_AVAILABLE:
            return ""
        prep = self.preprocess_for_ocr(crop_bgr)
        if prep is None:
            return ""
        try:
            # PSM 7: Treat the image as a single text line
            raw = pytesseract.image_to_string(prep, lang="chi_tra+eng", config="--psm 7 --oem 1")
            clean = self.clean_ocr_text(raw)
            if not clean:
                # PSM 8: Single word fallback
                raw_w = pytesseract.image_to_string(prep, lang="chi_tra+eng", config="--psm 8 --oem 1")
                clean = self.clean_ocr_text(raw_w)
            return clean
        except Exception as e:
            logger.debug(f"Single-line OCR failed: {e}")
            return ""

    def recognize_chat_item_text(
        self,
        screenshot_bgr: np.ndarray,
        dot_pos: Tuple[int, int]
    ) -> str:
        """
        Runs local OCR on the sidebar item crop (including both name and preview text).
        Uses RapidOCR if available, or Tesseract with multi-PSM fallback.
        """
        combined_crop = self.crop_sidebar_chat_item(screenshot_bgr, dot_pos)
        if combined_crop is None:
            return ""

        # 1. Primary: RapidOCR if available
        if self.rapid_ocr is not None:
            try:
                upscaled_crop = cv2.resize(combined_crop, (0, 0), fx=2.5, fy=2.5, interpolation=cv2.INTER_CUBIC)
                ocr_results, _ = self.rapid_ocr(upscaled_crop)
                if ocr_results:
                    recognized_lines = [item[1] for item in ocr_results if len(item) > 1 and item[1]]
                    clean = self.clean_ocr_text("".join(recognized_lines))
                    if clean:
                        return clean
            except Exception as e:
                logger.warning(f"RapidOCR 辨識側邊欄文字異常: {e}")

        # 2. Fallback: Local Tesseract OCR on full item
        if TESSERACT_AVAILABLE:
            prep = self.preprocess_for_ocr(combined_crop)
            if prep is not None:
                # Try PSM 6 (uniform block of text)
                try:
                    raw_ocr = pytesseract.image_to_string(prep, lang="chi_tra+eng", config="--psm 6")
                    clean = self.clean_ocr_text(raw_ocr)
                    if clean:
                        return clean
                except Exception:
                    pass

                # Try PSM 11 (sparse text)
                try:
                    raw_ocr_sparse = pytesseract.image_to_string(prep, lang="chi_tra+eng", config="--psm 11")
                    clean_s = self.clean_ocr_text(raw_ocr_sparse)
                    if clean_s:
                        return clean_s
                except Exception:
                    pass

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

        # 3. Match with whitelist (Direct substring, prefix, and SequenceMatcher fuzzy matching)
        from difflib import SequenceMatcher
        matched_contact = None
        for wl in whitelist:
            clean_wl = self.clean_ocr_text(wl)
            if not clean_wl:
                continue

            # A. Direct or substring match
            if clean_wl.lower() in recognized_text.lower() or recognized_text.lower() in clean_wl.lower():
                matched_contact = wl
                break

            # B. Substring prefix / suffix match (>= 2 chars)
            if len(clean_wl) >= 2 and (clean_wl[:2] in recognized_text or clean_wl[-2:] in recognized_text):
                matched_contact = wl
                break

            # C. Sequence-aware fuzzy match (prevents random alphabet matching like 'AutoReply' in 'Keyboardshortcuts...')
            matcher = SequenceMatcher(None, clean_wl.lower(), recognized_text.lower())
            match = matcher.find_longest_match(0, len(clean_wl), 0, len(recognized_text))
            # If the longest contiguous matching block >= 60% of name length (and >= 2 chars)
            if match.size >= 2 and (match.size / len(clean_wl)) >= 0.60:
                logger.info(f"✨ [模糊匹配命中白名單] OCR: '{recognized_text}' -> 白名單: '{wl}' (連續匹配長度: {match.size}/{len(clean_wl)})")
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
