#!/bin/sh
set -eu

#啟動：
#cd /Users/bowwow/line-hermes-gateway-bot
#./run.sh

#停止：
#cd /Users/bowwow/line-hermes-gateway-bot
#./stop.sh

#手動：./start.sh

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PID_FILE="$SCRIPT_DIR/.bot.pid"
LOG_FILE="$SCRIPT_DIR/line-bot.log"
PORT="${LINE_BOT_PORT:-8766}"
START_CMD="uvicorn app:app --host 127.0.0.1 --port ${PORT}"

cd "$SCRIPT_DIR"

if [ -f "$PID_FILE" ]; then
  OLD_PID=$(cat "$PID_FILE" 2>/dev/null || true)
  if [ -n "$OLD_PID" ] && kill -0 "$OLD_PID" 2>/dev/null; then
    echo "LINE bot 已在執行中，PID=$OLD_PID"
    exit 0
  fi
  rm -f "$PID_FILE"
fi

EXISTING_PIDS=$(lsof -tiTCP:"$PORT" -sTCP:LISTEN -n -P 2>/dev/null || true)
if [ -n "$EXISTING_PIDS" ]; then
  echo "偵測到 ${PORT} port 已被占用，先停止舊的 LINE bot：$EXISTING_PIDS"
  echo "$EXISTING_PIDS" | xargs kill
fi

if [ ! -d .venv ]; then
  python3 -m venv .venv
fi

. .venv/bin/activate
pip install -r requirements.txt >/dev/null

nohup sh -c "$START_CMD" >> "$LOG_FILE" 2>&1 &
PID=$!

i=0
while [ "$i" -lt 20 ]; do
  if lsof -tiTCP:"$PORT" -sTCP:LISTEN -n -P >/dev/null 2>&1; then
    echo "$PID" > "$PID_FILE"
    echo "LINE bot 已啟動，PID=$PID"
    echo "log: $LOG_FILE"
    exit 0
  fi
  if ! kill -0 "$PID" 2>/dev/null; then
    echo "LINE bot 啟動失敗，請檢查 log: $LOG_FILE" >&2
    tail -n 20 "$LOG_FILE" >&2 || true
    exit 1
  fi
  sleep 1
  i=$((i + 1))
done

echo "LINE bot 啟動逾時，請檢查 log: $LOG_FILE" >&2
tail -n 20 "$LOG_FILE" >&2 || true
exit 1
