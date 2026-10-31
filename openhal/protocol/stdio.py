"""The stdio transport. One JSON-RPC message per line, bridged to the hub's `/rpc` WebSocket.

`openhal rpc` runs `bridge` for clients that spawn a process instead of opening a socket. Each line
read is sent as one frame, and each frame received is written as one line. When input ends, the
bridge stays open until the responses to the requests already sent arrive, then closes. Nothing is
changed on the way, so the hub's dispatcher receives exactly what the client wrote.

The bridge sends a token as the Authorization header only when it was given one. It never reads
the human token file, so a spawned agent can't act as a person by accident. Without a token the
client sends its own in `hal/initialize` params.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from collections.abc import Awaitable, Callable
from typing import Any, Final

from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed

ReadLine = Callable[[], Awaitable[bytes]]
WriteLine = Callable[[str], None]

ANSWER_WAIT_S: Final = 30.0
MAX_MESSAGE_BYTES: Final = 4 * 1024 * 1024


def rpc_url(base: str) -> str:
    """The `/rpc` WebSocket address for a hub base URL such as http://127.0.0.1:7420."""
    url = base.rstrip("/")
    if url.startswith("https://"):
        url = "wss://" + url.removeprefix("https://")
    elif url.startswith("http://"):
        url = "ws://" + url.removeprefix("http://")
    elif not url.startswith(("ws://", "wss://")):
        url = "ws://" + url
    return url if url.endswith("/rpc") else url + "/rpc"


def expects_answer(line: bytes) -> bool:
    """True when the hub sends a response to this line. Only a well-formed notification gets no response."""
    try:
        message: Any = json.loads(line)
    except ValueError:
        return True
    if not isinstance(message, dict) or "id" in message:
        return True
    return not (message.get("jsonrpc") == "2.0" and isinstance(message.get("method"), str))


async def bridge(url: str, token: str | None, read_line: ReadLine, write_line: WriteLine) -> None:
    """Pump lines to frames and frames to lines until input ends and every response arrived."""
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    async with connect(url, additional_headers=headers, max_size=MAX_MESSAGE_BYTES) as socket:
        waiting = 0
        settled = asyncio.Event()
        settled.set()
        input_done = asyncio.Event()

        async def upstream() -> None:
            nonlocal waiting
            while True:
                line = await read_line()
                if not line:
                    input_done.set()
                    return
                line = line.strip()
                if not line:
                    continue
                if expects_answer(line):
                    waiting += 1
                    settled.clear()
                await socket.send(line.decode("utf-8", "replace"))

        async def downstream() -> None:
            nonlocal waiting
            async for frame in socket:
                text = frame if isinstance(frame, str) else frame.decode("utf-8", "replace")
                write_line(text)
                with contextlib.suppress(ValueError):
                    message = json.loads(text)
                    if isinstance(message, dict) and "id" in message and "method" not in message:
                        waiting = max(0, waiting - 1)
                        if waiting == 0:
                            settled.set()

        reader = asyncio.create_task(downstream())
        writer = asyncio.create_task(upstream())
        try:
            done, _ = await asyncio.wait({reader, writer}, return_when=asyncio.FIRST_COMPLETED)
            if writer in done and input_done.is_set():
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(settled.wait(), ANSWER_WAIT_S)
            for task in done:
                with contextlib.suppress(ConnectionClosed):
                    task.result()
        finally:
            for task in (reader, writer):
                task.cancel()
            for task in (reader, writer):
                with contextlib.suppress(asyncio.CancelledError, ConnectionClosed, Exception):
                    await task
