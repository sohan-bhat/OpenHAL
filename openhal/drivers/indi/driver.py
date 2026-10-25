"""INDI telescope mounts, focusers and cameras, with this driver's own XML client.

Protocol (INDI protocol 1.7 white paper and the INDI standard properties). XML handling is in
`protocol.py`, the TCP client and property cache in `session.py`, and the maps in `channels.py`.

- One device file is one INDI device, named in `device`, on an indiserver (TCP 7624). `kind`
  picks the channel conventions, telescope, focuser, camera or generic.
- connect() asks for the device's properties, turns its CONNECTION switch on unless
  `connect_device: false`, and waits until every property the file uses is defined. close()
  leaves the device connected, since another client such as Ekos may be using it.
- Reads come from the property cache the server keeps current by pushing updates. Writes and
  actions send new*Vector with only the changed members and wait for the server's answer. An
  answer in the Alert state fails the command with the device's own message.
- Actions with `wait` follow the property while it is Busy and answer `done`, or `started`
  after `action_wait`.
- BLOBs (images) are never requested, so camera frames are not downloaded.

Safe state. Native, by kind. Telescopes get TELESCOPE_ABORT_MOTION, focusers FOCUS_ABORT_MOTION
and cameras CCD_ABORT_EXPOSURE. A generic device has none, its file's own steps apply.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from typing import Any, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from openhal.drivers.base import Discovered, Driver, DriverError, DriverInfo, Health, Reading
from openhal.drivers.indi import channels, protocol
from openhal.drivers.indi.channels import ActionMap, ReadMap, WriteMap
from openhal.drivers.indi.protocol import Vector
from openhal.drivers.indi.session import IndiSession
from openhal.drivers.serial import mapping
from openhal.spec.models import DeviceFile
from openhal.spec.units import Quantity, UnitError, convert, parse_unit

POLL_S = 0.1
FOLLOW_GRACE_S = 0.3


class IndiParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    host: str = Field(min_length=1, max_length=253)
    port: int = Field(default=7624, ge=1, le=65535)
    device: str = Field(min_length=1, max_length=128)
    kind: Literal["telescope", "focuser", "camera", "generic"] = "telescope"
    timeout: float = 5.0
    action_wait: float = 8.0
    define_wait: float = 5.0
    connect_device: bool = True

    @field_validator("timeout", "action_wait", "define_wait", mode="before")
    @classmethod
    def _duration(cls, value: Any) -> float:
        return mapping.duration(value)

    @model_validator(mode="after")
    def _ranges(self) -> IndiParams:
        checks = (("timeout", 0.1, 30), ("action_wait", 0.1, 9), ("define_wait", 0.1, 30))
        for name, low, high in checks:
            if not low <= getattr(self, name) <= high:
                raise ValueError(f"{name} must be between {low:g} s and {high:g} s.")
        return self


def _convert(value: float, source: str | None, target: str | None, where: str) -> float:
    if not source or not target or source == target:
        return value
    try:
        return convert(Quantity(value, parse_unit(source)), target)
    except UnitError as exc:
        raise DriverError(f"{where}: {exc}") from exc


class IndiDriver(Driver):
    """Telescope mounts, focusers and cameras on an INDI server."""

    info: ClassVar[DriverInfo] = DriverInfo(
        name="indi",
        protocols=("INDI XML protocol 1.7 over TCP",),
        hazard_default="medium",
        summary="INDI mounts, focusers and cameras. Number, switch and text properties, abort as the safe state.",
        safe_state_support="native",
        conformance="full",
    )
    params_model: ClassVar[type[Any] | None] = IndiParams
    discovery_hosts: ClassVar[list[tuple[str, int]]] = [("127.0.0.1", 7624)]
    discovery_wait: ClassVar[float] = 1.0

    def __init__(self, device: DeviceFile) -> None:
        super().__init__(device)
        self.settings = IndiParams.model_validate(device.connect.params)
        self.session: IndiSession | None = None
        self.reads: dict[str, ReadMap] = {}
        self.writes: dict[str, WriteMap] = {}
        self.actions: dict[str, ActionMap] = {}
        self._check_maps()

    def _check_maps(self) -> None:
        kind = self.settings.kind
        for name, spec in self.device.read.items():
            if spec.type == "image":
                raise DriverError(f"read.{name}: the INDI driver doesn't download images.")
            read_map = channels.validate(ReadMap, spec.map, channels.READS.get(kind, {}).get(name), f"read.{name}")
            if read_map.state and spec.type not in ("bool", "enum"):
                raise DriverError(f"read.{name}: a property state reads as a bool (busy) or an enum.")
            if read_map.state and spec.type == "enum" and set(spec.values) - set(protocol.STATES):
                raise DriverError(f"read.{name}: states are {', '.join(protocol.STATES)}.")
            self.reads[name] = read_map
        for name, write_spec in self.device.write.items():
            write_map = channels.validate(
                WriteMap, write_spec.map, channels.WRITES.get(kind, {}).get(name), f"write.{name}"
            )
            if write_map.element is None and write_spec.type != "enum":
                raise DriverError(f"write.{name}: give map.element, or make it an enum of switch members.")
            self.writes[name] = write_map
        for name, action in self.device.actions.items():
            action_map = channels.validate(
                ActionMap, action.map, channels.ACTIONS.get(kind, {}).get(name), f"actions.{name}"
            )
            if set(action.args) != set(action_map.args):
                raise DriverError(
                    f"actions.{name}: the arguments {sorted(action.args)} must match "
                    f"map.args {sorted(action_map.args)}."
                )
            self.actions[name] = action_map

    def _device(self, item: Any = None) -> str:
        return item.device if item is not None and item.device else self.settings.device

    def _properties(self) -> set[tuple[str, str]]:
        found: set[tuple[str, str]] = set()
        for item in [*self.reads.values(), *self.writes.values()]:
            found.add((self._device(item), item.property))
        for action in self.actions.values():
            found.add((self._device(action), action.property))
            found.update((self._device(step), step.property) for step in action.before)
        if self.settings.kind in channels.SAFE:
            found.add((self.settings.device, channels.SAFE[self.settings.kind][0]))
        return found

    def _session(self) -> IndiSession:
        if self.session is None:
            raise DriverError(f"{self.device.device_id} is not connected. Connect it first.")
        self.session.require()
        return self.session

    @classmethod
    async def discover(cls) -> list[Discovered]:
        found: list[Discovered] = []
        for host, port in cls.discovery_hosts:
            session = IndiSession(host, port, timeout=1.0)
            try:
                await session.open()
                await session.send(protocol.get_properties())
                await asyncio.sleep(cls.discovery_wait)
            except DriverError:
                continue
            finally:
                await session.close()
            for device in sorted({key[0] for key in session.vectors}):
                info = session.vectors.get((device, "DRIVER_INFO"))
                members = {name: str(member.value) for name, member in (info.members.items() if info else [])}
                identifiers = {"indi.device": device}
                if "DRIVER_NAME" in members:
                    identifiers["indi.driver"] = members["DRIVER_NAME"]
                if "DRIVER_INTERFACE" in members:
                    identifiers["indi.interface"] = members["DRIVER_INTERFACE"]
                found.append(
                    Discovered(
                        driver="indi", address=f"indi://{host}:{port}/{device}", identifiers=identifiers, label=device
                    )
                )
        return found

    async def identify(self) -> dict[str, str]:
        identity = {"server": f"{self.settings.host}:{self.settings.port}", "device": self.settings.device}
        if self.session is None:
            return identity
        info = self.session.vectors.get((self.settings.device, "DRIVER_INFO"))
        if info is not None:
            identity.update({name.lower(): str(member.value) for name, member in info.members.items()})
        return identity

    async def connect(self) -> None:
        await self.close()
        session = IndiSession(self.settings.host, self.settings.port, timeout=self.settings.timeout)
        await session.open()
        self.session = session
        for device in sorted({device for device, _ in self._properties()} | {self.settings.device}):
            await session.send(protocol.get_properties(device))
        main = self.settings.device
        if not await session.wait_for(lambda: (main, "CONNECTION") in session.vectors, self.settings.define_wait):
            session.vector(main, "CONNECTION")
        if self.settings.connect_device:
            await self._connect_device(session)
        wanted = self._properties()
        if not await session.wait_for(lambda: wanted <= set(session.vectors), self.settings.define_wait):
            missing = sorted(f"{device}.{name}" for device, name in wanted - set(session.vectors))
            raise DriverError(
                f"The INDI server never defined {', '.join(missing)}. Check the device and the file's maps."
            )

    async def _connect_device(self, session: IndiSession) -> None:
        connection = session.vector(self.settings.device, "CONNECTION")
        member = connection.members.get("CONNECT")
        if member is None:
            raise DriverError(f"{self.settings.device}'s CONNECTION switch has no CONNECT member.")
        if member.value is True and connection.state == "ok":
            return
        await self._send(connection, {"CONNECT": True})

        def done() -> bool:
            latest = session.vectors.get((self.settings.device, "CONNECTION"))
            return latest is not None and latest.state != "busy" and latest.members["CONNECT"].value is True

        if not await session.wait_for(done, self.settings.timeout):
            reason = connection.message or session.messages.get(self.settings.device, "it didn't say why")
            raise DriverError(f"{self.settings.device} didn't connect to its hardware ({reason}).")

    def _vector(self, item: Any) -> Vector:
        vector = self._session().vector(self._device(item), item.property)
        if vector.invalid:
            raise DriverError(f"{vector.device}.{vector.name} sent a value the driver can't read ({vector.invalid}).")
        return vector

    async def read(self, channel: str) -> Reading:
        if channel in self.reads:
            read_map = self.reads[channel]
            vector = self._vector(read_map)
            if read_map.state:
                kind = self.device.read[channel].type
                value: Any = vector.state == "busy" if kind == "bool" else vector.state
                return Reading(channel, value, None, at=vector.at)
            return self._reading(channel, vector, read_map.element, read_map.unit, read_map.scale)
        if channel in self.writes:
            write_map = self.writes[channel]
            vector = self._vector(write_map)
            return self._reading(channel, vector, write_map.element, write_map.unit, write_map.scale)
        raise DriverError(f"{self.device.device_id} has no channel {channel!r}.")

    def _reading(self, channel: str, vector: Vector, element: str | None, unit: str | None, scale: float) -> Reading:
        spec = self.device.read.get(channel) or self.device.write[channel]
        target = self.device.channel_unit(channel)
        if element is None:
            if vector.kind != "switch":
                raise DriverError(f"{channel}: {vector.name} is a {vector.kind} vector, so the map needs an element.")
            on = [name.lower() for name, member in vector.members.items() if member.value is True]
            value = on[0] if on else None
            if value is not None and spec.type == "enum" and value not in spec.values:
                raise DriverError(
                    f"{channel}: {vector.name} has {value} on, which is not one of {', '.join(spec.values)}."
                )
            return Reading(channel, value, None, at=vector.at)
        member = vector.members.get(element)
        if member is None:
            raise DriverError(
                f"{vector.device}.{vector.name} has no member {element}. It has {', '.join(vector.members)}."
            )
        raw = member.value
        if spec.type == "number":
            if not isinstance(raw, float):
                raise DriverError(f"{channel}: {vector.name}.{element} is not a number.")
            number = _convert(raw * scale, unit, target, channel)
            span = getattr(spec, "range", None)
            suspect = span is not None and not span[0] <= number <= span[1]
            return Reading(channel, number, target, at=vector.at, suspect=suspect)
        if spec.type == "bool":
            if not isinstance(raw, bool):
                raise DriverError(f"{channel}: {vector.name}.{element} is not a switch.")
            return Reading(channel, raw, None, at=vector.at)
        text = str(raw)
        if spec.type == "enum" and text not in spec.values:
            raise DriverError(f"{channel}: {vector.name}.{element} is {text!r}, not one of {', '.join(spec.values)}.")
        return Reading(channel, text, None, at=vector.at)

    async def _send(self, vector: Vector, values: dict[str, float | bool | str]) -> None:
        """Send new values and wait for the server's answer. Alert fails with the device's message."""
        if vector.perm == "ro":
            raise DriverError(f"{vector.device}.{vector.name} is read only. Nothing was sent.")
        for name in values:
            if name not in vector.members:
                raise DriverError(f"{vector.device}.{vector.name} has no member {name}. Nothing was sent.")
        session = self._session()
        before = vector.at
        sent_at = time.time()
        await session.send(protocol.new_vector(vector.kind, vector.device, vector.name, values))
        current = session.vectors

        def answered() -> bool:
            latest = current.get((vector.device, vector.name))
            return latest is not None and latest.at > before and latest.at >= sent_at - 0.001

        if not await session.wait_for(answered, self.settings.timeout):
            raise TimeoutError(
                f"{vector.device} didn't answer the change to {vector.name} within {self.settings.timeout:g} s."
            )
        latest = current[(vector.device, vector.name)]
        if latest.state == "alert":
            reason = latest.message or session.messages.get(vector.device, "no reason given")
            raise DriverError(f"{vector.device} refused the change to {vector.name} ({reason}).")

    def _encode(
        self, value: float | bool | str, unit: str | None, protocol_unit: str | None, scale: float, where: str
    ) -> float | bool | str:
        if isinstance(value, bool) or not isinstance(value, int | float):
            return value
        return _convert(float(value), unit, protocol_unit, where) / scale

    async def _write(self, channel: str, value: float | bool | str) -> Reading | None:
        write_map = self.writes.get(channel)
        if write_map is None:
            raise DriverError(f"{self.device.device_id} has no write channel {channel!r}.")
        vector = self._vector(write_map)
        spec = self.device.write[channel]
        if vector.kind == "switch":
            values = self._switch_values(channel, vector, write_map, value)
        else:
            assert write_map.element is not None
            values = {write_map.element: self._encode(value, spec.unit, write_map.unit, write_map.scale, channel)}
        await self._send(vector, values)
        return Reading(channel, value, spec.unit)

    def _switch_values(
        self, channel: str, vector: Vector, write_map: WriteMap, value: Any
    ) -> dict[str, float | bool | str]:
        if write_map.element is None:
            matches = [name for name in vector.members if name.lower() == str(value)]
            if not matches:
                raise DriverError(f"{channel}: {vector.name} has no member {value!r}. Nothing was sent.")
            return {matches[0]: True}
        if not isinstance(value, bool):
            raise DriverError(f"{channel} needs true or false.")
        if value or vector.rule == "AnyOfMany":
            return {write_map.element: value}
        if write_map.off is not None:
            return {write_map.off: True}
        if vector.rule == "OneOfMany":
            raise DriverError(
                f"{channel}: {vector.name} is one of many, so turning it off needs map.off. Nothing was sent."
            )
        return {write_map.element: False}

    async def _action(self, name: str, args: dict[str, Any]) -> Any:
        action_map = self.actions.get(name)
        if action_map is None:
            raise DriverError(f"{self.device.device_id} has no action {name!r}.")
        for step in action_map.before:
            await self._send(self._vector(step), {step.element: True})
        vector = self._vector(action_map)
        if action_map.element is not None:
            values: dict[str, float | bool | str] = {action_map.element: True}
        else:
            specs = self.device.actions[name].args
            values = {
                arg.element: self._encode(args[key], specs[key].unit, arg.unit, arg.scale, f"{name}.{key}")
                for key, arg in action_map.args.items()
            }
        await self._send(vector, values)
        sent = {"sent": f"{vector.name} {' '.join(values)}"}
        if not action_map.wait:
            return sent
        return {**sent, "status": await self._follow(vector.device, vector.name)}

    async def _follow(self, device: str, name: str) -> str:
        """Follow a property while it is Busy. An update that was already on its way counts only after a grace time."""
        session = self._session()
        loop = asyncio.get_running_loop()
        start = loop.time()
        deadline = start + self.settings.action_wait
        saw_busy = False
        while (remaining := deadline - loop.time()) > 0:
            current = session.vectors.get((device, name))
            if current is None:
                return "done"
            state = current.state
            if state == "alert":
                raise DriverError(f"{device} reported {name} failed ({current.message or 'no reason given'}).")
            if state == "busy":
                saw_busy = True
            elif saw_busy or loop.time() - start >= FOLLOW_GRACE_S:
                return "done"

            def changed(seen: Vector = current, was: str = state) -> bool:
                return seen.state != was

            await session.wait_for(changed, min(remaining, POLL_S))
        return "started"

    async def _safe_state(self) -> None:
        if self.settings.kind not in channels.SAFE:
            return
        name, element = channels.SAFE[self.settings.kind]
        vector = self._session().vector(self.settings.device, name)
        await self._send(vector, {element: True})

    async def describe(self) -> dict[str, Any] | None:
        if self.session is None or not self.session.connected:
            return None
        from openhal.drivers.indi.describe import proposal

        return proposal(self.session, self.settings.device, self.settings.kind)

    async def health(self) -> Health:
        if self.session is None:
            return Health(connected=False, detail="not connected")
        if not self.session.connected:
            return Health(connected=False, detail=self.session.lost or "not connected")
        device = self.settings.device
        if device in self.session.removed:
            return Health(connected=False, detail=f"the server removed {device}")
        connection = self.session.vectors.get((device, "CONNECTION"))
        member = connection.members.get("CONNECT") if connection else None
        if self.settings.connect_device and (member is None or member.value is not True):
            return Health(connected=False, detail=f"{device} is disconnected from its hardware")
        return Health(connected=True, detail=f"{device} on {self.settings.host}:{self.settings.port}")

    async def close(self) -> None:
        session, self.session = self.session, None
        if session is not None:
            with contextlib.suppress(Exception):
                await session.close()
