"""
Android LINE App Automation Controller using uiautomator2.
Designed for Waydroid environment to replace OCR and mouse-based automation.
"""

import os
import re
import time
import logging
from typing import List, Dict, Optional, Tuple

import uiautomator2 as u2

logger = logging.getLogger("AndroidLineController")


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

    def _ensure_device_ready(self):
        """Ensures device screen is turned on and ready."""
        try:
            self.d.screen_on()
            self.d.unlock()
            info = self.d.info
            logger.info(f"Device ready: SDK={info.get('sdkInt')}, Display={info.get('displayWidth')}x{info.get('displayHeight')}")
        except Exception as e:
            logger.error(f"Error ensuring device ready: {e}")

    def is_line_installed(self) -> bool:
        """Checks if LINE app is installed on the device."""
        try:
            packages = self.d.app_list()
            return self.LINE_PACKAGE in packages
        except Exception as e:
            logger.error(f"Error checking app list: {e}")
            return False

    def is_line_running(self) -> bool:
        """Checks if LINE app is running in foreground."""
        try:
            cur = self.d.app_current()
            return cur.get("package") == self.LINE_PACKAGE
        except Exception:
            return False

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

    def back_to_chat_list(self):
        """Presses BACK to return to the chat list, avoiding keeping chat open."""
        try:
            self.d.press("back")
            time.sleep(0.5)
        except Exception as e:
            logger.error(f"Error pressing back: {e}")
