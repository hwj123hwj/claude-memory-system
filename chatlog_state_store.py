from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


class ChatlogStateStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS processed_messages (
                  idempotency_key TEXT PRIMARY KEY,
                  talker TEXT NOT NULL,
                  message_time TEXT,
                  created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS checkpoints (
                  talker TEXT PRIMARY KEY,
                  last_processed_time TEXT,
                  last_processed_seq INTEGER,
                  updated_at TEXT NOT NULL
                )
                """
            )
            conn.commit()

    def is_processed(self, idempotency_key: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM processed_messages WHERE idempotency_key = ?",
                (idempotency_key,),
            ).fetchone()
            return row is not None

    def mark_processed(self, idempotency_key: str, talker: str, message_time: str | None) -> bool:
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT OR IGNORE INTO processed_messages
                  (idempotency_key, talker, message_time, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (idempotency_key, talker, message_time, _now_iso()),
            )
            conn.commit()
            return cur.rowcount > 0

    def load_checkpoint(self, talker: str) -> tuple[str | None, int | None]:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT last_processed_time, last_processed_seq
                FROM checkpoints
                WHERE talker = ?
                """,
                (talker,),
            ).fetchone()
            if row is None:
                return None, None
            return row["last_processed_time"], row["last_processed_seq"]

    def advance_checkpoint(self, talker: str, message_time: str | None, message_seq: int | None) -> None:
        current_time, current_seq = self.load_checkpoint(talker)

        should_update = False
        if current_time is None:
            should_update = True
        else:
            old_dt = _parse_iso(current_time)
            new_dt = _parse_iso(message_time)
            if new_dt and old_dt:
                if new_dt > old_dt:
                    should_update = True
                elif new_dt == old_dt:
                    old_seq = current_seq if current_seq is not None else -1
                    new_seq = message_seq if message_seq is not None else -1
                    should_update = new_seq > old_seq
            elif message_time and message_time > current_time:
                should_update = True

        if not should_update:
            return

        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO checkpoints (talker, last_processed_time, last_processed_seq, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(talker) DO UPDATE SET
                  last_processed_time = excluded.last_processed_time,
                  last_processed_seq = excluded.last_processed_seq,
                  updated_at = excluded.updated_at
                """,
                (talker, message_time, message_seq, _now_iso()),
            )
            conn.commit()
