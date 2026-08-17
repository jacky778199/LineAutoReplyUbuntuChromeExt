import os
import sys
import time
import shutil
import logging
import subprocess
import cv2
import numpy as np

if sys.platform != "win32" and "DISPLAY" not in os.environ:
    os.environ["DISPLAY"] = ":99"

import pyautogui

pyautogui.FAILSAFE = False

from core.notifier import TelegramNotifier

logger = logging.getLogger(__name__)


class RecoveryManager:
    """Manages Chrome LINE extension lifecycle, recovery, auto-login, and fullscreen mode."""

    def __init__(self, config: dict = None):
        self.config = config or {}
        env_cfg = self.config.get("environment", {})
        notify_cfg = self.config.get("notification", {})

        self.auto_recover = env_cfg.get("auto_recover", True)
        self.max_recover_attempts = env_cfg.get("max_recover_attempts", 3)
        self.recover_cooldown_sec = env_cfg.get("recover_cooldown_sec", 10.0)
        self.display = env_cfg.get("display", os.environ.get("DISPLAY", ":99"))
        self.chrome_bin = env_cfg.get("chrome_bin", "google-chrome")
        self.line_extension_id = env_cfg.get("line_extension_id", "ophjlpahpchlmihnnnihgmmeilfjmjjc")
        self.line_email = env_cfg.get("line_email", "")
        self.line_password = env_cfg.get("line_password", "")
        self.login_template_path = env_cfg.get("login_template_path", "assets/login_email_field.png")
        self.login_logo_template_path = env_cfg.get("login_logo_template_path", "assets/login_line_logo.png")
        self.login_button_template_path = env_cfg.get("login_button_template_path", "assets/login_button.png")
        self.login_confidence = env_cfg.get("login_confidence", 0.45)
        self.fullscreen = env_cfg.get("fullscreen", True)

        self.notifier = TelegramNotifier(self.config)
        self.verification_timeout = notify_cfg.get("verification_timeout", 90)

        self._last_recovery_time = 0
        self._consecutive_failures = 0


    def get_password(self) -> str:
        """Returns LINE password from environment variable (preferred) or config."""
        return os.environ.get("LINE_PASSWORD") or self.line_password or ""

    def get_email(self) -> str:
        """Returns LINE email from environment variable or config."""
        return os.environ.get("LINE_EMAIL") or self.line_email or ""

    def is_chrome_running(self) -> bool:
        """Checks if Chrome or LINE extension process is running."""
        try:
            res = subprocess.run(["pgrep", "-f", "google-chrome"], capture_output=True, text=True)
            return res.returncode == 0 and bool(res.stdout.strip())
        except Exception:
            return False

    def find_all_line_windows(self) -> list:
        """
        Retrieves all open LINE application window IDs on the current DISPLAY.
        Uses xwininfo and xdotool to accurately identify LINE extension windows.
        """
        line_wids = []
        env = os.environ.copy()
        env["DISPLAY"] = self.display

        # 1. Search via xwininfo root tree for accurate window titles and classes
        try:
            res = subprocess.run(["xwininfo", "-root", "-tree"], capture_output=True, text=True, env=env)
            if res.returncode == 0 and res.stdout:
                for line in res.stdout.splitlines():
                    # Check for LINE window or extension ID in window definition
                    if ('"LINE"' in line or self.line_extension_id in line) and "xwininfo:" not in line:
                        parts = line.strip().split()
                        if parts and parts[0].startswith("0x"):
                            wid_hex = parts[0]
                            # Check window size to ignore 10x10 hidden helper windows
                            if any(f"{w}x{h}" in line for w in range(300, 4000) for h in [range(300, 3000)]) or ("1920x1080" in line or "1919x1079" in line):
                                line_wids.append(wid_hex)
                            elif "LINE" in line and not any(dim in line for dim in ["10x10", "1x1", "200x200"]):
                                line_wids.append(wid_hex)
        except Exception as e:
            logger.debug(f"xwininfo 搜尋 LINE 視窗失敗: {e}")

        # 2. Fallback to xdotool search
        if not line_wids:
            try:
                res = subprocess.run(["xdotool", "search", "--onlyvisible", "--name", "LINE"], capture_output=True, text=True, env=env)
                if res.returncode == 0 and res.stdout.strip():
                    line_wids = [wid.strip() for wid in res.stdout.strip().splitlines() if wid.strip()]
            except Exception:
                pass

        return line_wids

    def find_all_non_line_chrome_windows(self) -> list:
        """
        Retrieves all non-LINE Chrome window IDs (e.g. 'Untitled - Google Chrome', accidental web tabs).
        """
        non_line_wids = []
        env = os.environ.copy()
        env["DISPLAY"] = self.display

        try:
            res = subprocess.run(["xwininfo", "-root", "-tree"], capture_output=True, text=True, env=env)
            if res.returncode == 0 and res.stdout:
                for line in res.stdout.splitlines():
                    if ("google-chrome" in line.lower() or "chrome" in line.lower()) and "xwininfo:" not in line:
                        # Exclude main LINE window and tiny helper windows
                        if '"LINE"' not in line and self.line_extension_id not in line:
                            if not any(dim in line for dim in ["10x10", "1x1", "200x200"]):
                                parts = line.strip().split()
                                if parts and parts[0].startswith("0x"):
                                    non_line_wids.append(parts[0])
        except Exception as e:
            logger.debug(f"xwininfo 搜尋非 LINE Chrome 視窗失敗: {e}")

        return non_line_wids

    def cleanup_duplicate_windows(self, keep_latest: bool = True) -> int:
        """
        Singleton Guard:
        1. Closes all unwanted non-LINE browser windows (Untitled, accidental link tabs).
        2. If multiple LINE windows exist, closes all older instances, keeping strictly ONE active LINE window.
        """
        closed_count = 0
        env = os.environ.copy()
        env["DISPLAY"] = self.display

        # 1. Close all non-LINE chrome windows
        non_line_wids = self.find_all_non_line_chrome_windows()
        for wid in non_line_wids:
            logger.info(f"🧹 [清理多餘視窗] 正在關閉非 LINE 的外部 Chrome 視窗: {wid}...")
            subprocess.run(["xdotool", "windowclose", wid], env=env, capture_output=True)
            closed_count += 1

        # 2. Deduplicate LINE windows (Keep only 1)
        line_wids = self.find_all_line_windows()
        if len(line_wids) > 1:
            logger.warning(f"⚠️ [偵測到多個 LINE 視窗] 共有 {len(line_wids)} 個實例，正在清除多餘舊視窗以維持單例...")
            wids_to_close = line_wids[:-1] if keep_latest else line_wids
            for wid in wids_to_close:
                logger.info(f"🧹 關閉多餘的 LINE 歷史視窗: {wid}...")
                subprocess.run(["xdotool", "windowclose", wid], env=env, capture_output=True)
                closed_count += 1
            time.sleep(0.5)
        elif not keep_latest and line_wids:
            for wid in line_wids:
                subprocess.run(["xdotool", "windowclose", wid], env=env, capture_output=True)
                closed_count += 1

        if closed_count > 0:
            logger.info(f"✅ [視窗去重完成] 共清理關閉了 {closed_count} 個多餘視窗。")
        return closed_count

    def cleanup_stale_processes(self):
        """Terminates stale Chrome / LINE processes and locks cleanly."""
        logger.info("🧹 正在清理可能殘留的 Google Chrome 與 LINE 視窗、行程與鎖定檔案...")
        env = os.environ.copy()
        env["DISPLAY"] = self.display

        try:
            # 1. Close open X11 windows cleanly first
            self.cleanup_duplicate_windows(keep_latest=False)
            time.sleep(0.5)

            # 2. Send SIGTERM first, then SIGKILL across all chrome & extension processes
            subprocess.run(["pkill", "-f", "google-chrome|chrome-extension|ophjlpahpchlmihnnnihgmmeilfjmjjc"], capture_output=True)
            time.sleep(0.8)
            subprocess.run(["pkill", "-9", "-f", "google-chrome|chrome-extension|ophjlpahpchlmihnnnihgmmeilfjmjjc"], capture_output=True)
            time.sleep(0.5)
        except Exception as e:
            logger.debug(f"清理 Chrome 行程時發生非嚴重例外: {e}")

        # 3. Clean up stale SingletonLock / SingletonSocket in profile
        profile_dir = os.path.expanduser("~/.config/google-chrome")
        if os.path.exists(profile_dir):
            for lock_file in ["SingletonLock", "SingletonSocket", "SingletonCookie"]:
                target_path = os.path.join(profile_dir, lock_file)
                try:
                    if os.path.islink(target_path) or os.path.exists(target_path):
                        os.unlink(target_path)
                        logger.debug(f"已清除過期鎖定檔案: {target_path}")
                except Exception as e:
                    logger.debug(f"清理鎖定檔 {lock_file} 失敗: {e}")

            # Clean up all stale LevelDB LOCK files across Chrome profile
            for root, dirs, files in os.walk(profile_dir):
                for f in files:
                    if f == "LOCK":
                        lock_path = os.path.join(root, f)
                        try:
                            os.remove(lock_path)
                            logger.debug(f"已清除資料庫鎖定檔案: {lock_path}")
                        except Exception:
                            pass

    def launch_chrome_line_extension(self) -> subprocess.Popen:
        """Launches Google Chrome directly in LINE extension standalone app mode."""
        app_url = f"chrome-extension://{self.line_extension_id}/index.html"
        chrome_path = shutil.which(self.chrome_bin) or self.chrome_bin

        cmd = [
            chrome_path,
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-gpu",                  # 避免虛擬螢幕 GPU 渲染假死
            "--disable-dev-shm-usage",        # 避免 Linux /dev/shm 記憶體不足
            "--disable-session-crashed-bubble",
            "--disable-infobars",
            f"--app={app_url}"
        ]

        env = os.environ.copy()
        env["DISPLAY"] = self.display

        logger.info(f"🚀 正在於 DISPLAY={self.display} 啟動 Chrome LINE 擴充套件...")
        logger.info(f"   指令: {' '.join(cmd)}")

        proc = subprocess.Popen(
            cmd,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True
        )
        return proc

    def find_line_window_id(self, timeout: float = 12.0) -> str:
        """Searches for active LINE window using xdotool / xwininfo within timeout."""
        start_t = time.time()
        while time.time() - start_t < timeout:
            wids = self.find_all_line_windows()
            if wids:
                return wids[-1]
            time.sleep(0.8)
        return ""

    def reposition_and_fullscreen(self, window_id: str = None) -> bool:
        """Repositions LINE window to (0,0), sizes it, and applies Fullscreen (F11)."""
        env = os.environ.copy()
        env["DISPLAY"] = self.display

        try:
            # 1. Locate window if not provided
            if not window_id:
                window_id = self.find_line_window_id(timeout=5.0)

            # Get screen dimensions
            screen_w, screen_h = pyautogui.size()

            if window_id:
                logger.info(f"📐 正在對齊 LINE 視窗 (Window ID: {window_id}) 到座標 (0, 0)...")
                # Activate & Move to (0, 0)
                subprocess.run(["xdotool", "windowactivate", "--sync", window_id], env=env, capture_output=True)
                time.sleep(0.3)
                subprocess.run(["xdotool", "windowmove", window_id, "0", "0"], env=env, capture_output=True)
                time.sleep(0.2)
                subprocess.run(["xdotool", "windowsize", window_id, str(screen_w), str(screen_h)], env=env, capture_output=True)
                time.sleep(0.3)

                if self.fullscreen:
                    logger.info("🖥️ 正在將 LINE 視窗切換為全螢幕模式 (F11)...")
                    subprocess.run(["xdotool", "key", "--window", window_id, "F11"], env=env, capture_output=True)
                    time.sleep(0.5)
            else:
                # Fallback without window ID: activate current window and press F11
                logger.info("視窗 ID 未取得，嘗試以預設鍵盤事件切換全螢幕...")
                if self.fullscreen:
                    pyautogui.press('f11')
                    time.sleep(0.5)

            return True
        except Exception as e:
            logger.error(f"設定全螢幕與視窗對齊時發生錯誤: {e}")
            return False

    def locate_login_anchors(self, confidence: float = None, screenshot_bgr=None) -> dict:
        """
        Scheme 1: Locates login UI anchors using the invariant green 'LINE' Logo
        and 'Log in' button, calculating exact coordinates for:
        1. Email input field (center)
        2. Password input field (center)
        3. Log in button (center)

        This is 100% immune to whether the email field is empty or pre-filled with text.
        """
        if confidence is None:
            confidence = self.login_confidence

        res_dict = {
            "is_found": False,
            "anchor_type": None,
            "logo_pos": None,
            "button_pos": None,
            "email_field": None,
            "password_field": None,
            "login_button": None,
            "confidence": 0.0
        }

        try:
            if screenshot_bgr is None:
                screenshot_pil = pyautogui.screenshot()
                screenshot_np = np.array(screenshot_pil)
                screenshot_bgr = cv2.cvtColor(screenshot_np, cv2.COLOR_RGB2BGR)

            s_h, s_w = screenshot_bgr.shape[:2]

            # 1. Match LINE Logo (Top invariant anchor)
            logo_pos = None
            logo_score = 0.0
            if os.path.exists(self.login_logo_template_path):
                tpl_logo = cv2.imread(self.login_logo_template_path, cv2.IMREAD_COLOR)
                if tpl_logo is not None:
                    lh, lw = tpl_logo.shape[:2]
                    res = cv2.matchTemplate(screenshot_bgr, tpl_logo, cv2.TM_CCOEFF_NORMED)
                    min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)
                    logo_score = float(max_val)
                    if max_val >= confidence:
                        logo_pos = (max_loc[0] + lw // 2, max_loc[1] + lh // 2)

            # 2. Match Log in Button (Bottom anchor)
            btn_pos = None
            btn_score = 0.0
            if os.path.exists(self.login_button_template_path):
                tpl_btn = cv2.imread(self.login_button_template_path, cv2.IMREAD_COLOR)
                if tpl_btn is not None:
                    bh, bw = tpl_btn.shape[:2]
                    res = cv2.matchTemplate(screenshot_bgr, tpl_btn, cv2.TM_CCOEFF_NORMED)
                    min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)
                    btn_score = float(max_val)
                    if max_val >= confidence:
                        btn_pos = (max_loc[0] + bw // 2, max_loc[1] + bh // 2)

            # 3. Match fallback Email field template if exists
            email_field_pos = None
            email_score = 0.0
            if os.path.exists(self.login_template_path):
                tpl_email = cv2.imread(self.login_template_path, cv2.IMREAD_COLOR)
                if tpl_email is not None:
                    eh, ew = tpl_email.shape[:2]
                    res = cv2.matchTemplate(screenshot_bgr, tpl_email, cv2.TM_CCOEFF_NORMED)
                    min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)
                    email_score = float(max_val)
                    if max_val >= confidence:
                        email_field_pos = (max_loc[0] + ew // 2, max_loc[1] + eh // 2)

            logger.info(
                f"🔍 [登入錨點掃描] Logo得分: {logo_score:.2f}, 按鈕得分: {btn_score:.2f}, "
                f"帳號框得分: {email_score:.2f} (門檻: {confidence:.2f})"
            )

            # 4. Calculate exact coordinates using dual-anchor interpolation or single offset
            if logo_pos and btn_pos:
                # Mode A: Dual-anchor interpolation (Adaptive to screen scaling)
                center_x = int((logo_pos[0] + btn_pos[0]) / 2)
                h_span = btn_pos[1] - logo_pos[1]
                email_y = int(logo_pos[1] + h_span * 0.40)
                pass_y = int(logo_pos[1] + h_span * 0.67)

                res_dict["is_found"] = True
                res_dict["anchor_type"] = "dual_anchor"
                res_dict["logo_pos"] = logo_pos
                res_dict["button_pos"] = btn_pos
                res_dict["email_field"] = (center_x, email_y)
                res_dict["password_field"] = (center_x, pass_y)
                res_dict["login_button"] = btn_pos
                res_dict["confidence"] = max(logo_score, btn_score)
                logger.info(
                    f"🎯 [雙錨點插值成功] 水平中心: {center_x}, 跨度: {h_span}px -> "
                    f"帳號框: {res_dict['email_field']}, 密碼框: {res_dict['password_field']}, 按鈕: {btn_pos}"
                )
                return res_dict

            elif logo_pos:
                # Mode B: Single Logo anchor offset
                res_dict["is_found"] = True
                res_dict["anchor_type"] = "logo_anchor"
                res_dict["logo_pos"] = logo_pos
                res_dict["email_field"] = (logo_pos[0], logo_pos[1] + 72)
                res_dict["password_field"] = (logo_pos[0], logo_pos[1] + 120)
                res_dict["login_button"] = (logo_pos[0], logo_pos[1] + 180)
                res_dict["confidence"] = logo_score
                logger.info(
                    f"🎯 [LINE Logo 錨點定位成功] Logo: {logo_pos} -> "
                    f"推算帳號框: {res_dict['email_field']}, 密碼框: {res_dict['password_field']}"
                )
                return res_dict

            elif btn_pos:
                # Mode C: Single Button anchor offset
                res_dict["is_found"] = True
                res_dict["anchor_type"] = "button_anchor"
                res_dict["button_pos"] = btn_pos
                res_dict["email_field"] = (btn_pos[0], btn_pos[1] - 108)
                res_dict["password_field"] = (btn_pos[0], btn_pos[1] - 60)
                res_dict["login_button"] = btn_pos
                res_dict["confidence"] = btn_score
                logger.info(
                    f"🎯 [Log In 按鈕錨點定位成功] 按鈕: {btn_pos} -> "
                    f"推算帳號框: {res_dict['email_field']}, 密碼框: {res_dict['password_field']}"
                )
                return res_dict

            elif email_field_pos:
                # Mode D: Legacy email field template
                res_dict["is_found"] = True
                res_dict["anchor_type"] = "email_field"
                res_dict["email_field"] = email_field_pos
                res_dict["password_field"] = (email_field_pos[0], email_field_pos[1] + 48)
                res_dict["login_button"] = (email_field_pos[0], email_field_pos[1] + 108)
                res_dict["confidence"] = email_score
                return res_dict

        except Exception as e:
            logger.error(f"比對登入畫面錨點時發生例外: {e}")

        # Fallback to screen center
        sw, sh = pyautogui.size()
        res_dict["email_field"] = (sw // 2, sh // 2 - 20)
        res_dict["password_field"] = (sw // 2, sh // 2 + 28)
        res_dict["login_button"] = (sw // 2, sh // 2 + 88)
        return res_dict

    def locate_login_email_field(self, confidence: float = None) -> tuple:
        """Compatibility wrapper: Returns email field coordinate tuple."""
        anchors = self.locate_login_anchors(confidence=confidence)
        return anchors.get("email_field")

    def perform_auto_login_if_needed(self, validator=None, timeout: float = 15.0) -> bool:
        """
        Checks if LINE is on login screen.
        Locates UI anchors using invariant LINE Logo + Log in Button, then:
        Clicks email field -> Clears & Types email -> Clicks password field -> Clears & Types password -> Clicks Log In.
        """
        password = self.get_password()
        email = self.get_email()

        if validator:
            report = validator.validate_screen()
            if report.get("is_valid"):
                logger.info("✅ LINE 已經處於登入狀態，無需輸入帳號密碼。")
                return True

        if not password:
            logger.warning("⚠️ 未設定 LINE 密碼 (LINE_PASSWORD 環境變數或 config.yaml)，跳過自動登入。")
            return False

        logger.info("🔑 正在透過 LINE Logo 與按鈕錨點定位登入介面並執行自動登入流程...")
        try:
            # 1. Locate login coordinates via invariant anchors
            anchors = self.locate_login_anchors()

            email_pos = anchors.get("email_field")
            pass_pos = anchors.get("password_field")
            btn_pos = anchors.get("login_button")

            if anchors.get("is_found"):
                logger.info(f"🎯 [登入錨點就緒 ({anchors.get('anchor_type')})] 帳號框: {email_pos}, 密碼框: {pass_pos}, 按鈕: {btn_pos}")
            else:
                logger.warning(f"⚠️ 未能完全以樣板鎖定錨點，使用備用推算座標: 帳號框 {email_pos}...")

            # 2. Click email field and clear old text (preventing pre-filled text collision)
            if email_pos:
                logger.info(f"點擊帳號欄位座標 {email_pos}...")
                pyautogui.click(email_pos[0], email_pos[1])
                time.sleep(0.4)

                if email:
                    logger.info(f"清除可能已填寫的舊帳號並輸入: {email}")
                    pyautogui.hotkey('ctrl', 'a')
                    time.sleep(0.15)
                    pyautogui.press('backspace')
                    time.sleep(0.15)
                    pyautogui.typewrite(email, interval=0.03)
                    time.sleep(0.3)

            # 3. Focus password field (Click directly or TAB)
            if pass_pos:
                logger.info(f"點擊密碼欄位座標 {pass_pos}...")
                pyautogui.click(pass_pos[0], pass_pos[1])
                time.sleep(0.3)
            else:
                pyautogui.press('tab')
                time.sleep(0.3)

            # 4. Type Password
            logger.info("清除舊密碼並輸入新密碼...")
            pyautogui.hotkey('ctrl', 'a')
            time.sleep(0.15)
            pyautogui.press('backspace')
            time.sleep(0.15)
            pyautogui.typewrite(password, interval=0.03)
            time.sleep(0.3)

            # 5. Submit Login (Click button or Enter)
            if btn_pos:
                logger.info(f"點擊登入按鈕座標 {btn_pos}...")
                pyautogui.click(btn_pos[0], btn_pos[1])
                time.sleep(0.3)
            else:
                logger.info("按下 Enter 送出登入...")
                pyautogui.press('enter')
                time.sleep(0.3)

            logger.info("⏳ 等待 5 秒讓 LINE 登入回應與畫面載入 (適應網路延遲)...")
            time.sleep(5.0)

            # Check if immediately logged in (e.g. if verification wasn't requested)
            if validator:
                chk = validator.validate_screen()
                if chk.get("is_valid"):
                    logger.info("🎉 LINE 自動登入成功！")
                    return True

            # 7. Verification Code Notification (PC verification)
            logger.info("📱 登入請求已送出，正在擷取畫面並檢查是否需要手機輸入驗證號碼 (PC verification)...")
            verify_img_path = "debug/login_verification_code.png"
            try:
                os.makedirs("debug", exist_ok=True)
                screenshot_pil = pyautogui.screenshot()
                screenshot_pil.save(verify_img_path)
                logger.info(f"📁 登入驗證畫面已儲存至: {verify_img_path}")

                if self.notifier.is_configured():
                    logger.info("📤 正在發送驗證碼截圖至 Telegram...")
                    self.notifier.send_photo(
                        verify_img_path,
                        caption="🔐 <b>LINE 電腦版驗證碼已生成</b>\n請於手機 LINE 輸入畫面上的 6 位數以完成登入！"
                    )
                else:
                    logger.warning(
                        "⚠️ Telegram 通知未設定 (TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID)。"
                        f"請由 VNC 或檢視本機圖片 {verify_img_path} 取得驗證碼！"
                    )
            except Exception as e:
                logger.error(f"儲存或發送驗證碼截圖失敗: {e}")

            # 8. Wait for user to enter verification code on mobile
            wait_timeout = max(timeout, self.verification_timeout)
            logger.info(f"⏳ 等待手機端完成驗證 (等待時間上限: {wait_timeout} 秒)...")
            start_t = time.time()
            while time.time() - start_t < wait_timeout:
                if validator:
                    chk = validator.validate_screen()
                    if chk.get("is_valid"):
                        logger.info("🎉 [手機驗證成功] LINE 成功登入並通過介面檢測！")
                        if self.notifier.is_configured():
                            self.notifier.send_message("✅ <b>手機驗證通過！</b>\nLINE 自動回覆機器人已就緒運作。")
                        return True
                time.sleep(2.0)

            logger.warning(f"⚠️ 超過 {wait_timeout} 秒未偵測到 LINE 主介面，手機驗證可能超時。")
            return False
        except Exception as e:
            logger.error(f"自動登入時發生錯誤: {e}")
            return False




    def switch_to_chat_tab(
        self,
        template_path: str = "assets/Message_icon.png",
        friend_template_path: str = "assets/sidebar_friend_icon.png",
        voom_template_path: str = "assets/sidebar_voom_icon.png",
        confidence: float = 0.60
    ) -> bool:
        """
        Locates the Message/Chat tab using dual-anchor relative positioning (Friend + VOOM icons),
        with fallback to template matching, and clicks it to ensure LINE is on the Chats tab.
        """
        try:
            screenshot_pil = pyautogui.screenshot()
            screenshot_np = np.array(screenshot_pil)
            screen_bgr = cv2.cvtColor(screenshot_np, cv2.COLOR_RGB2BGR)
            s_h, s_w = screen_bgr.shape[:2]

            friend_pos = None
            voom_pos = None

            # 1. Detect Friend Icon (Top Anchor)
            if os.path.exists(friend_template_path):
                f_tpl = cv2.imread(friend_template_path, cv2.IMREAD_COLOR)
                if f_tpl is not None:
                    fh, fw = f_tpl.shape[:2]
                    top_roi = screen_bgr[:min(180, s_h), :min(80, s_w)]
                    if top_roi.shape[0] >= fh and top_roi.shape[1] >= fw:
                        res_f = cv2.matchTemplate(top_roi, f_tpl, cv2.TM_CCOEFF_NORMED)
                        _, f_max, _, f_loc = cv2.minMaxLoc(res_f)
                        if f_max >= confidence:
                            friend_pos = (f_loc[0] + fw // 2, f_loc[1] + fh // 2)

            # 2. Detect VOOM Icon (Bottom Anchor)
            if os.path.exists(voom_template_path):
                v_tpl = cv2.imread(voom_template_path, cv2.IMREAD_COLOR)
                if v_tpl is not None:
                    vh, vw = v_tpl.shape[:2]
                    bot_roi_y1 = 120
                    bot_roi = screen_bgr[bot_roi_y1:min(350, s_h), :min(80, s_w)]
                    if bot_roi.shape[0] >= vh and bot_roi.shape[1] >= vw:
                        res_v = cv2.matchTemplate(bot_roi, v_tpl, cv2.TM_CCOEFF_NORMED)
                        _, v_max, _, v_loc = cv2.minMaxLoc(res_v)
                        if v_max >= confidence:
                            voom_pos = (v_loc[0] + vw // 2, bot_roi_y1 + v_loc[1] + vh // 2)

            # 3. Determine Click Coordinates
            click_x, click_y = None, None
            if friend_pos and voom_pos:
                click_x = int((friend_pos[0] + voom_pos[0]) / 2)
                click_y = int(friend_pos[1] + (voom_pos[1] - friend_pos[1]) * (1.0 / 3.0))
                logger.info(f"🎯 [切換至聊天分頁] 透過雙錨點定位成功，點擊訊息分頁座標 ({click_x}, {click_y})！")
            elif friend_pos:
                click_x = friend_pos[0]
                click_y = int(friend_pos[1] + 53)
                logger.info(f"🎯 [切換至聊天分頁] 透過好友錨點定位成功，點擊訊息分頁座標 ({click_x}, {click_y})！")
            elif os.path.exists(template_path):
                # Fallback to direct Message_icon.png match
                tpl = cv2.imread(template_path, cv2.IMREAD_COLOR)
                if tpl is not None:
                    th, tw = tpl.shape[:2]
                    sidebar_roi = screen_bgr[:min(250, s_h), :min(80, s_w)]
                    if sidebar_roi.shape[0] >= th and sidebar_roi.shape[1] >= tw:
                        res = cv2.matchTemplate(sidebar_roi, tpl, cv2.TM_CCOEFF_NORMED)
                        _, max_val, _, max_loc = cv2.minMaxLoc(res)
                        if max_val >= confidence:
                            click_x = max_loc[0] + tw // 2
                            click_y = max_loc[1] + th // 2
                            logger.info(f"🎯 [切換至聊天分頁] 透過備援樣板比對成功，點擊座標 ({click_x}, {click_y})！")

            if click_x is None or click_y is None:
                click_x, click_y = 27, 90
                logger.warning(f"⚠️ [切換至聊天分頁] 側邊欄錨點皆未命中，點擊預設聊天分頁座標 ({click_x}, {click_y})...")

            pyautogui.click(click_x, click_y)
            logger.info("⏳ 點擊 Message 分頁後等待 5 秒 (確保對話列表與網路資料載入完成)...")
            time.sleep(5.0)
            pyautogui.press('escape')
            time.sleep(0.3)
            return True
        except Exception as e:
            logger.error(f"切換聊天分頁時發生錯誤: {e}")
            return False

    def dismiss_accidental_tabs(self, validator=None) -> bool:
        """
        Scheme C: Lightweight self-healing defense against accidental hyperlink clicks.
        If a click opened a new browser tab or popup, sends Ctrl+W and Escape to close
        the unwanted tab and restore LINE desktop focus.

        Returns True if environment becomes valid immediately after, avoiding full Chrome restart.
        """
        logger.info("🛡️ [防禦性自癒 Scheme C] 嘗試發送 Ctrl+W / Esc 關閉可能誤開的外部網頁分頁...")
        try:
            # 1. Send Ctrl+W (Close current active tab in Chrome)
            pyautogui.hotkey('ctrl', 'w')
            time.sleep(0.5)

            # 2. Press Escape
            pyautogui.press('escape')
            time.sleep(0.3)

            # 3. If validator provided, verify if screen recovered
            if validator:
                chk = validator.validate_screen(save_debug_image_on_fail=False)
                if chk.get("is_valid"):
                    logger.info("🎉 [防禦性自癒成功] 外部網頁分頁已關閉，LINE 介面已自動恢復！")
                    self.switch_to_chat_tab()
                    self._consecutive_failures = 0
                    return True
                else:
                    logger.debug("防禦性關閉分頁後環境仍未恢復，將交由完整恢復流程處理。")
        except Exception as e:
            logger.debug(f"執行防禦性自癒關閉分頁時發生例外: {e}")

        return False

    def recover_environment(self, validator=None) -> bool:
        """
        Main recovery procedure:
        0. Scheme C: Try lightweight dismissal of accidental tabs (Ctrl+W) & duplicate window cleanup first!
        1. Process cleanup
        2. Launch Chrome LINE extension
        3. Reposition & Fullscreen
        4. Auto-login if needed
        5. Validate screen readiness & switch to Chats tab (Message_icon.png)
        """
        if not self.auto_recover:
            logger.info("環境自動恢復已停用 (auto_recover=false)。")
            return False

        # 0. Lightweight defense & Singleton cleanup: Close accidental tabs and deduplicate windows
        if validator and self.dismiss_accidental_tabs(validator):
            return True

        # Check if an existing LINE window is already running and valid after deduplication
        self.cleanup_duplicate_windows(keep_latest=True)
        time.sleep(0.3)
        if validator:
            chk = validator.validate_screen(save_debug_image_on_fail=False)
            if chk.get("is_valid"):
                logger.info("🎉 [單例檢查通過] 現有單一 LINE 視窗正常且通過驗證，無需重啟 Chrome！")
                self.reposition_and_fullscreen()
                self.switch_to_chat_tab()
                self._consecutive_failures = 0
                return True

        # Cooldown check
        curr_t = time.time()
        if curr_t - self._last_recovery_time < self.recover_cooldown_sec:
            logger.warning(f"⏳ 距離上次恢復未滿冷卻時間 ({self.recover_cooldown_sec}s)，稍候重試...")
            return False

        self._last_recovery_time = curr_t
        logger.info("==================================================")
        logger.info(" 🛠️ 開始執行環境自動恢復流程 (Auto-Recovery) ")
        logger.info("==================================================")

        for attempt in range(1, self.max_recover_attempts + 1):
            logger.info(f"🔄 [嘗試第 {attempt}/{self.max_recover_attempts} 次] 正在重啟 Chrome LINE 並重置環境...")

            # 1. Clean up stale processes
            self.cleanup_stale_processes()
            time.sleep(1.0)

            # 2. Launch Chrome LINE extension
            self.launch_chrome_line_extension()

            # 3. Wait for LINE window to appear
            logger.info("⏳ 等待 LINE 視窗啟動...")
            win_id = self.find_line_window_id(timeout=12.0)
            if win_id:
                logger.info(f"✅ 成功找到 LINE 視窗 (ID: {win_id})")
            else:
                logger.warning("⚠️ 未能在超時時間內定位到 LINE 視窗，繼續後續步驟...")

            time.sleep(2.0)

            # 4. Reposition & Fullscreen
            self.reposition_and_fullscreen(win_id)
            time.sleep(1.5)

            # 5. Check screen readiness or perform auto login
            if validator:
                report = validator.validate_screen()
                if report.get("is_valid"):
                    logger.info("🎉 [環境恢復成功] LINE 介面已就緒且通過驗證！")
                    self.switch_to_chat_tab()
                    self._consecutive_failures = 0
                    return True

                # If not valid, attempt auto-login
                logger.info("偵測到尚未進入主聊天介面，嘗試自動登入...")
                login_ok = self.perform_auto_login_if_needed(validator, timeout=12.0)
                if login_ok:
                    # Re-apply fullscreen if login caused window reload
                    self.reposition_and_fullscreen(win_id)
                    time.sleep(1.0)
                    final_chk = validator.validate_screen()
                    if final_chk.get("is_valid"):
                        logger.info("🎉 [環境恢復成功] LINE 自動登入並通過驗證！")
                        # 剛登入完成後點擊 Message_icon.png 確保停留在聊天對話分頁
                        self.switch_to_chat_tab()
                        self._consecutive_failures = 0
                        return True

            time.sleep(2.0)

        self._consecutive_failures += 1
        logger.error(f"❌ 連續 {self.max_recover_attempts} 次環境恢復嘗試皆未成功，請手動檢查 VNC 畫面！")
        return False

