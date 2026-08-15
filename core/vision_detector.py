"""
Vision Detector for LINE Unread Badges (Green Dots).
Uses OpenCV template matching to locate unread dots on screen.
"""

import os
import sys
import logging
import numpy as np
import cv2

if sys.platform != "win32" and "DISPLAY" not in os.environ:
    os.environ["DISPLAY"] = ":99"

import pyautogui
from PIL import Image

logger = logging.getLogger(__name__)

class GreenDotDetector:
    """
    Detects unread green badges on the LINE desktop window.
    Supports:
    1. HSV Green Blob Area Filter (e.g. 248px ~ 356px).
    2. OpenCV Template Matching (Normalized Cross-Correlation).
    3. Hybrid Mode: Combines color blob + template matching for maximum reliability.
    """

    def __init__(
        self,
        template_path: str = "assets/green_dot_white_x.png",
        confidence: float = 0.65,
        debug: bool = False,
        min_blob_area: int = 248,
        max_blob_area: int = 356,
        detection_mode: str = "hybrid"
    ):
        self.template_path = template_path
        self.confidence = confidence
        self.debug = debug
        self.min_blob_area = min_blob_area
        self.max_blob_area = max_blob_area
        self.detection_mode = detection_mode.lower()
        self.ensure_template_exists()

    def ensure_template_exists(self):
        """Creates a synthetic default green dot template if the file does not exist yet."""
        if not os.path.exists(self.template_path):
            os.makedirs(os.path.dirname(self.template_path), exist_ok=True)
            logger.warning(f"Template '{self.template_path}' not found. Generating default green dot template...")
            
            # Create a 16x16 circular green badge (LINE default green: BGR ~ (46, 197, 6))
            img = np.zeros((16, 16, 3), dtype=np.uint8)
            img[:] = (240, 240, 240)  # Light gray background
            cv2.circle(img, (8, 8), 6, (46, 197, 6), -1)  # Green filled circle
            
            cv2.imwrite(self.template_path, img)
            logger.info(f"Default green dot template saved to '{self.template_path}'.")

    def capture_screen(self, region=None):
        """
        Captures a screenshot safely and returns (screenshot_bgr, screenshot_pil).
        If it fails, logs clear diagnostic information.
        """
        try:
            screenshot = pyautogui.screenshot(region=region)
            screenshot_np = np.array(screenshot)
            screenshot_bgr = cv2.cvtColor(screenshot_np, cv2.COLOR_RGB2BGR)
            return screenshot_bgr, screenshot
        except Exception as e:
            logger.error(
                f"❌ 螢幕截圖失敗: {e}\n"
                f"💡 [排查提示] 若在 Linux 環境，請確認是否安裝了 gnome-screenshot 或 scrot (sudo apt install gnome-screenshot scrot)\n"
                f"💡 若在遠端/無介面環境，請確認 DISPLAY 環境變數是否正確設定。"
            )
            return None, None

    def find_unread_dots_by_color_blob(self, screenshot_bgr, region=None) -> tuple:
        """
        Locates unread green dots using LINE's signature green color (#06C755) and area filter (min_blob_area ~ max_blob_area px).
        Returns (list of (cx, cy) tuples, list of blob metadata dicts).
        """
        hsv = cv2.cvtColor(screenshot_bgr, cv2.COLOR_BGR2HSV)
        lower_green = np.array([35, 120, 100])
        upper_green = np.array([85, 255, 255])
        green_mask = cv2.inRange(hsv, lower_green, upper_green)

        contours, _ = cv2.findContours(green_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        offset_x = region[0] if region else 0
        offset_y = region[1] if region else 0

        blob_points = []
        blob_details = []

        for cnt in contours:
            area = cv2.contourArea(cnt)
            if self.min_blob_area <= area <= self.max_blob_area:
                x, y, w, h = cv2.boundingRect(cnt)
                aspect_ratio = float(w) / h if h > 0 else 0
                # Filter for circular / rounded pill shape
                if 0.5 <= aspect_ratio <= 2.2:
                    cx = x + w // 2 + offset_x
                    cy = y + h // 2 + offset_y
                    blob_points.append((cx, cy))
                    blob_details.append({
                        "rect": (x, y, w, h),
                        "area": area,
                        "center": (cx, cy)
                    })

        filtered_points = self._group_nearby_points(blob_points, min_distance=15)
        filtered_points.sort(key=lambda p: p[1])
        return filtered_points, blob_details

    def find_unread_dots(self, region=None, save_debug_image=False) -> list:
        """
        Locates unread green dot badges on screen within optional region tuple (left, top, width, height).
        Uses specified detection_mode ('hybrid', 'color_blob', or 'template').
        """
        try:
            # 1. Capture screenshot
            screenshot_bgr, screenshot_pil = self.capture_screen(region=region)
            if screenshot_bgr is None:
                return []

            s_h, s_w = screenshot_bgr.shape[:2]
            offset_x = region[0] if region else 0
            offset_y = region[1] if region else 0

            detected_points = []
            blob_matches = []
            template_matches = []
            max_val = 0.0
            max_loc = (0, 0)
            template = None

            # 2. Method A: Color Blob Area Filter (248px ~ 356px)
            if self.detection_mode in ["color_blob", "hybrid"]:
                blob_points, blob_matches = self.find_unread_dots_by_color_blob(screenshot_bgr, region=region)
                if blob_points:
                    logger.info(
                        f"🟢 [綠色色塊辨識] 成功命中 {len(blob_points)} 個綠點！"
                        f" (面積限制: {self.min_blob_area}~{self.max_blob_area}px，命中色塊面積: {[int(b['area']) for b in blob_matches]})"
                    )
                    detected_points.extend(blob_points)

            # 3. Method B: Template Matching
            if self.detection_mode in ["template", "hybrid"]:
                if os.path.exists(self.template_path):
                    template = cv2.imread(self.template_path, cv2.IMREAD_COLOR)
                    if template is not None:
                        t_h, t_w = template.shape[:2]
                        res = cv2.matchTemplate(screenshot_bgr, template, cv2.TM_CCOEFF_NORMED)
                        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)

                        loc = np.where(res >= self.confidence)
                        for pt in zip(*loc[::-1]):  # (x, y)
                            cx = pt[0] + t_w // 2 + offset_x
                            cy = pt[1] + t_h // 2 + offset_y
                            template_matches.append((cx, cy))

                        filtered_tpl = self._group_nearby_points(template_matches, min_distance=15)
                        if filtered_tpl:
                            logger.info(f"🎯 [樣板比對辨識] 命中 {len(filtered_tpl)} 個綠點 (最高信心度: {max_val:.2f})")
                            detected_points.extend(filtered_tpl)
                        elif self.detection_mode == "template" and max_val >= 0.50:
                            best_x = max_loc[0] + t_w // 2 + offset_x
                            best_y = max_loc[1] + t_h // 2 + offset_y
                            logger.info(f"⚠️ 樣板最高相似度 {max_val:.2f} < 門檻 {self.confidence:.2f} 於座標 ({best_x}, {best_y})")

            # 4. Merge and Deduplicate Points
            final_points = self._group_nearby_points(detected_points, min_distance=18)
            final_points.sort(key=lambda p: p[1])

            # Debug logging and Visual Output (僅在 debug 模式或明確指定 save_debug_image 時才輸出圖片)
            if self.debug or save_debug_image:
                self._save_debug_visualization(
                    screenshot_bgr, template, max_loc, max_val, final_points, blob_matches, offset_x, offset_y
                )

            return final_points

        except Exception as e:
            logger.error(f"❌ 綠點辨識過程發生未預期錯誤: {e}", exc_info=True)
            return []

    def create_coordinate_grid_map(
        self,
        image_bgr=None,
        points: list = None,
        grid_spacing: int = 100,
        output_path: str = "debug/coordinate_grid_map.png"
    ):
        """
        Generates a coordinate grid overlay map on top of screenshot_bgr.
        Draws 100px major / 50px minor grid lines, coordinate labels, and crosshair pins
        for all provided points to make debugging coordinate clicks effortless.
        """
        try:
            if image_bgr is None:
                image_bgr, _ = self.capture_screen()
                if image_bgr is None:
                    return None

            os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else "debug", exist_ok=True)
            h, w = image_bgr.shape[:2]

            # Create overlay for semi-transparent grid lines
            grid_layer = image_bgr.copy()

            # 1. Draw Minor Grid Lines (every grid_spacing // 2, e.g. 50px)
            minor_step = max(25, grid_spacing // 2)
            for x in range(0, w, minor_step):
                if x % grid_spacing != 0:
                    cv2.line(grid_layer, (x, 0), (x, h), (80, 80, 80), 1, cv2.LINE_AA)
            for y in range(0, h, minor_step):
                if y % grid_spacing != 0:
                    cv2.line(grid_layer, (0, y), (w, y), (80, 80, 80), 1, cv2.LINE_AA)

            # 2. Draw Major Grid Lines (every grid_spacing, e.g. 100px)
            for x in range(0, w, grid_spacing):
                cv2.line(grid_layer, (x, 0), (x, h), (180, 180, 180), 1, cv2.LINE_AA)
            for y in range(0, h, grid_spacing):
                cv2.line(grid_layer, (0, y), (w, y), (180, 180, 180), 1, cv2.LINE_AA)

            # Blend grid layer with 40% opacity
            annotated = cv2.addWeighted(grid_layer, 0.45, image_bgr, 0.55, 0)

            # 3. Draw Axis Coordinate Numbers along top, middle, and bottom
            for x in range(0, w, grid_spacing):
                txt = f"{x}"
                # Top ruler bar
                cv2.rectangle(annotated, (x - 2, 0), (x + 36, 16), (20, 20, 20), -1)
                cv2.putText(annotated, txt, (x + 2, 12), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (0, 255, 255), 1)

            for y in range(0, h, grid_spacing):
                txt = f"{y}"
                # Left ruler bar
                cv2.rectangle(annotated, (0, y - 2), (36, y + 14), (20, 20, 20), -1)
                cv2.putText(annotated, txt, (2, y + 10), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (0, 255, 255), 1)

            # 4. Highlight Provided Points with Crosshairs & Coordinate Badges
            if points:
                for idx, pt in enumerate(points):
                    if isinstance(pt, dict):
                        cx, cy = pt.get("pos", (0, 0))
                        label = pt.get("label", f"P{idx+1}")
                        color = pt.get("color", (0, 255, 0))
                    elif isinstance(pt, (tuple, list)):
                        cx, cy = int(pt[0]), int(pt[1])
                        label = f"Target {idx+1}"
                        color = (0, 255, 0)
                    else:
                        continue

                    # Draw Crosshairs
                    cv2.line(annotated, (max(0, cx - 30), cy), (min(w, cx + 30), cy), color, 2)
                    cv2.line(annotated, (cx, max(0, cy - 30)), (cx, min(h, cy + 30)), color, 2)
                    
                    # Target Circles
                    cv2.circle(annotated, (cx, cy), 16, color, 2)
                    cv2.circle(annotated, (cx, cy), 4, (0, 0, 255), -1)

                    # Coordinate Badge Box
                    badge_txt = f"{label} ({cx}, {cy})"
                    (tw, th), _ = cv2.getTextSize(badge_txt, cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1)
                    
                    bx = min(w - tw - 12, max(5, cx + 18))
                    by = max(20, min(h - 10, cy - 10))
                    
                    # Background badge
                    cv2.rectangle(annotated, (bx - 4, by - th - 4), (bx + tw + 6, by + 6), (0, 0, 0), -1)
                    cv2.rectangle(annotated, (bx - 4, by - th - 4), (bx + tw + 6, by + 6), color, 1)
                    cv2.putText(annotated, badge_txt, (bx, by), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1)

            cv2.imwrite(output_path, annotated)
            logger.info(f"🗺️ 座標網格對應圖已生成並儲存至: {output_path}")
            return annotated

        except Exception as e:
            logger.error(f"❌ 生成座標網格圖失敗: {e}", exc_info=True)
            return None

    def _save_debug_visualization(self, screenshot_bgr, template, max_loc, max_val, final_points, blob_matches, offset_x, offset_y):
        """Saves an annotated screenshot and coordinate grid map for visual debugging."""
        try:
            os.makedirs("debug", exist_ok=True)
            debug_img = screenshot_bgr.copy()

            # Draw template best match if template exists
            if template is not None:
                t_h, t_w = template.shape[:2]
                bx, by = max_loc[0], max_loc[1]
                t_color = (0, 255, 255) if max_val >= self.confidence else (0, 140, 255)
                cv2.rectangle(debug_img, (bx, by), (bx + t_w, by + t_h), t_color, 1)
                cv2.putText(debug_img, f"Tpl: {max_val:.2f}", (bx, max(15, by - 4)), cv2.FONT_HERSHEY_SIMPLEX, 0.4, t_color, 1)

            # Draw detected Green Blobs (248px ~ 356px)
            for b in blob_matches:
                rx, ry, rw, rh = b["rect"]
                area = b["area"]
                cv2.rectangle(debug_img, (rx, ry), (rx + rw, ry + rh), (255, 0, 255), 2)
                cv2.putText(debug_img, f"Blob:{int(area)}px", (rx, max(15, ry - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 0, 255), 1)

            # Draw final targets to click (Green circles)
            for (cx, cy) in final_points:
                px = cx - offset_x
                py = cy - offset_y
                cv2.circle(debug_img, (px, py), 12, (0, 255, 0), 2)
                cv2.circle(debug_img, (px, py), 3, (0, 0, 255), -1)
                cv2.putText(debug_img, f"TARGET ({cx},{cy})", (px - 20, py + 22), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 0), 1)

            out_path = "debug/latest_detection.png"
            cv2.imwrite(out_path, debug_img)

            # Automatically generate coordinate grid map for discovered points
            marked_points = [{"pos": pt, "label": f"GreenDot {i+1}", "color": (0, 255, 0)} for i, pt in enumerate(final_points)]
            self.create_coordinate_grid_map(screenshot_bgr, points=marked_points, output_path="debug/coordinate_grid_map.png")

        except Exception as e:
            logger.debug(f"無法儲存偵錯圖片: {e}")

    def _group_nearby_points(self, points: list, min_distance: float = 15) -> list:
        """Groups nearby detected points to avoid multiple detections for the same green dot."""
        if not points:
            return []

        grouped = []
        for p in points:
            if not any(np.hypot(p[0] - g[0], p[1] - g[1]) < min_distance for g in grouped):
                grouped.append(p)
        return grouped

    def find_message_icon(self, template_path: str = "assets/Message_icon.png", confidence: float = 0.60, region=None) -> tuple:
        """
        Locates the Message_icon.png on screen using OpenCV template matching.
        Returns (center_x, center_y) tuple if found, else None.
        """
        if not os.path.exists(template_path):
            logger.warning(f"Message icon template '{template_path}' not found.")
            return None

        try:
            screenshot_bgr, _ = self.capture_screen(region=region)
            if screenshot_bgr is None:
                return None

            template = cv2.imread(template_path, cv2.IMREAD_COLOR)
            if template is None:
                logger.error(f"Failed to read message icon template from '{template_path}'.")
                return None

            t_h, t_w = template.shape[:2]
            res = cv2.matchTemplate(screenshot_bgr, template, cv2.TM_CCOEFF_NORMED)
            min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)

            if max_val >= confidence:
                offset_x = region[0] if region else 0
                offset_y = region[1] if region else 0
                center_x = max_loc[0] + t_w // 2 + offset_x
                center_y = max_loc[1] + t_h // 2 + offset_y
                logger.info(f"🎯 [影像辨識] 成功比對找到 Message_icon.png 於座標 ({center_x}, {center_y})，信心度: {max_val:.2f}")
                return (center_x, center_y)
            else:
                logger.warning(f"Message_icon.png 未達信心度門檻 (最高信心度: {max_val:.2f} < 門檻 {confidence})")
                return None
        except Exception as e:
            logger.error(f"Error matching Message_icon.png: {e}")
            return None

