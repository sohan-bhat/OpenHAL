"""A real hub on a background thread, for the website's tested snippets and demo storyboard.

It loads the config folder at `home` exactly as `openhald` would and serves the local API on a free
loopback port, never port 4000. Devices come from that folder, so with the `openhal init` sample it
runs one simulated desk fan on the mock driver. Nothing here can reach hardware.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import socket
import threading
import time
from collections.abc import Iterator
from pathlib import Path

import httpx
import uvicorn

from openhal.hub.api import create_app
from openhal.hub.config import load_config
from openhal.hub.hub import Hub


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        port = int(sock.getsockname()[1])
    if port == 4000:
        return free_port()
    return port


class EmbeddedHub:
    def __init__(self, home: Path) -> None:
        self.home = home
        self.port = free_port()
        self.url = f"http://127.0.0.1:{self.port}"
        self.hub: Hub | None = None
        self.server: uvicorn.Server | None = None
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self._run, name="website-hub", daemon=True)
        self.error: BaseException | None = None

    def _run(self) -> None:
        asyncio.set_event_loop(self.loop)
        try:
            self.loop.run_until_complete(self._serve())
        except BaseException as exc:  # noqa: BLE001 (reported by start)
            self.error = exc

    async def _serve(self) -> None:
        config = load_config(self.home)
        config.api.port = self.port
        self.hub = Hub(config)
        await self.hub.start()
        self.server = uvicorn.Server(
            uvicorn.Config(create_app(self.hub), host="127.0.0.1", port=self.port, log_level="warning", lifespan="off")
        )
        try:
            await self.server.serve()
        finally:
            await self.hub.close()

    def start(self, timeout: float = 15.0) -> None:
        self.thread.start()
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.error is not None:
                raise RuntimeError("The embedded hub failed to start.") from self.error
            with contextlib.suppress(httpx.HTTPError):
                if httpx.get(f"{self.url}/v1/status", timeout=0.5).status_code in (200, 401):
                    return
            time.sleep(0.05)
        raise RuntimeError("The embedded hub did not answer in time.")

    def stop(self) -> None:
        if self.server is not None:
            self.server.should_exit = True
        self.thread.join(10)


@contextlib.contextmanager
def running_hub(home: Path) -> Iterator[EmbeddedHub]:
    """Run the hub for `home` and point OPENHAL_URL at it while the block runs."""
    hub = EmbeddedHub(home)
    hub.start()
    previous = os.environ.get("OPENHAL_URL")
    os.environ["OPENHAL_URL"] = hub.url
    try:
        yield hub
    finally:
        if previous is None:
            os.environ.pop("OPENHAL_URL", None)
        else:
            os.environ["OPENHAL_URL"] = previous
        hub.stop()
