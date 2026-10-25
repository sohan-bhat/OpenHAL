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
    """Append-only audit log stored in SQLite. Use `:memory:` for tests.

    For a file-backed log, the latest sequence number and hash are also written to `<db>.head`
    after every append, so cutting entries off the end of the database is detectable by `verify()`
    (review finding F10). Publish that head somewhere else for stronger guarantees.

    Each append reads the previous hash from the database inside an immediate transaction, so a
    second process writing to the same file extends the one chain instead of forking it.
    """

    def __init__(self, path: str | Path = ":memory:") -> None:
        self._lock = threading.Lock()
        self._head_path = None if str(path) == ":memory:" else Path(f"{path}.head")
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
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                row = self._conn.execute("SELECT hash FROM audit ORDER BY seq DESC LIMIT 1").fetchone()
                prev = row[0] if row else GENESIS
                digest = _digest(prev, canonical)
                cursor = self._conn.execute(
                    "INSERT INTO audit (at, event, principal, device, target, status, code, body, prev_hash, hash)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (at, event, principal, device, target, status, code, canonical, prev, digest),
                )
                self._conn.execute("COMMIT")
            except BaseException:
                self._conn.execute("ROLLBACK")
                raise
            self._head = digest
            seq = int(cursor.lastrowid or 0)
            if self._head_path is not None:
                temporary = self._head_path.with_suffix(".tmp")
                temporary.write_text(f"{seq} {digest}\n", encoding="utf-8")
                temporary.replace(self._head_path)
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
        where = " AND ".join(clauses)
        sql = (
            "SELECT seq, at, event, principal, device, target, status, code, body, prev_hash, hash FROM audit"  # noqa: S608
            f" WHERE {where} ORDER BY seq DESC LIMIT ?"
        )
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        entries = []
        for row in rows:
            body = json.loads(row[8])
            entries.append(
                Entry(
                    row[0],
                    body.get("at", row[1]),
                    body.get("event", row[2]),
                    body.get("principal", row[3]),
                    body.get("device"),
                    body.get("target"),
                    body.get("status"),
                    body.get("code"),
                    body,
                    row[9],
                    row[10],
                )
            )
        return entries

    def _all(self) -> Iterator[tuple[Any, ...]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT seq, at, event, principal, device, target, status, code, body, prev_hash, hash FROM audit"
                " ORDER BY seq"
            ).fetchall()
        yield from rows

    def verify(self) -> tuple[bool, int | None]:
        """Recompute the chain and check every column against the hashed body.

        Returns (ok, first broken sequence number). A missing tail is reported at the sequence
        number the head file expected.
        """
        prev = GENESIS
        last_seq = 0
        for seq, at, event, principal, device, target, status, code, body, prev_hash, digest in self._all():
            if prev_hash != prev or _digest(prev, body) != digest:
                return False, seq
            parsed = json.loads(body)
            columns = {
                "at": at,
                "event": event,
                "principal": principal,
                "device": device,
                "target": target,
                "status": status,
                "code": code,
            }
            if any(parsed.get(name) != value for name, value in columns.items()):
                return False, seq
            prev = digest
            last_seq = seq
        if self._head_path is not None and self._head_path.exists():
            recorded = self._head_path.read_text(encoding="utf-8").split()
            if len(recorded) == 2 and (int(recorded[0]) != last_seq or recorded[1] != prev):
                return False, min(int(recorded[0]), last_seq + 1)
        return True, None

    @property
    def head(self) -> str:
        return self._head

    def close(self) -> None:
        with self._lock:
            self._conn.close()
