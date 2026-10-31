"""One protocol connection. The principal, the lifecycle state and the outgoing queue.

A transport opens a session with `Dispatcher.open`, passes every received text to `receive`, and
sends whatever `next` yields until `closed` is set. Responses are never dropped. A client that falls
1,000 messages behind loses new notifications until its queue drains, and `dropped` counts them.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, Final, Literal

if TYPE_CHECKING:
    from openhal.kernel.principals import Principal
    from openhal.protocol.dispatch import Dispatcher

QUEUE_LIMIT: Final = 1000
CONCURRENCY: Final = 16

State = Literal["new", "initialized", "ready", "closed"]
"""new until initialize succeeds, ready after hal/initialized, closed after hal/shutdown."""


class Session:
    """One connection to one dispatcher."""

    def __init__(
        self,
        dispatcher: Dispatcher,
        *,
        principal: Principal | None = None,
        token_rejected: bool = False,
        fallback: Principal | None = None,
    ) -> None:
        self.dispatcher = dispatcher
        self.header_principal = principal
        self.token_rejected = token_rejected
        self.fallback = fallback
        self.principal: Principal | None = None
        self.client: str | None = None
        self.client_version: str | None = None
        self.protocol_version: str | None = None
        self.state: State = "new"
        self.dropped = 0
        self.closed = asyncio.Event()
        self._loop = asyncio.get_running_loop()
        self._queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._tasks: set[asyncio.Task[None]] = set()
        self._limit = asyncio.Semaphore(CONCURRENCY)

    @property
    def label(self) -> str | None:
        return self.principal.label if self.principal is not None else None

    def send(self, message: dict[str, Any]) -> None:
        """Queue a message for the transport and log it as sent."""
        self.dispatcher.log.record("out", self.client, self.label, message)
        self._queue.put_nowait(message)

    def notify(self, message: dict[str, Any]) -> None:
        """Queue a notification, only once the client sent hal/initialized."""
        if self.state != "ready":
            return
        if self._queue.qsize() >= QUEUE_LIMIT:
            self.dropped += 1
            return
        self.send(message)

    def notify_threadsafe(self, message: dict[str, Any]) -> None:
        """Queue a notification from any thread."""
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        if running is self._loop:
            self.notify(message)
        elif not self._loop.is_closed():
            self._loop.call_soon_threadsafe(self.notify, message)

    async def next(self) -> dict[str, Any]:
        """The next message to send, blocking until there is one."""
        return await self._queue.get()

    def pending(self) -> list[dict[str, Any]]:
        """Every queued message, without blocking."""
        items = []
        while not self._queue.empty():
            items.append(self._queue.get_nowait())
        return items

    async def receive(self, text: str | bytes) -> None:
        """Handle one received frame or line.

        `hal/initialize` gets its response before the next frame is read, so a client may pipeline requests
        after it. Other requests run concurrently, and their responses may arrive in any order.
        """
        message = self.dispatcher.parse(self, text)
        if message is None:
            return
        if isinstance(message, dict) and message.get("method") == "hal/initialize":
            await self._answer(message)
            return
        task = asyncio.create_task(self._answer(message))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _answer(self, message: Any) -> None:
        async with self._limit:
            response = await self.dispatcher.handle(self, message)
        if response is not None and self.state != "closed":
            self.send(response)

    async def drain(self) -> None:
        """Await the requests that are still running."""
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)

    def close(self) -> None:
        """Stop notifications and leave the dispatcher. Requests already running still finish."""
        self.state = "closed"
        self.closed.set()
        self.dispatcher.sessions.discard(self)
