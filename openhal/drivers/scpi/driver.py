"""SCPI instruments over VISA (USB-TMC, LAN VXI-11 and raw socket, serial, GPIB).

Protocol. SCPI (IEEE 488.2 plus the SCPI 1999 standard) is line-based text. Queries end in `?`
and return one reply. Settings return nothing, and failures are reported through the error
queue, read with `SYST:ERR?` until it answers `0,...`. PyVISA with the pyvisa-py backend
handles the transports, or NI-VISA when `visa_library` points at it.

Mapping, per channel in the device file.

    read   { query: "MEAS:VOLT? CH1", parse, scale, offset, unit, on, off, lookup }
    write  { set: "OUTP CH1,{on_off}", get: "OUTP? CH1" }      {value} for every type, {on_off} for bool
    action { command: "APPL CH1,{volts},{amps}" }              placeholders are the argument names

Quirks.

- With `check_errors: true` (the default) every setting is followed by `SYST:ERR?`, and any
  error fails the write with the instrument's own message. The error queue is drained once on
  connect so old errors aren't blamed on the first write.
- After a timeout the driver reopens the session before the next command, because a late reply
  would otherwise be read as the answer to the next query.
- `health()` sends `*OPC?`, which every IEEE 488.2 instrument answers, so a dropped LAN link
  is noticed by the heartbeat.
- pyvisa-py reads a closed raw socket as no data and waits out the timeout, and on Linux a send
  to a closed peer can still succeed. So before each exchange, and after a timeout, the driver
  peeks at the socket, and a closed one marks the connection lost instead of reopening it.
- `describe()` reads `*IDN?` and proposes channels for known power supplies, multimeters,
  loads, generators and scopes (families.py). Proposed writes are `suggested: true`.
- SCPI has no universal emergency command, so the safe state comes from the device file.
"""

from __future__ import annotations

import asyncio
import contextlib
import re
import select
import socket
from collections.abc import Callable
from typing import Any, ClassVar, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from openhal.drivers.base import Discovered, Driver, DriverError, DriverInfo, Health, Reading
from openhal.drivers.scpi import families
from openhal.drivers.serial import mapping
from openhal.spec.models import DeviceFile

T = TypeVar("T")
TERMINATIONS = {"lf": "\n", "crlf": "\r\n", "cr": "\r"}
NO_ERROR = re.compile(r"^\s*[+]?0\s*(,|$)")
USB_RESOURCE = re.compile(r"^USB\d*::(0x[0-9A-Fa-f]+|\d+)::(0x[0-9A-Fa-f]+|\d+)::([^:]+)::", re.IGNORECASE)


class ScpiParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resource: str = Field(min_length=1, max_length=300, description="VISA resource string or auto.")
    visa_library: str = Field(default="@py", max_length=300, description="@py, a NI-VISA path, or file.yaml@sim.")
    timeout: float = 2.0
    termination: Literal["lf", "crlf", "cr"] = "lf"
    check_errors: bool = True
    baud: int | None = Field(default=None, ge=300, le=4_000_000, description="For ASRL resources.")

    @field_validator("timeout", mode="before")
    @classmethod
    def _duration(cls, value: Any) -> float:
        seconds = mapping.duration(value)
        if not 0.05 <= seconds <= 60:
            raise ValueError("timeout must be between 50 ms and 60 s.")
        return seconds


class ReadMap(mapping.ValueMap):
    query: str = Field(max_length=mapping.MAX_TEMPLATE)


class WriteMap(mapping.ValueMap):
    set: str = Field(max_length=mapping.MAX_TEMPLATE)
    get: str | None = Field(default=None, max_length=mapping.MAX_TEMPLATE)


class ActionMap(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    command: str = Field(max_length=mapping.MAX_TEMPLATE)
    on: str = "ON"
    off: str = "OFF"


def _parse(model: type[BaseModel], raw: dict[str, Any] | None, where: str, example: str) -> Any:
    if raw is None:
        raise DriverError(f"{where} needs a map for the scpi driver, for example map: {{ {example} }}.")
    try:
        return model.model_validate(raw)
    except ValidationError as exc:
        problems = "; ".join(f"{'.'.join(str(p) for p in e['loc']) or 'map'}: {e['msg']}" for e in exc.errors())
        raise DriverError(f"{where}.map is not valid for the scpi driver ({problems}).") from exc


def _is_timeout(exc: BaseException) -> bool:
    code = getattr(exc, "error_code", None)
    try:
        from pyvisa import constants

        return code == constants.StatusCode.error_timeout
    except ImportError:  # pragma: no cover - pyvisa is required by this driver
        return False


def _socket_of(inst: Any) -> socket.socket | None:
    """The raw socket behind a pyvisa-py TCPIP SOCKET session, or None for every other session."""
    try:
        session = inst.visalib.sessions[inst.session]
    except (AttributeError, KeyError, TypeError):
        return None
    interface = getattr(session, "interface", None)
    return interface if isinstance(interface, socket.socket) else None


def _peer_closed(inst: Any) -> bool:
    """Whether the instrument closed a raw socket connection cleanly. Never blocks or consumes data.

    Any other socket error is left to the next exchange, which reports it with the exchange's name.
    """
    sock = _socket_of(inst)
    if sock is None or sock.fileno() < 0:
        return False
    try:
        readable, _, _ = select.select([sock], [], [], 0)
        return bool(readable) and sock.recv(1, socket.MSG_PEEK) == b""
    except OSError:
        return False


CLOSED_BY_INSTRUMENT = "the instrument closed the connection"


class ScpiDriver(Driver):
    """Programmable test instruments over USB-TMC, LAN, serial and GPIB."""

    info: ClassVar[DriverInfo] = DriverInfo(
        name="scpi",
        protocols=("SCPI over USB-TMC", "SCPI over LAN (VXI-11, HiSLIP, raw socket)", "SCPI over serial"),
        hazard_default="medium",
        summary="Programmable test instruments over USB, LAN and serial.",
    )
    params_model: ClassVar[type[Any] | None] = ScpiParams

    def __init__(self, device: DeviceFile) -> None:
        super().__init__(device)
        self.settings = ScpiParams.model_validate(device.connect.params)
        self.termination = TERMINATIONS[self.settings.termination]
        self.reads: dict[str, ReadMap] = {}
        self.writes: dict[str, WriteMap] = {}
        self.actions: dict[str, ActionMap] = {}
        self.idn: str | None = None
        self.resource_name: str | None = None
        self._rm: Any = None
        self._inst: Any = None
        self._broken: str | None = None
        self._dirty = False
        self._written: dict[str, Reading] = {}
        self._lock = asyncio.Lock()
        self._check_maps()

    def _check_maps(self) -> None:
        for name, spec in self.device.read.items():
            if spec.type == "image":
                raise DriverError(f"read.{name}: the scpi driver doesn't read images.")
            read_map = _parse(ReadMap, spec.map, f"read.{name}", "query: 'MEAS:VOLT?'")
            mapping.check_template(read_map.query, set(), f"read.{name}.map.query")
            mapping.plain_text(read_map.query, f"read.{name}.map.query")
            self.reads[name] = read_map
        for name, write_spec in self.device.write.items():
            write_map = _parse(WriteMap, write_spec.map, f"write.{name}", "set: 'VOLT {value}', get: 'VOLT?'")
            allowed = {"value", "on_off"} if write_spec.type == "bool" else {"value"}
            mapping.check_template(write_map.set, allowed, f"write.{name}.map.set")
            sample = {"value": mapping.sample(write_spec), "on_off": "ON"}
            mapping.render(write_map.set, {k: v for k, v in sample.items() if k in allowed}, f"write.{name}.map.set")
            if write_map.get is not None:
                mapping.check_template(write_map.get, set(), f"write.{name}.map.get")
                mapping.plain_text(write_map.get, f"write.{name}.map.get")
            self.writes[name] = write_map
        for name, action in self.device.actions.items():
            action_map = _parse(ActionMap, action.map, f"actions.{name}", "command: 'APPL CH1,{volts},{amps}'")
            mapping.check_template(action_map.command, set(action.args), f"actions.{name}.map.command")
            samples = {arg: mapping.sample(spec) for arg, spec in action.args.items()}
            mapping.render(action_map.command, samples, f"actions.{name}.map.command")
            self.actions[name] = action_map

    def _resource_manager(self) -> Any:
        import pyvisa

        if self._rm is None:
            try:
                self._rm = pyvisa.ResourceManager(self.settings.visa_library)
            except (OSError, ValueError, pyvisa.Error) as exc:
                raise DriverError(
                    f"Could not load the VISA library {self.settings.visa_library!r} ({exc}). "
                    "Install the scpi extra, or point visa_library at your NI-VISA installation."
                ) from exc
        return self._rm

    def _open(self) -> None:
        import pyvisa

        rm = self._resource_manager()
        resource = self._resolve(rm)
        kwargs: dict[str, Any] = {
            "read_termination": self.termination,
            "write_termination": self.termination,
            "timeout": round(self.settings.timeout * 1000),
        }
        if self.settings.baud and resource.upper().startswith("ASRL"):
            kwargs["baud_rate"] = self.settings.baud
        try:
            self._inst = rm.open_resource(resource, **kwargs)
        except (pyvisa.Error, OSError, ValueError) as exc:
            raise DriverError(
                f"Could not open {resource} ({exc}). Check the cable or address, and that no other program has it open."
            ) from exc
        self.resource_name = resource
        self._broken = None
        self._dirty = False

    def _resolve(self, rm: Any) -> str:
        if self.settings.resource != "auto":
            return self.settings.resource
        wanted = {item.lower() for item in self.device.match.usb}
        if not wanted:
            raise DriverError("resource: auto needs match.usb in the device file, or give the VISA resource string.")
        found = []
        for name in rm.list_resources():
            usb = _usb_id(name)
            if usb is None or usb not in wanted:
                continue
            serial = USB_RESOURCE.match(name)
            pattern = self.device.match.serial_number
            if pattern and serial and not re.search(pattern, serial[3]):
                continue
            found.append(name)
        if len(found) != 1:
            listed = ", ".join(found) or "none"
            raise DriverError(
                f"resource: auto needs exactly one instrument with USB id {sorted(wanted)}, found {listed}."
            )
        return str(found[0])

    def _close_session(self) -> None:
        inst, self._inst = self._inst, None
        if inst is not None:
            with contextlib.suppress(Exception):
                inst.close()

    async def _call(self, work: Callable[[Any], T], what: str) -> T:
        """Run one blocking VISA exchange in a worker thread, one at a time."""
        async with self._lock:
            if self._broken:
                raise self._lost()
            if self._inst is None:
                raise DriverError(f"{self.device.device_id} is not connected. Connect it first.")
            if _peer_closed(self._inst):
                self._broken = CLOSED_BY_INSTRUMENT
                raise self._lost()
            if self._dirty:
                await asyncio.to_thread(self._reopen)
            try:
                return await asyncio.to_thread(work, self._inst)
            except Exception as exc:
                if _is_timeout(exc):
                    if _peer_closed(self._inst):
                        self._broken = CLOSED_BY_INSTRUMENT
                        raise self._lost() from None
                    self._dirty = True
                    raise TimeoutError(
                        f"{self.resource_name} didn't answer {what} within {self.settings.timeout:g} s. "
                        "Check the command and the termination setting."
                    ) from None
                if isinstance(exc, DriverError):
                    raise
                self._broken = f"{type(exc).__name__}: {exc}"
                raise DriverError(f"{self.resource_name} failed during {what} ({exc}). Check the connection.") from exc

    def _lost(self) -> DriverError:
        return DriverError(f"{self.device.device_id} lost its connection ({self._broken}). Reconnect it.")

    def _reopen(self) -> None:
        self._close_session()
        self._open()

    @classmethod
    async def discover(cls) -> list[Discovered]:
        def listed() -> list[str]:
            try:
                import pyvisa

                return list(pyvisa.ResourceManager("@py").list_resources())
            except Exception:  # noqa: BLE001 (discovery never fails the caller)
                return []

        found = []
        for name in await asyncio.to_thread(listed):
            identifiers = {"resource": name}
            usb = _usb_id(name)
            if usb:
                identifiers["usb"] = usb
            found.append(Discovered(driver="scpi", address=name, identifiers=identifiers))
        return found

    async def identify(self) -> dict[str, str]:
        if self._inst is None:
            return {"resource": self.settings.resource}
        reply = await self._call(lambda inst: str(inst.query("*IDN?")).strip(), "*IDN?")
        self.idn = reply
        identity = families.Identity.parse(reply)
        return {
            "resource": self.resource_name or self.settings.resource,
            "idn": reply,
            "manufacturer": identity.manufacturer,
            "model": identity.model,
            "serial": identity.serial,
            "firmware": identity.firmware,
        }

    async def describe(self) -> dict[str, Any] | None:
        if self._inst is None:
            return None
        if self.idn is None:
            await self.identify()
        assert self.idn is not None
        return families.propose(self.idn)

    async def connect(self) -> None:
        await self.close()
        await asyncio.to_thread(self._open)
        self.idn = await self._call(lambda inst: str(inst.query("*IDN?")).strip(), "*IDN?")
        if self.device.match.scpi_idn and not re.search(self.device.match.scpi_idn, self.idn):
            found = self.idn
            await self.close()
            raise DriverError(
                f"The instrument at {self.resource_name} identifies as {found!r}, "
                f"which doesn't match match.scpi_idn {self.device.match.scpi_idn!r}."
            )
        if self.settings.check_errors:
            await self._call(self._drain_errors, "SYST:ERR?")
        self._written.clear()

    def _drain_errors(self, inst: Any) -> list[str]:
        errors: list[str] = []
        for _ in range(20):
            reply = str(inst.query("SYST:ERR?")).strip()
            if NO_ERROR.match(reply):
                return errors
            errors.append(reply)
        return errors

    async def health(self) -> Health:
        if self._inst is None:
            return Health(connected=False, detail="not connected")
        if self._broken:
            return Health(connected=False, detail=self._broken)
        try:
            await self._call(lambda inst: str(inst.query("*OPC?")), "*OPC?")
        except (DriverError, TimeoutError) as exc:
            return Health(connected=False, detail=str(exc))
        return Health(connected=True, detail=self.idn or "")

    async def close(self) -> None:
        async with self._lock:
            await asyncio.to_thread(self._close_session)

    async def read(self, channel: str) -> Reading:
        unit = self.device.channel_unit(channel)
        if channel in self.reads:
            read_map = self.reads[channel]
            reply = await self._query(read_map.query)
            value = mapping.decode(channel, reply, self.device.read[channel], read_map, f"read.{channel}")
            return Reading(channel, value, unit)
        if channel in self.writes:
            write_map = self.writes[channel]
            if write_map.get is None:
                if self._inst is None:
                    raise DriverError(f"{self.device.device_id} is not connected. Connect it first.")
                last = self._written.get(channel)
                return last if last is not None else Reading(channel, None, unit)
            reply = await self._query(write_map.get)
            value = mapping.decode(channel, reply, self.device.write[channel], write_map, f"write.{channel}")
            return Reading(channel, value, unit)
        raise DriverError(f"{self.device.device_id} has no channel {channel!r}.")

    async def _query(self, command: str) -> str:
        return await self._call(lambda inst: str(inst.query(command)).strip(), command)

    async def _setting(self, command: str) -> None:
        def run(inst: Any) -> list[str]:
            inst.write(command)
            return self._drain_errors(inst) if self.settings.check_errors else []

        errors = await self._call(run, command)
        if errors:
            raise DriverError(f"The instrument rejected {command!r} with {'; '.join(errors)}.")

    async def _write(self, channel: str, value: float | bool | str) -> Reading | None:
        write_map = self.writes.get(channel)
        if write_map is None:
            raise DriverError(f"{self.device.device_id} has no write channel {channel!r}.")
        spec = self.device.write[channel]
        values: dict[str, Any] = {"value": mapping.encode(value, spec, write_map, f"write.{channel}")}
        if spec.type == "bool":
            values["on_off"] = "ON" if value else "OFF"
        command = mapping.render(write_map.set, values, f"write.{channel}")
        self._written.pop(channel, None)
        await self._setting(command)
        reading = Reading(channel, value, self.device.channel_unit(channel))
        self._written[channel] = reading
        return reading

    async def _action(self, name: str, args: dict[str, Any]) -> Any:
        action_map = self.actions.get(name)
        if action_map is None:
            raise DriverError(f"{self.device.device_id} has no action {name!r}.")
        values = {
            arg: (action_map.on if value else action_map.off) if isinstance(value, bool) else value
            for arg, value in args.items()
        }
        command = mapping.render(action_map.command, values, f"actions.{name}")
        await self._setting(command)
        return {"sent": command}


def _usb_id(resource: str) -> str | None:
    match = USB_RESOURCE.match(resource)
    if match is None:
        return None
    vid, pid = (int(part, 16) if part.lower().startswith("0x") else int(part) for part in match.groups()[:2])
    return f"{vid:04x}:{pid:04x}"
