"""Serve the Inspector from a real embedded hub with mock devices.

    uv run python -m tests.inspector.serve --port 7431 --state /path/to/state.json

The state file names the URL and the tokens the browser tests use. Stop it with its PID.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import tempfile
from pathlib import Path

import uvicorn

from tests.inspector.harness import start, state


def write_state(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


async def main(port: int, state_path: Path, home: Path | None) -> None:
    folder = home or Path(tempfile.mkdtemp(prefix="openhal-inspector-"))
    harness = await start(folder)
    server = uvicorn.Server(uvicorn.Config(harness.app, host="127.0.0.1", port=port, log_level="warning"))
    await asyncio.to_thread(write_state, state_path, json.dumps(state(harness, port), indent=2))
    try:
        await server.serve()
    finally:
        await harness.hub.close()


def run() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=7431)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--home", type=Path, default=None)
    args = parser.parse_args()
    if args.port == 4000:
        parser.error("Port 4000 is reserved. Choose another port.")
    asyncio.run(main(args.port, args.state, args.home))


if __name__ == "__main__":
    run()
