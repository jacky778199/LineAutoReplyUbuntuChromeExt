# LINE 桌面版智慧自動回覆機器人 (LINE Auto-Reply Bot)

本專案使用 Python 開發，專為 LINE 桌面版（支援 **Linux / Ubuntu Headless** 與 **Windows**）設計。採用 **點前 Tesseract OCR 視覺白名單預判 (Zero-Click Whitelist Pre-filtering)**、**側邊欄與登入介面雙錨點自適應相對定位 (Dual-Anchor Relative Positioning)**、**未讀綠點色塊與樣板雙重視覺辨識 (HSV GreenBlob + OpenCV Template Matching)**、**畫面基線監控與無人值守自動自癒恢復 (Auto-Recovery & Fullscreen)**、**Telegram Bot 驗證碼與待處理訊息推播 (Telegram Notifier)**、**全方位 Log 輪轉與失敗現場自動歸檔 (Rotating Log & Failure Archiver)**、**剪貼簿安全鎖與多重編碼容錯 (Robust Clipboard Manager)** 以及 **Vertex AI (主) / OpenAI (備) 雙 LLM 智慧備援回覆** 架構。

---

## 🌟 特色亮點

### 1. 點前 Tesseract OCR 視覺白名單預判 (Zero-Click Whitelist Pre-filtering) 🔥
* **徹底解決「被動已讀 (Unintended Read Marking)」痛點**：
  * 當偵測到側邊欄未讀綠點 `(cx, cy)` 時，**先不進行滑鼠點擊**。
  * 自動裁切綠點左側的好友/群組名稱區塊，透過本地高速 Tesseract OCR（`chi_tra+eng`，耗時僅約 0.05 秒）進行文字辨識與白名單比對。
  * **非白名單聯絡人/群組 ➡️ 100% 絕對不點擊進入！** LINE 伺服器與您的手機端將**永久保持原生未讀綠點/紅點**，絕不造成真人漏接或誤已讀。
  * 內建 **30 秒非白名單冷卻快取**，避免重複辨識消耗 CPU 運算資源。

### 2. 格式自適應時序分析與 Chrome 擴充套件雜訊清洗 🔥
* **雙格式自適應辨識 (Dual-Format Auto Detection)**：
  * 自動識別對話紀錄為 **Linux Chrome 擴充套件（由新到舊，頂端最新）** 或 **桌面版應用程式（由舊到新，底端最新）**。
  * **Chrome 擴充套件模式**：由頂部開始精準提取最新訊息，並透過該訊息下方緊隨的 `Read` / `已讀` 狀態標記，100% 精準判斷是否為本人發言（`is_me`）。
  * **桌面版模式**：由底端向上（Bottom-Up）解析 `HH:MM 發送者 訊息` 結構。
* **全域無死角白名單比對**：突破過去長度限制盲區，支援長對話全文與頂部標頭全域比對，避免好友暱稱在長對話中被截斷。
* **自適應防重複發送雜湊 (Format-Aware Signature Deduplication)**：結合發送者、最新訊息內容與自適應時序視窗計算雜湊值，徹底杜絕因底部舊歷史相同而誤觸 `DUPLICATE_TEXT` 的問題。
* **LLM 上下文與 Prompt 時序調優**：根據格式動態截取最新 4000 字元視窗並注入對應時序指示（頂端最新 vs 底端最新），確保 AI 理解最精準的對話語境。
* **系統雜訊過濾**：自動清洗貼圖佔位符 `￼`、零寬字元 `\u200c`、系統按鈕 (`Save as...`, `Size: 109KB`)、未讀分隔線 (`Unread messages below`) 與語音未支援提示 (`Your OS version doesn't support this feature.`)。


### 3. 全方位 Log 輪轉與失敗事件自動歸檔系統 (`ChatLogger`) 🔥
* **`logs/bot.log` 自動輪轉**：採用 `RotatingFileHandler`（單檔上限 5MB，保留 5 份備份），徹底解決單一日誌檔過大問題。
* **`logs/reply_history.log` 成功回覆專屬清單**：記錄每一筆成功回覆的 Session ID、對象、最新訊息、AI 生成內容、模型供應商與耗時。
* **`logs/failures/YYYYMMDD_HHMMSS_<REASON>/` 失敗/略過專屬封包**：每當發生未回覆或失敗（如剪貼簿為空、被白名單攔截、最後一句為自己發出、LLM 判定無須回覆、發送失敗），系統自動建立時間戳資料夾，完整打包：
  1. `summary.json`：結構化診斷報告與決策原因代碼。
  2. `raw_chat.txt`：當時複製之完整原始文字。
  3. `prompt_and_llm.txt`：傳給 LLM 之完整 Prompt 與模型回傳資訊。
  4. `screenshot.png`：當時螢幕畫面與點擊座標標註截圖。

### 4. Telegram 秘書即時推播 (`TelegramNotifier`)
* **待處理訊息推播**：當白名單聊天室被點開，但 AI 判定無須回覆 (`[NO_REPLY]`)、或最後一句是自己發出時，即時推播最新訊息至您的 Telegram，提醒您手動確認。
* **異常即時警報**：訊息發送失敗或 API 異常時第一時間推播。
* **手機 2FA 驗證碼截圖**：登入觸發雙重驗證時，自動截圖推播驗證碼至手機，無須開啟 VNC 即可完成登入。

### 5. 側邊欄「雙錨點自適應相對定位」(Dual-Anchor Relative Positioning)
* **頂部錨點**：好友人形圖示 (`sidebar_friend_icon.png`)
* **底部錨點**：VOOM 箭頭圖示 (`sidebar_voom_icon.png`)
* **線性插值推算**：$Y_{\text{message}} = Y_{\text{friend}} + \frac{1}{3}(Y_{\text{voom}} - Y_{\text{friend}})$，徹底擺脫**未讀訊息紅點覆蓋破壞模板**與**螢幕解析度/視窗縮放偏移**的問題。

### 6. 登入介面雙錨點自適應定位 (Dual-Anchor Login Resolution)
* 透過 LINE Logo (`login_line_logo.png`) 與 登入按鈕 (`login_button.png`) 雙錨點插值，即使用戶已預先填寫帳號文字，依然能精確定位帳號框、密碼框與登入按鈕。
* 內建 **5 秒網路載入延遲適應緩衝**，確保慢速網路下登入回應與對話列表完整載入。

### 7. 雙重混合視覺辨識 (Hybrid Vision Detector)
* **HSV 綠色色塊面積過濾**：精準鎖定 LINE 專屬綠點面積（預設 `248px ~ 356px`），不受文字數字或縮放比例干擾。
* **OpenCV 樣板比對**：支援多樣板（如 `green_dot_white_x.png`）相似度比對與信心度門檻控制。
* 支援 `hybrid`（混合模式）、`color_blob`（純色塊模式）與 `template`（純樣板模式）。

### 8. 畫面基線健康監控與 Chrome LINE 自動自癒 (`RecoveryManager`)
* 實時監測畫面左側（x: 0 ~ 400px）是否具備 LINE 介面核心特徵，排查視窗最小化或黑畫面。
* 當偵測到 LINE 異常關閉或崩潰時，自動清理重複視窗並重新拉起 Chrome LINE 擴充套件，自動登入並切換至全螢幕模式 (`F11`)。

### 9. 三重防護純白背景安全點擊與自癒防禦 (Safe Click Protection A+B+C)
* **方案 A（動態視覺純白安全區辨識）**：以 OpenCV 掃描對話區塊，動態尋找 $20 \times 20$ 像素之 100% 純白無文字/無連結空白區，確保點擊取得焦點時絕不誤觸超連結或圖片。
* **方案 B（結構性安全邊界錨點備援）**：若視覺搜尋未果，自動降級至右側極限邊距間隙（Gutter 95% 寬度）。
* **方案 C（外部分頁誤開防禦）**：若因任何外部原因開啟新分頁，自動發送 `Ctrl + W` 與 `ESC` 關閉外部分頁並即刻重新聚焦 LINE。
* **自動解除焦點 (`unfocus_chat_room`)**：每次處理完畢（或跳過非白名單）自動點擊 Message Icon 並按下 `ESC` 切回聊天列表，確保後續新訊息能正常產生綠點。

### 10. 多好友獨立 Persona 與雙 LLM 自動備援
* **主模型**：Google Vertex AI / Gemini (`gemini-3.6-flash`)
* **備用模型**：OpenAI API / 相容模型 (`agnes-2.0-flash` / `gpt-4o-mini`)
* 當主模型配額不足或連線逾時時，自動無縫切換至備用模型。
* 支援針對不同好友或群組設定專屬 Prompt（語氣風格、繁體中文、英語、泰語等）。

### 11. LLM 提示詞注入防禦與資料邊界隔離 (Prompt Injection Defense) 🔥
* **`<untrusted_chat_history>` 邊界防護**：將外部聊天內容封裝於專屬 XML 標籤內，並對惡意標籤跳脫逃逸進行即時消毒過濾。
* **Prompt 越獄與敏感資訊防護**：嚴格指示模型忽略聊天記錄中任何企圖覆寫系統規則、索取 Prompt 或金鑰的指令，杜絕對抗性注入攻擊。
* **輸出清理過濾 (`_clean_reply_text`)**：自動剔除多餘的 Markdown 代碼標記（` ``` `）與外層包裹引號，確保回覆為純淨文字。

### 12. `.env` 機密憑證集中管理與大小寫相容載入 🔥
* **杜絕 Git 程式碼外洩**：所有敏感憑證（LINE Messaging API Token、User ID、LINE 登入帳密、OpenAI Key、Telegram Token）皆支援集中於 `.env` 管理（已被 `.gitignore` 預設排除）。
* **內建無外部依賴載入器 (`core.load_dotenv`)**：相容大寫 (`LINE_PASSWORD`) 與小寫 (`line_password`) 命名，開箱即用。

---

## 🛠️ 安裝與環境準備

### 1. 系統依賴套件安裝 (Linux / Ubuntu)
本機器人依賴圖形化 X11 介面與 Tesseract OCR 引擎。若在 Linux 伺服器運行，請先安裝所需套件：
```bash
sudo apt-get update
sudo apt-get install -y xvfb openbox x11vnc xclip gnome-screenshot scrot xdotool x11-utils google-chrome-stable tesseract-ocr tesseract-ocr-chi-tra tesseract-ocr-eng
```

### 2. 配置 Headless 虛擬桌面背景常駐服務 (Xvfb + Openbox + VNC)
為了確保 LINE 視窗與 Python 機器人能在 Linux 背景穩定運行，建議將 **Xvfb（虛擬螢幕 :99）**、**Openbox** 與 **x11vnc** 設定為 Systemd 系統服務：

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

啟用服務：
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now xvfb-desktop
```

### 3. 建立 Python 虛擬環境與安裝套件
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 4. 設定機密環境變數 `.env` (推薦)
在專案根目錄建立 `.env` 檔案存放敏感金鑰（此檔案已被 `.gitignore` 忽略）：
```bash
# .env
LINE_CHANNEL_ACCESS_TOKEN="您的_LINE_CHANNEL_ACCESS_TOKEN"
LINE_USER_ID="您的_LINE_USER_ID"
line_email="your_line_email@example.com"
line_password="your_line_password"
OPENAI_API_KEY="sk-..."
TELEGRAM_BOT_TOKEN="123456:ABC..."
```
> 💡 建議設定嚴格權限確保檔案僅供本人讀寫：`chmod 600 .env`

### 5. 設定 `config.yaml`
複製範本檔建立您的設定檔：
```bash
cp config.example.yaml config.yaml
```
開啟 `config.yaml` 進行設定：
* **`llm`**：設定 GCP Project ID (Vertex AI) 與備用 LLM API Key / Base URL。
* **`bot.my_name`**：設定您的 LINE 暱稱。
* **`bot.whitelist`**：填入允許自動回覆的好友或群組名稱白名單（未在名單內的聯絡人將被點前 OCR 攔截，永久保持未讀）。
* **`bot.contact_prompts`**：設定特定對象的專屬對話風格（Persona）。
* **`ui`**：設定綠點辨識模式（`hybrid` / `color_blob` / `template`）、色塊面積範圍（預設 `248` ~ `356` px）與樣板信心度。
* **`notification`**：設定 Telegram Bot Token 與 Chat ID。

---

## 🚀 執行與診斷工具

### 1. 執行影像辨識診斷 (推薦首次使用)
```bash
python main.py --test-vision
```
* 生成 `debug/coordinate_grid_map.png`（全螢幕 100px 座標網格標註圖）。

### 2. 測試雙 LLM API 連線狀態
```bash
python main.py --test-llm
```

### 3. 測試 Telegram Bot 連線與推播
```bash
python main.py --test-notify
```

### 4. 測試 Chrome LINE 環境自動恢復與登入
```bash
python main.py --test-recover
```

### 5. 測試 LINE 主動推播訊息 (Push Message)
```bash
python send_test_message.py --message "🤖 這是一條來自 LINE AutoReplyBot 的測試主動推播！"
```
* 自動讀取 `.env` 中的 `LINE_CHANNEL_ACCESS_TOKEN` 與 `LINE_USER_ID`。

### 6. 以乾執行模式 (Dry-Run) 測試（不實際送出訊息）
```bash
python main.py --dry-run
```

### 7. 正式啟動自動回覆機器人
```bash
python main.py
```

---

## 📂 專案結構說明

```text
AutoReplyMessage/
├── assets/                  # 視覺辨識樣板圖片 (sidebar_*.png, login_*.png, green_dot_*.png)
├── core/
│   ├── __init__.py          # 核心套件初始化與 .env 環境變數自動載入器
│   ├── sidebar_ocr.py       # 點前 Tesseract OCR 視覺白名單預判 (Zero-Click)
│   ├── chat_logger.py       # 5MB 日誌輪轉、回覆歷史與失敗封包自動存檔 (ChatLogger)
│   ├── clipboard_manager.py # 多編碼安全剪貼簿管理器 (xclip / pyperclip / Lock)
│   ├── environment_validator.py # 螢幕左側 400px 基線與側邊欄雙錨點檢測
│   ├── notifier.py          # Telegram 待處理訊息、異常警報與 2FA 驗證碼推播
│   ├── recovery_manager.py  # Chrome LINE 崩潰重啟、雙錨點自動登入、視窗全螢幕 (F11)
│   ├── llm_service.py       # 雙 LLM 引擎 (Vertex AI 主 / OpenAI 備援，含 Prompt Injection 防禦)
│   ├── vision_detector.py   # 側邊欄雙錨點插值 + HSV 色塊過濾 + 樣板比對 + 座標網格生成
│   └── window_helper.py     # 視窗幾何計算、SafeChatHistory、SafeInputBox、解除焦點
├── logs/                    # 執行日誌與歸檔庫 (已被 .gitignore 忽略)
│   ├── bot.log              # 5MB 循環輪轉日常日誌 (bot.log.1, bot.log.2)
│   ├── reply_history.log    # 成功回覆歷程清單
│   └── failures/            # 失敗與略過事件專屬封包 (summary.json, raw_chat.txt, screenshot.png)
├── debug/                   # 偵錯暫存檔案與最新對話文字
├── tests/                   # 單元測試集 (OCR 預判、對話解析、Log 存檔、雙錨點恢復等)
├── .env                     # 機密環境變數檔案 (已被 .gitignore 忽略，不入版本庫)
├── config.example.yaml      # 設定檔安全範本
├── send_test_message.py     # LINE Messaging API 主動推播測試腳本
├── main.py                  # 機器人主入口程式
├── requirements.txt         # Python 依賴清單 (包含 pytesseract, opencv, google-genai)
└── README.md                # 專案說明文件
```

---

## 🧪 單元測試

執行內建單元測試集以驗證各核心模組：
```bash
python tests/test_sidebar_ocr.py     # 驗證點前 OCR 視覺預判與冷卻快取
python tests/test_sender_parser.py   # 驗證長對話解析、雜訊過濾與白名單匹配
python tests/test_chat_logger.py     # 驗證 Log 輪轉與失敗診斷封包歸檔
python tests/test_notifier.py        # 驗證 Telegram 通知模組
python tests/test_recovery.py        # 驗證環境自癒與雙錨點插值
```

