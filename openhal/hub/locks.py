"""Exclusive per-device lock files, so a daemon and an embedded hub never open the same device."""

from __future__ import annotations

import fcntl
import os
from pathlib import Path
from typing import IO


class DeviceLocked(RuntimeError):  # noqa: N818
    """Another OpenHAL process already has this device open."""


class DeviceLock:
    def __init__(self, locks_dir: Path, device_id: str) -> None:
        self.path = locks_dir / f"{device_id}.lock"
        self._handle: IO[str] | None = None

    def acquire(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = self.path.open("a+", encoding="utf-8")
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            handle.close()
            raise DeviceLocked(
                f"Another OpenHAL process has {self.path.stem} open. Stop it, or use the running daemon."
            ) from exc
        handle.seek(0)
        handle.truncate()
        handle.write(str(os.getpid()))
        handle.flush()
        self._handle = handle

    def release(self) -> None:
        if self._handle is not None:
            fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
            self._handle.close()
            self._handle = None
