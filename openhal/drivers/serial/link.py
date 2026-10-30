"""An asyncio byte and line link over a pyserial port.

The serial, marlin and firmata drivers share this link. pyserial is blocking, so a daemon
thread reads the port and hands bytes to the event loop, and writes run in a worker thread.
Anything that behaves like a pyserial port (`read`, `write`, `close`) can sit underneath, which
is how the simulators plug in without touching real hardware.

The link never retries on its own. A read or write after the port failed raises `DriverError`,
and `connected` turns false, so the driver's health check reports the loss.
"""

from __future__ import annotations

import asyncio
import contextlib
import threading
from collections.abc import Callable
from typing import Any, Protocol

from openhal.drivers.base import DriverError


class PortLike(Protocol):
    """The part of `serial.Serial` the link uses."""

    def read(self, size: int = 1) -> bytes: ...

    def write(self, data: bytes, /) -> int | None: ...

    def close(self) -> None: ...


Opener = Callable[[], PortLike]
"""Opens a port and returns it. Called once per connect."""

READ_POLL_S = 0.05
"""How long one blocking read waits before the reader thread checks whether it should stop."""


def pyserial_opener(port: str, baud: int, *, rtscts: bool = False, dsrdtr: bool = False) -> Opener:
    """An opener for a device path or a pyserial URL (socket://, rfc2217://, loop://).

    Ports are opened with `exclusive=True` where the platform supports it, so the link never
    shares a port another process holds.
    """

    def open_port() -> PortLike:
        import serial

        kwargs: dict[str, Any] = {"baudrate": baud, "timeout": READ_POLL_S, "rtscts": rtscts, "dsrdtr": dsrdtr}
        if "://" not in port:
            kwargs["exclusive"] = True
        try:
            opened: PortLike = serial.serial_for_url(port, **kwargs)
        except (serial.SerialException, OSError, ValueError) as exc:
            raise DriverError(
                f"Could not open {port} ({exc}). Check the cable, the port name and that no other program has it open."
            ) from exc
        return opened

    return open_port


class SerialLink:
    """One open port with an async reader. Use one consumer at a time."""

    def __init__(self, opener: Opener, *, name: str = "port") -> None:
        self._opener = opener
        self.name = name
        self._port: PortLike | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._buffer = bytearray()
        self._wake = asyncio.Event()
        self._error: BaseException | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._write_lock = asyncio.Lock()

    @property
    def connected(self) -> bool:
        return self._port is not None and self._error is None

    async def open(self) -> None:
        await self.close()
        self._loop = asyncio.get_running_loop()
        self._error = None
        self._buffer.clear()
        self._wake = asyncio.Event()
        self._stop = threading.Event()
        self._port = await asyncio.to_thread(self._opener)
        self._thread = threading.Thread(target=self._reader, name=f"openhal-serial-{self.name}", daemon=True)
        self._thread.start()

    def _reader(self) -> None:
        port, loop, stop = self._port, self._loop, self._stop
        assert port is not None
        assert loop is not None
        while not stop.is_set():
            try:
                waiting = getattr(port, "in_waiting", 0) or 1
                data = port.read(min(int(waiting), 4096))
            except Exception as exc:  # noqa: BLE001 (any port failure ends the link)
                if not stop.is_set():
                    self._post(loop, self._lost, exc)
                return
            if data:
                self._post(loop, self._feed, bytes(data))

    @staticmethod
    def _post(loop: asyncio.AbstractEventLoop, callback: Callable[..., None], *args: Any) -> None:
        with contextlib.suppress(RuntimeError):
            loop.call_soon_threadsafe(callback, *args)

    def _feed(self, data: bytes) -> None:
        self._buffer.extend(data)
        self._wake.set()

    def _lost(self, exc: BaseException) -> None:
        self._error = exc
        self._wake.set()

    def _check(self) -> None:
        if self._port is None:
            raise DriverError(f"{self.name} is not open. Connect the device first.")
        if self._error is not None:
            raise DriverError(f"{self.name} stopped sending data ({self._error}). Check the cable, then reconnect.")

    async def write(self, data: bytes) -> None:
        self._check()
        port = self._port
        assert port is not None
        async with self._write_lock:
            try:
                await asyncio.to_thread(port.write, data)
            except Exception as exc:
                self._error = exc
                raise DriverError(f"Writing to {self.name} failed ({exc}). Check the cable, then reconnect.") from exc

    def take_buffered(self) -> bytes:
        """Return and clear everything received so far."""
        data = bytes(self._buffer)
        self._buffer.clear()
        return data

    async def _wait(self, ready: Callable[[], int | None], within: float) -> int:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + within
        while True:
            found = ready()
            if found is not None:
                return found
            self._check()
            remaining = deadline - loop.time()
            if remaining <= 0:
                raise TimeoutError(f"{self.name} sent nothing within {within:g} s.")
            self._wake.clear()
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._wake.wait(), remaining)

    async def read_chunk(self, within: float) -> bytes:
        """Wait for at least one byte and return everything buffered."""
        await self._wait(lambda: len(self._buffer) if self._buffer else None, within)
        return self.take_buffered()

    async def read_line(self, within: float, terminator: bytes = b"\n") -> bytes:
        """Wait for one line and return it without the terminator."""

        def ready() -> int | None:
            index = self._buffer.find(terminator)
            return None if index < 0 else index

        index = await self._wait(ready, within)
        line = bytes(self._buffer[:index])
        del self._buffer[: index + len(terminator)]
        return line

    async def close(self) -> None:
        port, thread = self._port, self._thread
        self._port = None
        self._thread = None
        self._stop.set()
        if port is not None:
            with contextlib.suppress(Exception):
                await asyncio.to_thread(port.close)
        if thread is not None and thread is not threading.current_thread():
            await asyncio.to_thread(thread.join, 1.0)


def list_serial_ports() -> list[Any]:
    """The serial ports the OS reports. Listing never opens a port."""
    try:
        from serial.tools import list_ports
    except ImportError:
        return []
    try:
        return list(list_ports.comports())
    except OSError:
        return []


def usb_id(info: Any) -> str | None:
    vid, pid = getattr(info, "vid", None), getattr(info, "pid", None)
    if vid is None or pid is None:
        return None
    return f"{vid:04x}:{pid:04x}"


def port_identifiers(info: Any) -> dict[str, str]:
    """Identifiers for a listed port, for `Discovered.identifiers`."""
    found: dict[str, str] = {}
    usb = usb_id(info)
    if usb:
        found["usb"] = usb
    for key in ("serial_number", "manufacturer", "product", "description"):
        value = getattr(info, key, None)
        if value and value != "n/a":
            found[key] = str(value)
    return found


def resolve_port(port: str, usb: list[str], serial_number: str | None, *, driver: str) -> str:
    """Return `port`, or with `auto` the one listed port that matches the device file's `match`."""
    if port != "auto":
        return port
    if not usb:
        raise DriverError(
            f"port: auto needs match.usb in the device file so the {driver} driver can select your port. "
            "Add the USB vendor and product id, or give the port path."
        )
    import re

    wanted = {item.lower() for item in usb}
    candidates = []
    for info in list_serial_ports():
        if usb_id(info) not in wanted:
            continue
        number = getattr(info, "serial_number", None) or ""
        if serial_number and not re.search(serial_number, number):
            continue
        candidates.append(info.device)
    if not candidates:
        raise DriverError(
            f"No serial port matches USB id {', '.join(sorted(wanted))}. Plug the device in, "
            "or run openhal discover to see what is connected."
        )
    if len(candidates) > 1:
        raise DriverError(
            f"Several ports match ({', '.join(candidates)}). Add match.serial_number or give the port path."
        )
    return str(candidates[0])
