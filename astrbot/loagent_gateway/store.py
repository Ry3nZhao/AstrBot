"""The gateway's own SQLite file (``<data>/loagent_gateway/gateway.db``).

- ``outbox``: inbound events not yet acknowledged by the backend, oldest first.
  An event leaves only on a 2xx (delivered) or a permanent 4xx (moved to
  ``dead`` for inspection); everything else is retried, across restarts.
- ``sent``: the result of every send request id, for idempotent retries.

Calls are synchronous and short; the async callers run them in a thread.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS outbox (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL,
    body TEXT NOT NULL,
    created_ms INTEGER NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS dead (
    seq INTEGER PRIMARY KEY,
    event_id TEXT NOT NULL,
    body TEXT NOT NULL,
    reason TEXT NOT NULL,
    dead_ms INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS sent (
    request_id TEXT PRIMARY KEY,
    result TEXT NOT NULL,
    created_ms INTEGER NOT NULL
);
"""


def now_ms() -> int:
    return int(time.time() * 1000)


class GatewayStore:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        if str(path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(path), check_same_thread=False)
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.executescript(_SCHEMA)
        self._lock = threading.Lock()

    def close(self) -> None:
        with self._lock:
            self._db.close()

    # --- outbox ---------------------------------------------------------

    def enqueue(self, event_id: str, body: dict) -> None:
        with self._lock, self._db:
            self._db.execute(
                "INSERT INTO outbox (event_id, body, created_ms) VALUES (?, ?, ?)",
                (event_id, json.dumps(body, ensure_ascii=False), now_ms()),
            )

    def peek(self, limit: int) -> list[tuple[int, dict]]:
        with self._lock:
            rows = self._db.execute(
                "SELECT seq, body FROM outbox ORDER BY seq LIMIT ?", (limit,)
            ).fetchall()
        return [(seq, json.loads(body)) for seq, body in rows]

    def ack(self, seqs: list[int]) -> None:
        if not seqs:
            return
        with self._lock, self._db:
            self._db.executemany(
                "DELETE FROM outbox WHERE seq = ?", [(s,) for s in seqs]
            )

    def bury(self, seqs: list[int], reason: str) -> None:
        if not seqs:
            return
        with self._lock, self._db:
            for seq in seqs:
                self._db.execute(
                    "INSERT OR REPLACE INTO dead (seq, event_id, body, reason, dead_ms) "
                    "SELECT seq, event_id, body, ?, ? FROM outbox WHERE seq = ?",
                    (reason, now_ms(), seq),
                )
                self._db.execute("DELETE FROM outbox WHERE seq = ?", (seq,))

    def note_attempt(self, seqs: list[int]) -> None:
        with self._lock, self._db:
            self._db.executemany(
                "UPDATE outbox SET attempts = attempts + 1 WHERE seq = ?",
                [(s,) for s in seqs],
            )

    def pending(self) -> int:
        with self._lock:
            return self._db.execute("SELECT COUNT(*) FROM outbox").fetchone()[0]

    def dead_count(self) -> int:
        with self._lock:
            return self._db.execute("SELECT COUNT(*) FROM dead").fetchone()[0]

    # --- send ledger ----------------------------------------------------

    def sent_result(self, request_id: str) -> dict | None:
        with self._lock:
            row = self._db.execute(
                "SELECT result FROM sent WHERE request_id = ?", (request_id,)
            ).fetchone()
        return json.loads(row[0]) if row else None

    def record_sent(self, request_id: str, result: dict) -> None:
        with self._lock, self._db:
            self._db.execute(
                "INSERT OR REPLACE INTO sent (request_id, result, created_ms) VALUES (?, ?, ?)",
                (request_id, json.dumps(result, ensure_ascii=False), now_ms()),
            )

    def prune_sent(self, max_age_days: float) -> int:
        cutoff = now_ms() - int(max_age_days * 86_400_000)
        with self._lock, self._db:
            return self._db.execute(
                "DELETE FROM sent WHERE created_ms < ?", (cutoff,)
            ).rowcount
