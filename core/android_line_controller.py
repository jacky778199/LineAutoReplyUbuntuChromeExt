"""
Android LINE App Automation Controller using uiautomator2.
Designed for Waydroid environment to replace OCR and mouse-based automation.
"""

import os
import re
import time
import logging
import functools
import subprocess
from typing import List, Dict, Optional, Tuple

import uiautomator2 as u2

logger = logging.getLogger("AndroidLineController")


def auto_heal(func):
    """
    Decorator that catches connection / RPC errors during AndroidLineController actions,
    triggers self.reconnect(), and retries the action once.
    """
    @functools.wraps(func)
    def wrapper(self, *args, **kwargs):
        try:
            return func(self, *args, **kwargs)
        except Exception as e:
            logger.warning(f"⚠️ [Auto-Healing] 執行 {func.__name__} 時連線中斷或異常: {e}")
            logger.info("🔄 [Auto-Healing] 啟動自動自癒重連機制...")
            if self.reconnect():
                logger.info(f"🔄 [Auto-Healing] 重連成功，重新執行 {func.__name__}...")
                try:
                    return func(self, *args, **kwargs)
                except Exception as retry_err:
                    logger.error(f"❌ [Auto-Healing] 重試 {func.__name__} 依然失敗: {retry_err}")
                    raise
            else:
                logger.error(f"❌ [Auto-Healing] 無法恢復連線，{func.__name__} 終止。")
                raise
    return wrapper


class AndroidLineController:
    """Controls the LINE Android app on Waydroid via uiautomator2."""

    LINE_PACKAGE = "jp.naver.line.android"

    def __init__(self, serial: Optional[str] = None):
        """
        Initializes the controller and connects to the Waydroid device.
        If serial is None, auto-discovers Waydroid IP from dnsmasq leases or adb devices.
        """
        self.serial = serial or self._autodiscover_serial()
        logger.info(f"Connecting to Android device via uiautomator2 at: {self.serial}")
        self.d = u2.connect(self.serial)
        self._ensure_device_ready()

    def _autodiscover_serial(self) -> str:
        """Finds the IP address of Waydroid container."""
        # 1. Check dnsmasq leases
        leases_path = "/var/lib/misc/dnsmasq.waydroid0.leases"
        if os.path.exists(leases_path):
            try:
                with open(leases_path, "r", encoding="utf-8") as f:
                    content = f.read()
                    matches = re.findall(r"(\d{1,3}(?:\.\d{1,3}){3})", content)
                    if matches:
                        target_ip = matches[-1]
                        logger.info(f"Discovered Waydroid IP from dnsmasq: {target_ip}")
                        return f"{target_ip}:5555"
            except Exception as e:
                logger.warning(f"Failed to read dnsmasq leases: {e}")

        # 2. Fallback to default Waydroid subnet IP
        return "192.168.240.112:5555"

    def reconnect(self, max_retries: int = 3, retry_delay: float = 2.0) -> bool:
        """
        Reconnects to Android device via ADB and re-initializes uiautomator2.
        Auto-discovers IP in case Waydroid container IP changed.
        """
        for attempt in range(1, max_retries + 1):
            logger.info(f"🔄 [Auto-Healing] 嘗試重新連線至 Android ({attempt}/{max_retries})...")
            try:
                # 1. Re-discover serial if necessary
                new_serial = self._autodiscover_serial()
                if new_serial:
                    self.serial = new_serial

                # 2. Re-establish ADB connection
                try:
                    subprocess.run(
                        ["adb", "connect", self.serial],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        timeout=5
                    )
                except Exception as adb_err:
                    logger.warning(f"ADB connect 失敗: {adb_err}")

                # 3. Re-connect uiautomator2
                self.d = u2.connect(self.serial)

                # 4. Verify responsiveness and ensure ready
                self.d.screen_on()
                self.d.unlock()
                info = self.d.info
                if info and "sdkInt" in info:
                    logger.info(f"✅ [Auto-Healing] Android 連線成功恢復！(SDK={info.get('sdkInt')})")
                    return True
            except Exception as err:
                logger.warning(f"⚠️ [Auto-Healing] 第 {attempt} 次重連失敗: {err}")
                time.sleep(retry_delay)

        logger.error(f"❌ [Auto-Healing] 連線重試 {max_retries} 次皆失敗。")
        return False

    def ensure_connection(self) -> bool:
        """Checks if device connection is alive, reconnects if dead."""
        try:
            _ = self.d.info
            return True
        except Exception:
            logger.warning("⚠️ 偵測到 Android 連線已斷開，啟動自動自癒連線...")
            return self.reconnect()

    def ensure_waydroid_ui_attached(self) -> bool:
        """
        Ensures Waydroid full UI window is actively attached to Weston/X11 display.
        Checks if 'waydroid show-full-ui' process is running; if not, launches it in background.
        """
        try:
            # 1. Check if show-full-ui is already running
            res = subprocess.run(["pgrep", "-f", "waydroid show-full-ui"], stdout=subprocess.PIPE, text=True)
            if res.returncode == 0 and res.stdout.strip():
                return True

            logger.info("🖥️ [UI-KeepAlive] 偵測到 Waydroid UI 尚未附著至 Weston，正在自動啟動視窗...")
            # 2. Discover Wayland Display socket
            user_id = os.getuid()
            runtime_dir = f"/run/user/{user_id}"
            w_disp = "wayland-1"
            if os.path.exists(runtime_dir):
                sockets = [f for f in os.listdir(runtime_dir) if f.startswith("wayland-") and not f.endswith(".lock")]
                if sockets:
                    # Sort to get the latest socket
                    sockets.sort(key=lambda s: os.path.getmtime(os.path.join(runtime_dir, s)), reverse=True)
                    w_disp = sockets[0]

            env = os.environ.copy()
            env["WAYLAND_DISPLAY"] = w_disp
            env["XDG_RUNTIME_DIR"] = runtime_dir
            cmd = f"WAYLAND_DISPLAY={w_disp} waydroid show-full-ui >/dev/null 2>&1 &"
            subprocess.Popen(cmd, shell=True, env=env)
            time.sleep(1.0)
            logger.info(f"🖥️ [UI-KeepAlive] 已發送 Waydroid show-full-ui 指令 (WAYLAND_DISPLAY={w_disp})")
            return True
        except Exception as e:
            logger.warning(f"⚠️ [UI-KeepAlive] 確保 Waydroid UI 附著失敗: {e}")
            return False

    def check_line_health(self) -> Tuple[bool, str]:
        """
        Performs deep health check on LINE process and Android system:
        1. Checks for SQLite connection pool deadlocks in logcat.
        2. Checks if WindowManager has lost focus while LINE is in foreground (ANR / Frozen).
        3. Checks responsiveness of uiautomator connection.
        Returns: (is_healthy, reason_if_unhealthy)
        """
        # 1. Check SQLite Deadlock signature via logcat
        try:
            logcat_res = self.d.shell("logcat -d -t 40")
            logcat_text = logcat_res.output if hasattr(logcat_res, "output") else str(logcat_res)
            if "SQLiteConnectionPool" in logcat_text and "unable to grant a connection" in logcat_text:
                return False, "偵測到 LINE 內部 SQLite 連線池死鎖 (SQLiteConnectionPool Deadlock)"
        except Exception as e:
            logger.warning(f"檢查 logcat SQLite 狀態異常: {e}")

        # 2. Check Window Focus / ANR
        try:
            dumpsys_res = self.d.shell("dumpsys window")
            dump_text = dumpsys_res.output if hasattr(dumpsys_res, "output") else str(dumpsys_res)
            
            # Check if LINE is focused app but mCurrentFocus is null (frozen UI)
            if "mFocusedApp" in dump_text and self.LINE_PACKAGE in dump_text:
                if "mCurrentFocus=null" in dump_text:
                    # Verify if it persists
                    time.sleep(1.0)
                    dump_retry = self.d.shell("dumpsys window")
                    dump_retry_text = dump_retry.output if hasattr(dump_retry, "output") else str(dump_retry)
                    if "mCurrentFocus=null" in dump_retry_text and self.LINE_PACKAGE in dump_retry_text:
                        return False, "LINE 處於前景但視窗焦點遺失且無響應 (Window Focus Deadlock / ANR)"
        except Exception as e:
            logger.warning(f"檢查視窗焦點狀態異常: {e}")

        # 3. Check UIAutomator responsiveness
        try:
            _ = self.d.info
        except Exception as e:
            return False, f"UIAutomator RPC 無法連線或無回應: {e}"

        return True, "OK"

    def restart_line(self, reason: str = "", stop_wait: float = 3.0, start_wait: float = 8.0) -> bool:
        """
        Robustly restarts LINE app with generous timings:
        1. Force stops LINE to release SQLite and Binder locks.
        2. Waits stop_wait seconds to ensure kernel locks are released.
        3. Starts LINE SplashActivity.
        4. Waits start_wait seconds for network handshake and DB sync.
        5. Switches back to Chats tab.
        """
        logger.warning(f"🔄 [Restart-Line] 執行 LINE 重啟 (原因: {reason or '無特定原因'})...")
        try:
            # 1. Force stop
            self.stop_line()
            logger.info(f"⏳ [Restart-Line] 充足等待釋放檔案鎖 ({stop_wait:.1f} 秒)...")
            time.sleep(stop_wait)

            # 2. Start LINE
            logger.info("🚀 [Restart-Line] 啟動 LINE 應用程式...")
            self.d.shell(f"am start -n {self.LINE_PACKAGE}/.activity.SplashActivity")
            logger.info(f"⏳ [Restart-Line] 充足等待網路交握與資料庫同步 ({start_wait:.1f} 秒)...")
            time.sleep(start_wait)

            # 3. Ensure back on Chats tab
            self.switch_to_chats_tab()
            time.sleep(1.0)

            # 4. Ensure Waydroid UI window is attached
            self.ensure_waydroid_ui_attached()

            is_running = self.is_line_running()
            if is_running:
                logger.info("✅ [Restart-Line] LINE 重啟成功並已回到聊天列表！")
            else:
                logger.warning("⚠️ [Restart-Line] LINE 重啟後未處於前景，嘗試再次喚醒...")
                self.launch_line(wait_seconds=4.0)
                is_running = self.is_line_running()

            return is_running
        except Exception as e:
            logger.error(f"❌ [Restart-Line] LINE 重啟失敗: {e}")
            return False

    def _ensure_device_ready(self):
        """Ensures device screen is turned on and ready."""
        try:
            self.d.screen_on()
            self.d.unlock()
            self.ensure_waydroid_ui_attached()
            info = self.d.info
            logger.info(f"Device ready: SDK={info.get('sdkInt')}, Display={info.get('displayWidth')}x{info.get('displayHeight')}")
        except Exception as e:
            logger.error(f"Error ensuring device ready: {e}")

    @auto_heal
    def is_line_installed(self) -> bool:
        """Checks if LINE app is installed on the device."""
        try:
            packages = self.d.app_list()
            return self.LINE_PACKAGE in packages
        except Exception as e:
            logger.error(f"Error checking app list: {e}")
            return False

    @auto_heal
    def is_line_running(self) -> bool:
        """Checks if LINE app is running in foreground."""
        try:
            cur = self.d.app_current()
            return cur.get("package") == self.LINE_PACKAGE
        except Exception:
            return False

    @auto_heal
    def launch_line(self, wait_seconds: float = 3.0) -> bool:
        """Launches the LINE app safely using am start and waits for it to appear."""
        logger.info(f"Launching LINE app ({self.LINE_PACKAGE})...")
        try:
            # Use direct am start instead of monkey to avoid triggering system shortcuts
            self.d.shell("am start -n jp.naver.line.android/.activity.SplashActivity")
            time.sleep(wait_seconds)
            return self.is_line_running()
        except Exception as e:
            logger.error(f"Failed to launch LINE: {e}")
            return False

    def stop_line(self):
        """Stops the LINE app."""
        logger.info(f"Stopping LINE app...")
        try:
            self.d.shell(f"am force-stop {self.LINE_PACKAGE}")
        except Exception as e:
            logger.error(f"Failed to stop LINE: {e}")

    @auto_heal
    def switch_to_chats_tab(self) -> bool:
        """Clicks on the 'Chats' / '聊天' bottom navigation tab with auto-recovery."""
        try:
            # Auto-recovery: If LINE is not in foreground, wake it up immediately
            if not self.is_line_running():
                logger.info("LINE 應用不在前景，自動喚醒中...")
                self.launch_line(wait_seconds=2.0)

            for _ in range(2):
                for text in ["聊天", "Chats", "Chats tab"]:
                    elem = self.d(text=text)
                    if elem.exists:
                        elem.click()
                        time.sleep(0.5)
                        return True
                    elem_desc = self.d(description=text)
                    if elem_desc.exists:
                        elem_desc.click()
                        time.sleep(0.5)
                        return True
                # Try XPath for tab icons
                tab = self.d.xpath('//android.widget.TextView[@text="聊天" or @text="Chats"]')
                if tab.exists:
                    tab.click()
                    return True

                # If not found, we might be inside a chat room, press back and retry
                current_act = self.d.app_current().get("activity", "")
                if "ChatHistory" in current_act or "activity" in current_act:
                    self.back_to_chat_list()
                    time.sleep(0.8)
        except Exception as e:
            logger.error(f"Failed to switch to Chats tab: {e}")
        return False

    @auto_heal
    def scan_chat_items(self) -> List[Dict[str, any]]:
        """
        Scans current chat list on screen using native LINE resource IDs.
        Returns a list of dicts with:
          - name: contact/group name
          - last_message: preview text
          - date: timestamp or date text
          - has_unread: boolean
          - unread_count: int
          - bounds: element bounds tuple
        """
        chat_items = []
        try:
            screen_info = self.d.info
            max_y = screen_info.get("displayHeight", 960) - 80

            # Target only real chat item rows (id/root)
            rows = self.d.xpath('//android.view.ViewGroup[@resource-id="jp.naver.line.android:id/root"]').all()
            if not rows:
                # Fallback: scan RecyclerView children with height check to exclude full list container
                all_rows = self.d.xpath('//androidx.recyclerview.widget.RecyclerView/*').all()
                rows = [r for r in all_rows if (r.bounds[3] - r.bounds[1]) < 180]

            for r in rows:
                bounds = r.bounds
                # Skip items that are outside visible list area or overlapping bottom navigation
                if bounds[1] >= max_y or bounds[3] <= 100:
                    continue

                # 1. Contact / Group Name
                name_elems = r.elem.xpath('.//*[@resource-id="jp.naver.line.android:id/name"]')
                contact_name = name_elems[0].attrib.get("text", "").strip() if name_elems else ""

                # 2. Preview Message Text
                msg_elems = r.elem.xpath('.//*[@resource-id="jp.naver.line.android:id/last_message"]')
                last_msg = msg_elems[0].attrib.get("text", "").strip() if msg_elems else ""

                # 3. Date / Time String
                date_elems = r.elem.xpath('.//*[@resource-id="jp.naver.line.android:id/date"]')
                date_str = date_elems[0].attrib.get("text", "").strip() if date_elems else ""

                # If name is not found by ID, fallback to text nodes
                if not contact_name:
                    text_nodes = [tn.attrib.get("text", "").strip() for tn in r.elem.xpath('.//*[@text]') if tn.attrib.get("text", "").strip()]
                    if not text_nodes:
                        continue
                    if text_nodes[0] in ["主頁", "聊天", "VOOM", "Today", "錢包", "Home", "Chats", "Wallet", "LINE"]:
                        continue
                    contact_name = text_nodes[0]
                    if not last_msg and len(text_nodes) > 1:
                        for tn in text_nodes[1:]:
                            if tn != date_str and not (tn.isdigit() and len(tn) <= 4):
                                last_msg = tn
                                break

                if not contact_name:
                    continue

                # 4. Unread Indicators
                has_unread = False
                unread_count = 0

                # Check unread message count elements (both normal and square/openchat)
                unread_elems = r.elem.xpath('.//*[contains(@resource-id, "unread_message_count")]')
                if unread_elems:
                    txt = unread_elems[0].attrib.get("text", "").strip().replace(",", "")
                    if txt.isdigit():
                        unread_count = int(txt)
                        has_unread = unread_count > 0
                    else:
                        has_unread = True
                        unread_count = 1
                else:
                    # Also check unread alert container (e.g. mute green/red dot badge)
                    alert_elems = r.elem.xpath('.//*[@resource-id="jp.naver.line.android:id/unread_alert_container"]')
                    if alert_elems:
                        has_unread = True
                        unread_count = 1

                chat_items.append({
                    "name": contact_name,
                    "last_message": last_msg,
                    "date": date_str,
                    "has_unread": has_unread,
                    "unread_count": unread_count,
                    "bounds": bounds
                })
        except Exception as e:
            logger.error(f"Error scanning chat list: {e}")

        return chat_items

    @auto_heal
    def enter_chat(self, contact_name: str) -> bool:
        """Clicks on the chat room matching contact_name."""
        logger.info(f"Attempting to enter chat room: '{contact_name}'")
        try:
            elem = self.d(text=contact_name)
            if elem.exists:
                elem.click()
                time.sleep(1.0)
                return True
            
            # Fallback: XPath text contains
            elem_xpath = self.d.xpath(f'//android.widget.TextView[contains(@text, "{contact_name}")]')
            if elem_xpath.exists:
                elem_xpath.click()
                time.sleep(1.0)
                return True
            
            logger.warning(f"Chat room '{contact_name}' not found on current screen.")
            return False
        except Exception as e:
            logger.error(f"Failed to enter chat '{contact_name}': {e}")
            return False

    @auto_heal
    def get_chat_history(self, max_count: int = 15) -> List[str]:
        """
        Reads visible messages in the current chat room directly from TextViews.
        Returns cleaned text list from oldest to newest.
        """
        messages = []
        try:
            # Extract all message TextViews inside the chat list
            text_nodes = self.d.xpath('//androidx.recyclerview.widget.RecyclerView//android.widget.TextView | //android.widget.ListView//android.widget.TextView')
            for node in text_nodes.all():
                t = node.text
                if t and len(t.strip()) > 0:
                    # Filter out system timestamps or tiny labels if needed
                    clean_t = t.strip()
                    if clean_t not in ["傳送", "已讀", "Read", "+", "LINE"]:
                        messages.append(clean_t)
            
            # Keep the latest max_count messages
            if len(messages) > max_count:
                messages = messages[-max_count:]
        except Exception as e:
            logger.error(f"Failed to extract chat history: {e}")

        return messages

    @auto_heal
    def send_reply(self, message_text: str) -> bool:
        """
        Inputs message into the input field and clicks send.
        """
        logger.info(f"Sending reply: '{message_text}'")
        try:
            # 1. Locate message input field (EditText)
            edit_box = self.d(className="android.widget.EditText")
            if not edit_box.exists:
                # Try xpath
                edit_box = self.d.xpath('//android.widget.EditText')

            if not edit_box.exists:
                logger.error("Could not find message input box (EditText)!")
                return False

            edit_box.set_text(message_text)
            time.sleep(0.3)

            # 2. Locate and click Send button
            # Usually Send button appears after text is typed
            for send_target in [
                self.d(description="傳送"),
                self.d(description="Send"),
                self.d(text="傳送"),
                self.d(text="Send"),
                self.d(resourceIdMatches=".*send.*|.*btn_send.*")
            ]:
                if send_target.exists:
                    send_target.click()
                    logger.info("Successfully clicked Send button.")
                    time.sleep(0.5)
                    return True

            # XPath fallback for send button
            send_xpath = self.d.xpath('//android.widget.ImageView[contains(@content-desc, "傳送") or contains(@content-desc, "Send")]')
            if send_xpath.exists:
                send_xpath.click()
                logger.info("Successfully clicked Send button via XPath.")
                time.sleep(0.5)
                return True

            logger.error("Could not locate Send button after entering text.")
            return False
        except Exception as e:
            logger.error(f"Error sending reply: {e}")
            return False

    @auto_heal
    def back_to_chat_list(self):
        """Presses BACK to return to the chat list, avoiding keeping chat open."""
        try:
            self.d.press("back")
            time.sleep(0.5)
        except Exception as e:
            logger.error(f"Error pressing back: {e}")
