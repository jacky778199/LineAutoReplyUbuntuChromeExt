"""
LINE Bot Vision Detector Diagnostic Tool.
Tests screen capture, template matching scores for all templates in assets/,
HSV green color detection, and generates visual debugging images in debug/.
"""

import os
import sys
import glob
import cv2
import numpy as np
import pyautogui
import yaml

# Setup default DISPLAY=:99 for Linux headless environment if not set
if sys.platform != "win32" and "DISPLAY" not in os.environ:
    os.environ["DISPLAY"] = ":99"


def load_config(config_path: str = "config.yaml") -> dict:
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    return {}


def run_vision_test(config: dict = None):
    if config is None:
        config = load_config()

    os.makedirs("debug", exist_ok=True)
    ui_cfg = config.get("ui", {})
    configured_threshold = ui_cfg.get("green_dot_confidence", 0.65)
    configured_template = ui_cfg.get("green_dot_template_path", "assets/green_dot_white_x.png")
    min_blob_area = ui_cfg.get("green_blob_min_area", 248)
    max_blob_area = ui_cfg.get("green_blob_max_area", 356)
    detection_mode = ui_cfg.get("detection_mode", "hybrid")

    print("=================================================================")
    print(" 🛠️  LINE 綠點影像辨識專屬診斷測試 (Vision Diagnostics)")
    print("=================================================================")

    # 1. 測試 Python 螢幕截圖功能
    print("\n[步驟 1/4] 測試螢幕截圖 (pyautogui.screenshot)...")
    try:
        screenshot_pil = pyautogui.screenshot()
        screenshot_np = np.array(screenshot_pil)
        screenshot_bgr = cv2.cvtColor(screenshot_np, cv2.COLOR_RGB2BGR)
        s_h, s_w = screenshot_bgr.shape[:2]
        
        raw_screenshot_path = "debug/screenshot_full.png"
        cv2.imwrite(raw_screenshot_path, screenshot_bgr)
        print(f"  ✅ 成功取得螢幕畫面！解析度: {s_w} x {s_h} 像素")
        print(f"  📁 完整截圖已儲存至: {raw_screenshot_path}")
    except Exception as e:
        print(f"  ❌ 螢幕截圖失敗: {e}")
        print("\n  💡 排查建議:")
        print("  - 若在 Linux / Ubuntu: 請確認有安裝 gnome-screenshot: `sudo apt install gnome-screenshot scrot`")
        print("  - 若使用 X11 / Wayland: 請確認 DISPLAY 環境變數已設定且具有螢幕擷取權限。")
        return

    # 2. 測試樣板圖片比對
    print("\n[步驟 2/4] 掃描 assets/ 下所有樣板圖片並計算最高相似度 (Confidence)...")
    template_files = sorted(glob.glob("assets/*.png"))
    
    if not template_files:
        print("  ⚠️ assets/ 目錄下沒有找到任何 .png 樣板圖片！")
    
    annotated_img = screenshot_bgr.copy()
    results = []

    for t_path in template_files:
        t_name = os.path.basename(t_path)
        template = cv2.imread(t_path, cv2.IMREAD_COLOR)
        if template is None:
            print(f"  ❌ 無法載入樣板: {t_name}")
            continue

        t_h, t_w = template.shape[:2]
        
        # Template matching
        res = cv2.matchTemplate(screenshot_bgr, template, cv2.TM_CCOEFF_NORMED)
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)

        center_x = max_loc[0] + t_w // 2
        center_y = max_loc[1] + t_h // 2
        
        is_configured = (t_path == configured_template)
        config_mark = " (config.yaml 正在使用)" if is_configured else ""
        
        results.append({
            "path": t_path,
            "name": t_name,
            "size": (t_w, t_h),
            "max_val": max_val,
            "max_loc": max_loc,
            "center": (center_x, center_y),
            "is_configured": is_configured
        })

        # 標註於偵錯圖上
        color = (0, 255, 0) if max_val >= configured_threshold else (0, 165, 255)
        bx, by = max_loc[0], max_loc[1]
        cv2.rectangle(annotated_img, (bx, by), (bx + t_w, by + t_h), color, 2)
        label = f"{t_name[:12]}: {max_val:.2f}"
        cv2.putText(annotated_img, label, (bx, max(18, by - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1)

        print(f"  🔹 樣板: {t_name:<26} 尺寸: {t_w}x{t_h:<4} | 最高信心度: {max_val:.4f} | 最佳座標: ({center_x}, {center_y}){config_mark}")

    # 3. 綠色色相分析 (HSV Green Detection)
    print("\n[步驟 3/4] 進行 LINE 專屬綠色特徵色塊偵測 (HSV Color Filter)...")
    # LINE 綠色特徵 HSV 範圍 (~ #06C755)
    hsv = cv2.cvtColor(screenshot_bgr, cv2.COLOR_BGR2HSV)
    lower_green = np.array([35, 120, 100])
    upper_green = np.array([85, 255, 255])
    green_mask = cv2.inRange(hsv, lower_green, upper_green)
    
    # 尋找圓形或小色塊輪廓
    contours, _ = cv2.findContours(green_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    detected_green_blobs = []

    for cnt in contours:
        area = cv2.contourArea(cnt)
        if 40 <= area <= 3000:
            x, y, w, h = cv2.boundingRect(cnt)
            aspect_ratio = float(w) / h if h > 0 else 0
            if 0.5 <= aspect_ratio <= 2.2:
                is_in_range = (min_blob_area <= area <= max_blob_area)
                detected_green_blobs.append((x + w // 2, y + h // 2, w, h, area, is_in_range))
                
                # 依據是否符合指定面積區間 (248~356px) 繪製不同顏色
                if is_in_range:
                    cv2.rectangle(annotated_img, (x, y), (x + w, y + h), (0, 255, 0), 2)
                    cv2.putText(annotated_img, f"TARGET Blob({int(area)}px)", (x, max(15, y - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 0), 1)
                else:
                    cv2.circle(annotated_img, (x + w // 2, y + h // 2), max(w, h) // 2 + 3, (255, 0, 255), 1)
                    cv2.putText(annotated_img, f"Blob({int(area)}px)", (x, max(15, y - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (255, 0, 255), 1)

    in_range_blobs = [b for b in detected_green_blobs if b[5]]
    print(f"  🟢 畫面中共偵測到 {len(detected_green_blobs)} 個綠色色塊區域，其中 {len(in_range_blobs)} 個完全符合目標面積 [{min_blob_area}px ~ {max_blob_area}px]！")
    for idx, (gx, gy, gw, gh, garea, in_rng) in enumerate(detected_green_blobs[:5]):
        status_tag = "🎯 [符合目標面積]" if in_rng else "[未符區間]"
        print(f"     [色塊 {idx+1}] {status_tag} 中心座標: ({gx}, {gy}) | 尺寸: {gw}x{gh} | 面積: {garea:.0f} 像素")

    # 4. 生成並輸出全螢幕座標網格對應圖 (Coordinate Grid Map)
    print("\n[步驟 4/5] 繪製高解析全螢幕座標網格圖 (100px 標尺與座標十字針)...")
    from core.vision_detector import GreenDotDetector
    from core.window_helper import LineWindowHelper

    detector = GreenDotDetector()
    win_helper = LineWindowHelper()

    # 取得目前 config 所設定樣板的結果 (或最高分的樣板)
    active_res = next((r for r in results if r["is_configured"]), None)
    if not active_res and results:
        active_res = max(results, key=lambda x: x["max_val"])

    points_to_mark = []
    # (A) 加入綠點色塊
    for idx, (gx, gy, gw, gh, garea, in_rng) in enumerate(detected_green_blobs):
        tag = "🎯 TargetBlob" if in_rng else "Blob"
        col = (0, 255, 0) if in_rng else (255, 0, 255)
        points_to_mark.append({"pos": (gx, gy), "label": f"{tag}[{int(garea)}px]", "color": col})

    # (B) 加入樣板最高命中點
    if active_res:
        points_to_mark.append({
            "pos": active_res["center"],
            "label": f"TplMatch({active_res['max_val']:.2f})",
            "color": (0, 255, 255)
        })

    # (C) 加入 LINE 視窗安全點擊座標
    win = win_helper.get_line_window()
    if win:
        safe_chat_pos = win_helper.get_safe_chat_history_click_pos()
        safe_input_pos = win_helper.get_input_box_click_pos()
        points_to_mark.append({"pos": safe_chat_pos, "label": "SafeChatHistory", "color": (255, 140, 0)})
        points_to_mark.append({"pos": safe_input_pos, "label": "SafeInputBox", "color": (0, 165, 255)})

    grid_map_path = "debug/coordinate_grid_map.png"
    detector.create_coordinate_grid_map(
        image_bgr=screenshot_bgr,
        points=points_to_mark,
        grid_spacing=100,
        output_path=grid_map_path
    )

    result_img_path = "debug/test_vision_result.png"
    cv2.imwrite(result_img_path, annotated_img)
    print(f"\n[步驟 5/5] 診斷圖輸出完成！")
    print(f"  🖼️  已儲存標註診斷圖至: {result_img_path}")
    print(f"  🗺️  已儲存座標網格對應圖至: {grid_map_path}")

    # 5. 總結分析與建議
    print("\n=================================================================")
    print(" 📊 診斷分析結論與建議")
    print("=================================================================")

    # 檢查目前 config.yaml 使用的樣板
    active_res = next((r for r in results if r["is_configured"]), None)
    if active_res:
        curr_score = active_res["max_val"]
        print(f"1. 目前 config.yaml 設定門檻: {configured_threshold:.2f}，實際最高得分: {curr_score:.4f}")
        
        if curr_score >= configured_threshold:
            print(f"  🎉 恭喜！目前設定可正常觸發辨識 (相似度 {curr_score:.2f} >= 門檻 {configured_threshold:.2f})。")
        else:
            print(f"  ⚠️ 目前信心度 {curr_score:.2f} 低於門檻 {configured_threshold:.2f}，因此程式會判定為無未讀訊息。")
            if curr_score >= 0.50:
                suggested_thresh = max(0.50, round(curr_score - 0.05, 2))
                print(f"  👉 建議調整 config.yaml 中的 green_dot_confidence 為: {suggested_thresh}")
            else:
                print("  👉 相似度過低，可能原因：")
                print("     (A) 螢幕縮放比例 (DPI Scaling) 不同 (如 125%、150%) 造成像素大小不一致。")
                print("     (B) 綠點樣板與實際 LINE 視窗中的圖案差異較大（例如數字不同）。")
                print("     (C) 請打開 debug/screenshot_full.png 確認截圖當下畫面中是否有 LINE 視窗及綠點。")
    
    # 檢查是否有其他樣板得分更高
    if results:
        best_overall = max(results, key=lambda x: x["max_val"])
        if best_overall["max_val"] > (active_res["max_val"] if active_res else 0):
            print(f"\n2. 發現 assets 中有更高相似度的樣板: '{best_overall['name']}' (相似度: {best_overall['max_val']:.4f})")
            print(f"   👉 可在 config.yaml 將 green_dot_template_path 改為: \"{best_overall['path']}\"")

    print("\n=================================================================\n")


if __name__ == "__main__":
    run_vision_test()
