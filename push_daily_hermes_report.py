#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import sqlite3
import subprocess
import sys
from pathlib import Path
from urllib import request

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "data" / "bridge.db"
ENV_PATH = BASE_DIR / ".env"
LINE_PUSH_URL = "https://api.line.me/v2/bot/message/push"


def load_env() -> None:
    if not ENV_PATH.exists():
        return
    for raw_line in ENV_PATH.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def run_insights() -> str:
    proc = subprocess.run(
        ["hermes", "insights", "--days", "1"],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or "hermes insights failed").strip())
    return proc.stdout


def extract(pattern: str, text: str, default: str = "?") -> str:
    m = re.search(pattern, text, re.MULTILINE)
    return m.group(1).strip() if m else default


def build_report(insights: str) -> str:
    period = extract(r"Period:\s*(.+)", insights)
    sessions = extract(r"Sessions:\s*([0-9,]+)", insights)
    messages = extract(r"Messages:\s*([0-9,]+)", insights)
    tool_calls = extract(r"Tool calls:\s*([0-9,]+)", insights)
    input_tokens = extract(r"Input tokens:\s*([0-9,]+)", insights)
    output_tokens = extract(r"Output tokens:\s*([0-9,]+)", insights)
    total_tokens = extract(r"Total tokens:\s*([0-9,]+)", insights)

    model_line = None
    lines = insights.splitlines()
    for i, line in enumerate(lines):
        if "🤖 Models Used" in line:
            for candidate in lines[i + 1 : i + 8]:
                if re.search(r"\bgpt-|claude|gemini|qwen|llama|deepseek", candidate, re.I):
                    model_line = re.sub(r"\s+", " ", candidate).strip()
                    break
            break
    if not model_line:
        model_line = "未知"

    tool_lines = []
    for i, line in enumerate(lines):
        if "🔧 Top Tools" in line:
            for candidate in lines[i + 1 : i + 10]:
                if re.match(r"\s*[A-Za-z_][A-Za-z0-9_\- ]+\s+[0-9,]+\s+[0-9.]+%", candidate):
                    tool_lines.append(re.sub(r"\s+", " ", candidate).strip())
            break
    top_tools = "；".join(tool_lines[:3]) if tool_lines else "無資料"

    return (
        "Hermes 今日 token 使用報告\n"
        f"日期區間：{period}\n"
        f"Sessions：{sessions}\n"
        f"Messages：{messages}\n"
        f"Tool calls：{tool_calls}\n"
        f"Input tokens：{input_tokens}\n"
        f"Output tokens：{output_tokens}\n"
        f"Total tokens：{total_tokens}\n"
        f"主要模型：{model_line}\n"
        f"最常用工具：{top_tools}"
    )


def pick_target_id() -> str:
    explicit = os.getenv("LINE_PUSH_DEFAULT_TO", "").strip()
    if explicit:
        return explicit
    if not DB_PATH.exists():
        raise RuntimeError(f"bridge db not found: {DB_PATH}")
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            """
            SELECT reply_target_id
            FROM sessions
            WHERE source_type = 'user'
            ORDER BY updated_at DESC
            LIMIT 1
            """
        ).fetchone()
    if not row or not row[0]:
        raise RuntimeError("no LINE user target found in bridge.db; set LINE_PUSH_DEFAULT_TO in .env")
    return str(row[0])


def chunk_text(text: str, limit: int = 4500) -> list[str]:
    text = text.strip() or "(空訊息)"
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    current = ""
    for paragraph in text.splitlines(True):
        if len(current) + len(paragraph) <= limit:
            current += paragraph
            continue
        if current:
            chunks.append(current.rstrip())
            current = ""
        while len(paragraph) > limit:
            chunks.append(paragraph[:limit])
            paragraph = paragraph[limit:]
        current = paragraph
    if current:
        chunks.append(current.rstrip())
    return chunks or [text[:limit]]


def push_text(to: str, text: str) -> None:
    token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "").strip()
    if not token:
        raise RuntimeError("LINE_CHANNEL_ACCESS_TOKEN is missing")
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    for start in range(0, len(chunk_text(text)), 5):
        batch = [{"type": "text", "text": chunk} for chunk in chunk_text(text)[start : start + 5]]
        body = json.dumps({"to": to, "messages": batch}).encode("utf-8")
        req = request.Request(LINE_PUSH_URL, data=body, headers=headers, method="POST")
        with request.urlopen(req, timeout=20) as resp:
            if resp.status >= 300:
                raise RuntimeError(f"LINE push failed with status {resp.status}")


def main() -> int:
    load_env()
    dry_run = "--dry-run" in sys.argv
    insights = run_insights()
    report = build_report(insights)
    target = pick_target_id()
    if dry_run:
        print(f"TARGET={target}")
        print(report)
        return 0
    push_text(target, report)
    print(f"pushed report to LINE target {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
