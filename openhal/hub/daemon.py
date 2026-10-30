"""`openhald`, the hub daemon. Runs one Hub and serves the local API until stopped."""

from __future__ import annotations

import argparse
import asyncio
import logging
import signal
import socket

import uvicorn

from openhal._brand import DAEMON_NAME
from openhal.hub.api import create_app
from openhal.hub.config import HubConfig, load_config
from openhal.hub.hub import Hub
from openhal.hub.locks import DeviceLock, DeviceLocked

HUB_LOCK = "_openhald"
"""The lock a running daemon holds in the locks folder. Device ids can't start with an underscore."""


def claim(config: HubConfig) -> DeviceLock:
    """Make sure no other daemon runs on this config folder and the port is free, before anything is logged.

    A second daemon used to open the audit log and write hub_start and hub_stop before it found
    the port taken.
    """
    config.ensure_dirs()
    lock = DeviceLock(config.locks_dir, HUB_LOCK)
    try:
        lock.acquire()
    except DeviceLocked:
        raise SystemExit(
            f"Another {DAEMON_NAME} already runs with the config folder {config.home}. Stop it first, or use it."
        ) from None
    family = socket.AF_INET6 if ":" in config.api.host else socket.AF_INET
    with socket.socket(family, socket.SOCK_STREAM) as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind((config.api.host, config.api.port))
        except OSError as exc:
            lock.release()
            raise SystemExit(
                f"Port {config.api.port} on {config.api.host} is in use ({exc.strerror}). "
                "Stop what holds it, or set api.port in config.yaml."
            ) from None
    return lock


async def serve(host: str | None = None, port: int | None = None) -> None:
    config = load_config()
    if host:
        config.api.host = host
    if port:
        config.api.port = port
    if config.api.host not in ("127.0.0.1", "::1", "localhost") and not config.api.allow_lan:
        raise SystemExit("Listening on a non-loopback address needs api.allow_lan: true in config.yaml.")
    lock = claim(config)
    try:
        await _run(config)
    finally:
        lock.release()


async def _run(config: HubConfig) -> None:
    hub = Hub(config)
    await hub.start()
    app = create_app(hub)
    server = uvicorn.Server(
        uvicorn.Config(app, host=config.api.host, port=config.api.port, log_level="warning", lifespan="off")
    )
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda: setattr(server, "should_exit", True))
    try:
        await server.serve()
    finally:
        await hub.close()


def main() -> None:
    parser = argparse.ArgumentParser(prog=DAEMON_NAME, description="Run the OpenHAL hub.")
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.WARNING)
    asyncio.run(serve(args.host, args.port))


if __name__ == "__main__":
    main()
