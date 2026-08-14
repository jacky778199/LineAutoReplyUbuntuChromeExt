# LINE Windows 桌面版智慧自動回覆機器人

本專案使用 Python 開發，專為 LINE Windows 桌面版設計。採用 **未讀綠點視覺辨識 (OpenCV)** + **剪貼簿安全鎖 (Clipboard Lock)** + **白名單 FIFO 佇列** + **Vertex AI (主) / OpenAI (備) 雙 LLM 智慧回覆** 最佳化架構。

---

## 🌟 特色亮點

1. **綠點視覺自動比對**：自動掃描 LINE 左側視窗的未讀綠點標籤，自動點擊並處理新訊息。
2. **多好友獨立 Persona (客製 Prompt)**：在 `config.yaml` 中，可以針對不同的好友或群組設定不同的系統提示詞（例如特助語氣、技術顧問語氣）。
3. **雙大語言模型自動備援 (Failover)**：
   * **主模型**：Google Vertex AI / Gemini API (`gemini-2.0-flash-001`)
   * **備用模型**：OpenAI API (`gpt-4o-mini`)
   * 當 Vertex AI 超時或配額不足時，系統會自動流暢切換至 OpenAI 備用模型進行回覆。
4. **剪貼簿安全防護 (Thread Safety)**：採用 `threading.Lock()` 確保對話複製與訊息貼上發送不發生競爭與干擾。
5. **人模人樣防封禁**：內建防重複處理簽章與隨機延遲發送機制。

---

## 🛠️ 安裝與環境準備

### 1. 建立獨立虛擬環境與安裝套件
```powershell
# 建立虛擬環境
python -m venv .venv

# 啟動虛擬環境 (PowerShell)
.\.venv\Scripts\Activate.ps1

# 安裝所需套件
.venv\Scripts\pip.exe install -r requirements.txt
```

### 2. 設定 `config.yaml`
開啟 `config.yaml` 進行相關設定：
* **`llm`**：設定您的 GCP Project ID (Vertex AI) 與 OpenAI API Key。
* **`bot.my_name`**：設定您的 LINE 暱稱。
* **`bot.whitelist`**：填入允許自動回覆的好友或群組名稱白名單。
* **`bot.contact_prompts`**：設定特定對象的專屬對話風格（Persona）。

---

## 🚀 執行說明

### 1. 生成未讀綠點範本圖片 (初次使用)
```powershell
.venv\Scripts\python.exe main.py --generate-template
```
此命令會在 `assets/green_dot_template.png` 生成標準未讀綠點測試範本。您也可以從自己螢幕截取 LINE 實際的綠點標籤取代該圖片以提升辨識率。

### 2. 測試雙 LLM API 連線
```powershell
.venv\Scripts\python.exe main.py --test-llm
```

### 3. 以乾執行模式 (Dry-Run Mode) 測試辨識與生成（不實際發送訊息）
```powershell
.venv\Scripts\python.exe main.py --dry-run
```

### 4. 正式啟動自動回覆機器人
```powershell
.venv\Scripts\python.exe main.py
```

---

## 🧪 單元測試
執行測試驗證設定檔與剪貼簿線程安全：
```powershell
.venv\Scripts\python.exe tests/test_config.py
.venv\Scripts\python.exe tests/test_clipboard.py
```
