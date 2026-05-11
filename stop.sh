#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PID_FILE="$SCRIPT_DIR/.bot.pid"
PORT="${LINE_BOT_PORT:-8888}"

cd "$SCRIPT_DIR"

if [ ! -f "$PID_FILE" ]; then
  echo "找不到 .bot.pid，改抓 ${PORT} port 上的 uvicorn/Python..."
  PIDS=$(lsof -tiTCP:"$PORT" -sTCP:LISTEN -n -P 2>/dev/null || true)
  if [ -z "$PIDS" ]; then
    echo "LINE bot 沒有在執行"
    exit 0
  fi
  echo "$PIDS" | xargs kill
  echo "已停止：$PIDS"
  exit 0
fi

PID=$(cat "$PID_FILE" 2>/dev/null || true)
if [ -z "$PID" ]; then
  rm -f "$PID_FILE"
  echo ".bot.pid 是空的，已清掉"
  exit 0
fi

if kill -0 "$PID" 2>/dev/null; then
  kill "$PID"
  echo "已停止，PID=$PID"
else
  echo "PID=$PID 不存在，改抓 ${PORT} port 上的 uvicorn/Python..."
  PIDS=$(lsof -tiTCP:"$PORT" -sTCP:LISTEN -n -P 2>/dev/null || true)
  if [ -n "$PIDS" ]; then
    echo "$PIDS" | xargs kill
    echo "已停止：$PIDS"
  fi
fi

rm -f "$PID_FILE"
