"""Client tokens and dashboard pairing (ADR 0012).

Tokens are random, shown once, and stored only as SHA-256 hashes. Each token has a kind (human
or agent) and a scope. The dashboard pairs by exchanging a short one-time code printed by the
CLI for a human session token.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from openhal.kernel.principals import Principal, Scope

TOKEN_PREFIX: Final = "ohal_"  # noqa: S105 (a prefix, not a secret)
PAIRING_TTL_S: Final = 300.0

_SCHEMA: Final = """
CREATE TABLE IF NOT EXISTS tokens (
    token_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('human', 'agent')),
    scope TEXT NOT NULL CHECK (scope IN ('read', 'control_low', 'control_medium')),
    hash TEXT NOT NULL UNIQUE,
    created_at REAL NOT NULL,
    revoked_at REAL
);
"""


@dataclass(frozen=True, slots=True)
class TokenInfo:
    token_id: str
    name: str
    kind: str
    scope: str
    created_at: float
    revoked: bool


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class TokenStore:
    """Tokens in the hub database. Plain tokens are returned once and never stored."""

    def __init__(self, path: str | Path = ":memory:") -> None:
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None)
        self._conn.executescript(_SCHEMA)
        self._pairing: dict[str, tuple[str, float]] = {}

    def create(self, name: str, kind: str, scope: Scope = "read") -> tuple[str, TokenInfo]:
        """Create a token. Returns the plain token, which is shown to the user once."""
        if kind not in ("human", "agent"):
            raise ValueError("kind must be human or agent.")
        if kind == "human":
            scope = "control_medium"
        token = TOKEN_PREFIX + secrets.token_urlsafe(32)
        token_id = secrets.token_hex(6)
        now = time.time()
        with self._lock:
            self._conn.execute(
                "INSERT INTO tokens (token_id, name, kind, scope, hash, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (token_id, name[:80], kind, scope, _hash(token), now),
            )
        return token, TokenInfo(token_id, name[:80], kind, scope, now, False)

    def principal(self, token: str | None) -> Principal | None:
        """The principal for a token, or None if it is unknown or revoked."""
        if not token or not token.startswith(TOKEN_PREFIX):
            return None
        digest = _hash(token)
        with self._lock:
            row = self._conn.execute(
                "SELECT name, kind, scope, hash FROM tokens WHERE hash = ? AND revoked_at IS NULL", (digest,)
            ).fetchone()
        if row is None or not hmac.compare_digest(row[3], digest):
            return None
        return Principal(row[1], row[0], row[2])

    def list(self) -> list[TokenInfo]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT token_id, name, kind, scope, created_at, revoked_at FROM tokens ORDER BY created_at"
            ).fetchall()
        return [TokenInfo(row[0], row[1], row[2], row[3], row[4], row[5] is not None) for row in rows]

    def revoke(self, token_id: str) -> bool:
        with self._lock:
            cursor = self._conn.execute(
                "UPDATE tokens SET revoked_at = ? WHERE token_id = ? AND revoked_at IS NULL", (time.time(), token_id)
            )
        return cursor.rowcount > 0

    def revoke_secret(self, token: str) -> bool:
        """Revoke a token by its secret, for a tool that holds the token but not its id."""
        with self._lock:
            cursor = self._conn.execute(
                "UPDATE tokens SET revoked_at = ? WHERE hash = ? AND revoked_at IS NULL", (time.time(), _hash(token))
            )
        return cursor.rowcount > 0

    def new_pairing_code(self) -> str:
        """A six-digit code the CLI prints and the dashboard exchanges for a human session."""
        self._expire_pairing()
        code = f"{secrets.randbelow(10**6):06d}"
        self._pairing[code] = ("dashboard", time.monotonic() + PAIRING_TTL_S)
        return code

    def exchange_pairing_code(self, code: str) -> str | None:
        """Turn a valid code into a human session token. Each code works once."""
        self._expire_pairing()
        entry = self._pairing.pop(code.strip(), None)
        if entry is None:
            return None
        token, _ = self.create(f"{entry[0]} session", "human")
        return token

    def _expire_pairing(self) -> None:
        now = time.monotonic()
        for code, (_, expires) in list(self._pairing.items()):
            if now > expires:
                del self._pairing[code]

    def close(self) -> None:
        with self._lock:
            self._conn.close()


def write_secret_file(path: Path, value: str) -> None:
    """Write a secret readable only by the current user."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch(mode=0o600, exist_ok=True)
    path.chmod(0o600)
    path.write_text(value + "\n", encoding="utf-8")


def read_secret_file(path: Path) -> str | None:
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8").strip() or None
