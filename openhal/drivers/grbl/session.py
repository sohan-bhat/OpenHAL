"""One open GRBL connection. Sends lines and realtime bytes and sorts out what comes back.

Line commands go out one at a time and are matched to `ok` and `error:N` in order. Status
reports, alarms, messages and the reset banner can arrive at any moment and are handled as
they come. Nothing here knows about device files.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections import deque
from dataclasses import dataclass, field

from openhal.drivers.base import DriverError
from openhal.drivers.grbl import protocol
from openhal.drivers.grbl.protocol import Status
from openhal.drivers.serial import mapping
from openhal.drivers.serial.link import Opener, SerialLink

RESET_WAIT_S = 3.0


class GrblError(DriverError):
    """GRBL answered a line with error:N."""

    def __init__(self, message: str, code: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass
class Pending:
    command: str
    future: asyncio.Future[list[str]]
    lines: list[str] = field(default_factory=list)


class GrblSession:
    """The line protocol over one serial link."""

    def __init__(self, opener: Opener, *, name: str, timeout: float) -> None:
        self.link = SerialLink(opener, name=name)
        self.name = name
        self.timeout = timeout
        self.version = ""
        self.alarm = 0
        self.critical = False
        self.message = ""
        self.last_status: Status | None = None
        self.status_at = 0.0
        self.wco: tuple[float, ...] | None = None
        self.lock = asyncio.Lock()
        self._inflight: deque[Pending] = deque()
        self._waiters: list[asyncio.Future[Status]] = []
        self._banner = asyncio.Event()
        self._pump: asyncio.Task[None] | None = None

    @property
    def inflight(self) -> int:
        return len(self._inflight)

    async def open(self, settle: float) -> None:
        """Open the port and wait up to `settle` for the banner most boards print after the reset on open."""
        self._banner = asyncio.Event()
        await self.link.open()
        self._pump = asyncio.create_task(self._read_forever())
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(self._banner.wait(), settle)

    def require(self) -> SerialLink:
        if not self.link.connected or self._pump is None or self._pump.done():
            raise DriverError(f"The controller on {self.name} is not connected. Reconnect it.")
        return self.link

    async def _read_forever(self) -> None:
        try:
            while True:
                try:
                    raw = await self.link.read_line(3600)
                except TimeoutError:
                    continue
                self.handle(raw[:1024].decode("ascii", errors="replace").strip())
        except DriverError as exc:
            lost = DriverError(f"The controller disconnected ({exc}). Check the USB cable, then reconnect.")
            self.fail_all(lost)
            self._fail_waiters(lost)

    def handle(self, line: str) -> None:
        """Route one line from the controller."""
        if not line:
            return
        head = self._inflight[0] if self._inflight else None
        if line == "ok" or line.startswith("error:"):
            if head is None:
                return
            self._inflight.popleft()
            if head.future.done():
                return
            if line == "ok":
                head.future.set_result(head.lines)
                return
            code = line[6:].strip()
            detail = protocol.error_text(int(code)) if code.isdigit() else code
            head.future.set_exception(GrblError(f"GRBL refused {head.command} with {line} ({detail}).", code))
            head.future.exception()
        elif line.startswith("<"):
            self._note_status(line)
        elif line.startswith("ALARM:"):
            code = line[6:].strip()
            self.alarm = int(code) if code.isdigit() else -1
            self.status_at = 0.0
            text = protocol.alarm_text(self.alarm)
            self.fail_all(DriverError(f"GRBL raised {line} ({text}). Clear it with clear_alarm or home."))
        elif protocol.BANNER.match(line):
            match = protocol.BANNER.match(line)
            assert match is not None
            self.version = match.group(1)
            self.critical = False
            self.status_at = 0.0
            self.wco = None
            self.fail_all(DriverError("The controller reset. Commands in flight were dropped."))
            self._banner.set()
        else:
            if line.startswith("[MSG:"):
                self.message = line[5:-1] if line.endswith("]") else line[5:]
                self.critical = self.critical or "reset to continue" in self.message.lower()
            if head is not None:
                head.lines.append(line)

    def _note_status(self, line: str) -> None:
        try:
            status = protocol.parse_status(line)
        except ValueError as exc:
            self._fail_waiters(DriverError(f"GRBL sent a status report the driver can't read ({exc})."))
            return
        if status.wco is not None:
            self.wco = status.wco
        if status.state != "alarm":
            self.alarm = 0
        self.last_status = status
        self.status_at = asyncio.get_running_loop().time()
        waiters, self._waiters = self._waiters, []
        for waiter in waiters:
            if not waiter.done():
                waiter.set_result(status)

    def _fail_waiters(self, error: DriverError) -> None:
        waiters, self._waiters = self._waiters, []
        for waiter in waiters:
            if not waiter.done():
                waiter.set_exception(error)
                waiter.exception()

    def fail_all(self, error: DriverError) -> None:
        while self._inflight:
            pending = self._inflight.popleft()
            if not pending.future.done():
                pending.future.set_exception(error)
                pending.future.exception()

    async def send(self, line: str) -> Pending:
        """Write one line and queue it for its answer. Hold `lock` around send and wait."""
        link = self.require()
        mapping.plain_text(line, "G-code")
        if self.critical:
            raise DriverError(
                f"GRBL is waiting for a reset after ALARM:{self.alarm} ({protocol.alarm_text(self.alarm)}). "
                "Run the reset action or stop first. Nothing was sent."
            )
        pending = Pending(line, asyncio.get_running_loop().create_future())
        self._inflight.append(pending)
        await link.write((line + "\n").encode("ascii"))
        return pending

    async def command(self, line: str, *, budget: float | None = None) -> list[str]:
        """Send one line and return the lines that came before its `ok`."""
        wait = budget or self.timeout
        async with self.lock:
            pending = await self.send(line)
            try:
                return await asyncio.wait_for(asyncio.shield(pending.future), wait)
            except TimeoutError:
                with contextlib.suppress(ValueError):
                    self._inflight.remove(pending)
                raise TimeoutError(
                    f"GRBL didn't answer {line} within {wait:g} s. Check the baud rate and that the controller is on."
                ) from None

    async def realtime(self, byte: bytes) -> None:
        await self.require().write(byte)

    async def status(self, max_age: float) -> Status:
        """A status report no older than `max_age` seconds."""
        loop = asyncio.get_running_loop()
        if self.last_status is not None and loop.time() - self.status_at <= max_age:
            self.require()
            return self.last_status
        waiter: asyncio.Future[Status] = loop.create_future()
        self._waiters.append(waiter)
        try:
            await self.realtime(protocol.STATUS_QUERY)
            return await asyncio.wait_for(asyncio.shield(waiter), self.timeout)
        except TimeoutError:
            raise TimeoutError(f"GRBL didn't answer a status query within {self.timeout:g} s.") from None
        finally:
            with contextlib.suppress(ValueError):
                self._waiters.remove(waiter)

    async def soft_reset(self) -> None:
        """Send Ctrl-X and wait for the banner that confirms it."""
        self._banner = asyncio.Event()
        await self.realtime(protocol.SOFT_RESET)
        try:
            await asyncio.wait_for(self._banner.wait(), RESET_WAIT_S)
        except TimeoutError:
            raise DriverError("GRBL didn't confirm the soft reset with its banner. Check the controller.") from None

    async def close(self) -> None:
        task, self._pump = self._pump, None
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        closed = DriverError("The connection was closed.")
        self.fail_all(closed)
        self._fail_waiters(closed)
        await self.link.close()
