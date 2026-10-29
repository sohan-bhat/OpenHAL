"""Protocol versions and the negotiation rule (ADR 0015, Versions, and ADR 0017).

Versions are numbers written `MAJOR.MINOR`, such as `0.1`, and compare as numbers, so 0.10 is newer
than 0.9. People see them with a leading v, as v0.1, and the spec's folder uses that form too. The
client sends the newest version it supports. The hub answers with that version when it supports it,
and otherwise with the newest version it supports. A client that can't use the answer disconnects.
"""

from __future__ import annotations

import re
from typing import Final

_NUMBER: Final = re.compile(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)")

PROTOCOL_VERSIONS: Final = ["0.1"]
"""Every protocol version this hub speaks, oldest first."""


def is_version(text: str) -> bool:
    """True when `text` has the `MAJOR.MINOR` shape of a protocol version, such as `0.1`."""
    return _NUMBER.fullmatch(text) is not None


def parts(version: str) -> tuple[int, int]:
    """The major and minor numbers of `version`, the order versions sort in."""
    found = _NUMBER.fullmatch(version)
    if found is None:
        raise ValueError(f"{version!r} is not a version number such as 0.1")
    return int(found[1]), int(found[2])


LATEST: Final = max(PROTOCOL_VERSIONS, key=parts)


def label(version: str) -> str:
    """The version as people see it, such as `v0.1`. The spec's folder and URL use this form."""
    return f"v{version}"


def supported() -> str:
    """Every version this hub speaks as a reason names them, such as `0.1` or `0.1 and 0.2`."""
    *rest, last = PROTOCOL_VERSIONS
    return f"{', '.join(rest)} and {last}" if rest else last


def negotiate(requested: str) -> str:
    """The version the hub answers with when a client asks for `requested`."""
    if requested in PROTOCOL_VERSIONS:
        return requested
    return LATEST
