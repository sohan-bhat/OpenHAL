"""Marlin firmware over USB serial.

Protocol (Marlin G-code reference, marlinfw.org/docs/gcode, and the RepRap G-code wiki).

- The host sends one G-code per line. Each line carries a line number and an XOR checksum,
  `N12 M104 S200*93`, so the firmware can ask for a resend after line noise (`Resend: 12`).
  `M110 N0` resets the numbering after connect.
- The firmware answers every command with `ok` once it has finished it, in order. The driver
  keeps a FIFO of commands in flight and resolves them as the `ok` lines arrive.
- Long commands such as G28 send `echo:busy: processing` keepalives and hold back later
  commands. The home action returns `started` after `action_wait` if the printer is still busy,
  and its `ok` is consumed in the background.
- Temperatures come from `M105` (`ok T:21.0 /0.0 B:20.5 /0.0 @:0 B@:0`) and, when M115 reports
  `Cap:AUTOREPORT_TEMP:1`, from `M155 S<seconds>` auto-reports. Reads use the latest report
  when it is fresh, so they keep working while the printer is busy homing.
- `start` in the middle of a session means the board reset. Heaters are off after a reset, so
  commands in flight fail and the driver renumbers lines. `Error:Printer halted` means the
  firmware killed itself and needs a reset, and the driver reports itself disconnected.

Mapping. Channel names map to G-code by convention, and `map` can override them.

    read   extruder_temp, bed_temp, chamber_temp   map { temperature: T0 | T1 | B | C, field: actual | target }
           position_x, position_y, position_z      map { position: X | Y | Z | E }
           sd_printing, sd_progress                map { sd: printing | progress }
    write  extruder_target, bed_target, chamber_target   map { heater: T0 | B | C }  (M104, M140, M141)
           fan_speed (percent)                           map { fan: 0 }  (M106 S0..255, 100 % is 255)
    action home (arg axes: x, y, z, xy, all), pause, resume, cancel   map { command: home | pause | ... }

Pause, resume and cancel are M25, M24 and M524, which act on prints from the printer's own SD
card. A print streamed by a host program is paused by that program, not by the firmware.

Safe state. Native. Every heater named in the file gets target 0 (M104 S0, M140 S0, M141 S0).
M112 is never sent unless `m112_on_stop: true`, because after M112 the firmware needs a reset.
There is deliberately no raw G-code action, since it would step around every limit.
"""

from __future__ import annotations

import asyncio
import contextlib
import re
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from openhal.drivers.base import Discovered, Driver, DriverError, DriverInfo, Health, Reading
from openhal.drivers.serial import mapping
from openhal.drivers.serial.link import (
    Opener,
    SerialLink,
    list_serial_ports,
    port_identifiers,
    pyserial_opener,
    resolve_port,
)
from openhal.spec.models import DeviceFile
from openhal.spec.units import Quantity, UnitError, convert, parse_unit

HEATER = r"^(T[0-7]?|B|C)$"
TEMPERATURE = re.compile(r"(?<![A-Z@])(T\d?|B|C)\s*:\s*(-?\d+(?:\.\d+)?)(?:\s*/\s*(-?\d+(?:\.\d+)?))?")
POSITION = re.compile(r"\b([XYZE])\s*:\s*(-?\d+(?:\.\d+)?)")
SD_BYTES = re.compile(r"SD printing byte (\d+)\s*/\s*(\d+)")
RESEND = re.compile(r"^(?:Resend|rs)\s*:?\s*N?(\d+)", re.IGNORECASE)
HEATER_CODE = {"B": "M140", "C": "M141"}


class MarlinParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    port: str = Field(min_length=1, max_length=300)
    baud: int = Field(default=115200, ge=9600, le=4_000_000)
    timeout: float = Field(default=5.0, description="How long to wait for ok.")
    settle: float = Field(default=2.0, description="Wait after opening. Most boards reset when the port opens.")
    action_wait: float = Field(default=8.0, description="How long home waits before returning started.")
    autoreport: float = Field(default=2.0, description="M155 interval, 0 s to poll with M105 instead.")
    checksums: bool = True
    m112_on_stop: bool = False

    @field_validator("timeout", "settle", "action_wait", "autoreport", mode="before")
    @classmethod
    def _duration(cls, value: Any) -> float:
        return mapping.duration(value)

    @model_validator(mode="after")
    def _ranges(self) -> MarlinParams:
        checks = (("timeout", 0.1, 60), ("settle", 0, 10), ("action_wait", 0.1, 9), ("autoreport", 0, 60))
        for name, low, high in checks:
            if not low <= getattr(self, name) <= high:
                raise ValueError(f"{name} must be between {low:g} s and {high:g} s.")
        return self


class ReadMap(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    temperature: str | None = Field(default=None, pattern=HEATER)
    field: Literal["actual", "target"] = "actual"
    position: Literal["X", "Y", "Z", "E"] | None = None
    sd: Literal["printing", "progress"] | None = None

    @model_validator(mode="after")
    def _one(self) -> ReadMap:
        if sum(item is not None for item in (self.temperature, self.position, self.sd)) != 1:
            raise ValueError("give exactly one of temperature, position or sd.")
        return self


class WriteMap(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    heater: str | None = Field(default=None, pattern=HEATER)
    fan: int | None = Field(default=None, ge=0, le=7)

    @model_validator(mode="after")
    def _one(self) -> WriteMap:
        if (self.heater is None) == (self.fan is None):
            raise ValueError("give exactly one of heater or fan.")
        return self


class ActionMap(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    command: Literal["home", "pause", "resume", "cancel"]


READ_DEFAULTS: dict[str, dict[str, Any]] = {
    "extruder_temp": {"temperature": "T0"},
    "hotend_temp": {"temperature": "T0"},
    "bed_temp": {"temperature": "B"},
    "chamber_temp": {"temperature": "C"},
    "position_x": {"position": "X"},
    "position_y": {"position": "Y"},
    "position_z": {"position": "Z"},
    "position_e": {"position": "E"},
    "sd_printing": {"sd": "printing"},
    "sd_progress": {"sd": "progress"},
}
WRITE_DEFAULTS: dict[str, dict[str, Any]] = {
    "extruder_target": {"heater": "T0"},
    "hotend_target": {"heater": "T0"},
    "bed_target": {"heater": "B"},
    "chamber_target": {"heater": "C"},
    "fan_speed": {"fan": 0},
}
HOME_AXES = {"x": "G28 X", "y": "G28 Y", "z": "G28 Z", "xy": "G28 X Y", "all": "G28"}
ACTION_CODES = {"pause": "M25", "resume": "M24", "cancel": "M524"}


def checksum(text: str) -> int:
    value = 0
    for byte in text.encode("ascii"):
        value ^= byte
    return value


@dataclass
class _Pending:
    command: str
    number: int | None
    future: asyncio.Future[list[str]]
    lines: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    touched: float = field(default_factory=time.monotonic)


def _validate(model: type[BaseModel], raw: dict[str, Any] | None, defaults: dict[str, Any] | None, where: str) -> Any:
    data = raw if raw is not None else defaults
    if data is None:
        raise DriverError(f"{where} is not a Marlin channel the driver knows. Add a map, see docs/drivers/marlin.md.")
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        problems = "; ".join(f"{'.'.join(str(p) for p in e['loc']) or 'map'}: {e['msg']}" for e in exc.errors())
        raise DriverError(f"{where}.map is not valid for the Marlin driver ({problems}).") from exc


class MarlinDriver(Driver):
    """FDM printers and other machines running Marlin firmware, over USB serial."""

    info: ClassVar[DriverInfo] = DriverInfo(
        name="marlin",
        protocols=("Marlin G-code over USB serial",),
        hazard_default="medium",
        summary="3D printers running Marlin firmware. Temperatures, heater targets, fan and homing.",
        safe_state_support="native",
    )
    params_model: ClassVar[type[Any] | None] = MarlinParams

    def __init__(self, device: DeviceFile, *, opener: Opener | None = None) -> None:
        super().__init__(device)
        self.settings = MarlinParams.model_validate(device.connect.params)
        self._opener = opener
        self.link: SerialLink | None = None
        self.reads: dict[str, ReadMap] = {}
        self.writes: dict[str, WriteMap] = {}
        self.actions: dict[str, ActionMap] = {}
        self.temps: dict[str, tuple[float, float | None]] = {}
        self.temps_at = 0.0
        self.firmware: dict[str, str] = {}
        self.halted: str | None = None
        self.autoreporting = False
        self._line = 0
        self._history: dict[int, str] = {}
        self._inflight: deque[_Pending] = deque()
        self._lock = asyncio.Lock()
        self._pump_task: asyncio.Task[None] | None = None
        self._background: set[asyncio.Task[Any]] = set()
        self._fan_sent: dict[str, Reading] = {}
        self._skip_ok = 0
        self._last_rx = 0.0
        self._check_maps()

    def _check_maps(self) -> None:
        for name, spec in self.device.read.items():
            read_map = _validate(ReadMap, spec.map, READ_DEFAULTS.get(name), f"read.{name}")
            if read_map.temperature is not None or read_map.position is not None:
                self._need_unit(name, spec.unit, "degC" if read_map.temperature else "mm")
            self.reads[name] = read_map
        for name, write_spec in self.device.write.items():
            write_map = _validate(WriteMap, write_spec.map, WRITE_DEFAULTS.get(name), f"write.{name}")
            if write_map.heater is not None:
                self._need_unit(name, write_spec.unit, "degC")
            elif write_spec.type != "number" or write_spec.unit not in ("percent", "%"):
                raise DriverError(f"write.{name}: fan channels must be numbers in percent.")
            self.writes[name] = write_map
        for name, action in self.device.actions.items():
            known = {"command": name} if name in ACTION_CODES or name == "home" else None
            action_map = _validate(ActionMap, action.map, known, f"actions.{name}")
            if action_map.command == "home":
                extra = set(action.args) - {"axes"}
                if extra:
                    raise DriverError(f"actions.{name}: home takes only an axes argument, not {sorted(extra)}.")
            self.actions[name] = action_map

    def _need_unit(self, name: str, unit: str | None, wanted: str) -> None:
        try:
            convert(Quantity(0, parse_unit(unit or "")), wanted)
        except UnitError:
            raise DriverError(f"{name} needs a unit that converts to {wanted}, not {unit!r}.") from None

    @classmethod
    async def discover(cls) -> list[Discovered]:
        ports = await asyncio.to_thread(list_serial_ports)
        return [
            Discovered(driver="marlin", address=str(info.device), identifiers=port_identifiers(info))
            for info in ports
            if getattr(info, "vid", None) is not None
        ]

    async def identify(self) -> dict[str, str]:
        if self.link is None or not self.link.connected:
            return {"port": self.settings.port}
        lines = await self._gcode("M115")
        return {"port": self.settings.port, **self._parse_firmware(lines)}

    def _parse_firmware(self, lines: list[str]) -> dict[str, str]:
        found: dict[str, str] = {}
        for line in lines:
            if line.startswith("Cap:"):
                key, _, value = line[4:].partition(":")
                found[f"cap.{key.lower()}"] = value
                continue
            for key, value in re.findall(r"([A-Z_]+):(.*?)(?=\s+[A-Z_]+:|$)", line):
                found[key.lower()] = value.strip()
        self.firmware = found
        return found

    async def connect(self) -> None:
        await self.close()
        opener = self._opener
        if opener is None:
            port = await asyncio.to_thread(
                resolve_port,
                self.settings.port,
                self.device.match.usb,
                self.device.match.serial_number,
                driver="marlin",
            )
            opener = pyserial_opener(port, self.settings.baud)
        self.link = SerialLink(opener, name=self.settings.port)
        await self.link.open()
        await self._wait_for_boot(self.link)
        self.link.take_buffered()
        self.halted = None
        self._fan_sent.clear()
        self._line = 0
        self._skip_ok = 0
        self._history.clear()
        self._inflight.clear()
        self.temps.clear()
        self.temps_at = 0.0
        self._pump_task = asyncio.create_task(self._pump(self.link))
        await self._gcode("M110 N0", numbered=False)
        info = self._parse_firmware(await self._gcode("M115"))
        self.autoreporting = False
        if self.settings.autoreport and info.get("cap.autoreport_temp") == "1":
            await self._gcode(f"M155 S{max(1, round(self.settings.autoreport))}")
            self.autoreporting = True

    async def _wait_for_boot(self, link: SerialLink) -> None:
        """Most boards reset when the port opens. Wait for the `start` banner and a quiet moment."""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self.settings.settle
        booted = False
        while (remaining := deadline - loop.time()) > 0:
            try:
                line = await link.read_line(min(remaining, 0.15) if booted else remaining)
            except TimeoutError:
                if booted:
                    return
                continue
            booted = booted or line.strip() == b"start"

    async def _pump(self, link: SerialLink) -> None:
        try:
            while True:
                try:
                    raw = await link.read_line(3600)
                except TimeoutError:
                    continue
                self._handle_line(raw[:4096].decode("ascii", errors="replace").strip())
        except DriverError as exc:
            self._fail_all(DriverError(f"The printer disconnected ({exc}). Check the USB cable, then reconnect."))

    def _handle_line(self, line: str) -> None:
        if not line:
            return
        head = self._inflight[0] if self._inflight else None
        self._last_rx = time.monotonic()
        if line.startswith("ok"):
            self._note_temperatures(line)
            if self._skip_ok:
                self._skip_ok -= 1
                return
            if head is not None:
                self._inflight.popleft()
                if not head.future.done():
                    head.future.set_result([*head.lines, line])
            return
        if line == "start":
            self._line = 0
            self._skip_ok = 0
            self._history.clear()
            self._fail_all(DriverError("The printer reset itself. Heaters are off. Check its power and display."))
            return
        if line.startswith("Error:"):
            if "halted" in line.lower() or "kill" in line.lower():
                self.halted = line
                self._fail_all(DriverError(f"The firmware stopped ({line}). Reset the printer, then reconnect."))
            elif head is not None:
                head.errors.append(line)
            return
        resend = RESEND.match(line)
        if resend:
            self._resend(int(resend.group(1)))
            return
        if line.startswith("echo:busy"):
            return
        if TEMPERATURE.search(line) and "Count" not in line and line.startswith(("T:", "T0:", "B:", " T:")):
            self._note_temperatures(line)
            return
        if head is not None:
            head.lines.append(line)

    def _note_temperatures(self, line: str) -> None:
        found = TEMPERATURE.findall(line)
        if not found:
            return
        keys = {key for key, _, _ in found}
        for key, actual, target in found:
            self.temps[key] = (float(actual), float(target) if target else None)
        if "T" in keys and "T0" not in keys:
            self.temps["T0"] = self.temps["T"]
        self.temps_at = time.monotonic()

    def _resend(self, number: int) -> None:
        text = self._history.get(number)
        if text is None or self.link is None:
            return
        self._skip_ok += 1
        for pending in self._inflight:
            if pending.number is not None and pending.number >= number:
                pending.errors.clear()
        task = asyncio.create_task(self._resend_from(number))
        self._background.add(task)
        task.add_done_callback(self._background.discard)

    async def _resend_from(self, number: int) -> None:
        assert self.link is not None
        for line_number in sorted(n for n in self._history if n >= number):
            with contextlib.suppress(DriverError):
                await self.link.write((self._history[line_number] + "\n").encode("ascii"))

    def _fail_all(self, error: DriverError) -> None:
        while self._inflight:
            pending = self._inflight.popleft()
            if not pending.future.done():
                pending.future.set_exception(error)
                pending.future.exception()

    def _require_link(self) -> SerialLink:
        if self.halted:
            raise DriverError(f"The firmware stopped ({self.halted}). Reset the printer, then reconnect.")
        if self.link is None or not self.link.connected or self._pump_task is None or self._pump_task.done():
            raise DriverError(f"The printer on {self.settings.port} is not connected. Reconnect it.")
        return self.link

    def _frame(self, command: str, numbered: bool) -> tuple[str, int | None]:
        mapping.plain_text(command, "G-code")
        if not (numbered and self.settings.checksums):
            return command, None
        self._line += 1
        body = f"N{self._line} {command}"
        text = f"{body}*{checksum(body)}"
        self._history[self._line] = text
        for old in [n for n in self._history if n < self._line - 32]:
            del self._history[old]
        return text, self._line

    async def _send(self, command: str, *, numbered: bool = True) -> _Pending:
        link = self._require_link()
        text, number = self._frame(command, numbered)
        pending = _Pending(command, number, asyncio.get_running_loop().create_future())
        self._inflight.append(pending)
        await link.write((text + "\n").encode("ascii"))
        return pending

    async def _await(self, pending: _Pending, budget: float) -> list[str]:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + budget
        while True:
            idle = self._idle(pending)
            remaining = min(deadline - loop.time(), self.settings.timeout - idle)
            if remaining <= 0:
                raise TimeoutError(
                    f"The printer didn't acknowledge {pending.command} within {self.settings.timeout:g} s. "
                    "Check the baud rate and that the printer is on."
                )
            try:
                lines = await asyncio.wait_for(asyncio.shield(pending.future), remaining)
            except TimeoutError:
                if loop.time() >= deadline:
                    raise
                continue
            if pending.errors:
                raise DriverError(f"The printer rejected {pending.command} ({'; '.join(pending.errors)}).")
            unknown = [line for line in lines if line.startswith("echo:Unknown command")]
            if unknown:
                raise DriverError(f"The firmware doesn't support {pending.command} ({unknown[0]}).")
            return lines

    def _idle(self, pending: _Pending) -> float:
        """Seconds since the printer last said anything, counted from when this command was sent."""
        return time.monotonic() - max(pending.touched, self._last_rx)

    async def _gcode(self, command: str, *, numbered: bool = True) -> list[str]:
        async with self._lock:
            pending = await self._send(command, numbered=numbered)
            try:
                return await self._await(pending, self.settings.timeout * 4)
            except TimeoutError:
                with contextlib.suppress(ValueError):
                    self._inflight.remove(pending)
                raise

    async def _temperatures(self) -> dict[str, tuple[float, float | None]]:
        fresh_for = max(self.settings.autoreport * 2.5, 1.0)
        if self.autoreporting and self.temps and time.monotonic() - self.temps_at < fresh_for:
            self._require_link()
            return self.temps
        if self._lock.locked() and self.temps and time.monotonic() - self.temps_at < 10:
            return self.temps
        await self._gcode("M105")
        return self.temps

    async def read(self, channel: str) -> Reading:
        unit = self.device.channel_unit(channel)
        if channel in self.reads:
            read_map = self.reads[channel]
            if read_map.temperature is not None:
                value = await self._temperature(read_map.temperature, read_map.field, channel)
                return Reading(channel, self._from(value, "degC", unit), unit)
            if read_map.position is not None:
                lines = await self._gcode("M114")
                report = next((ln for ln in lines if "X:" in ln), "")
                positions = dict(POSITION.findall(report.split("Count", 1)[0]))
                if read_map.position not in positions:
                    raise DriverError(f"M114 didn't report {read_map.position}. The printer said {lines!r}.")
                return Reading(channel, self._from(float(positions[read_map.position]), "mm", unit), unit)
            return await self._read_sd(channel, read_map, unit)
        if channel in self.writes:
            write_map = self.writes[channel]
            if write_map.heater is not None:
                value = await self._temperature(write_map.heater, "target", channel)
                return Reading(channel, self._from(value, "degC", unit), unit)
            last = self._fan_sent.get(channel)
            return last if last is not None else Reading(channel, None, unit)
        raise DriverError(f"{self.device.device_id} has no channel {channel!r}.")

    async def _temperature(self, key: str, which: str, channel: str) -> float:
        temps = await self._temperatures()
        if key not in temps:
            raise DriverError(f"The printer doesn't report heater {key}, so {channel} can't be read.")
        actual, target = temps[key]
        if which == "target":
            if target is None:
                raise DriverError(f"The printer reports no target for {key}.")
            return target
        return actual

    async def _read_sd(self, channel: str, read_map: ReadMap, unit: str | None) -> Reading:
        lines = await self._gcode("M27")
        status = next((ln for ln in lines if "SD print" in ln), "")
        match = SD_BYTES.search(status)
        if read_map.sd == "printing":
            return Reading(channel, match is not None, None)
        if match is None:
            return Reading(channel, 0.0, unit)
        done, total = int(match.group(1)), int(match.group(2))
        return Reading(channel, round(100.0 * done / total, 2) if total else 0.0, unit)

    def _from(self, value: float, protocol_unit: str, channel_unit: str | None) -> float:
        if not channel_unit or channel_unit == protocol_unit:
            return value
        return convert(Quantity(value, parse_unit(protocol_unit)), channel_unit)

    def _to(self, value: float, channel_unit: str | None, protocol_unit: str) -> float:
        if not channel_unit or channel_unit == protocol_unit:
            return value
        return convert(Quantity(value, parse_unit(channel_unit)), protocol_unit)

    def _heater_command(self, heater: str, celsius: float) -> str:
        if heater in HEATER_CODE:
            return f"{HEATER_CODE[heater]} S{celsius:.1f}"
        tool = heater[1:] or "0"
        return f"M104 T{tool} S{celsius:.1f}"

    async def _write(self, channel: str, value: float | bool | str) -> Reading | None:
        write_map = self.writes.get(channel)
        if write_map is None or isinstance(value, bool) or not isinstance(value, int | float):
            raise DriverError(f"{self.device.device_id} has no numeric write channel {channel!r}.")
        unit = self.device.channel_unit(channel)
        if write_map.heater is not None:
            celsius = self._to(float(value), unit, "degC")
            await self._gcode(self._heater_command(write_map.heater, celsius))
        else:
            pwm = max(0, min(255, round(float(value) * 255 / 100)))
            self._fan_sent.pop(channel, None)
            await self._gcode(f"M106 P{write_map.fan} S{pwm}")
            self._fan_sent[channel] = Reading(channel, value, unit)
        return Reading(channel, value, unit)

    async def _action(self, name: str, args: dict[str, Any]) -> Any:
        action_map = self.actions.get(name)
        if action_map is None:
            raise DriverError(f"{self.device.device_id} has no action {name!r}.")
        if action_map.command != "home":
            await self._gcode(ACTION_CODES[action_map.command])
            return {"sent": ACTION_CODES[action_map.command]}
        axes = str(args.get("axes", "all"))
        if axes not in HOME_AXES:
            raise DriverError(f"home can't take axes {axes!r}. Use one of {', '.join(HOME_AXES)}.")
        command = HOME_AXES[axes]
        async with self._lock:
            pending = await self._send(command)
            try:
                await self._await(pending, self.settings.action_wait)
            except TimeoutError:
                if self._idle(pending) < self.settings.timeout and pending in self._inflight:
                    self._watch(pending)
                    return {"sent": command, "status": "started"}
                raise
        return {"sent": command, "status": "done"}

    def _watch(self, pending: _Pending) -> None:
        async def finish() -> None:
            with contextlib.suppress(DriverError, TimeoutError):
                await self._await(pending, 600)

        task = asyncio.create_task(finish())
        self._background.add(task)
        task.add_done_callback(self._background.discard)

    async def _safe_state(self) -> None:
        heaters = {item.heater for item in self.writes.values() if item.heater is not None} | {"T0", "B"}
        commands = [self._heater_command(heater, 0.0) for heater in sorted(heaters)]
        if self.settings.m112_on_stop:
            commands.append("M112")
        sent = [await self._send(command) for command in commands]
        if self.settings.m112_on_stop:
            return
        for pending in sent:
            await self._await(pending, self.settings.timeout)

    async def health(self) -> Health:
        try:
            self._require_link()
        except DriverError as exc:
            return Health(connected=False, detail=str(exc))
        detail = self.firmware.get("firmware_name", "Marlin")
        return Health(connected=True, detail=detail)

    async def close(self) -> None:
        task, link = self._pump_task, self.link
        self._pump_task = None
        self.link = None
        for background in list(self._background):
            background.cancel()
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        self._fail_all(DriverError("The connection was closed."))
        if link is not None:
            await link.close()
