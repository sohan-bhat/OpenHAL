"""GRBL 1.1 CNC routers and laser cutters over USB serial.

Protocol (gnea/grbl wiki, "Grbl v1.1 Interface", "Grbl v1.1 Commands", "Grbl v1.1 Jogging"
and "Grbl v1.1 Laser Mode"). Message parsing is in `protocol.py`, the line protocol client in
`session.py` and the channel maps in `channels.py`.

- Line commands end with a newline and are answered in order with `ok` or `error:N`. The driver
  sends one line at a time and waits for its answer, the "send and wait" streaming GRBL
  documents as the simplest safe method.
- Realtime commands are single bytes that act at once and are never answered with `ok`. `?`
  asks for a status report, `!` holds the feed, `~` resumes, 0x85 cancels a jog and 0x18 resets.
- Motion lines get `ok` once they are queued, not when the move ends. Jog and move actions poll
  the status until the machine is idle again, or return `started` after `action_wait`.
- `ALARM:N` means the controller stopped. In alarm GRBL refuses G-code with error:9 until `$X`
  or `$H`. After a hard or soft limit it waits for a reset (`[MSG:Reset to continue]`).
- The banner (`Grbl 1.1h ['$' for help]`) means the controller reset. Lines in flight are lost.

Read only. `?`, `$$` (settings), `$I` (build info), `$G` (parser state) and `$#` (offsets).
discover() lists serial ports and never opens one, because opening a port resets most boards.

Mapping. Channel names map by convention, and `map` can override them.

    read   state, alarm, position_x/y/z/a, work_x/y/z/a, feed_rate, spindle_speed, pins
           map { status: state | alarm | x | y | z | a | feed | spindle | pins, frame: machine | work }
           map { setting: 130 }   any numeric $ setting, read only
    write  spindle_speed (rpm)     map { spindle: cw | ccw }        M3 or M4 S<rpm>, M5 at 0
           laser_power (percent)   map { laser: dynamic | constant } M4 or M3 S<percent * $30 / 100>
           flood, mist (bool)      map { coolant: flood | mist }    M8, M7, M9
    action home ($H), jog ($J=, args x y z a feed), move (G0 or G1, args x y z a feed),
           set_work_zero (G10 L20 P0, arg axes), cancel_jog, hold, resume, clear_alarm ($X), reset
           map { command: ..., distance: relative | absolute, frame: work | machine, rapid: true }

Safe state. Native. Feed hold (`!`), wait for the machine to stop, then soft reset (0x18), which
turns the spindle, laser and coolant off. If the machine was moving GRBL comes back in ALARM:3
and needs `$X` or `$H`. There is deliberately no raw G-code action.
"""

from __future__ import annotations

import asyncio
import contextlib
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from openhal.drivers.base import Discovered, Driver, DriverError, DriverInfo, Health, Reading
from openhal.drivers.grbl import channels, protocol
from openhal.drivers.grbl.channels import ActionMap, ReadMap, WriteMap, to_unit
from openhal.drivers.grbl.protocol import Status
from openhal.drivers.grbl.session import GrblError, GrblSession, Pending
from openhal.drivers.serial import mapping
from openhal.drivers.serial.link import Opener, list_serial_ports, port_identifiers, pyserial_opener, resolve_port
from openhal.spec.models import DeviceFile

HOLD_WAIT_S = 2.0
POLL_S = 0.05
MOTION_STATES = frozenset({"run", "jog", "home"})


class GrblParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    port: str = Field(min_length=1, max_length=300)
    baud: int = Field(default=115200, ge=9600, le=4_000_000)
    timeout: float = Field(default=5.0, description="How long to wait for ok or a status report.")
    settle: float = Field(default=2.0, description="Longest wait for the banner after opening the port.")
    action_wait: float = Field(default=8.0, description="How long motion actions wait before returning started.")
    status_age: float = Field(default=0.2, description="Reuse a status report this fresh across reads.")

    @field_validator("timeout", "settle", "action_wait", "status_age", mode="before")
    @classmethod
    def _duration(cls, value: Any) -> float:
        return mapping.duration(value)

    @model_validator(mode="after")
    def _ranges(self) -> GrblParams:
        checks = (("timeout", 0.1, 30), ("settle", 0, 10), ("action_wait", 0.1, 9), ("status_age", 0, 2))
        for name, low, high in checks:
            if not low <= getattr(self, name) <= high:
                raise ValueError(f"{name} must be between {low:g} s and {high:g} s.")
        return self


def _moving(status: Status) -> bool:
    return status.state in MOTION_STATES or (status.state == "hold" and status.substate == 1)


class GrblDriver(Driver):
    """CNC routers, mills and laser cutters running GRBL 1.1, over USB serial."""

    info: ClassVar[DriverInfo] = DriverInfo(
        name="grbl",
        protocols=("GRBL 1.1 over USB serial",),
        hazard_default="high",
        summary="CNC routers and laser cutters on GRBL 1.1. Status, settings, spindle, laser, coolant, jog and moves.",
        safe_state_support="native",
        conformance="full",
    )
    params_model: ClassVar[type[Any] | None] = GrblParams

    def __init__(self, device: DeviceFile, *, opener: Opener | None = None) -> None:
        super().__init__(device)
        self.settings = GrblParams.model_validate(device.connect.params)
        self._opener = opener
        self.session: GrblSession | None = None
        self.reads: dict[str, ReadMap]
        self.writes: dict[str, WriteMap]
        self.actions: dict[str, ActionMap]
        self.reads, self.writes, self.actions = channels.build(device)
        self.grbl: dict[int, float] = {}
        self.build: dict[str, str] = {}
        self.note = ""
        self._background: set[asyncio.Task[Any]] = set()

    @classmethod
    async def discover(cls) -> list[Discovered]:
        ports = await asyncio.to_thread(list_serial_ports)
        return [
            Discovered(driver="grbl", address=str(info.device), identifiers=port_identifiers(info))
            for info in ports
            if getattr(info, "vid", None) is not None
        ]

    def _session(self) -> GrblSession:
        if self.session is None:
            raise DriverError(f"The controller on {self.settings.port} is not connected. Reconnect it.")
        self.session.require()
        return self.session

    async def identify(self) -> dict[str, str]:
        if self.session is None or not self.session.link.connected:
            return {"port": self.settings.port}
        return {"port": self.settings.port, **self._parse_build(await self._session().command("$I"))}

    def _parse_build(self, lines: list[str]) -> dict[str, str]:
        found: dict[str, str] = {}
        if self.session is not None and self.session.version:
            found["banner"] = f"Grbl {self.session.version}"
        for line in lines:
            parsed = protocol.parse_bracket(line)
            if parsed is None:
                continue
            tag, body = parsed
            if tag == "VER":
                version, _, info = body.partition(":")
                number, dot, build = version.rpartition(".")
                found["version"] = number if dot and build.isdigit() else version
                if dot and build.isdigit():
                    found["build"] = build
                if info.rstrip(":"):
                    found["info"] = info.rstrip(":")
            elif tag == "OPT":
                found["options"] = body
        self.build = found
        return found

    async def connect(self) -> None:
        await self.close()
        opener = self._opener
        if opener is None:
            port = await asyncio.to_thread(
                resolve_port, self.settings.port, self.device.match.usb, self.device.match.serial_number, driver="grbl"
            )
            opener = pyserial_opener(port, self.settings.baud)
        self.session = GrblSession(opener, name=self.settings.port, timeout=self.settings.timeout)
        await self.session.open(self.settings.settle)
        self._parse_build(await self.session.command("$I"))
        await self._load_settings()
        status = await self.session.status(0)
        for name, write_map in self.writes.items():
            if write_map.laser is not None and self.grbl and self.grbl.get(32) != 1:
                raise DriverError(
                    f"write.{name} needs laser mode, and this controller reports $32={self.grbl.get(32, 0):g}. "
                    "Enable laser mode on the controller, or use spindle_speed."
                )
        if status.spindle is None:
            self.note = "This build reports no spindle speed (no FS field), so spindle reads come from $G."

    async def _load_settings(self) -> None:
        try:
            lines = await self._session().command("$$")
        except DriverError:
            return
        found: dict[int, float] = {}
        for line in lines:
            parsed = protocol.parse_setting(line)
            if parsed is not None:
                with contextlib.suppress(ValueError):
                    found[parsed[0]] = float(parsed[1])
        self.grbl = found

    async def _status(self, max_age: float | None = None) -> Status:
        return await self._session().status(self.settings.status_age if max_age is None else max_age)

    def _length_unit(self) -> str:
        return "inch" if self.grbl.get(13) == 1 else "mm"

    async def _report(self, line: str, tag: str) -> str:
        for item in await self._session().command(line):
            parsed = protocol.parse_bracket(item)
            if parsed is not None and parsed[0] == tag:
                return parsed[1]
        raise DriverError(f"GRBL didn't send its [{tag}:] report for {line}.")

    async def _modes(self) -> dict[str, str | float]:
        return protocol.parse_modes(await self._report("$G", "GC"))

    async def _offsets(self) -> tuple[float, ...]:
        session = self._session()
        if session.wco is not None:
            return session.wco
        modes = await self._modes()
        rows: dict[str, str] = {}
        for line in await session.command("$#"):
            parsed = protocol.parse_bracket(line)
            if parsed is not None:
                rows[parsed[0]] = parsed[1]
        try:
            base = [float(item) for item in rows[str(modes.get("wcs", "G54"))].split(",")]
            shift = [float(item) for item in rows.get("G92", "0,0,0").split(",")]
            tool = float(rows.get("TLO", "0").split(",")[0])
        except (KeyError, ValueError):
            raise DriverError("GRBL's $# answer has no usable work offsets.") from None
        offsets = [base[i] + (shift[i] if i < len(shift) else 0.0) for i in range(len(base))]
        if len(offsets) > 2:
            offsets[2] += tool
        session.wco = tuple(offsets)
        return session.wco

    async def read(self, channel: str) -> Reading:
        unit = self.device.channel_unit(channel)
        if channel in self.reads:
            read_map = self.reads[channel]
            if read_map.setting is not None:
                return Reading(channel, await self._setting(read_map.setting, channel, unit), unit)
            return Reading(channel, await self._status_value(channel, read_map, unit), unit)
        if channel in self.writes:
            return Reading(channel, await self._output(self.writes[channel], unit), unit)
        raise DriverError(f"{self.device.device_id} has no channel {channel!r}.")

    async def _setting(self, number: int, channel: str, unit: str | None) -> float | bool:
        if number not in self.grbl:
            await self._load_settings()
        if number not in self.grbl:
            raise DriverError(f"GRBL has no setting ${number}, or it can't list settings right now.")
        value = self.grbl[number]
        if self.device.read[channel].type == "bool":
            return value == 1
        known = protocol.SETTING_UNITS.get(number)
        return to_unit(value, known, unit, channel) if known and unit else value

    async def _status_value(self, channel: str, read_map: ReadMap, unit: str | None) -> float | str:
        status = await self._status()
        kind = read_map.status
        if kind == "state":
            values = self.device.read[channel].values
            if values and status.state not in values:
                raise DriverError(f"{channel}: GRBL is in state {status.state}, which is not in the file's values.")
            return status.state
        if kind == "alarm":
            return float(self._session().alarm if status.state == "alarm" else 0)
        if kind == "pins":
            return status.pins
        if kind == "feed":
            if status.feed is None:
                raise DriverError("GRBL's status report has no feed rate. Check $10.")
            return to_unit(status.feed, f"{self._length_unit()}/min", unit or "mm/min", channel)
        if kind == "spindle":
            return await self._spindle_rpm(status, unit or "rpm", channel)
        assert kind is not None
        position = await self._position(status, read_map.frame, protocol.AXES.index(kind), channel)
        return to_unit(position, self._length_unit(), unit or "mm", channel)

    async def _position(self, status: Status, frame: str, index: int, channel: str) -> float:
        direct = status.mpos if frame == "machine" else status.wpos
        if direct is not None:
            if index >= len(direct):
                raise DriverError(f"{channel}: this controller reports {len(direct)} axes.")
            return direct[index]
        other = status.wpos if frame == "machine" else status.mpos
        assert other is not None
        offsets = await self._offsets()
        if index >= min(len(other), len(offsets)):
            raise DriverError(f"{channel}: this controller reports {len(other)} axes.")
        return other[index] + offsets[index] if frame == "machine" else other[index] - offsets[index]

    async def _spindle_rpm(self, status: Status, unit: str, channel: str) -> float:
        if status.spindle is not None:
            rpm = status.spindle
        else:
            modes = await self._modes()
            rpm = float(modes.get("speed", 0.0)) if modes.get("spindle") in ("M3", "M4") else 0.0
        return to_unit(rpm, "rpm", unit, channel)

    async def _output(self, write_map: WriteMap, unit: str | None) -> float | bool:
        if write_map.coolant is not None:
            coolant = str((await self._modes()).get("coolant", "M9")).split()
            return ("M8" if write_map.coolant == "flood" else "M7") in coolant
        rpm = await self._spindle_rpm(await self._status(), "rpm", "spindle")
        if write_map.laser is not None:
            return round(rpm / self._max_rpm() * 100.0, 3)
        return to_unit(rpm, "rpm", unit or "rpm", "spindle")

    def _max_rpm(self) -> float:
        top = self.grbl.get(30, 0.0)
        if top <= 0:
            raise DriverError("GRBL's $30 (max spindle speed) is not set, so power can't be scaled.")
        return top

    async def _write(self, channel: str, value: float | bool | str) -> Reading | None:
        write_map = self.writes.get(channel)
        if write_map is None:
            raise DriverError(f"{self.device.device_id} has no write channel {channel!r}.")
        unit = self.device.channel_unit(channel)
        session = self._session()
        if write_map.coolant is not None:
            if not isinstance(value, bool):
                raise DriverError(f"{channel} needs true or false.")
            await self._coolant(write_map.coolant, value)
            return Reading(channel, value, None)
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise DriverError(f"{channel} needs a number.")
        if write_map.laser is not None:
            s_word = float(value) / 100.0 * self._max_rpm()
            code = "M4" if write_map.laser == "dynamic" else "M3"
        else:
            s_word = to_unit(float(value), unit or "rpm", "rpm", channel)
            code = "M3" if write_map.spindle == "cw" else "M4"
            self._check_rpm(channel, s_word)
        if s_word <= 0:
            await self._off("M5", "spindle", "M5")
        else:
            await session.command(f"{code} S{protocol.number(s_word)}")
        session.status_at = 0.0
        return Reading(channel, value, unit)

    def _check_rpm(self, channel: str, rpm: float) -> None:
        top, bottom = self.grbl.get(30), self.grbl.get(31, 0.0)
        if top is not None and rpm > top * (1 + 1e-9):
            raise DriverError(f"{channel} {rpm:g} rpm is above this controller's $30 of {top:g} rpm. Nothing was sent.")
        if 0 < rpm < bottom:
            raise DriverError(f"{channel} {rpm:g} rpm is below the $31 of {bottom:g} rpm. Nothing was sent.")

    async def _off(self, line: str, key: str, already: str) -> None:
        """Turn an output off. In alarm GRBL refuses G-code, and the reset already turned the output off."""
        try:
            await self._session().command(line)
        except GrblError as exc:
            if exc.code != "9" or str((await self._modes()).get(key, "")) != already:
                raise
            self.note = f"{line} skipped in alarm, the output was already off."

    async def _coolant(self, which: str, on: bool) -> None:
        code = "M8" if which == "flood" else "M7"
        if on:
            await self._session().command(code)
            return
        active = set(str((await self._modes()).get("coolant", "M9")).split()) - {"M9", code}
        await self._off("M9", "coolant", "M9")
        for other in sorted(active):
            await self._session().command(other)

    async def _action(self, name: str, args: dict[str, Any]) -> Any:
        action_map = self.actions.get(name)
        if action_map is None:
            raise DriverError(f"{self.device.device_id} has no action {name!r}.")
        session = self._session()
        command = action_map.command
        if command == "home":
            return await self._home(session)
        if command in ("jog", "move"):
            line = self._motion_line(name, action_map, args)
            await session.command(line)
            session.status_at = 0.0
            return {"sent": line, "status": await self._wait_for_idle()}
        if command == "set_work_zero":
            line = f"G10 L20 P0 {channels.ZERO_AXES[str(args.get('axes', 'all'))]}"
            await session.command(line)
            session.wco = None
            return {"sent": line}
        if command == "clear_alarm":
            await session.command("$X")
            session.status_at = 0.0
            return {"sent": "$X"}
        if command == "reset":
            await session.soft_reset()
            return {"sent": "soft reset"}
        byte = {"cancel_jog": protocol.JOG_CANCEL, "hold": protocol.FEED_HOLD, "resume": protocol.CYCLE_START}[command]
        await session.realtime(byte)
        session.status_at = 0.0
        return {"sent": command.replace("_", " ")}

    def _motion_line(self, name: str, action_map: ActionMap, args: dict[str, Any]) -> str:
        specs = self.device.actions[name].args
        words = []
        for axis in protocol.AXES:
            if axis in args:
                millimeters = to_unit(float(args[axis]), specs[axis].unit or "mm", "mm", f"{name}.{axis}")
                words.append(f"{axis.upper()}{protocol.number(millimeters)}")
        if "feed" in args:
            feed = to_unit(float(args["feed"]), specs["feed"].unit or "mm/min", "mm/min", f"{name}.feed")
            if feed <= 0:
                raise DriverError(f"{name} needs a feed above zero. Nothing was sent.")
            words.append(f"F{protocol.number(feed)}")
        default = "relative" if action_map.command == "jog" else "absolute"
        distance = "G91" if (action_map.distance or default) == "relative" else "G90"
        frame = "G53 " if action_map.frame == "machine" and distance == "G90" else ""
        if action_map.command == "jog":
            return f"$J=G21 {distance} {frame}{' '.join(words)}"
        return f"G21 {distance} {frame}{'G0' if action_map.rapid else 'G1'} {' '.join(words)}"

    async def _wait_for_idle(self) -> str:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self.settings.action_wait
        while loop.time() < deadline:
            status = await self._status(0)
            if status.state == "alarm":
                alarm = self._session().alarm
                raise DriverError(f"GRBL raised ALARM:{alarm} ({protocol.alarm_text(alarm)}).")
            if not _moving(status):
                return "done" if status.state == "idle" else status.state
            await asyncio.sleep(POLL_S)
        return "started"

    async def _home(self, session: GrblSession) -> dict[str, str]:
        async with session.lock:
            pending = await session.send("$H")
            try:
                await asyncio.wait_for(asyncio.shield(pending.future), self.settings.action_wait)
            except TimeoutError:
                task = asyncio.create_task(self._finish(pending))
                self._background.add(task)
                task.add_done_callback(self._background.discard)
                return {"sent": "$H", "status": "started"}
        session.status_at = 0.0
        return {"sent": "$H", "status": "done"}

    async def _finish(self, pending: Pending) -> None:
        with contextlib.suppress(DriverError, TimeoutError):
            await asyncio.wait_for(pending.future, 600)

    async def _safe_state(self) -> None:
        session = self._session()
        await session.realtime(protocol.FEED_HOLD)
        loop = asyncio.get_running_loop()
        deadline = loop.time() + HOLD_WAIT_S
        while loop.time() < deadline:
            try:
                status = await asyncio.wait_for(session.status(0), max(0.1, deadline - loop.time()))
            except (TimeoutError, DriverError):
                break
            if not _moving(status):
                break
            await asyncio.sleep(POLL_S)
        await session.soft_reset()

    async def describe(self) -> dict[str, Any] | None:
        if self.session is None or not self.session.link.connected:
            return None
        if not self.grbl:
            await self._load_settings()
        return channels.proposal(self.grbl, self.build, self._length_unit())

    async def health(self) -> Health:
        try:
            session = self._session()
            status = await self._status()
        except (DriverError, TimeoutError) as exc:
            return Health(connected=False, detail=str(exc))
        detail = f"Grbl {session.version or self.build.get('version', '')}, {status.state}"
        if status.state == "alarm" and session.alarm:
            detail += f", ALARM:{session.alarm} ({protocol.alarm_text(session.alarm)})"
        if session.critical:
            detail += ", waiting for a reset"
        return Health(connected=True, detail=detail)

    async def close(self) -> None:
        for background in list(self._background):
            background.cancel()
        session, self.session = self.session, None
        if session is not None:
            await session.close()
