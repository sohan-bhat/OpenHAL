"""The message log the Inspector reads. The last 2,000 JSON-RPC messages, in and out, on every transport.

Tokens are never stored. `hal/initialize` params have `token` redacted, and any text shaped like an
OpenHAL token is replaced wherever it appears, including in messages that failed to parse. An image
reading keeps its description, and its base64 `data` is replaced with a short note.
"""

from __future__ import annotations

import contextlib
import copy
import re
import time
from collections import deque
from collections.abc import Callable
from typing import Any, Final, Literal

from openhal.hub.tokens import TOKEN_PREFIX

LOG_SIZE: Final = 2000
REDACTED: Final = "[redacted]"
NOT_KEPT: Final = "[base64 not kept]"
RAW_LIMIT: Final = 4096

_TOKEN_TEXT: Final = re.compile(re.escape(TOKEN_PREFIX) + r"[A-Za-z0-9_\-]+")
_IMAGE_KEYS: Final = frozenset({"mimeType", "bytes", "width", "height", "data"})

Direction = Literal["in", "out"]
Listener = Callable[[dict[str, Any]], None]


def _scrub(value: Any) -> Any:
    if isinstance(value, str):
        return _TOKEN_TEXT.sub(REDACTED, value)
    if isinstance(value, dict):
        if value.keys() == _IMAGE_KEYS:
            return {key: NOT_KEPT if key == "data" else _scrub(item) for key, item in value.items()}
        return {key: REDACTED if key == "token" else _scrub(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_scrub(item) for item in value]
    return value


def redact(message: Any) -> Any:
    """A copy of `message` that is safe to keep. Raw text is cut to 4 KiB."""
    if isinstance(message, str):
        return _scrub(message[:RAW_LIMIT])
    return _scrub(copy.deepcopy(message))


class MessageLog:
    """A ring buffer of recent messages with live listeners."""

    def __init__(self, size: int = LOG_SIZE) -> None:
        self._entries: deque[dict[str, Any]] = deque(maxlen=size)
        self._seq = 0
        self._listeners: list[Listener] = []

    @property
    def last_seq(self) -> int:
        return self._seq

    def record(self, direction: Direction, client: str | None, principal: str | None, message: Any) -> dict[str, Any]:
        """Keep one message and notify live listeners. Returns the stored entry."""
        self._seq += 1
        entry = {
            "seq": self._seq,
            "at": time.time(),
            "direction": direction,
            "client": _scrub(client),
            "principal": _scrub(principal),
            "message": redact(message),
        }
        self._entries.append(entry)
        for listener in list(self._listeners):
            with contextlib.suppress(Exception):
                listener(entry)
        return entry

    def since(self, seq: int = 0) -> list[dict[str, Any]]:
        """Every kept entry after `seq`, oldest first."""
        return [entry for entry in self._entries if entry["seq"] > seq]

    def subscribe(self, listener: Listener) -> Callable[[], None]:
        """Receive every new entry. Returns an unsubscribe function."""
        self._listeners.append(listener)

        def unsubscribe() -> None:
            with contextlib.suppress(ValueError):
                self._listeners.remove(listener)

        return unsubscribe
