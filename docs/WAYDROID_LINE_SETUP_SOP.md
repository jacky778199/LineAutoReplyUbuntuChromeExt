# Ubuntu Headless 環境：Waydroid + LINE App + Python uiautomator2 完整建置 SOP

本文件整理了在 **無實體螢幕的 Ubuntu 伺服器 / 雲端 VM（如 GCP、AWS、個人 Linux Server）** 上，從零打造 **Waydroid (Android 13) + ARM 轉譯層 (libndk) + LINE App + Python uiautomator2 原生自動化** 的完整流程與踩坑避坑指南。下次在全新機器部署時，直接依照本文件步驟依序執行即可。

---

## 🏛️ 架構原理與運作關係

在無實體螢幕的 Linux 伺服器上，各模組層級關係如下：
1. **Xvfb (:99 虛擬螢幕)**：模擬出一個 1920x1080 的虛擬顯示器。
2. **x11vnc (Port 5900)**：將 `:99` 虛擬桌面透過 VNC 廣播，供真人隨時以 VNC Viewer 連線預覽、登入 LINE 與排查問題。
3. **pipewire-pulse**：常駐音訊伺服器，提供 `/run/user/<UID>/pulse/native` 通訊端點，避免 Waydroid LXC 容器掛載音訊失敗。
4. **Weston (Wayland 合成器)**：嵌套在 Xvfb 內運行，提供 Wayland 協議環境（解析度設為 `540x960`，剛好適應 1080p 螢幕高度）。
5. **Waydroid (Android 13 GAPPS)**：運行在 Weston 內的 Android 容器。
6. **libndk (ARM 轉譯層)**：讓 x86_64 處理器能無縫執行純 ARM 架構的 LINE App。
7. **Python uiautomator2**：透過本機 ADB (Port 5555) 直連 Android，精準讀取 UI 樹與操作按鈕。

```text
┌─────────────────────────────────────────────────────────────┐
│ Ubuntu Headless (無螢幕主機 / 雲端 VM)                       │
│                                                             │
│   Xvfb (:99 虛擬桌面 1920x1080)                             │
│      ├── x11vnc (Port 5900) ── 供真人 VNC 連線手動登入      │
│      └── Weston (Wayland 合成器 540x960 嵌套在 :99)         │
│             └── Waydroid (Android 13 容器)                  │
│                    ├── libndk (ARM 轉譯層，供 LINE 執行)    │
│                    └── LINE App (arm64-v8a)                 │
│                                                             │
│   pipewire-pulse (音訊服務) ── 避免 Waydroid LXC 掛載失敗   │
│   ADB (192.168.240.112:5555) ── 免密鑰自動授權              │
│   Python uiautomator2 ── 直讀 Android UI 樹與原生按鈕       │
└─────────────────────────────────────────────────────────────┘
```

---

## 📋 第一階段：系統依賴套件與音訊環境安裝

### 1. 更新系統並安裝基礎工具
```bash
sudo apt-get update
sudo apt-get install -y \
    curl git lzip psmisc adb \
    xvfb openbox x11vnc scrot xdotool x11-utils \
    weston pipewire pipewire-pulse
```

### 2. 確保 Linux 內核支援 Binder
Waydroid 需要 Android Binder IPC：
```bash
ls -d /dev/binder* /dev/binderfs
```
* Ubuntu 22.04 / 24.04 / 26.04 核心皆已原生包含 `binderfs`。
* 若無 `/dev/binderfs`，執行：
  ```bash
  sudo mkdir -p /dev/binderfs
  sudo mount -t binder binder /dev/binderfs
  ```

### 3. 常駐音訊服務 (解決 LXC 掛載 pulse 報錯關鍵)
```bash
systemctl --user enable --now pipewire pipewire-pulse
# 檢查 socket 是否存在：
ls -l /run/user/$(id -u)/pulse/native
```

---

## 📦 第二階段：安裝 Waydroid 與初始化 Android 映像檔

### 1. 新增 Waydroid 官方 Repo 並安裝
```bash
export DISTRO=$(lsb_release -cs)
sudo curl -s https://repo.waydro.id/waydroid.gpg > /usr/share/keyrings/waydroid.gpg
echo "deb [signed-by=/usr/share/keyrings/waydroid.gpg] https://repo.waydro.id/ $DISTRO main" | sudo tee /etc/apt/sources.list.d/waydroid.list
sudo apt-get update
sudo apt-get install -y waydroid
```

### 2. 初始化 Android 13 (GAPPS 版本)
```bash
# 預先停止可能殘留的服務
sudo systemctl stop waydroid-container 2>/dev/null || true

# 下載官方 Android 13 GAPPS 映像檔並初始化
sudo waydroid init -s GAPPS -f
```

---

## ⚡ 第三階段：安裝 ARM 轉譯層 (libndk) 🔥（關鍵必備）

> [!IMPORTANT]
> **官方 Android 版 LINE App 只有 ARM 架構（`arm64-v8a`）**。
> 若未安裝 ARM 轉譯層，安裝 LINE 會噴出 `INSTALL_FAILED_NO_MATCHING_ABIS` 或閃退。

### 1. 取得 `waydroid_script` 工具並安裝依賴
```bash
cd ~
git clone https://github.com/casualsnek/waydroid_script
cd waydroid_script
python3 -m venv venv
./venv/bin/pip install -r requirements.txt InquirerPy
```

### 2. 注入 libndk 轉譯層
```bash
# 確保 container 停止
sudo systemctl stop waydroid-container

# 注入 libndk
sudo ./venv/bin/python3 main.py -a 13 install libndk

# 重啟 container 服務
sudo systemctl start waydroid-container
```

### 3. 驗證 ABI 支援列表
啟動 Waydroid session 後檢查：
```bash
sudo waydroid shell getprop ro.product.cpu.abilist
```
* 正確輸出應包含：`x86_64,x86,arm64-v8a,armeabi-v7a,armeabi`。

---

## 🖥️ 第四階段：建立虛擬桌面與 Weston 環境（解決裁切與按鈕）

### 1. 虛擬螢幕與 Weston 解析度調校
* **Xvfb 尺寸**：`1920x1080x24`。
* **Weston 尺寸**：**必須設定為 `540x960`（或高度不超過 1000px）**，避免底部 Home / 返回鍵掉出螢幕外。

### 2. 開啟 Android 三大金剛鍵（返回、Home、多工）
Android 13 預設為手勢導航，透過 ADB 一鍵改回三鍵導航：
```bash
adb shell cmd overlay enable com.android.internal.systemui.navbar.threebutton
```

### 3. 免密鑰授權（永久免跳出 "Allow USB Debugging" 提示）
將 Host 端 ADB 公鑰複製至 Waydroid 系統目錄：
```bash
adb start-server
sudo cp ~/.android/adbkey.pub /home/$USER/.local/share/waydroid/data/misc/adb/adb_keys
sudo chown 1000:2000 /home/$USER/.local/share/waydroid/data/misc/adb/adb_keys
sudo chmod 640 /home/$USER/.local/share/waydroid/data/misc/adb/adb_keys
```

---

## 📜 第五階段：一鍵啟動腳本與 Systemd 常駐

建立常駐啟動腳本 `scripts/start_waydroid_env.sh`：

```bash
#!/usr/bin/env bash
set -e

USER_ID=$(id -u)
RUNTIME_DIR="/run/user/${USER_ID}"
export XDG_RUNTIME_DIR="${RUNTIME_DIR}"
mkdir -p ~/.local/share/waydroid

echo "[+] 檢查 Xvfb :99..."
if ! pgrep -f "Xvfb :99" > /dev/null; then
    Xvfb :99 -screen 0 1920x1080x24 &
    sleep 1
fi

echo "[+] 檢查 x11vnc..."
if ! pgrep -f "x11vnc.*:99" > /dev/null; then
    x11vnc -display :99 -rfbauth ~/.vnc/passwd -localhost -forever -bg >/dev/null 2>&1 || true
    sleep 1
fi

echo "[+] 檢查 pipewire-pulse..."
systemctl --user start pipewire-pulse >/dev/null 2>&1 || true

echo "[+] 啟動 Weston (540x960)..."
if ! pgrep -x weston > /dev/null; then
    rm -f "${RUNTIME_DIR}"/wayland-* 2>/dev/null || true
    DISPLAY=:99 weston --backend=x11 --width=540 --height=960 > ~/.local/share/waydroid/weston.log 2>&1 &
    sleep 2
fi

W_DISP=$(ls -t "${RUNTIME_DIR}"/wayland-[0-9] 2>/dev/null | head -n 1 | xargs -r basename)
export WAYLAND_DISPLAY="${W_DISP}"

echo "[+] 啟動 Waydroid Session..."
SESSION_STATUS=$(waydroid status 2>/dev/null | grep "Session:" | awk '{print $2}' || true)
if [ "${SESSION_STATUS}" != "RUNNING" ]; then
    waydroid session start > ~/.local/share/waydroid/session.log 2>&1 &
    sleep 5
fi

# 等待開機完成
for i in $(seq 1 30); do
    if [ "$(sudo waydroid shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')" = "1" ]; then
        break
    fi
    sleep 2
done

# 連接 ADB
IP=$(grep -oE "([0-9]{1,3}\.){3}[0-9]{1,3}" /var/lib/misc/dnsmasq.waydroid0.leases 2>/dev/null | tail -n 1 || true)
if [ -n "${IP}" ]; then
    adb connect "${IP}:5555" || true
fi

# 開啟三大金剛鍵並拉起 UI
adb shell cmd overlay enable com.android.internal.systemui.navbar.threebutton 2>/dev/null || true
waydroid show-full-ui >/dev/null 2>&1 &

echo "[+] Waydroid 環境已成功就緒！VNC 埠號 5900。"
```

給予執行權限：
```bash
chmod +x scripts/start_waydroid_env.sh
```

---

## 📱 第六階段：安裝 LINE App 與登入

1. **下載 LINE 官方 Standalone APK**（注意：下載完必須確認檔案大小約 180MB 且不是 XAPK）：
   ```bash
   adb install -r line-15.21.3.apk
   ```
2. **打開 VNC Viewer（Port 5900）**：
   - 看到 Android 手機畫面。
   - 點開 LINE App，使用手機號碼或 QR Code 完成首次登入。

---

## 🤖 第七階段：Python uiautomator2 自動化開發注意點

### 1. 安裝套件
```bash
pip install uiautomator2 adbutils
```

### 2. 連線與基本操作
```python
import uiautomator2 as u2

# 連線 (IP:5555 或自動抓取)
d = u2.connect("192.168.240.112:5555")

# 喚醒與解鎖
d.screen_on()
d.unlock()

# 啟動 LINE
d.app_start("jp.naver.line.android")

# 取得目前前景 App (注意：u2 3.x 請使用 app_current() 而非 current_app)
print(d.app_current())
```

### 3. UI 元素抓取與文字輸入
```python
# 點擊「聊天」頁籤
d(text="聊天").click()

# 點擊好友
d(text="好友名稱").click()

# 讀取對話紀錄 (直接讀 TextView，100% 正確免 OCR)
messages = [node.text for node in d.xpath('//android.widget.TextView').all() if node.text]

# 輸入回覆並發送
d(className="android.widget.EditText").set_text("你好，這是自動回覆！")
d(description="傳送").click()

# 返回聊天列表 (避免維持在對話中被判定為已讀)
d.press("back")
```

---

## 🛠️ 常見錯誤排查速查表 (Cheat Sheet)

| 錯誤現象 | 根本原因 | 解決方法 |
| :--- | :--- | :--- |
| `Failed to mount pulse/native` | `pipewire-pulse` 未在背景執行 | `systemctl --user start pipewire-pulse` |
| `INSTALL_FAILED_NO_MATCHING_ABIS` | 尚未安裝 ARM 轉譯層，LINE APK 是 ARM 架構 | 使用 `waydroid_script` 安裝 `libndk` |
| `INSTALL_PARSE_FAILED_NOT_APK` | 下載未完成中斷，或下載成 XAPK 分割包 | 確認 APK 大小完整，或下載 Standalone APK |
| VNC 畫面下方被截斷、看不到 Home 鍵 | Weston 高度 (1280px) 超過螢幕 (1080px) | 將 Weston 寬高改為 `540x960` |
| Android 無返回與 Home 按鈕 | Android 13 預設為全螢幕手勢導航 | `adb shell cmd overlay enable com.android.internal.systemui.navbar.threebutton` |
| `bash: killall: command not found` | 系統缺少 `psmisc` 套件 | `sudo apt install -y psmisc` |
| `'Device' object has no attribute 'current_app'` | uiautomator2 3.x API 改名 | 改用 `d.app_current()` |
