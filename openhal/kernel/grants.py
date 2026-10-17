"""Single-use grants. The only way a driver may change hardware (ADR 0004).

A grant names one device, one target (a write channel, an action, or the safe-state hook) and
one exact value. The kernel issues it, the driver base class consumes it, and it can't be used
twice, after it expires, or for anything else. Grants are checked against the issuing book's
private table, so an object that merely looks like a grant is worthless.
"""

from __future__ import annotations

import hashlib
import json
import secrets
import time
from dataclasses import dataclass, field
from typing import Final

_GUARD: Final = object()
DEFAULT_TTL_S: Final = 5.0


class GrantError(PermissionError):
    """A driver was asked to act without a valid grant. Nothing was sent to the hardware."""


def value_digest(value: object) -> str:
    """A stable digest of a value or argument mapping, used to bind a grant to it."""
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"), default=repr)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class Grant:
    """Permission for exactly one hardware operation. Only a GrantBook can create one."""

    grant_id: str
    device_id: str
    target: str
    digest: str
    expires_at: float
    _guard: object = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        if self._guard is not _GUARD:
            raise GrantError("Grants can only be issued by the safety kernel.")


class GrantBook:
    """Issues and consumes grants. One book belongs to one kernel."""

    def __init__(self, *, ttl_s: float = DEFAULT_TTL_S) -> None:
        self._ttl_s = ttl_s
        self._live: dict[str, Grant] = {}

    def issue(self, device_id: str, target: str, value: object) -> Grant:
        """Create a grant for one operation."""
        self._expire()
        grant = Grant(
            grant_id=secrets.token_hex(16),
            device_id=device_id,
            target=target,
            digest=value_digest(value),
            expires_at=time.monotonic() + self._ttl_s,
            _guard=_GUARD,
        )
        self._live[grant.grant_id] = grant
        return grant

    def consume(self, grant: object, device_id: str, target: str, value: object) -> None:
        """Check a grant matches this exact operation and mark it used. Raises GrantError."""
        if not isinstance(grant, Grant):
            raise GrantError("No grant was given. Every hardware change must come from the safety kernel.")
        issued = self._live.pop(grant.grant_id, None)
        if issued is None or issued is not grant:
            raise GrantError("This grant was not issued by this kernel, or it was already used.")
        if time.monotonic() > issued.expires_at:
            raise GrantError("This grant has expired.")
        if issued.device_id != device_id or issued.target != target:
            raise GrantError(f"This grant is for {issued.device_id} {issued.target}, not {device_id} {target}.")
        if issued.digest != value_digest(value):
            raise GrantError("This grant is for a different value.")

    def revoke_all(self, device_id: str | None = None) -> None:
        """Drop live grants, for one device or all of them."""
        for grant_id, grant in list(self._live.items()):
            if device_id is None or grant.device_id == device_id:
                del self._live[grant_id]

    def live_count(self) -> int:
        self._expire()
        return len(self._live)

    def _expire(self) -> None:
        now = time.monotonic()
        for grant_id, grant in list(self._live.items()):
            if now > grant.expires_at:
                del self._live[grant_id]
