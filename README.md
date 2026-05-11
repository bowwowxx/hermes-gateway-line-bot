# LINE Hermes Gateway Bot

A standalone Python LINE webhook bot that talks to the running Hermes gateway API server instead of spawning `hermes chat` commands.

## What changed from the older bridge

- Old bridge: shell out to `hermes chat -q ...`
- This bot: call Hermes gateway API directly at `/v1/responses`
- Session continuity is kept by a stable `conversation` name derived from the LINE chat key

## Files

- `app.py` — FastAPI webhook app
- `config.py` — env/config loader
- `storage.py` — sqlite store for sessions + deduped webhook events
- `line_client.py` — LINE reply/push wrapper
- `hermes_gateway_client.py` — client for Hermes gateway API server
- `requirements.txt` — Python dependencies
- `start.sh` — bootstrap + run helper

## Environment

Copy `.env.example` to `.env` and fill in the values.

Important values:

- `LINE_CHANNEL_SECRET`
- `LINE_CHANNEL_ACCESS_TOKEN`
- `LINE_PUBLIC_BASE_URL`
- `LINE_WEBHOOK_PATH`
- `HERMES_GATEWAY_BASE_URL`
- `HERMES_GATEWAY_API_KEY`

## Run

```bash
cd /Users/bowwow/line-hermes-gateway-bot
cp .env.example .env
./start.sh
```

Default bind:

- `127.0.0.1:8888`

Recommended reverse proxy:

- `https://xx.xx.org/line-gateway/webhook` -> `127.0.0.1:8888/line-gateway/webhook`

## Health check

```bash
curl http://127.0.0.1:8888/health
```

## Hermes gateway requirement

This bot expects Hermes gateway API server to already be running locally, for example:

- `http://127.0.0.1:8888/v1`

It sends requests to:

- `POST /v1/responses`

with a stable `conversation` name like:

- `line:user:<userId>`
- `line:group:<groupId>`
- `line:room:<roomId>`
