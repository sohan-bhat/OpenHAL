"""One TCP connection to an INDI server, with a live cache of every property it defines.

The server pushes definitions and updates on its own. A reader task feeds them into the cache,
and callers wait for conditions on the cache, such as a property being defined or leaving the
Busy state. Nothing here knows about device files.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from collections.abc import Callable
from xml.etree.ElementTree import Element

from openhal.drivers.base import DriverError
from openhal.drivers.indi import protocol
from openhal.drivers.indi.protocol import ProtocolError, Vector

READ_CHUNK = 65536


class IndiSession:
    """A client connection. `vectors` maps (device, property) to the latest Vector."""

    def __init__(self, host: str, port: int, *, timeout: float) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout
        self.vectors: dict[tuple[str, str], Vector] = {}
        self.messages: dict[str, str] = {}
        self.lost: str | None = None
        self.removed: set[str] = set()
        self.errors: list[str] = []
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._task: asyncio.Task[None] | None = None
        self._waiters: list[tuple[Callable[[], bool], asyncio.Future[None]]] = []

    async def open(self) -> None:
        try:
            reader, writer = await asyncio.wait_for(asyncio.open_connection(self.host, self.port), self.timeout)
        except (OSError, TimeoutError) as exc:
            raise DriverError(
                f"Could not reach the INDI server at {self.host}:{self.port} ({exc or 'timed out'}). "
                "Check that indiserver is running and the port is open."
            ) from exc
        self._reader, self._writer = reader, writer
        self.lost = None
        self._task = asyncio.create_task(self._read_forever(reader))

    @property
    def connected(self) -> bool:
        return self._writer is not None and self.lost is None and self._task is not None and not self._task.done()

    def require(self) -> None:
        if self.lost is not None:
            raise DriverError(f"The INDI server connection was lost ({self.lost}). Reconnect it.")
        if not self.connected:
            raise DriverError(f"The INDI server at {self.host}:{self.port} is not connected. Connect it first.")

    async def _read_forever(self, reader: asyncio.StreamReader) -> None:
        stream = protocol.Stream()
        try:
            while True:
                data = await reader.read(READ_CHUNK)
                if not data:
                    self.lost = "the server closed the connection"
                    break
                for element in stream.feed(data):
                    self._handle(element)
                self._wake()
        except ProtocolError as exc:
            self.lost = f"the server sent bad XML, {exc}"
        except (OSError, asyncio.IncompleteReadError) as exc:
            self.lost = f"the connection failed ({exc})"
        self._fail_waiters()
        if self._writer is not None:
            with contextlib.suppress(Exception):
                self._writer.close()

    def _handle(self, element: Element) -> None:
        tag = element.tag
        device = element.get("device") or ""
        if tag.startswith("def") and tag.endswith("Vector"):
            try:
                vector = protocol.vector_from(element)
            except ProtocolError as exc:
                self.errors.append(f"{element.get('name')}: {exc}")
                return
            vector.at = time.time()
            self.vectors[(vector.device, vector.name)] = vector
            self.removed.discard(vector.device)
        elif tag.startswith("set") and tag.endswith("Vector"):
            known = self.vectors.get((device, element.get("name") or ""))
            if known is None:
                return
            try:
                protocol.apply_update(known, element)
            except ProtocolError as exc:
                known.invalid = str(exc)
                return
            known.at = time.time()
            if known.message:
                self.messages[device] = known.message
        elif tag == "delProperty":
            name = element.get("name")
            if name:
                self.vectors.pop((device, name), None)
            else:
                for key in [key for key in self.vectors if key[0] == device]:
                    del self.vectors[key]
                self.removed.add(device)
        elif tag == "message" and element.get("message"):
            self.messages[device] = str(element.get("message"))[:300]

    def _wake(self) -> None:
        still: list[tuple[Callable[[], bool], asyncio.Future[None]]] = []
        for check, future in self._waiters:
            if future.done():
                continue
            if check():
                future.set_result(None)
            else:
                still.append((check, future))
        self._waiters = still

    def _fail_waiters(self) -> None:
        error = DriverError(f"The INDI server connection was lost ({self.lost}). Reconnect it.")
        for _, future in self._waiters:
            if not future.done():
                future.set_exception(error)
                future.exception()
        self._waiters = []

    async def wait_for(self, check: Callable[[], bool], within: float) -> bool:
        """Wait until `check()` holds. Returns False when `within` runs out first."""
        self.require()
        if check():
            return True
        future: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        self._waiters.append((check, future))
        try:
            await asyncio.wait_for(asyncio.shield(future), within)
        except TimeoutError:
            return False
        finally:
            if not future.done():
                future.cancel()
        return True

    async def send(self, data: bytes) -> None:
        self.require()
        assert self._writer is not None
        try:
            self._writer.write(data)
            await asyncio.wait_for(self._writer.drain(), self.timeout)
        except (OSError, TimeoutError) as exc:
            self.lost = f"sending failed ({exc})"
            raise DriverError(f"Sending to the INDI server failed ({exc}). Reconnect it.") from exc

    def vector(self, device: str, name: str) -> Vector:
        found = self.vectors.get((device, name))
        if found is None:
            devices = sorted({key[0] for key in self.vectors})
            if device not in devices:
                raise DriverError(f"The INDI server has no device {device!r}. It has {', '.join(devices) or 'none'}.")
            raise DriverError(f"{device} has no property {name}. Check the property name in the INDI control panel.")
        return found

    async def close(self) -> None:
        task, writer = self._task, self._writer
        self._task, self._writer, self._reader = None, None, None
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
        if writer is not None:
            with contextlib.suppress(Exception):
                writer.close()
                await asyncio.wait_for(writer.wait_closed(), 1.0)
        if self.lost is None:
            self.lost = "closed"
        self._fail_waiters()
