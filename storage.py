from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterator, Optional


class Storage:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def init_db(self) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    chat_key TEXT PRIMARY KEY,
                    conversation_name TEXT NOT NULL,
                    reply_target_id TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    user_id TEXT,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS processed_events (
                    event_key TEXT PRIMARY KEY,
                    chat_key TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

    def upsert_session(
        self,
        *,
        chat_key: str,
        conversation_name: str,
        reply_target_id: str,
        source_type: str,
        source_id: str,
        user_id: Optional[str],
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO sessions (
                    chat_key, conversation_name, reply_target_id, source_type, source_id, user_id, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(chat_key) DO UPDATE SET
                    conversation_name = excluded.conversation_name,
                    reply_target_id = excluded.reply_target_id,
                    source_type = excluded.source_type,
                    source_id = excluded.source_id,
                    user_id = excluded.user_id,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (chat_key, conversation_name, reply_target_id, source_type, source_id, user_id),
            )

    def get_session(self, chat_key: str) -> Optional[Dict[str, Any]]:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM sessions WHERE chat_key = ?", (chat_key,)).fetchone()
            return dict(row) if row else None

    def record_event_if_new(self, *, event_key: str, chat_key: str) -> bool:
        with self.connect() as conn:
            cur = conn.execute(
                "INSERT OR IGNORE INTO processed_events (event_key, chat_key) VALUES (?, ?)",
                (event_key, chat_key),
            )
            return cur.rowcount > 0
