"""The WebSocket transport. One JSON-RPC message per text frame (ADR 0015, Messages and transports).

The hub API (openhal/hub/api.py) checks the network and resolves the caller, then hands the socket
to `serve_rpc`. `serve_log` streams the Inspector's message log to a person.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect

from openhal.kernel.principals import Principal
from openhal.protocol.dispatch import Dispatcher
from openhal.protocol.session import Session

LOG_QUEUE_LIMIT = 2000


def encode(message: Any) -> str:
    """One message as a text frame. Values JSON can't hold are sent as text."""
    return json.dumps(message, default=str, separators=(",", ":"))


async def _pump(websocket: WebSocket, session: Session) -> None:
    while True:
        message = await session.next()
        await websocket.send_text(encode(message))


async def serve_rpc(
    websocket: WebSocket,
    dispatcher: Dispatcher,
    *,
    principal: Principal | None,
    token_rejected: bool,
    fallback: Principal | None,
) -> None:
    """Run one protocol connection until the client disconnects or sends hal/shutdown."""
    await websocket.accept()
    session = dispatcher.open(principal=principal, token_rejected=token_rejected, fallback=fallback)
    writer = asyncio.create_task(_pump(websocket, session))
    try:
        while not session.closed.is_set():
            frame = await websocket.receive()
            if frame["type"] == "websocket.disconnect":
                break
            data = frame.get("text")
            if data is None:
                data = frame.get("bytes") or b""
            await session.receive(data)
        if session.closed.is_set():
            await session.drain()
            for message in session.pending():
                await websocket.send_text(encode(message))
            await websocket.close()
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        session.close()
        writer.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await writer


async def serve_log(websocket: WebSocket, dispatcher: Dispatcher, since: int = 0) -> None:
    """Send the kept log entries after `since`, then every new entry as it happens."""
    await websocket.accept()
    queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=LOG_QUEUE_LIMIT)

    def push(entry: dict[str, Any]) -> None:
        with contextlib.suppress(asyncio.QueueFull):
            queue.put_nowait(entry)

    async def send() -> None:
        backlog = dispatcher.log.since(since)
        last = backlog[-1]["seq"] if backlog else since
        for entry in backlog:
            await websocket.send_text(encode(entry))
        while True:
            entry = await queue.get()
            if entry["seq"] > last:
                await websocket.send_text(encode(entry))

    unsubscribe = dispatcher.log.subscribe(push)
    sender = asyncio.create_task(send())
    try:
        while (await websocket.receive())["type"] != "websocket.disconnect":
            continue
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        unsubscribe()
        sender.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await sender
