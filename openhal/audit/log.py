"""The append-only audit log with a hash chain (ADR 0010).

Every read request, write attempt, block, confirmation, stop and unlock is one entry. Each
entry's hash covers the previous entry's hash and its own canonical body, so editing or
removing an entry breaks the chain at that point. SQLite triggers refuse UPDATE and DELETE.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

GENESIS: Final = "0" * 64

_SCHEMA: Final = """
CREATE TABLE IF NOT EXISTS audit (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    at REAL NOT NULL,
    event TEXT NOT NULL,
    principal TEXT NOT NULL,
    device TEXT,
    target TEXT,
    status TEXT,
    code TEXT,
    body TEXT NOT NULL,
    prev_hash TEXT NOT NULL,
    hash TEXT NOT NULL
);
CREATE TRIGGER IF NOT EXISTS audit_no_update BEFORE UPDATE ON audit
BEGIN SELECT RAISE(ABORT, 'audit log is append-only'); END;
CREATE TRIGGER IF NOT EXISTS audit_no_delete BEFORE DELETE ON audit
BEGIN SELECT RAISE(ABORT, 'audit log is append-only'); END;
CREATE INDEX IF NOT EXISTS audit_device ON audit(device);
CREATE INDEX IF NOT EXISTS audit_status ON audit(status);
"""


@dataclass(frozen=True, slots=True)
class Entry:
    seq: int
    at: float
    event: str
    principal: str
    device: str | None
    target: str | None
    status: str | None
    code: str | None
    body: dict[str, Any]
    prev_hash: str
    hash: str


def _canonical(body: dict[str, Any]) -> str:
    return json.dumps(body, sort_keys=True, separators=(",", ":"), default=str)


def _digest(prev_hash: str, canonical_body: str) -> str:
    return hashlib.sha256(f"{prev_hash}{canonical_body}".encode()).hexdigest()


class AuditLog:
    """Append-only audit log stored in SQLite. Use `:memory:` for tests."""

    def __init__(self, path: str | Path = ":memory:") -> None:
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None)
        if str(path) != ":memory:":
            self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(_SCHEMA)
        row = self._conn.execute("SELECT hash FROM audit ORDER BY seq DESC LIMIT 1").fetchone()
        self._head = row[0] if row else GENESIS
        self._listeners: list[Any] = []

    def subscribe(self, callback: Any) -> None:
        """Call `callback(entry)` after every append, for live views. Errors in callbacks are ignored."""
        self._listeners.append(callback)

    def append(
        self,
        event: str,
        principal: str,
        *,
        device: str | None = None,
        target: str | None = None,
        status: str | None = None,
        code: str | None = None,
        **details: Any,
    ) -> Entry:
        """Add one entry and return it."""
        at = time.time()
        body = {
            "at": at,
            "event": event,
            "principal": principal,
            "device": device,
            "target": target,
            "status": status,
            "code": code,
            "details": details,
        }
        canonical = _canonical(body)
        with self._lock:
            prev = self._head
            digest = _digest(prev, canonical)
            cursor = self._conn.execute(
                "INSERT INTO audit (at, event, principal, device, target, status, code, body, prev_hash, hash)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (at, event, principal, device, target, status, code, canonical, prev, digest),
            )
            self._head = digest
            seq = int(cursor.lastrowid or 0)
        entry = Entry(seq, at, event, principal, device, target, status, code, body, prev, digest)
        for listener in list(self._listeners):
            try:
                listener(entry)
            except Exception:  # noqa: S112, BLE001 (a broken view must never stop logging)
                continue
        return entry

    def entries(
        self,
        *,
        device: str | None = None,
        status: str | None = None,
        event: str | None = None,
        since_seq: int = 0,
        limit: int = 200,
    ) -> list[Entry]:
        """Most recent entries first, filtered."""
        clauses = ["seq > ?"]
        params: list[Any] = [since_seq]
        for column, value in (("device", device), ("status", status), ("event", event)):
            if value is not None:
                clauses.append(f"{column} = ?")
                params.append(value)
        params.append(max(1, min(limit, 5000)))
        where = " AND ".join(clauses)  # only fixed column names, values are bound parameters
        sql = (
            "SELECT seq, at, event, principal, device, target, status, code, body, prev_hash, hash FROM audit"  # noqa: S608
            f" WHERE {where} ORDER BY seq DESC LIMIT ?"
        )
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        return [
            Entry(row[0], row[1], row[2], row[3], row[4], row[5], row[6], row[7], json.loads(row[8]), row[9], row[10])
            for row in rows
        ]

    def _all(self) -> Iterator[tuple[int, str, str, str]]:
        with self._lock:
            rows = self._conn.execute("SELECT seq, body, prev_hash, hash FROM audit ORDER BY seq").fetchall()
        yield from rows

    def verify(self) -> tuple[bool, int | None]:
        """Recompute the chain. Returns (ok, first broken sequence number)."""
        prev = GENESIS
        for seq, body, prev_hash, digest in self._all():
            if prev_hash != prev or _digest(prev, body) != digest:
                return False, seq
            prev = digest
        return True, None

    @property
    def head(self) -> str:
        return self._head

    def close(self) -> None:
        with self._lock:
            self._conn.close()
