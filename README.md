# LINE 桌面版智慧自動回覆機器人 (LINE Auto-Reply Bot)

本專案使用 Python 開發，專為 LINE 桌面版（支援 **Linux / Ubuntu Headless** 與 **Windows**）設計。採用 **未讀綠點色塊與樣板雙重視覺辨識 (HSV GreenBlob + OpenCV Template Matching)**、**畫面基線監控與無人值守自動自癒恢復 (Auto-Recovery & Fullscreen)**、**Telegram Bot 驗證碼截圖推播 (Telegram 2FA Notifier)**、**剪貼簿安全鎖與多重編碼容錯 (Robust Clipboard Manager)**、**白名單 FIFO 佇列** 以及 **Vertex AI (主) / OpenAI (備) 雙 LLM 智慧備援回覆** 架構。

---

## 🌟 特色亮點

1. **雙重混合視覺辨識 (Hybrid Vision Detector)**：
   - **HSV 綠色色塊面積過濾**：精準鎖定 LINE 專屬綠點面積（例如 `248px ~ 356px`），不受文字數字或縮放比例干擾。
   - **OpenCV 樣板比對**：支援多樣板（如 `green_dot_white_x.png`）相似度比對與信心度門檻控制。
   - 支援 `hybrid`（混合模式）、`color_blob`（純色塊模式）與 `template`（純樣板模式）。

2. **畫面左側 400px 基線與黑畫面健康監控 (`EnvironmentValidator`)**：
   - 實時監測畫面左側（x: 0 ~ 400px）是否具備 LINE 介面核心特徵（Message 圖示、搜尋列、非空白畫面）。
   - 週期性自動排查視窗是否被最小化、關閉或異常黑畫面。

3. **Chrome LINE 崩潰重啟與無人值守自癒 (`RecoveryManager`)**：
   - 當偵測到 LINE 異常關閉或黑畫面時，自動重新拉起 Chrome LINE 擴充套件 (`--app=chrome-extension://...`)。
   - 自動檢測登入介面並自動輸入密碼進行登入。
   - 透過 `xdotool` 自動聚焦視窗並切換至全螢幕模式 (`F11`)。
   - 啟動與恢復完成後主動點擊 `Message_icon` 切換回聊天列表。

4. **Telegram Bot 訊息推播與手機 2FA 驗證碼截圖 (`TelegramNotifier`)**：
   - 系統異常、環境恢復成功/失敗即時推播 Telegram。
   - 當 LINE 觸發手機雙重驗證 (2FA) 出現驗證碼畫面時，自動截圖並推播至您的 Telegram，無須開啟 VNC 即可由手機輸入驗證碼完成登入。

5. **全螢幕 100px 座標網格診斷系統 (`test_vision.py`)**：
   - 一鍵檢測螢幕截圖權限與解析度。
   - 自動計算畫面中所有樣板的匹配信心度與綠色色塊面積。
   - 自動生成標註圖 `debug/coordinate_grid_map.png`，覆蓋 100px 標尺與十字準星，方便精確排查與微調座標。

6. **智慧安全防誤點與焦點控制 (`LineWindowHelper`)**：
   - **`SafeChatHistory`**：動態定位至對話區域右側空白背景（92% 寬度、40% 高度），避免反白對話紀錄時誤點超連結、貼圖或圖片。
   - **`SafeInputBox`**：精確鎖定底部輸入框中心。
   - **自動解除焦點 (`unfocus_chat_room`)**：每次處理完畢（或跳過非白名單）自動點擊 Message Icon 並按下 `ESC` 切回聊天列表，確保後續新訊息能正常產生綠點。

7. **多重編碼容錯剪貼簿 (`ClipboardManager`)**：
   - 支援 UTF-8、Big5 / CP950（繁體中文）、GB18030、Latin-1 自動轉碼，解決 Linux / `xclip` 下的 `UnicodeDecodeError`。
   - 內建 `threading.Lock()` 確保對話複製與訊息貼上不發生競爭衝突。

8. **多好友獨立 Persona (客製 Prompt) 與雙 LLM 自動備援**：
   - **主模型**：Google Vertex AI / Gemini (`gemini-2.5-flash` / `gemini-3.5-flash`)
   - **備用模型**：OpenAI API (`gpt-4o-mini` / 相容模型)
   - 當主模型配額不足 (429) 或連線超時時，自動無縫切換至備用模型。
   - 支援針對不同好友或群組設定專屬 Prompt（如語氣設定、繁簡中文、泰文/英文回應等）。

9. **防重複與人模人樣防封禁**：
   - 內建最近 100 筆對話內容雜湊簽章防重複發送。
   - 隨機模擬打字延遲發送機制。

---

## 🛠️ 安裝與環境準備

### 1. 系統依賴套件安裝 (Linux / Ubuntu)
本機器人依賴圖形化 X11 介面進行影像擷取、視窗定位與剪貼簿操作。若在無實體螢幕的 Linux 伺服器 (Headless Server) 運行，請先安裝所需套件：
```bash
sudo apt-get update
sudo apt-get install -y xvfb openbox x11vnc xclip gnome-screenshot scrot xdotool x11-utils google-chrome-stable
```

### 2. 配置 Headless 虛擬桌面背景常駐服務 (Xvfb + Openbox + VNC) 🔥
為了確保 LINE 視窗與 Python 機器人能在 Linux 背景穩定運行，需將 **Xvfb（虛擬螢幕 :99）**、**Openbox（視窗管理器）** 與 **x11vnc（VNC 伺服器）** 設定為 Systemd 系統服務，實現**開機自啟與崩潰自動重啟**。

#### (1) 建立服務設定檔
建立 `/etc/systemd/system/xvfb-desktop.service`：
```ini
[Unit]
Description=Headless Xvfb + Openbox + VNC Display Server
After=network.target

[Service]
Type=forking
User=dinghonjay
Environment=DISPLAY=:99
ExecStartPre=-/usr/bin/pkill -f "Xvfb :99"
ExecStart=/bin/bash -c "Xvfb :99 -screen 0 1920x1080x24 -ac & sleep 1; DISPLAY=:99 openbox & sleep 1; x11vnc -display :99 -forever -shared -bg -nopw -rfbport 5900"
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

#### (2) 啟用並啟動服務
```bash
# 重新載入 Systemd 設定
sudo systemctl daemon-reload

# 啟動虛擬桌面服務
sudo systemctl start xvfb-desktop

# 設定開機自動啟動
sudo systemctl enable xvfb-desktop

# 檢查運行狀態 (確認 Active: active (running))
sudo systemctl status xvfb-desktop
```

> 💡 **遠端畫面監看 (VNC)**：
> 服務啟動後，您可以使用任何 VNC Viewer（如 RealVNC / TightVNC）連線至伺服器的 `Port 5900`（或透過 SSH Tunnel `ssh -L 5900:localhost:5900 user@server`），即可即時觀看並操作 LINE 桌面！

### 3. 建立 Python 虛擬環境與安裝套件
```bash
# 建立虛擬環境
python3 -m venv .venv

# 啟動虛擬環境 (Linux / macOS)
source .venv/bin/activate

# 啟動虛擬環境 (Windows PowerShell)
# .\.venv\Scripts\Activate.ps1

# 安裝所需依賴套件
pip install -r requirements.txt
```

### 4. 設定 `config.yaml`
複製範本檔建立您的設定檔：
```bash
cp config.example.yaml config.yaml
```
開啟 `config.yaml` 進行設定：
* **`llm`**：設定 GCP Project ID (Vertex AI) 與備用 LLM API Key。
* **`bot.my_name`**：設定您的 LINE 暱稱。
* **`bot.whitelist`**：填入允許自動回覆的好友或群組名稱白名單。
* **`bot.contact_prompts`**：設定特定對象的專屬對話風格（Persona）。
* **`ui`**：設定綠點辨識模式（`hybrid` / `color_blob` / `template`）、色塊面積範圍（預設 `248` ~ `356` px）與樣板信心度。
* **`environment`**：設定 Chrome 執行檔路徑、LINE 擴充套件 ID、登入帳號密碼（可留空或透過環境變數傳入）、全螢幕模式等。
* **`notification`**：設定 Telegram Bot Token 與 Chat ID（亦可透過 `TELEGRAM_BOT_TOKEN`、`TELEGRAM_CHAT_ID` 環境變數傳入）。

---

## 🚀 執行與診斷工具

### 1. 執行影像辨識診斷 (推薦首次使用)
開啟 LINE 視窗並確保螢幕上有綠點，執行診斷工具：
```bash
python test_vision.py
# 或
python main.py --test-vision
```
**執行成果：**
* 終端機顯示各樣板匹配分數與綠色色塊面積分析報表。
* 📁 `debug/screenshot_full.png`：Python 擷取到的全螢幕原始畫面。
* 🖼️ `debug/test_vision_result.png`：標記各樣板匹配位置與相似度的偵錯圖。
* 🗺️ `debug/coordinate_grid_map.png`：**全螢幕 100px 座標網格圖**（標註綠點目標、安全焦點與輸入框座標）。

### 2. 測試雙 LLM API 連線
```bash
python main.py --test-llm
```

### 3. 測試 Telegram Bot 通知連線
```bash
python main.py --test-notify
```

### 4. 測試 Chrome LINE 環境自動恢復、全螢幕與 2FA 驗證碼推播
```bash
python main.py --test-recover
```

### 5. 以乾執行模式 (Dry-Run) 測試流程（不實際發送訊息）
```bash
python main.py --dry-run
```

### 6. 正式啟動自動回覆機器人
```bash
python main.py
```
若需要觀察即時辨識數據與座標，可加上 `--debug`：
```bash
python main.py --debug
```

---

## 📂 專案結構說明

```text
AutoReplyMessage/
├── assets/                  # 視覺辨識樣板圖片 (Message_icon.png, green_dot_*.png, login_email_field.png)
├── core/
│   ├── clipboard_manager.py # 多編碼安全剪貼簿管理器 (xclip / pyperclip / Lock)
│   ├── environment_validator.py # 螢幕左側 400px 基線與黑畫面檢測
│   ├── notifier.py          # Telegram Bot 訊息與 2FA 驗證碼截圖推播通知
│   ├── recovery_manager.py  # Chrome LINE 崩潰重啟、自動密碼登入、手機驗證碼推播、視窗全螢幕 (F11)
│   ├── llm_service.py       # 雙 LLM 引擎 (Vertex AI 主 / OpenAI 備援)
│   ├── vision_detector.py   # HSV 色塊過濾 + 樣板比對 + 100px 座標網格生成器
│   └── window_helper.py     # 視窗幾何計算、SafeChatHistory、SafeInputBox、解除焦點
├── debug/                   # 自動生成的偵錯截圖與座標網格圖 (已被 .gitignore 忽略)
├── tests/                   # 單元測試 (Telegram 通知、環境恢復、剪貼簿線程安全、設定檔格式)
├── config.example.yaml      # 設定檔安全範本
├── main.py                  # 機器人主入口程式 (支援自動環境恢復與監控)
├── test_vision.py           # 獨立影像辨識與座標診斷測試工具
├── requirements.txt         # Python 依賴清單
└── README.md                # 專案說明文件
```

---

## 🧪 單元測試

執行內建單元測試以驗證 Telegram 通知、環境恢復、設定檔解析與剪貼簿線程安全：
```bash
python tests/test_notifier.py
python tests/test_recovery.py
python tests/test_config.py
python tests/test_clipboard.py
```
