"""The audit log is append-only and its hash chain detects edits (threat T15)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from openhal.audit import AuditLog


def test_chain_verifies(tmp_path: Path) -> None:
    log = AuditLog(tmp_path / "hub.db")
    for index in range(5):
        log.append("write", "agent:a", device="fan", status="done", value=index)
    assert log.verify() == (True, None)
    assert len(log.entries()) == 5
    assert log.entries(limit=2)[0].body["details"]["value"] == 4


def test_update_and_delete_refused(tmp_path: Path) -> None:
    log = AuditLog(tmp_path / "hub.db")
    log.append("write", "agent:a")
    conn = sqlite3.connect(tmp_path / "hub.db")
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        conn.execute("UPDATE audit SET principal = 'human:x'")
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        conn.execute("DELETE FROM audit")


def test_tampering_breaks_the_chain(tmp_path: Path) -> None:
    path = tmp_path / "hub.db"
    log = AuditLog(path)
    for index in range(4):
        log.append("write", "agent:a", value=index)
    log.close()
    conn = sqlite3.connect(path)
    conn.execute("DROP TRIGGER audit_no_update")
    conn.execute("UPDATE audit SET body = replace(body, '\"value\":2', '\"value\":9') WHERE seq = 3")
    conn.commit()
    conn.close()
    assert AuditLog(path).verify() == (False, 3)


def test_reopen_continues_chain(tmp_path: Path) -> None:
    path = tmp_path / "hub.db"
    first = AuditLog(path)
    first.append("stop", "human:o")
    head = first.head
    first.close()
    second = AuditLog(path)
    assert second.head == head
    entry = second.append("unlock", "human:o")
    assert entry.prev_hash == head
    assert second.verify() == (True, None)


def test_filters_and_listeners() -> None:
    log = AuditLog()
    seen = []
    log.subscribe(seen.append)
    log.subscribe(lambda entry: 1 / 0)
    log.append("write", "agent:a", device="fan", status="blocked", code="above_max")
    log.append("write", "agent:a", device="lamp", status="done")
    assert [entry.device for entry in log.entries(status="blocked")] == ["fan"]
    assert [entry.device for entry in log.entries(device="lamp")] == ["lamp"]
    assert len(seen) == 2
