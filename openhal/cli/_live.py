"""Asking a running OpenHAL to load a device file, so a confirmed file needs no restart.

The request goes only to a hub that serves this config folder. That is a hub holding the folder's
lock, which `openhal start` takes, or the hub that `--url` or `OPENHAL_URL` names. Any other hub on
the machine is left alone.
"""

from __future__ import annotations

import fcntl
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from openhal._brand import PRODUCT_NAME, START_COMMAND
from openhal.cli import _common
from openhal.client.settings import URL_ENV


@dataclass(frozen=True)
class Loaded:
    """What the running hub did with a file. `status` is added, reloaded, unchanged, not_running or failed."""

    status: str
    device_id: str
    writable: bool = False
    detail: str = ""

    @property
    def live(self) -> bool:
        return self.status in ("added", "reloaded", "unchanged")


def hub_runs_here() -> bool:
    """True when a hub serves this config folder, or the person named one with --url or OPENHAL_URL."""
    if _common.TRANSPORT is not None or _common.OPTIONS.url or os.environ.get(URL_ENV, "").strip():
        return True
    from openhal.hub.daemon import HUB_LOCK

    path = _common.config().locks_dir / f"{HUB_LOCK}.lock"
    try:
        handle = path.open("rb")
    except OSError:
        return False
    with handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_SH | fcntl.LOCK_NB)
        except OSError:
            return True
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    return False


def load(path: Path, device_id: str) -> Loaded:
    """Ask the running hub to load `path`. Never raises for a hub problem, the result says what happened."""
    from openhal.client import HubNotRunning, NotSupported, OpenHALError
    from openhal.client.calls import Call

    if not hub_runs_here():
        return Loaded("not_running", device_id)

    def parse(data: Any) -> dict[str, Any]:
        return dict(data)

    try:
        with _common.hub() as client:
            result = client.call(Call("POST", "/v1/device_files/load", parse, json={"path": str(path.resolve())}))
    except HubNotRunning:
        return Loaded("not_running", device_id)
    except NotSupported:
        return Loaded("failed", device_id, detail=f"This {PRODUCT_NAME} is older than the CLI.")
    except OpenHALError as exc:
        return Loaded("failed", device_id, detail=str(exc))
    return Loaded(str(result.get("status")), str(result.get("device_id", device_id)), bool(result.get("writable")))


def sentence(loaded: Loaded, *, writable: bool) -> str:
    """One sentence for the person about where the file stands in OpenHAL now."""
    device = loaded.device_id
    if loaded.live:
        return f"{device} is now writable." if loaded.writable else f"{device} is loaded read-only."
    state = "writable" if writable else "loaded read-only"
    if loaded.status == "not_running":
        return f"{device} is {state} once {PRODUCT_NAME} starts. Start {PRODUCT_NAME} with {START_COMMAND}."
    return (
        f"Loading {device} into the running {PRODUCT_NAME} failed. {loaded.detail} "
        f"{PRODUCT_NAME} loads the file when {PRODUCT_NAME} starts again."
    )
