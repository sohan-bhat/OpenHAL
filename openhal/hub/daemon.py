"""`openhald`, the hub daemon. Runs one Hub and serves the local API until stopped."""

from __future__ import annotations

import argparse
import asyncio
import logging
import signal

import uvicorn

from openhal._brand import DAEMON_NAME
from openhal.hub.api import create_app
from openhal.hub.config import load_config
from openhal.hub.hub import Hub


async def serve(host: str | None = None, port: int | None = None) -> None:
    config = load_config()
    if host:
        config.api.host = host
    if port:
        config.api.port = port
    if config.api.host not in ("127.0.0.1", "::1", "localhost") and not config.api.allow_lan:
        raise SystemExit("Refusing to listen on a non-loopback address. Set api.allow_lan: true in config.yaml first.")
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
