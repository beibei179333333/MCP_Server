"""SQLite persistence: subscribers, their settings, and last-seen match state.

A single connection guarded by a lock keeps this safe to share between the
command thread and the polling thread without per-call connection churn.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from typing import Optional

_SCHEMA = """
CREATE TABLE IF NOT EXISTS subscribers (
    chat_id          TEXT PRIMARY KEY,
    lang             TEXT NOT NULL DEFAULT 'zh',
    notify_reminders INTEGER NOT NULL DEFAULT 1,
    notify_kickoff   INTEGER NOT NULL DEFAULT 1,
    notify_goals     INTEGER NOT NULL DEFAULT 1,
    notify_halftime  INTEGER NOT NULL DEFAULT 1,
    notify_fulltime  INTEGER NOT NULL DEFAULT 1,
    created_at       REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS match_state (
    match_id    TEXT PRIMARY KEY,
    status      TEXT,
    home_score  INTEGER,
    away_score  INTEGER,
    reminded    INTEGER NOT NULL DEFAULT 0,
    updated_at  REAL
);
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""

SETTING_FIELDS = (
    "notify_reminders",
    "notify_kickoff",
    "notify_goals",
    "notify_halftime",
    "notify_fulltime",
)


class Storage:
    def __init__(self, path: str, default_lang: str = "zh"):
        self.default_lang = default_lang
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.executescript(_SCHEMA)
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # ---- subscribers ----------------------------------------------------
    def add_subscriber(self, chat_id: str, lang: Optional[str] = None) -> bool:
        """Return True if newly added, False if already subscribed."""
        chat_id = str(chat_id)
        with self._lock:
            row = self._conn.execute(
                "SELECT 1 FROM subscribers WHERE chat_id=?", (chat_id,)
            ).fetchone()
            if row:
                return False
            self._conn.execute(
                "INSERT INTO subscribers (chat_id, lang, created_at) VALUES (?,?,?)",
                (chat_id, lang or self.default_lang, time.time()),
            )
            self._conn.commit()
            return True

    def remove_subscriber(self, chat_id: str) -> bool:
        chat_id = str(chat_id)
        with self._lock:
            cur = self._conn.execute(
                "DELETE FROM subscribers WHERE chat_id=?", (chat_id,)
            )
            self._conn.commit()
            return cur.rowcount > 0

    def is_subscribed(self, chat_id: str) -> bool:
        with self._lock:
            return self._conn.execute(
                "SELECT 1 FROM subscribers WHERE chat_id=?", (str(chat_id),)
            ).fetchone() is not None

    def get_subscriber(self, chat_id: str) -> Optional[dict]:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM subscribers WHERE chat_id=?", (str(chat_id),)
            ).fetchone()
            return dict(row) if row else None

    def all_subscribers(self) -> list[dict]:
        with self._lock:
            rows = self._conn.execute("SELECT * FROM subscribers").fetchall()
            return [dict(r) for r in rows]

    def set_lang(self, chat_id: str, lang: str) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE subscribers SET lang=? WHERE chat_id=?", (lang, str(chat_id))
            )
            self._conn.commit()

    def toggle_setting(self, chat_id: str, field: str) -> Optional[int]:
        if field not in SETTING_FIELDS:
            return None
        with self._lock:
            row = self._conn.execute(
                f"SELECT {field} FROM subscribers WHERE chat_id=?", (str(chat_id),)
            ).fetchone()
            if not row:
                return None
            new_val = 0 if row[field] else 1
            self._conn.execute(
                f"UPDATE subscribers SET {field}=? WHERE chat_id=?",
                (new_val, str(chat_id)),
            )
            self._conn.commit()
            return new_val

    # ---- match state ----------------------------------------------------
    def get_match_state(self, match_id: str) -> Optional[dict]:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM match_state WHERE match_id=?", (str(match_id),)
            ).fetchone()
            return dict(row) if row else None

    def upsert_match_state(
        self,
        match_id: str,
        status: str,
        home_score,
        away_score,
        reminded: Optional[int] = None,
    ) -> None:
        with self._lock:
            existing = self._conn.execute(
                "SELECT reminded FROM match_state WHERE match_id=?", (str(match_id),)
            ).fetchone()
            keep_reminded = existing["reminded"] if existing else 0
            self._conn.execute(
                "INSERT INTO match_state (match_id, status, home_score, away_score, reminded, updated_at) "
                "VALUES (?,?,?,?,?,?) "
                "ON CONFLICT(match_id) DO UPDATE SET "
                "status=excluded.status, home_score=excluded.home_score, "
                "away_score=excluded.away_score, reminded=excluded.reminded, "
                "updated_at=excluded.updated_at",
                (
                    str(match_id),
                    status,
                    home_score,
                    away_score,
                    keep_reminded if reminded is None else reminded,
                    time.time(),
                ),
            )
            self._conn.commit()

    def mark_reminded(self, match_id: str) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE match_state SET reminded=1 WHERE match_id=?", (str(match_id),)
            )
            self._conn.commit()

    # ---- meta key/value -------------------------------------------------
    def get_meta(self, key: str) -> Optional[str]:
        with self._lock:
            row = self._conn.execute(
                "SELECT value FROM meta WHERE key=?", (key,)
            ).fetchone()
            return row["value"] if row else None

    def set_meta(self, key: str, value: str) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO meta (key, value) VALUES (?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, value),
            )
            self._conn.commit()
