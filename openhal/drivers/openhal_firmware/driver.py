"""Driver for boards running the OpenHAL Arduino library (spec/FIRMWARE-PROTOCOL.md).

The board describes itself (`DESC`), checks its own limits, and falls to its safe state when the
hub's heartbeats stop. The driver keeps a heartbeat task running while connected, matches replies to
requests by sequence number, and keeps streamed `EVT` values as the latest readings.

Ports. `port: auto` picks the first serial port whose USB id belongs to a common Arduino or ESP32
board and answers `HELLO`. `port: sim:<name>` connects to the built-in simulator (tests and the
demo). Any other value is a serial device path or a pyserial URL.

Quirks. Many boards reset when the port opens (DTR), so the driver waits `boot_s` before the first
`HELLO`. Discovery only sends `HELLO`, which the protocol defines as read-only, and only to ports
with a known board USB id.
"""

from __future__ import annotations

import asyncio
import contextlib
import itertools
import threading
import time
from typing import Any, ClassVar, Final

from pydantic import BaseModel, ConfigDict, Field

from openhal.drivers.base import Discovered, Driver, DriverError, DriverInfo, Health, Reading
from openhal.drivers.openhal_firmware.protocol import (
    PROTOCOL_VERSION,
    Message,
    ProtocolError,
    decode,
    description_to_sections,
    encode,
    format_number,
    parse_description,
    parse_number,
)
from openhal.drivers.openhal_firmware.simulator import SimTransport, simulator_for

BOARD_USB_VENDORS: Final = {"2341", "2a03", "1a86", "10c4", "303a", "239a", "0403"}
"""Arduino, Arduino.org, WCH CH340, Silicon Labs CP210x, Espressif, Adafruit, FTDI."""


class FirmwareParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    port: str = "auto"
    baud: int = Field(default=115200, ge=1200, le=2_000_000)
    timeout_s: float = Field(default=1.0, gt=0, le=30)
    boot_s: float = Field(default=0.0, ge=0, le=10)
    board: str | None = None


class SerialLineTransport:
    """A pyserial port read by a background thread, with lines handed to asyncio."""

    def __init__(self, port: str, baud: int) -> None:
        self.port = port
        self.baud = baud
        self._serial: Any = None
        self._lines: asyncio.Queue[str] = asyncio.Queue()
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._stop = threading.Event()

    async def connect(self) -> None:
        try:
            import serial  # type: ignore[import-untyped,unused-ignore]
        except ImportError as exc:
            raise DriverError(
                "The openhal-firmware driver needs pyserial. Install openhal-hub[openhal-firmware]."
            ) from exc
        self._loop = asyncio.get_running_loop()
        try:
            self._serial = await asyncio.to_thread(
                serial.serial_for_url, self.port, baudrate=self.baud, timeout=0.2, exclusive=True
            )
        except (OSError, ValueError) as exc:
            raise DriverError(
                f"Could not open {self.port} ({exc}). Check the cable and that no other program has it."
            ) from exc
        self._stop.clear()
        self._thread = threading.Thread(target=self._reader, name=f"openhal-serial-{self.port}", daemon=True)
        self._thread.start()

    def _reader(self) -> None:
        buffer = b""
        while not self._stop.is_set():
            try:
                chunk = self._serial.read(256)
            except Exception:  # noqa: BLE001 (the port went away, the heartbeat will notice)
                return
            if not chunk:
                continue
            buffer += chunk
            while b"\n" in buffer:
                raw, buffer = buffer.split(b"\n", 1)
                text = raw.decode("ascii", errors="replace")
                if self._loop is not None:
                    self._loop.call_soon_threadsafe(self._lines.put_nowait, text)

    async def write_line(self, line: str) -> None:
        if self._serial is None:
            raise ConnectionError("The port is closed.")
        await asyncio.to_thread(self._serial.write, line.encode("ascii"))

    async def read_line(self) -> str:
        return await self._lines.get()

    async def close(self) -> None:
        self._stop.set()
        if self._serial is not None:
            with contextlib.suppress(Exception):
                await asyncio.to_thread(self._serial.close)
        self._serial = None


class _Link:
    """One open line to a board: sends requests, matches replies by sequence number, keeps events."""

    def __init__(self, transport: Any, timeout_s: float) -> None:
        self.transport = transport
        self.timeout_s = timeout_s
        self.events: dict[str, tuple[float, float]] = {}
        self.safe_reports: list[str] = []
        self._seq = itertools.cycle(range(1, 65536))
        self._pending: dict[int, asyncio.Future[Message]] = {}
        self._reader: asyncio.Task[None] | None = None

    async def open(self) -> None:
        await self.transport.connect()
        self._reader = asyncio.create_task(self._read_loop(), name="openhal-firmware-reader")

    async def _read_loop(self) -> None:
        while True:
            try:
                line = await self.transport.read_line()
            except ConnectionError:
                return
            try:
                message = decode(line)
            except ProtocolError:
                continue
            if message.seq == 0:
                self._unsolicited(message)
                continue
            future = self._pending.pop(message.seq, None)
            if future is not None and not future.done():
                future.set_result(message)

    def _unsolicited(self, message: Message) -> None:
        if message.verb == "EVT" and len(message.args) == 2:
            with contextlib.suppress(ProtocolError):
                self.events[message.args[0]] = (parse_number(message.args[1]), time.time())
        elif message.verb == "SAFE":
            self.safe_reports.append(" ".join(message.args))

    async def request(self, verb: str, *args: str) -> Message:
        seq = next(self._seq)
        future: asyncio.Future[Message] = asyncio.get_running_loop().create_future()
        self._pending[seq] = future
        try:
            await self.transport.write_line(encode(seq, verb, *args))
            reply = await asyncio.wait_for(future, self.timeout_s)
        except TimeoutError as exc:
            raise DriverError(f"The board didn't answer {verb} within {self.timeout_s:g} s.") from exc
        except ConnectionError as exc:
            raise DriverError(f"The board's port closed during {verb}.") from exc
        finally:
            self._pending.pop(seq, None)
        if reply.verb == "ERR":
            raise DriverError(f"The board refused {verb} ({' '.join(reply.args)}).")
        return reply

    async def hello(self) -> tuple[str, ...]:
        reply = await self.request("HELLO")
        if len(reply.args) < 4 or reply.args[0] != "openhal":
            raise DriverError("This board didn't answer like an OpenHAL board. Is the OpenHAL library flashed?")
        if not reply.args[1].isdigit() or int(reply.args[1]) > PROTOCOL_VERSION:
            raise DriverError(f"This board speaks protocol {reply.args[1]}, which this hub doesn't support yet.")
        return reply.args

    async def close(self) -> None:
        if self._reader is not None:
            self._reader.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._reader
            self._reader = None
        await self.transport.close()


class OpenHalFirmwareDriver(Driver):
    """Talks to a board running the OpenHAL Arduino library."""

    info: ClassVar[DriverInfo] = DriverInfo(
        name="openhal-firmware",
        protocols=("OpenHAL firmware protocol 1 over serial",),
        hazard_default="low",
        summary="Arduino and ESP32 boards running the OpenHAL library. They describe themselves.",
        safe_state_support="native",
    )
    params_model: ClassVar[type[Any] | None] = FirmwareParams

    def __init__(self, device: Any) -> None:
        super().__init__(device)
        self.settings = FirmwareParams.model_validate(self.params)
        self._link: _Link | None = None
        self._heartbeat: asyncio.Task[None] | None = None
        self._hello: tuple[str, ...] = ()
        self._description: dict[str, Any] | None = None
        self.connected = False

    def _make_transport(self) -> Any:
        port = self.settings.port
        if port.startswith("sim:"):
            return SimTransport(simulator_for(port.removeprefix("sim:") or "default"))
        if port == "auto":
            ports = _board_ports()
            if not ports:
                raise DriverError("No Arduino or ESP32 board was found. Plug it in, or set port to its device path.")
            port = ports[0][0]
        return SerialLineTransport(port, self.settings.baud)

    def _require_link(self) -> _Link:
        if self._link is None:
            raise DriverError("The board is not connected.")
        return self._link

    @property
    def safe_reports(self) -> list[str]:
        """Safe-state reports the board sent on its own, such as after a lost heartbeat."""
        return self._link.safe_reports if self._link is not None else []

    async def connect(self) -> None:
        await self.close()
        link = _Link(self._make_transport(), self.settings.timeout_s)
        await link.open()
        self._link = link
        if self.settings.boot_s:
            await asyncio.sleep(self.settings.boot_s)
        self._hello = await link.hello()
        self._description = None
        description = await self._describe_raw()
        self.connected = True
        timeout_ms = int(description.get("hb") or 0)
        if timeout_ms:
            interval = max(timeout_ms / 3000.0, 0.05)
            self._heartbeat = asyncio.create_task(self._heartbeat_loop(interval), name="openhal-firmware-heartbeat")

    async def _heartbeat_loop(self, interval: float) -> None:
        while True:
            await asyncio.sleep(interval)
            try:
                await self._require_link().request("HB")
            except DriverError:
                self.connected = False
                return

    @classmethod
    async def discover(cls) -> list[Discovered]:
        found = []
        for port, vidpid in _board_ports():
            link = _Link(SerialLineTransport(port, 115200), timeout_s=0.5)
            try:
                await link.open()
                hello = await link.hello()
            except DriverError:
                continue
            finally:
                await link.close()
            found.append(
                Discovered(
                    driver="openhal-firmware",
                    address=port,
                    identifiers={"usb": vidpid, "firmware.product": hello[2], "firmware.version": hello[3]},
                    label=f"OpenHAL board {hello[2]}",
                )
            )
        return found

    async def identify(self) -> dict[str, str]:
        if not self._hello:
            return {}
        return {"protocol": self._hello[1], "product": self._hello[2], "version": self._hello[3]}

    async def _describe_raw(self) -> dict[str, Any]:
        if self._description is None:
            reply = await self._require_link().request("DESC")
            try:
                self._description = parse_description(reply.args[0] if reply.args else "")
            except ProtocolError as exc:
                raise DriverError(f"The board's description is invalid ({exc}).") from exc
        return self._description

    async def describe(self) -> dict[str, Any] | None:
        description = await self._describe_raw()
        sections = description_to_sections(description)
        sections["device"] = {"name": description["p"].replace("-", " ").capitalize()}
        return sections

    async def read(self, channel: str) -> Reading:
        link = self._require_link()
        unit = self.device.channel_unit(channel)
        streamed = link.events.get(channel)
        if streamed is not None and time.time() - streamed[1] < 5.0:
            return Reading(channel, streamed[0], unit, at=streamed[1])
        reply = await link.request("READ", channel)
        if len(reply.args) != 2 or reply.args[0] != channel:
            raise DriverError(f"The board answered READ {channel} with {' '.join(reply.args)}.")
        try:
            value = parse_number(reply.args[1])
        except ProtocolError as exc:
            raise DriverError(f"The board sent an unreadable value for {channel}.") from exc
        return Reading(channel, value, unit)

    async def _write(self, channel: str, value: float | bool | str) -> Reading | None:
        if isinstance(value, str):
            raise DriverError("OpenHAL boards take numbers and booleans only.")
        reply = await self._require_link().request("WRITE", channel, format_number(float(value)))
        if len(reply.args) != 2 or reply.args[0] != channel:
            raise DriverError(f"The board answered WRITE {channel} with {' '.join(reply.args)}.")
        return Reading(channel, parse_number(reply.args[1]), self.device.channel_unit(channel))

    async def _safe_state(self) -> None:
        await self._require_link().request("SAFE")

    async def health(self) -> Health:
        if not self.connected or self._link is None:
            return Health(connected=False, detail="not connected")
        started = time.monotonic()
        try:
            await self._link.request("HB")
        except DriverError as exc:
            self.connected = False
            return Health(connected=False, detail=str(exc))
        return Health(connected=True, latency_ms=(time.monotonic() - started) * 1000)

    async def close(self) -> None:
        if self._heartbeat is not None:
            self._heartbeat.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._heartbeat
            self._heartbeat = None
        if self._link is not None:
            await self._link.close()
        self._link = None
        self.connected = False


def _board_ports() -> list[tuple[str, str]]:
    try:
        from serial.tools import list_ports  # type: ignore[import-untyped,unused-ignore]
    except ImportError:
        return []
    found = []
    for port in list_ports.comports():
        if port.vid is None or port.pid is None:
            continue
        vidpid = f"{port.vid:04x}:{port.pid:04x}"
        if vidpid.split(":")[0] in BOARD_USB_VENDORS:
            found.append((port.device, vidpid))
    return found
