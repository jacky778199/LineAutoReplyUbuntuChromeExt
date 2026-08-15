"""
Environment & Screen Baseline Validator for LINE Auto-Reply Bot.
Validates if the current display/screen state matches the expected LINE desktop layout,
especially checking the left sidebar region (x: 0 ~ 400).
"""

import os
import sys
import logging
import cv2
import numpy as np

if sys.platform != "win32" and "DISPLAY" not in os.environ:
    os.environ["DISPLAY"] = ":99"

import pyautogui

logger = logging.getLogger(__name__)


class EnvironmentValidator:
    """Validates if the current screen environment matches expected LINE desktop UI layout."""

    def __init__(
        self,
        anchor_template_path: str = "assets/Message_icon.png",
        left_roi_width: int = 400,
        anchor_confidence_threshold: float = 0.55
    ):
        self.anchor_template_path = anchor_template_path
        self.left_roi_width = left_roi_width
        self.anchor_confidence_threshold = anchor_confidence_threshold

    def validate_screen(self, screenshot_bgr=None, save_debug_image_on_fail: bool = True) -> dict:
        """
        Runs comprehensive checks on the current screen:
        1. Screen capture & resolution readiness
        2. Blank / Black screen check
        3. Left ROI (x: 0 ~ left_roi_width) LINE UI anchor detection
        
        Returns:
            dict containing overall status (is_valid: bool), sub-check details, and diagnostics message.
        """
        report = {
            "is_valid": True,
            "resolution": (0, 0),
            "is_non_blank": False,
            "anchor_found": False,
            "anchor_score": 0.0,
            "anchor_location": None,
            "left_roi_width": self.left_roi_width,
            "warnings": [],
            "message": ""
        }

        # 1. Capture screen if not provided
        if screenshot_bgr is None:
            try:
                screenshot_pil = pyautogui.screenshot()
                screenshot_np = np.array(screenshot_pil)
                screenshot_bgr = cv2.cvtColor(screenshot_np, cv2.COLOR_RGB2BGR)
            except Exception as e:
                report["is_valid"] = False
                report["warnings"].append(f"螢幕截圖失敗: {e}")
                report["message"] = "❌ 無法擷取螢幕畫面，請確認 DISPLAY 環境變數與 X11/Xvfb 服務。"
                return report

        s_h, s_w = screenshot_bgr.shape[:2]
        report["resolution"] = (s_w, s_h)

        if s_w < 400 or s_h < 300:
            report["is_valid"] = False
            report["warnings"].append(f"螢幕解析度過小: {s_w}x{s_h}")

        # 2. Blank / Black Screen Check (Mean brightness & Standard deviation)
        gray = cv2.cvtColor(screenshot_bgr, cv2.COLOR_BGR2GRAY)
        mean_brightness = float(np.mean(gray))
        std_dev = float(np.std(gray))

        if mean_brightness < 8.0 or std_dev < 5.0:
            report["is_valid"] = False
            report["is_non_blank"] = False
            report["warnings"].append(f"螢幕畫面異常（疑似黑屏/待機）: 平均亮度={mean_brightness:.1f}, 標準差={std_dev:.1f}")
        else:
            report["is_non_blank"] = True

        # 3. Check Left Region (x: 0 ~ left_roi_width) for LINE UI Anchor (Message_icon.png)
        left_roi_w = min(self.left_roi_width, s_w)
        left_roi = screenshot_bgr[:, :left_roi_w]

        if os.path.exists(self.anchor_template_path):
            anchor_tpl = cv2.imread(self.anchor_template_path, cv2.IMREAD_COLOR)
            if anchor_tpl is not None:
                t_h, t_w = anchor_tpl.shape[:2]
                res = cv2.matchTemplate(left_roi, anchor_tpl, cv2.TM_CCOEFF_NORMED)
                min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)

                report["anchor_score"] = round(float(max_val), 4)
                report["anchor_location"] = (max_loc[0] + t_w // 2, max_loc[1] + t_h // 2)

                if max_val >= self.anchor_confidence_threshold:
                    report["anchor_found"] = True
                else:
                    report["is_valid"] = False
                    report["warnings"].append(
                        f"畫面左側 (x < {left_roi_w}) 未找到 LINE 導航圖示 (最高相似度 {max_val:.2f} < 門檻 {self.anchor_confidence_threshold})"
                    )
            else:
                report["warnings"].append(f"無法載入基準樣板圖片: {self.anchor_template_path}")
        else:
            report["warnings"].append(f"找不到基準樣板圖片檔案: {self.anchor_template_path}")

        # Construct final diagnostic message
        if report["is_valid"]:
            report["message"] = (
                f"✅ [環境檢測正常] 解析度: {s_w}x{s_h} | 左側 (x<{left_roi_w}) LINE 介面定位成功 "
                f"(圖標座標: {report['anchor_location']}, 信心度: {report['anchor_score']:.2f})"
            )
        else:
            report["message"] = (
                f"⚠️ [環境檢測異常] 畫面左側 (x < {left_roi_w}) 與預期 LINE 介面不符！\n"
                f"   詳細原因: {'; '.join(report['warnings'])}\n"
                f"   💡 排查提示: 請確認 (1) LINE 是否開啟且未最小化 (2) LINE 視窗是否在畫面左側 (3) 畫面未被瀏覽器等其他視窗完全覆蓋。"
            )
            if save_debug_image_on_fail:
                self._save_env_fail_image(screenshot_bgr, report)

        return report

    def _save_env_fail_image(self, screenshot_bgr, report):
        """Saves annotated debug image when environment validation fails."""
        try:
            os.makedirs("debug", exist_ok=True)
            dbg = screenshot_bgr.copy()
            h, w = dbg.shape[:2]

            # Highlight left ROI box (Red / Orange)
            roi_w = min(self.left_roi_width, w)
            cv2.rectangle(dbg, (0, 0), (roi_w, h), (0, 0, 255), 3)
            cv2.putText(
                dbg,
                f"EXPECTED LINE AREA (x: 0~{roi_w}) - ANCHOR NOT FOUND",
                (15, 35),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (0, 0, 255),
                2
            )

            # If anchor was found with lower score, show it
            if report.get("anchor_location"):
                ax, ay = report["anchor_location"]
                score = report.get("anchor_score", 0)
                cv2.circle(dbg, (ax, ay), 20, (0, 165, 255), 2)
                cv2.putText(
                    dbg,
                    f"Best Match ({score:.2f})",
                    (ax + 25, ay),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.5,
                    (0, 165, 255),
                    1
                )

            out_file = "debug/env_check_failed.png"
            cv2.imwrite(out_file, dbg)
            logger.info(f"📁 環境檢測失敗畫面已儲存至: {out_file}")
        except Exception as e:
            logger.debug(f"儲存環境檢測失敗圖失敗: {e}")
