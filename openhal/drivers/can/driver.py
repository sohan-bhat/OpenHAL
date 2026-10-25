"""CAN bus driver. Signals decoded from frames as reads, frames as writes and actions, through python-can.

Protocol. Classic CAN (ISO 11898-1, 11-bit and 29-bit identifiers, up to 8 data bytes) and CAN FD
(up to 64 bytes), through any python-can interface (socketcan on Linux, PCAN, Kvaser, slcan, gs_usb
and others). CAN has no request and reply. Nodes broadcast frames, and every node sees every frame.

How channels map to frames.

- A read channel names a frame id and where its value sits in the data bytes (`byte`, `length`,
  `endian`, `signed`, optionally `bit` and `bits`), plus `scale`, `offset` and the device `unit`
  (`openhal.drivers.can.bits`). A background thread keeps the newest frame per id, and a read
  decodes the newest one, timestamped when it arrived. An id that hasn't been seen since
  connecting reads as no value, which the kernel treats as unknown.
- A write channel names the frame to send and where the value goes. `data` gives the bytes the
  rest of the frame carries. Write channels may share one frame. A write starts from the last
  payload sent with that id, so fields another channel set are kept. An optional `state` map
  names the status frame that shows the result, otherwise a read returns the last value sent.
- An action sends one frame. Its `data` is fixed, and `args` places each action argument in it.

Behavior worth knowing.

- Reads never send anything. The driver doesn't send remote frames.
- A sent frame proves only that the controller put it on the bus. Read the status frame to see
  what the node did. Frames are never queued or retried.
- Values are rounded to the field's raw step, and the reading returned by a write shows the
  value that was actually sent. A value the field can't hold raises DriverError and nothing is sent.
- CAN has no emergency behavior of its own, so the device file's safe state is sent like any
  other frame, which needs the bus and the node to be up. Nodes usually have their own timeout
  for missing command frames, which is the real fallback.
"""

from __future__ import annotations

import asyncio
import contextlib
import threading
import time
from collections.abc import Callable
from typing import Annotated, Any, ClassVar, Final

import can
from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, ValidationError, field_validator, model_validator

from openhal.drivers.base import Discovered, Driver, DriverError, DriverInfo, Health, Reading
from openhal.drivers.can import bits
from openhal.spec.models import DeviceFile
from openhal.spec.units import parse_duration

CLASSIC_PAYLOAD: Final = 8
FD_LENGTHS: Final = (0, 1, 2, 3, 4, 5, 6, 7, 8, 12, 16, 20, 24, 32, 48, 64)
MAX_STANDARD_ID: Final = 0x7FF
MAX_EXTENDED_ID: Final = 0x1FFFFFFF
DESCRIBE_LIMIT: Final = 64


def _seconds(value: Any) -> Any:
    if isinstance(value, int | float) and not isinstance(value, bool):
        return float(value)
    return parse_duration(value)


Duration = Annotated[float, BeforeValidator(_seconds), Field(gt=0, le=60)]
Byte = Annotated[int, Field(ge=0, le=255)]


class CanParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    channel: str = Field(min_length=1, max_length=64)
    interface: str = "socketcan"
    bitrate: int | None = Field(default=None, ge=5_000, le=1_000_000)
    fd: bool = False
    data_bitrate: int | None = Field(default=None, ge=5_000, le=12_000_000)
    timeout: Duration = 1.0

    @field_validator("interface")
    @classmethod
    def _known(cls, value: str) -> str:
        from can.interfaces import VALID_INTERFACES

        if value not in VALID_INTERFACES:
            known = ", ".join(sorted(VALID_INTERFACES))
            raise ValueError(f"Unknown python-can interface {value!r}. Known ones are {known}.")
        return value

    @model_validator(mode="after")
    def _fd(self) -> CanParams:
        if self.data_bitrate is not None and not self.fd:
            raise ValueError("data_bitrate only applies with fd: true.")
        return self


class _Frame(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: int = Field(ge=0, le=MAX_EXTENDED_ID)
    extended: bool | None = None

    @model_validator(mode="after")
    def _id(self) -> _Frame:
        if self.extended is False and self.id > MAX_STANDARD_ID:
            raise ValueError(f"id 0x{self.id:X} needs a 29-bit extended identifier. Remove extended: false.")
        return self

    @property
    def is_extended(self) -> bool:
        return self.extended if self.extended is not None else self.id > MAX_STANDARD_ID

    @property
    def key(self) -> tuple[int, bool]:
        return self.id, self.is_extended


class ReadMap(bits.BitField, _Frame):
    """A value inside one received frame."""


class WriteMap(bits.BitField, _Frame):
    """A value placed inside one sent frame, with the rest of the frame from `data`."""

    data: list[Byte] = Field(default=[], max_length=64)
    dlc: int | None = Field(default=None, ge=0, le=64)
    state: ReadMap | None = None


class ActionMap(_Frame):
    """One frame an action sends, with each argument placed by its field."""

    data: list[Byte] = Field(default=[], max_length=64)
    dlc: int | None = Field(default=None, ge=0, le=64)
    args: dict[str, bits.BitField] = {}


BusFactory = Callable[[CanParams], Any]


def open_bus(settings: CanParams) -> Any:
    """Open a python-can bus from the driver parameters."""
    options: dict[str, Any] = {"interface": settings.interface, "channel": settings.channel}
    if settings.bitrate is not None:
        options["bitrate"] = settings.bitrate
    if settings.fd:
        options["fd"] = True
        if settings.data_bitrate is not None:
            options["data_bitrate"] = settings.data_bitrate
    return can.Bus(**options)


def notation(arbitration_id: int, extended: bool, data: bytes) -> str:
    """A frame in candump's compact notation, such as 201#0BB801."""
    width = 8 if extended else 3
    return f"{arbitration_id:0{width}X}#{data.hex().upper()}"


class CanDriver(Driver):
    """Signals in CAN frames. Reads decode the newest frame per id, writes and actions send frames."""

    info: ClassVar[DriverInfo] = DriverInfo(
        name="can",
        protocols=("CAN 2.0A and 2.0B", "CAN FD"),
        hazard_default="medium",
        summary="Signals from CAN bus frames as channels, and frames as writes and actions, through python-can.",
        safe_state_support="file",
        conformance="full",
    )
    params_model: ClassVar[type[Any] | None] = CanParams

    def __init__(self, device: DeviceFile, *, bus_factory: BusFactory = open_bus) -> None:
        super().__init__(device)
        self.settings = CanParams.model_validate(device.connect.params)
        self._factory = bus_factory
        self._bus: Any = None
        self._reader: threading.Thread | None = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._latest: dict[tuple[int, bool], tuple[bytes, float]] = {}
        self._sent: dict[str, float | bool | str] = {}
        self._frames: dict[tuple[int, bool], bytearray] = {}
        self._lost = ""
        self.error_frames = 0
        self.reads: dict[str, ReadMap] = {}
        self.writes: dict[str, WriteMap] = {}
        self.actions: dict[str, ActionMap] = {}
        limit = 64 if self.settings.fd else CLASSIC_PAYLOAD
        for name, spec in device.read.items():
            read_map = self._parse(ReadMap, f"read.{name}", spec.map)
            bits.check_channel(name, spec, read_map, sends=False)
            self._fits(f"read.{name}", read_map.end, limit)
            self.reads[name] = read_map
        for name, wspec in device.write.items():
            write_map = self._parse(WriteMap, f"write.{name}", wspec.map)
            bits.check_channel(name, wspec, write_map, sends=True)
            self._fits(f"write.{name}", max(write_map.end, len(write_map.data), write_map.dlc or 0), limit)
            if write_map.state is not None:
                bits.check_channel(name, wspec, write_map.state, sends=False)
                self._fits(f"write.{name}.state", write_map.state.end, limit)
            self.writes[name] = write_map
        for name, action in device.actions.items():
            action_map = self._parse(ActionMap, f"actions.{name}", action.map)
            if set(action_map.args) != set(action.args):
                raise DriverError(
                    f"actions.{name}: map.args must place every argument the action declares "
                    f"({', '.join(sorted(action.args)) or 'none'}), and no others."
                )
            ends = [len(action_map.data), action_map.dlc or 0]
            for arg, field in action_map.args.items():
                bits.check_channel(f"actions.{name}.{arg}", action.args[arg], field, sends=True)
                ends.append(field.end)
            self._fits(f"actions.{name}", max(ends), limit)
            self.actions[name] = action_map

    @staticmethod
    def _parse[M: BaseModel](model: type[M], where: str, raw: dict[str, Any] | None) -> M:
        if raw is None:
            raise DriverError(f"{where} needs a map with a frame id, for example map: {{ id: 0x101, byte: 0 }}.")
        try:
            return model.model_validate(raw)
        except ValidationError as exc:
            problems = "; ".join(f"{'.'.join(map(str, e['loc'])) or 'map'}: {e['msg']}" for e in exc.errors())
            raise DriverError(f"{where} has an invalid can map. {problems}") from None

    def _fits(self, where: str, end: int, limit: int) -> None:
        if end > limit:
            kind = "CAN FD frames" if self.settings.fd else "classic CAN frames (set fd: true for CAN FD)"
            raise DriverError(f"{where} needs {end} data bytes, but {kind} carry at most {limit}.")

    @property
    def _where(self) -> str:
        return f"CAN channel {self.settings.channel} ({self.settings.interface})"

    @classmethod
    async def discover(cls) -> list[Discovered]:
        """List SocketCAN interfaces that are up. Nothing is sent on any bus."""
        try:
            found = await asyncio.wait_for(asyncio.to_thread(can.detect_available_configs, ["socketcan"]), 3.0)
        except Exception:  # noqa: BLE001
            return []
        return [
            Discovered(
                driver="can",
                address=f"{config['interface']}:{config['channel']}",
                identifiers={"interface": str(config["interface"]), "channel": str(config["channel"])},
                label=f"CAN interface {config['channel']}",
            )
            for config in found
        ]

    async def identify(self) -> dict[str, str]:
        identity = {"interface": self.settings.interface, "channel": self.settings.channel}
        if self.settings.bitrate is not None:
            identity["bitrate"] = str(self.settings.bitrate)
        if self._bus is not None:
            identity["channel_info"] = str(getattr(self._bus, "channel_info", ""))
        return identity

    async def connect(self) -> None:
        await self.close()
        try:
            bus = await asyncio.wait_for(asyncio.to_thread(self._factory, self.settings), self.settings.timeout + 2)
        except TimeoutError:
            raise TimeoutError(f"{self._where} did not open within {self.settings.timeout + 2:g} s.") from None
        except (can.CanError, OSError, ValueError, ImportError) as exc:
            raise DriverError(
                f"Could not open {self._where} ({exc}). Check the adapter is plugged in and the interface "
                "is up, for example sudo ip link set can0 up type can bitrate 500000."
            ) from None
        self._lost = ""
        self.error_frames = 0
        self._frames.clear()
        with self._lock:
            self._latest.clear()
        self._stop = threading.Event()
        self._bus = bus
        self._reader = threading.Thread(
            target=self._receive, args=(bus, self._stop), name=f"openhal-can-{self.device.device_id}", daemon=True
        )
        self._reader.start()

    def _receive(self, bus: Any, stop: threading.Event) -> None:
        while not stop.is_set():
            try:
                message = bus.recv(0.1)
            except Exception as exc:  # noqa: BLE001
                if not stop.is_set():
                    self._lost = f"the bus failed ({exc})"
                return
            if message is None or message.is_remote_frame:
                continue
            if message.is_error_frame:
                self.error_frames += 1
                continue
            at = message.timestamp if message.timestamp and message.timestamp > 1e9 else time.time()
            with self._lock:
                self._latest[(message.arbitration_id, message.is_extended_id)] = (bytes(message.data), at)

    async def close(self) -> None:
        bus, reader = self._bus, self._reader
        self._bus = None
        self._reader = None
        self._stop.set()
        if reader is not None:
            await asyncio.to_thread(reader.join, 1.0)
        if bus is not None:
            with contextlib.suppress(Exception):
                await asyncio.to_thread(bus.shutdown)

    @property
    def bus(self) -> Any:
        """The open python-can bus, or None before connecting."""
        return self._bus

    def _check_open(self) -> Any:
        if self._bus is None:
            raise DriverError(f"{self._where} is not open. Connect the device first.")
        if self._lost:
            raise DriverError(f"{self._where} is down, {self._lost}. Reconnect it.")
        return self._bus

    async def health(self) -> Health:
        if self._bus is None:
            return Health(connected=False, detail=f"{self._where} not open")
        if self._lost:
            return Health(connected=False, detail=f"{self._where} {self._lost}")
        try:
            state = self._bus.state
        except NotImplementedError:
            state = None
        if state == can.BusState.ERROR:
            return Health(connected=False, detail=f"{self._where} is bus-off")
        return Health(connected=True, detail=self._where)

    async def read(self, channel: str) -> Reading:
        if channel in self.reads:
            return self._decode(channel, self.reads[channel])
        if channel in self.writes:
            write_map = self.writes[channel]
            if write_map.state is not None:
                return self._decode(channel, write_map.state)
            self._check_open()
            return Reading(channel, self._sent.get(channel), unit=self.device.channel_unit(channel))
        raise DriverError(f"This can device has no channel {channel!r}.")

    def _decode(self, channel: str, read_map: ReadMap) -> Reading:
        self._check_open()
        spec = self.device.read.get(channel) or self.device.write[channel]
        unit = self.device.channel_unit(channel)
        with self._lock:
            latest = self._latest.get(read_map.key)
        if latest is None:
            return Reading(channel, None, unit=unit)
        data, at = latest
        where = f"frame 0x{read_map.id:X} for {channel}"
        value = bits.to_value(bits.extract(data, read_map, where), spec, read_map, where)
        return Reading(channel, value, unit=unit, at=at, suspect=bits.suspect(value, spec))

    def _payload(self, base: list[int], dlc: int | None, end: int) -> bytearray:
        size = max(len(base), dlc or 0, end)
        return bytearray(base) + bytearray(size - len(base))

    def _finish(self, payload: bytearray) -> bytes:
        if len(payload) <= CLASSIC_PAYLOAD:
            return bytes(payload)
        size = next(length for length in FD_LENGTHS if length >= len(payload))
        return bytes(payload) + bytes(size - len(payload))

    async def _send(self, frame: _Frame, data: bytes) -> None:
        bus = self._check_open()
        message = can.Message(
            arbitration_id=frame.id,
            is_extended_id=frame.is_extended,
            data=data,
            is_fd=self.settings.fd and len(data) > CLASSIC_PAYLOAD,
        )
        timeout = self.settings.timeout
        try:
            await asyncio.wait_for(asyncio.to_thread(bus.send, message, timeout), timeout + 1)
        except TimeoutError:
            raise TimeoutError(
                f"{self._where} did not take frame {notation(frame.id, frame.is_extended, data)} within {timeout:g} s."
            ) from None
        except (can.CanError, OSError, ValueError) as exc:
            raise DriverError(
                f"{self._where} refused frame {notation(frame.id, frame.is_extended, data)} ({exc}). "
                "Check the bus is up and another node acknowledges frames."
            ) from None

    async def _write(self, channel: str, value: float | bool | str) -> Reading | None:
        write_map = self.writes.get(channel)
        if write_map is None:
            raise DriverError(f"This can device has no write channel {channel!r}.")
        self._check_open()
        where = f"write.{channel}"
        raw, sent = bits.to_raw(value, self.device.write[channel], write_map, where)
        previous = self._frames.get(write_map.key)
        base = list(previous) if previous is not None else write_map.data
        payload = self._payload(base, write_map.dlc, write_map.end)
        bits.insert(payload, write_map, raw, where)
        data = self._finish(payload)
        await self._send(write_map, data)
        self._frames[write_map.key] = bytearray(data)
        self._sent[channel] = sent
        if write_map.state is not None:
            return None
        return Reading(channel, sent, unit=self.device.channel_unit(channel))

    async def _action(self, name: str, args: dict[str, Any]) -> Any:
        action_map = self.actions.get(name)
        if action_map is None:
            raise DriverError(f"This can device has no action {name!r}.")
        self._check_open()
        spec = self.device.actions[name]
        ends = [field.end for field in action_map.args.values()]
        payload = self._payload(action_map.data, action_map.dlc, max(ends, default=0))
        for arg, field in action_map.args.items():
            raw, _ = bits.to_raw(args[arg], spec.args[arg], field, f"actions.{name}.{arg}")
            bits.insert(payload, field, raw, f"actions.{name}.{arg}")
        data = self._finish(payload)
        await self._send(action_map, data)
        return {"sent": notation(action_map.id, action_map.is_extended, data)}

    async def describe(self, listen_s: float = 1.0) -> dict[str, Any] | None:
        """Listen for a moment and propose one read channel per frame id seen on the bus."""
        if self._bus is None or self._lost:
            return None
        await asyncio.sleep(listen_s)
        with self._lock:
            seen = dict(self._latest)
        reads: dict[str, Any] = {}
        for (arbitration_id, extended), (data, _) in sorted(seen.items())[:DESCRIBE_LIMIT]:
            if not data:
                continue
            length = min(len(data), CLASSIC_PAYLOAD)
            name = f"frame_{arbitration_id:x}" + ("_ext" if extended and arbitration_id <= MAX_STANDARD_ID else "")
            reads[name] = {
                "unit": "dimensionless",
                "map": {"id": arbitration_id, "extended": extended, "byte": 0, "length": length},
            }
        result: dict[str, Any] = {
            "notes": (
                f"Proposed from {len(seen)} frame ids seen while listening. Each reads the frame's first bytes as one "
                "unsigned number. Split them into signals and set units from the node's documentation or DBC file. "
                "Command frames can't be seen by listening, so add writes and actions by hand."
            )
        }
        if reads:
            result["read"] = reads
        return result
