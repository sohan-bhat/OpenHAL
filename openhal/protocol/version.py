"""Protocol versions and the negotiation rule (ADR 0015, Versions).

Versions are dates written `YYYY-MM-DD`, so they sort as text. The client sends the newest version
it supports. The hub answers with that version when it supports it, and otherwise with the newest
version it supports. A client that can't use the answer disconnects.
"""

from __future__ import annotations

import re
from typing import Final

PROTOCOL_VERSIONS: Final = ["2026-10-24"]
"""Every protocol version this hub speaks, oldest first."""

LATEST: Final = PROTOCOL_VERSIONS[-1]

_DATE: Final = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def is_version(text: str) -> bool:
    """True when `text` has the `YYYY-MM-DD` shape of a protocol version."""
    return bool(_DATE.match(text))


def negotiate(requested: str) -> str:
    """The version the hub answers with when a client asks for `requested`."""
    if requested in PROTOCOL_VERSIONS:
        return requested
    return LATEST
