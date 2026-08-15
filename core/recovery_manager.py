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

    def cleanup_stale_processes(self):
        """Terminates stale Chrome / LINE processes to avoid Singleton lock collisions."""
        logger.info("🧹 正在清理可能殘留的 Google Chrome 與 LINE 行程與鎖定檔案...")
        try:
            # Send SIGTERM first, then SIGKILL
            subprocess.run(["pkill", "-f", "google-chrome"], capture_output=True)
            time.sleep(1.0)
            subprocess.run(["pkill", "-9", "-f", "google-chrome"], capture_output=True)
            time.sleep(0.5)
        except Exception as e:
            logger.debug(f"清理 Chrome 行程時發生非嚴重例外: {e}")

        # Clean up stale SingletonLock / SingletonSocket if left behind in profile
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
        """Searches for active LINE window using xdotool within timeout."""
        start_t = time.time()
        while time.time() - start_t < timeout:
            try:
                env = os.environ.copy()
                env["DISPLAY"] = self.display
                res = subprocess.run(
                    ["xdotool", "search", "--onlyvisible", "--name", "LINE"],
                    capture_output=True,
                    text=True,
                    env=env
                )
                if res.returncode == 0 and res.stdout.strip():
                    wids = res.stdout.strip().splitlines()
                    # Return the last active window id
                    return wids[-1].strip()
            except Exception as e:
                logger.debug(f"xdotool 搜尋視窗失敗: {e}")

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

    def locate_login_email_field(self, confidence: float = None) -> tuple:
        """
        Uses OpenCV template matching to locate assets/login_email_field.png on screen.
        Returns (center_x, center_y) or None.
        """
        if confidence is None:
            confidence = self.login_confidence

        if not os.path.exists(self.login_template_path):
            logger.debug(f"登入樣板圖檔不存在: {self.login_template_path}")
            return None

        try:
            screenshot_pil = pyautogui.screenshot()
            screenshot_np = np.array(screenshot_pil)
            screen_bgr = cv2.cvtColor(screenshot_np, cv2.COLOR_RGB2BGR)

            tpl = cv2.imread(self.login_template_path, cv2.IMREAD_COLOR)
            if tpl is None:
                return None

            t_h, t_w = tpl.shape[:2]
            res = cv2.matchTemplate(screen_bgr, tpl, cv2.TM_CCOEFF_NORMED)
            min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)

            logger.info(f"🔍 [登入畫面比對] 樣板 {self.login_template_path} 相似度: {max_val:.2f} (門檻: {confidence})")
            if max_val >= confidence:
                center_x = max_loc[0] + t_w // 2
                center_y = max_loc[1] + t_h // 2
                return (center_x, center_y)
        except Exception as e:
            logger.error(f"比對登入畫面樣板失敗: {e}")

        return None

    def perform_auto_login_if_needed(self, validator=None, timeout: float = 15.0) -> bool:
        """
        Checks if LINE is on login screen.
        Locates assets/login_email_field.png using OpenCV, then:
        Clicks email field -> Types email -> TAB -> Types password -> TAB -> ENTER.
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

        logger.info("🔑 正在透過 OpenCV 尋找登入帳號欄位並執行自動登入流程...")
        try:
            # 1. Locate login email field via template matching
            field_pos = self.locate_login_email_field()

            if field_pos:
                click_x, click_y = field_pos
                logger.info(f"🎯 [登入樣板定位成功] 點擊帳號欄位座標 ({click_x}, {click_y})...")
            else:
                sw, sh = pyautogui.size()
                click_x, click_y = sw // 2, sh // 2
                logger.warning(f"⚠️ 未能以樣板定位帳號欄位，使用螢幕中心備用座標 ({click_x}, {click_y})...")

            # 2. Click email field
            pyautogui.click(click_x, click_y)
            time.sleep(0.4)

            # 3. Type Email if provided
            if email:
                logger.info(f"輸入帳號: {email}")
                pyautogui.hotkey('ctrl', 'a')
                time.sleep(0.15)
                pyautogui.press('backspace')
                time.sleep(0.15)
                pyautogui.typewrite(email, interval=0.03)
                time.sleep(0.3)

            # 4. Press TAB to switch to Password field
            logger.info("按下 TAB 切換至密碼輸入框...")
            pyautogui.press('tab')
            time.sleep(0.3)

            # 5. Type Password
            logger.info("輸入密碼...")
            pyautogui.hotkey('ctrl', 'a')
            time.sleep(0.15)
            pyautogui.press('backspace')
            time.sleep(0.15)
            pyautogui.typewrite(password, interval=0.03)
            time.sleep(0.3)

            # 6. Press TAB then Enter
            logger.info("按下 TAB -> 按下 Enter 送出登入...")
            pyautogui.press('tab')
            time.sleep(0.2)
            pyautogui.press('enter')
            time.sleep(2.0)

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




    def switch_to_chat_tab(self, template_path: str = "assets/Message_icon.png", confidence: float = 0.55) -> bool:

        """
        Locates Message_icon.png using template matching and clicks it to ensure LINE is on the Chats tab.
        """
        if not os.path.exists(template_path):
            logger.debug(f"Message icon 樣板不存在: {template_path}")
            return False

        try:
            screenshot_pil = pyautogui.screenshot()
            screenshot_np = np.array(screenshot_pil)
            screen_bgr = cv2.cvtColor(screenshot_np, cv2.COLOR_RGB2BGR)

            tpl = cv2.imread(template_path, cv2.IMREAD_COLOR)
            if tpl is None:
                return False

            t_h, t_w = tpl.shape[:2]
            res = cv2.matchTemplate(screen_bgr, tpl, cv2.TM_CCOEFF_NORMED)
            min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)

            if max_val >= confidence:
                click_x = max_loc[0] + t_w // 2
                click_y = max_loc[1] + t_h // 2
                logger.info(f"🎯 [切換至聊天分頁] 成功比對並點擊 Message_icon.png 座標 ({click_x}, {click_y})，確保進入對話列表頁面！")
                pyautogui.click(click_x, click_y)
                time.sleep(0.4)
                pyautogui.press('escape')
                time.sleep(0.3)
                return True
            else:
                logger.warning(f"⚠️ Message_icon 相似度 {max_val:.2f} 低於門檻 {confidence}，點擊側邊欄預設位置 (32, 56)...")
                pyautogui.click(32, 56)
                time.sleep(0.4)
                pyautogui.press('escape')
                time.sleep(0.3)
                return False
        except Exception as e:
            logger.error(f"切換聊天分頁時發生錯誤: {e}")
            return False

    def recover_environment(self, validator=None) -> bool:
        """
        Main recovery procedure:
        1. Process cleanup
        2. Launch Chrome LINE extension
        3. Reposition & Fullscreen
        4. Auto-login if needed
        5. Validate screen readiness & switch to Chats tab (Message_icon.png)
        """
        if not self.auto_recover:
            logger.info("環境自動恢復已停用 (auto_recover=false)。")
            return False

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

