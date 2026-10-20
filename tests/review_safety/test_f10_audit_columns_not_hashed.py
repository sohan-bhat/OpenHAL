"""F10 (medium). `AuditLog.verify` does not cover the columns that `entries()` filters and returns.

The hash covers only the JSON body. The event, principal, device, target, status and code columns
are stored separately, are what `openhal log` filters on, and can be edited without breaking
the chain.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from openhal.audit.log import AuditLog


def test_f10_editing_status_column_is_detected(tmp_path: Path) -> None:
    path = tmp_path / "audit.db"
    log = AuditLog(path)
    log.append("write", "agent:claude", device="laser", target="write:power", status="blocked", code="interlock")
    log.append("write", "agent:claude", device="laser", target="write:power", status="done")
    log.close()

    conn = sqlite3.connect(path)
    conn.execute("DROP TRIGGER audit_no_update")
    conn.execute("UPDATE audit SET status = 'blocked', code = 'interlock', principal = 'human:owner' WHERE seq = 2")
    conn.commit()
    conn.close()

    reopened = AuditLog(path)
    ok, broken = reopened.verify()
    shown = reopened.entries(status="done")
    assert not ok, f"verify() passed although entry 2 now reads as blocked. done entries shown: {len(shown)}"
    assert broken == 2
