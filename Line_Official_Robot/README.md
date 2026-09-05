# LINE Official Robot 測試工具模組 (`AutoReply`)

本模組為專門配合 **Android LINE 自動回覆機器人 (`main_android.py`)** 設計的官方帳號（LINE Official Account / Messaging API）測試工具集。  
透過此工具，官方帳號 `AutoReply` 可以主動推播訊息給您的 LINE 帳號，模擬真實對話場景以測試自動回覆、記憶更新及 Prompt 提示詞反應。

---

## 快速導覽與執行方式

因執行指令時的「當前目錄」不同，Python 與虛擬環境的路徑會有所差異，請參考下方對照表：

### 情況 A：在專案根目錄 (`AutoReplyMessage/`) 執行【推薦】
```bash
# 1. 互動式即打即送模式 (隨打隨推播)
.venv/bin/python Line_Official_Robot/send_message.py -i

# 2. 發送單則指定訊息
.venv/bin/python Line_Official_Robot/send_message.py -m "你好 AutoReply！"

# 3. 檢查官方機器人連線與名稱
.venv/bin/python Line_Official_Robot/send_message.py --info

# 4. 每隔 15 秒隨機發送一則模擬測試訊息 (共 5 次)
.venv/bin/python Line_Official_Robot/send_message.py --auto 15 --count 5
```

### 情況 B：在模組目錄 (`AutoReplyMessage/Line_Official_Robot/`) 執行
如果你已經 `cd Line_Official_Robot` 進入此目錄：
```bash
# 1. 互動式即打即送模式 (隨打隨推播)
../.venv/bin/python send_message.py -i

# 2. 發送單則指定訊息
../.venv/bin/python send_message.py -m "你好 AutoReply！"

# 3. 檢查官方機器人連線與名稱
../.venv/bin/python send_message.py --info

# 4. 每隔 15 秒隨機發送一則模擬測試訊息
../.venv/bin/python send_message.py --auto 15 --count 5
```

> 💡 **如果在終端啟用了虛擬環境** (`source .venv/bin/activate` 或 `source ../.venv/bin/activate`)，可直接將前綴簡化為 `python send_message.py ...`。

---

## 模組檔案架構

```text
Line_Official_Robot/
├── __init__.py           # Python 套件初始化宣告
├── robot_client.py       # LINE Messaging API v3 Client 底層封裝 (自動載入 .env)
├── send_message.py       # 主測試推播 CLI 工具 (支援單發、互動式隨打隨送、自動模擬)
├── webhook_server.py     # Webhook 伺服器 (支援接收 Android Bot 的回覆訊息並印出或 Echo)
└── README.md             # 本說明文件
```

---

## 環境變數設定 (`.env`)

本模組會自動在目前目錄或專案根目錄尋找 `.env`，請確保包含以下金鑰：

```ini
# LINE Messaging API 憑證 (官方帳號: AutoReply)
LINE_CHANNEL_ACCESS_TOKEN="你的長期 Channel Access Token"
LINE_USER_ID="你的目標 LINE User ID (以 U 開頭的字串)"

# 選填 (若要使用 Webhook 接收或自動 Echo 回覆時才需要)
LINE_CHANNEL_SECRET="你的 Channel Secret"
```

> **如何查詢自己的 LINE User ID？**  
> 可在 LINE Developers Console 的 Basic Settings 頁面下方找到 `Your user ID`（例如 `U645e7f3d2ddf26bda322be963bea689a`）。

---

## 詳細指令說明

### 1. 互動式推播模式 (`-i` / `--interactive`)
進入互動命令行介面，每輸入一行文字按下 <kbd>Enter</kbd>，機器人便會立刻發送 Push 訊息到您的 LINE：

```bash
.venv/bin/python Line_Official_Robot/send_message.py -i
```
**終端範例畫面：**
```text
==================================================
 💬 進入互動式測試推播模式
 目標 User ID: U645e7f3d2ddf26bda322be963bea689a
 輸入訊息後按 Enter 即會推播至手機 LINE。
 輸入 'exit' 或 'quit' 或按 Ctrl+C 可離開。
==================================================

[輸入測試訊息] > 嗨，專案進度如何？
🚀 已推播: '嗨，專案進度如何？'

[輸入測試訊息] > 晚上要吃什麼？
🚀 已推播: '晚上要吃什麼？'

[輸入測試訊息] > exit
👋 離開互動模式。
```

---

### 2. 單則訊息發送 (`-m` / `--message`)
適合快速腳本呼叫或單次除錯：
```bash
.venv/bin/python Line_Official_Robot/send_message.py -m "測試自動回覆，收到請回覆 Over"
```
若需要臨時指定其他目標 User ID：
```bash
.venv/bin/python Line_Official_Robot/send_message.py -m "哈囉！" --user-id "Uxxxxxxxxxxxxxx"
```

---

### 3. 自動模擬真人傳訊模式 (`--auto`)
模擬真人傳訊的間隔節奏，程式會隨機挑選預設測試語句進行推播：
```bash
# 每隔 20 秒發送一則，共發送 3 次
.venv/bin/python Line_Official_Robot/send_message.py --auto 20 --count 3

# 每隔 10 秒無限發送 (按 Ctrl+C 中止)
.venv/bin/python Line_Official_Robot/send_message.py --auto 10
```

---

### 4. 檢查官方機器人狀態 (`--info`)
測試 Access Token 是否有效，並驗證官方機器人的名稱與基本資訊：
```bash
.venv/bin/python Line_Official_Robot/send_message.py --info
```
**輸出範例：**
```text
==================================================
 🤖 LINE Official Robot 資訊檢查
==================================================
  名稱 (Display Name): AutoReply
  Basic ID          : @@566smzus
  Bot User ID       : U61d167a82cf3cd1d95cd5217f3ea03d8
  聊天模式 (ChatMode): bot
  頭像連結 (Picture) : https://profile.line-scdn.net/...
==================================================
✅ 機器人 API Token 驗證成功！可正常連線。
```

---

### 5. （進階）Webhook 雙向對話測試 (`webhook_server.py`)
當 Android 端自動回覆了 `AutoReply` 後，若希望官方機器人端也能「聽」到回覆、並繼續回話形成「雙機自走循環聊天」：

```bash
# 啟動 Webhook 監聽並自動建立 ngrok 外部穿透網址
.venv/bin/python Line_Official_Robot/webhook_server.py --port 5000 --ngrok --echo
```
1. 啟動後將輸出的 ngrok 網址（例如 `https://xxxx.ngrok-free.app/callback`）填入 LINE Developers Console 的 **Webhook URL** 並開啟 **Use Webhook**。
2. Android Bot 回覆給官方帳號時，官方帳號將自動觸發 Webhook 並回應，實現兩台機器人全自動互相對話。

---

## 搭配 `main_android.py` 完整測試流程

1. **確認白名單**：開啟專案根目錄的 `config.yaml`，確認 `bot.whitelist` 中包含 `"AutoReply"`：
   ```yaml
   bot:
     whitelist:
       - "丁竑福"
       - "AutoReply"
       - "Eyeyupy"
     contact_prompts:
       "AutoReply": |
         看到他回的任何消息 想辦法延伸話題 簡短的回應一下代表有收到 句子最後加上"Over"表示結束
   ```

2. **終端機 1（運行 Android 自動回覆 Bot）**：
   ```bash
   cd /home/dinghonjay/AutoReplyMessage
   .venv/bin/python main_android.py
   ```

3. **終端機 2（啟動推播發訊測試）**：
   ```bash
   cd /home/dinghonjay/AutoReplyMessage
   .venv/bin/python Line_Official_Robot/send_message.py -i
   ```

4. 在終端機 2 輸入測試問句（例如：「`今天下班要不要一起吃飯？`」），手機上的 LINE 即可收到未讀紅點，終端機 1 的 `main_android.py` 將自動偵測、進入聊天室、透過 LLM 生成帶有 `Over` 的回覆並自動送出！

---

## 常見問題與排查 (Troubleshooting)

### Q1: 終端機出現 `exit code 127` 或 `No such file or directory`？
* **原因**：當前工作目錄（CWD）不正確。
* **解法**：
  * 若在 `AutoReplyMessage/` 根目錄，執行：`.venv/bin/python Line_Official_Robot/send_message.py -i`
  * 若在 `Line_Official_Robot/` 子目錄，執行：`../.venv/bin/python send_message.py -i`

### Q2: 收到 `LINE API 錯誤 (HTTP 401: Unauthorized)`？
* **原因**：`LINE_CHANNEL_ACCESS_TOKEN` 失效、過期，或在 `.env` 中有打錯字元。
* **解法**：至 LINE Developers Console 重新核發 (Issue) 長效型 Channel Access Token 並更新至 `.env`。

### Q3: 收到 `LINE API 錯誤 (HTTP 400: Failed to send push message)`？
* **原因**：`LINE_USER_ID` 不正確，或該 User ID 尚未加入該官方帳號為好友。
* **解法**：請用手機掃描官方帳號 QR Code 加為好友，並確認 `LINE_USER_ID` 為格式 `Uxxxxxxxx...` 的專屬識別碼。
