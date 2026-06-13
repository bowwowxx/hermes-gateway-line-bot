# LINE Hermes Gateway Bot

把 [Hermes Agent](https://github.com/nousresearch/hermes-agent) 的 AI 能力接到 LINE 上，讓你在 LINE 聊天室裡跟 AI 對話。支援文字、圖片、檔案，跑在自有伺服器上，隱私完全掌握。

## 功能特色

- **文字對話** — 在 LINE 裡直接跟 Hermes Agent 聊天，支援多輪對話與記憶
- **圖片辨識** — 傳照片給 Bot，AI 會看圖並回應
- **檔案支援** — 上傳 PDF 等檔案，AI 可讀取內容
- **圖片回傳** — AI 回傳的圖片自動轉換成 LINE 貼圖送出
- **輸入中動畫** — 處理中時顯示 LINE 的 loading 動畫，免費不消耗額度
- **群組 / 1對1** — 同時支援私訊和群組聊天，每個聊天室獨立記憶
- **防重複訊息** — SQLite 記錄已處理事件，不會回傳兩次同樣的內容
- **自動斷字與分批** — 長回應自動分段，超過 5 則訊息自動 fallback 到 push mode

## 架構

```
LINE 使用者
    │
    ▼
LINE Webhook ──→ FastAPI (這個 Bot)
                      │
                      ▼
              Hermes Gateway API
              (v1/responses)
                      │
                      ▼
              Hermes Agent (LLM)
```

## 安裝

### 1. 準備環境

```bash
cd /path/to/hermes-gateway-line-bot
```

### 3. 建立 Python 虛擬環境

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 4. 設定 `.env`

複製並編輯 `.env` 檔案：

```env
# LINE 開發者中繼金鑰（Channel Secret）
LINE_CHANNEL_SECRET=你的channel_secret

# LINE 存取權杖（Channel Access Token）
LINE_CHANNEL_ACCESS_TOKEN=你的channel_access_token

# Bot 的公開網址（Webhook 會被呼叫的網址）
LINE_PUBLIC_BASE_URL=https://your-domain.org

# Webhook 路徑（可自訂）
LINE_WEBHOOK_PATH=/line-gateway/webhook

# 伺服器連接埠
LINE_BOT_PORT=8766

# 時區
LINE_BOT_TIMEZONE=Asia/Taipei

# Hermes Gateway API 位址
HERMES_GATEWAY_BASE_URL=http://127.0.0.1:6666/v1

# Hermes Gateway API Key（如果有設定）
HERMES_GATEWAY_API_KEY=

# 要使用的 model 名稱
HERMES_GATEWAY_MODEL=hermes-agent

# 本地檔案路徑 → 公開 URL 的對應（讓 AI 回傳的圖片能在 LINE 顯示）
LINE_FILE_LOCAL_ROOT=/path/to/your/outputs
LINE_FILE_PUBLIC_BASE=https://your-domain.org/files

# 接收到的圖片/檔案存放目錄
LINE_INCOMING_DIR=/path/to/hermes-gateway-line-bot/data/incoming
```

### 5. 設定 LINE 開發者控制台

1. 前往 [LINE Developers Console](https://developers.line.biz/console/)
2. 建立新的 Channel（Messaging Channel）
3. 取得 **Channel ID**、**Channel Secret**、**Channel Access Token**
4. 在 Webhook settings 開啟 **Use webhook URL**
5. 設定 Webhook URL 為 `https://your-domain.org/line-gateway/webhook`（對應 `.env` 中的設定）

### 4. 啟動

```bash
# 快速啟動（開發用，直接在前端執行）
./start.sh

# 正式啟動（背景執行，有 PID 管理）
./run.sh

# 停止
./stop.sh
```

## 回傳地端AI圖片辨視結果
  ![mole](https://github.com/bowwowxx/hermes-gateway-line-bot/blob/main/IMG_8598.png)  

## PDF內容讀取測試
  ![mole](https://github.com/bowwowxx/hermes-gateway-line-bot/blob/main/IMG_8599.png)  


## 目錄結構

```
hermes-gateway-line-bot/
├── app.py              # FastAPI 主程式，webhook 處理
├── config.py           # 設定載入（.env → Settings）
├── hermes_gateway_client.py  # Hermes Gateway API 客戶端
├── line_client.py      # LINE Messaging API 客戶端
├── media.py            # 圖片路徑轉換、訊息組裝
├── storage.py          # SQLite 資料庫（session / event 記錄）
├── requirements.txt    # Python 依賴
├── start.sh            # 開發模式啟動
├── run.sh              # 正式背景啟動
├── stop.sh             # 停止 Bot
├── .env                # 環境變數（不進 git）
├── data/
│   ├── bridge.db       # SQLite 資料庫
│   └── incoming/       # 接收的圖片/檔案
└── .venv/              # Python 虛擬環境
```

## 設定項目說明

| 環境變數 | 說明 | 預設值 |
|---------|------|--------|
| `LINE_CHANNEL_SECRET` | LINE Channel Secret | - |
| `LINE_CHANNEL_ACCESS_TOKEN` | LINE Channel Access Token | - |
| `LINE_PUBLIC_BASE_URL` | Bot 公開網址 | `https://XX.org` |
| `LINE_WEBHOOK_PATH` | Webhook 路徑 | `/line-gateway/webhook` |
| `LINE_BOT_PORT` | 監聽埠號 | `8766` |
| `LINE_BOT_TIMEZONE` | 時區 | `Asia/Taipei` |
| `HERMES_GATEWAY_BASE_URL` | Hermes Gateway 位址 | `http://127.0.0.1:6666/v1` |
| `HERMES_GATEWAY_API_KEY` | API Key | 空 |
| `HERMES_GATEWAY_MODEL` | Model 名稱 | `hermes-agent` |
| `LINE_FILE_LOCAL_ROOT` | 本地檔案根目錄 | 空 |
| `LINE_FILE_PUBLIC_BASE` | 檔案公開 URL base | 空 |
| `LINE_INCOMING_DIR` | 接收檔案存放目錄 | `data/incoming` |

## API

### Health Check

```
GET /health
```

回傳 Bot 運行狀態與設定摘要。

### Webhook

```
POST <LINE_PUBLIC_BASE_URL><LINE_WEBHOOK_PATH>
```

接收 LINE 事件。支援的事件類型：

- `message.text` — 文字訊息
- `message.image` — 圖片（自動下載並轉成提示給 AI）
- `message.file` — 檔案（自動下載並轉成提示給 AI）

## 運作方式

1. LINE 使用者傳訊息到 Bot
2. Webhook 收到事件，驗證 LINE signature
3. 檢查是否為重複事件（防呆）
4. 顯示「輸入中」動畫（僅 1對1）
5. 如果有圖片/檔案，先從 LINE API 下載到本地
6. 呼叫 Hermes Gateway API 取得 AI 回應
7. 將回傳文字中的本地路徑轉換為公開 URL
8. 透過 LINE Reply / Push API 送回結果

## 依賴

- Python 3.11+
- FastAPI
- uvicorn
- httpx
- python-dotenv

## License

MIT
