# LINE 桌面版智慧自動回覆機器人 (LINE Auto-Reply Bot)

本專案使用 Python 開發，專為 LINE 桌面版（支援 **Linux / Ubuntu** 與 **Windows**）設計。採用 **未讀綠點色塊與樣板雙重視覺辨識 (HSV GreenBlob + OpenCV Template Matching)**、**剪貼簿安全鎖與多重編碼容錯 (Robust Clipboard Manager)**、**白名單 FIFO 佇列** 以及 **Vertex AI (主) / OpenAI (備) 雙 LLM 智慧備援回覆** 架構。

---

## 🌟 特色亮點

1. **雙重混合視覺辨識 (Hybrid Vision Detector)**：
   - **HSV 綠色色塊面積過濾**：精準鎖定 LINE 專屬綠點面積（例如 `248px ~ 356px`），不受文字數字或縮放比例干擾。
   - **OpenCV 樣板比對**：支援多樣板（如 `green_dot_white_x.png`）相似度比對與信心度門檻控制。
   - 支援 `hybrid`（混合模式）、`color_blob`（純色塊模式）與 `template`（純樣板模式）。

2. **全螢幕 100px 座標網格診斷系統 (`test_vision.py`)**：
   - 一鍵檢測螢幕截圖權限與解析度。
   - 自動計算畫面中所有樣板的匹配信心度與綠色色塊面積。
   - 自動生成標註圖 `debug/coordinate_grid_map.png`，覆蓋 100px 標尺與十字準星，方便精確排查與微調座標。

3. **智慧安全防誤點與焦點控制 (`LineWindowHelper`)**：
   - **`SafeChatHistory`**：動態定位至對話區域右側空白背景（92% 寬度、40% 高度），避免反白對話紀錄時誤點超連結、貼圖或圖片。
   - **`SafeInputBox`**：精確鎖定底部輸入框中心。
   - **自動解除焦點 (`unfocus_chat_room`)**：每次處理完畢（或跳過非白名單）自動點擊 Message Icon 並按下 `ESC` 切回聊天列表，確保後續新訊息能正常產生綠點。

4. **多重編碼容錯剪貼簿 (`ClipboardManager`)**：
   - 支援 UTF-8、Big5 / CP950（繁體中文）、GB18030、Latin-1 自動轉碼，解決 Linux / `xclip` 下的 `UnicodeDecodeError`。
   - 內建 `threading.Lock()` 確保對話複製與訊息貼上不發生競爭衝突。

5. **多好友獨立 Persona (客製 Prompt) 與雙 LLM 自動備援**：
   - **主模型**：Google Vertex AI / Gemini (`gemini-2.5-flash`)
   - **備用模型**：OpenAI API (`gpt-4o-mini` / 相容模型)
   - 當主模型配額不足 (429) 或連線超時時，自動無縫切換至備用模型。
   - 支援針對不同好友或群組設定專屬 Prompt（如語氣設定、繁簡中文、泰文/英文回應等）。

6. **防重複與人模人樣防封禁**：
   - 內建最近 100 筆對話內容雜湊簽章防重複發送。
   - 隨機模擬打字延遲發送機制。

---

## 🛠️ 安裝與環境準備

### 1. 系統依賴安裝 (Linux / Ubuntu)
若在 Linux 環境下運行，請先安裝剪貼簿與截圖工具：
```bash
sudo apt-get update
sudo apt-get install -y xclip gnome-screenshot scrot xdotool x11-utils
```

### 2. 建立 Python 虛擬環境與安裝套件
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

### 3. 設定 `config.yaml`
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

### 3. 以乾執行模式 (Dry-Run) 測試流程（不實際發送訊息）
```bash
python main.py --dry-run
```

### 4. 正式啟動自動回覆機器人
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
├── assets/                  # 視覺辨識樣板圖片 (Message_icon.png, green_dot_*.png)
├── core/
│   ├── clipboard_manager.py # 多編碼安全剪貼簿管理器 (xclip / pyperclip / Lock)
│   ├── llm_service.py       # 雙 LLM 引擎 (Vertex AI 主 / OpenAI 備援)
│   ├── vision_detector.py   # HSV 色塊過濾 + 樣板比對 + 100px 座標網格生成器
│   └── window_helper.py     # 視窗幾何計算、SafeChatHistory、SafeInputBox、解除焦點
├── debug/                   # 自動生成的偵錯截圖與座標網格圖 (已被 .gitignore 忽略)
├── tests/                   # 單元測試 (剪貼簿線程安全、設定檔格式)
├── config.example.yaml      # 設定檔安全範本
├── main.py                  # 機器人主入口程式
├── test_vision.py           # 獨立影像辨識與座標診斷測試工具
├── requirements.txt         # Python 依賴清單
└── README.md                # 專案說明文件
```

---

## 🧪 單元測試

執行內建單元測試以驗證設定檔解析與剪貼簿線程安全：
```bash
python tests/test_config.py
python tests/test_clipboard.py
```
