from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "bridge.db"


def load_env() -> None:
    load_dotenv(BASE_DIR / ".env")


@dataclass
class Settings:
    line_channel_secret: str
    line_channel_access_token: str
    public_base_url: str
    webhook_path: str
    port: int
    timezone: str
    ack_text: str
    gateway_base_url: str
    gateway_api_key: str
    gateway_model: str

    @property
    def webhook_url(self) -> str:
        base = self.public_base_url.rstrip("/")
        return f"{base}{self.webhook_path}"


def load_settings() -> Settings:
    load_env()
    return Settings(
        line_channel_secret=os.getenv("LINE_CHANNEL_SECRET", "").strip(),
        line_channel_access_token=os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "").strip(),
        public_base_url=os.getenv("LINE_PUBLIC_BASE_URL", "https://bowwow9.dpdns.org").strip(),
        webhook_path=os.getenv("LINE_WEBHOOK_PATH", "/line-gateway/webhook").strip() or "/line-gateway/webhook",
        port=int(os.getenv("LINE_BOT_PORT", "8766")),
        timezone=os.getenv("LINE_BOT_TIMEZONE", "Asia/Taipei").strip() or "Asia/Taipei",
        ack_text=os.getenv("LINE_ACK_TEXT", "收到，Jarvis 正在處理中 ✨").strip() or "收到，Jarvis 正在處理中 ✨",
        gateway_base_url=os.getenv("HERMES_GATEWAY_BASE_URL", "http://127.0.0.1:8642/v1").strip().rstrip("/"),
        gateway_api_key=os.getenv("HERMES_GATEWAY_API_KEY", "").strip(),
        gateway_model=os.getenv("HERMES_GATEWAY_MODEL", "hermes-agent").strip() or "hermes-agent",
    )


def ensure_directories() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
