"""`openhal rpc`, the protocol's stdio transport (ADR 0015).

It bridges JSON-RPC lines on stdin and stdout to the hub's `/rpc` WebSocket. The token comes from
`--token-file` or `OPENHAL_TOKEN`, never from the human token file. Without one the client puts its
token in `hal/initialize` params.
"""

from __future__ import annotations

import asyncio
import os
import sys
import threading
from pathlib import Path

import typer

from openhal.cli._common import EXIT_NO_HUB, EXIT_TOKEN, OPTIONS, fail


def _stdin_reader(loop: asyncio.AbstractEventLoop, queue: asyncio.Queue[bytes]) -> None:
    """Read stdin on a daemon thread, so a blocked read never keeps the process alive."""
    for line in iter(sys.stdin.buffer.readline, b""):
        loop.call_soon_threadsafe(queue.put_nowait, line)
    loop.call_soon_threadsafe(queue.put_nowait, b"")


def _write_line(text: str) -> None:
    sys.stdout.write(text + "\n")
    sys.stdout.flush()


async def _run(url: str, token: str | None) -> None:
    from openhal.protocol.stdio import bridge

    queue: asyncio.Queue[bytes] = asyncio.Queue()
    thread = threading.Thread(target=_stdin_reader, args=(asyncio.get_running_loop(), queue), daemon=True)
    thread.start()
    await bridge(url, token, queue.get, _write_line)


def register(app: typer.Typer) -> None:
    @app.command()
    def rpc(
        token_file: Path = typer.Option(None, "--token-file", help="A file holding the token to send."),  # noqa: B008
    ) -> None:
        """Serve the hub protocol on stdio, one JSON-RPC message per line."""
        from openhal.client.settings import TOKEN_ENV, read_token_file, resolve_url
        from openhal.protocol.stdio import rpc_url

        token = None
        path = token_file or OPTIONS.token_file
        if path is not None:
            token = read_token_file(path.expanduser())
            if token is None:
                fail(f"The token file {path} is missing or empty.", EXIT_TOKEN)
        else:
            token = os.environ.get(TOKEN_ENV, "").strip() or None
        url = rpc_url(resolve_url(OPTIONS.url))
        try:
            asyncio.run(_run(url, token))
        except OSError as exc:
            fail(f"The hub is not running at {url} ({exc}). Start the hub with openhald.", EXIT_NO_HUB)
        except KeyboardInterrupt:
            raise typer.Exit(0) from None
        except Exception as exc:  # noqa: BLE001
            fail(f"The connection to {url} failed ({type(exc).__name__}: {exc}).", EXIT_NO_HUB)
