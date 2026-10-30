"""ASCOM Alpaca astronomy devices over REST, with UDP discovery.

Protocol (ASCOM Alpaca API reference, ascom-standards.org/api). The REST client is in
`client.py`, the channel maps and the conventions per device type in `channels.py`, discovery
in `discovery.py` and the describe() proposal in `describe.py`.

- One device file is one Alpaca device, `device_type` and `device_number` in `connect`. A map
  may reach another device on the same server, for example a dome next to its mount.
- connect() checks `/management/apiversions` for version 1 and that every device the file
  uses is configured, then sets `Connected` to true on each. close() leaves it as it is, so
  other clients such as an imaging program keep their connection, unless `disconnect_on_close`.
- Reads are GET requests. Writes and actions are PUT requests with the parameter names exactly
  as the reference spells them (`RightAscension`, `Position`, `Id`, `State`).
- Right ascension and sidereal time arrive in hours and are reported in degrees (hours times 15),
  since OpenHAL's unit registry has no hour angle unit.
- Actions with a `wait` property (`slewing`, `ismoving`) poll it until false and return `done`,
  or return `started` after `action_wait`.

Safe state. Native. Telescopes and domes get AbortSlew, focusers Halt and cameras
AbortExposure. A parked mount returns InvalidWhileParked for AbortSlew, which counts as safe.
`park_on_stop: true` also parks a telescope or dome after the abort. Switches have no native
safe state, the device file's own steps set them.
"""

from __future__ import annotations

import asyncio
import math
from typing import Any, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from openhal.drivers.alpaca import channels, discovery
from openhal.drivers.alpaca.channels import ActionMap, ReadMap, WriteMap
from openhal.drivers.alpaca.client import INVALID_WHILE_PARKED, AlpacaClient, AlpacaError, form
from openhal.drivers.base import Discovered, Driver, DriverError, DriverInfo, Health, Reading
from openhal.drivers.serial import mapping
from openhal.spec.models import DeviceFile
from openhal.spec.units import Quantity, UnitError, convert, parse_unit

POLL_S = 0.1
DeviceType = Literal[
    "telescope",
    "focuser",
    "camera",
    "switch",
    "dome",
    "filterwheel",
    "rotator",
    "covercalibrator",
    "safetymonitor",
    "observingconditions",
]


class AlpacaParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    host: str = Field(min_length=1, max_length=253)
    port: int = Field(default=11111, ge=1, le=65535)
    scheme: Literal["http", "https"] = "http"
    device_type: DeviceType = "telescope"
    device_number: int = Field(default=0, ge=0, le=999)
    timeout: float = 5.0
    action_wait: float = 8.0
    park_on_stop: bool = False
    disconnect_on_close: bool = False

    @field_validator("timeout", "action_wait", mode="before")
    @classmethod
    def _duration(cls, value: Any) -> float:
        return mapping.duration(value)

    @model_validator(mode="after")
    def _ranges(self) -> AlpacaParams:
        if not 0.1 <= self.timeout <= 30:
            raise ValueError("timeout must be between 100 ms and 30 s.")
        if not 0.1 <= self.action_wait <= 9:
            raise ValueError("action_wait must be between 100 ms and 9 s.")
        return self


def _convert(value: float, source: str | None, target: str | None, where: str) -> float:
    if not source or not target or source == target:
        return value
    try:
        return convert(Quantity(value, parse_unit(source)), target)
    except UnitError as exc:
        raise DriverError(f"{where}: {exc}") from exc


class AlpacaDriver(Driver):
    """Telescopes, focusers, cameras, switches and domes that use ASCOM Alpaca."""

    info: ClassVar[DriverInfo] = DriverInfo(
        name="alpaca",
        protocols=("ASCOM Alpaca REST", "Alpaca UDP discovery"),
        hazard_default="medium",
        summary="ASCOM Alpaca mounts, focusers, cameras, switches and domes. Abort and park as actions.",
        safe_state_support="native",
        conformance="full",
    )
    params_model: ClassVar[type[Any] | None] = AlpacaParams
    discovery_targets: ClassVar[list[tuple[str, int]]] = [discovery.BROADCAST]
    discovery_wait: ClassVar[float] = 1.0
    discovery_transport: ClassVar[Any] = None

    def __init__(self, device: DeviceFile, *, http_transport: Any = None) -> None:
        super().__init__(device)
        self.settings = AlpacaParams.model_validate(device.connect.params)
        self._transport = http_transport
        self.client: AlpacaClient | None = None
        self.server: dict[str, Any] = {}
        self.configured: list[dict[str, Any]] = []
        self.reads: dict[str, ReadMap] = {}
        self.writes: dict[str, WriteMap] = {}
        self.actions: dict[str, ActionMap] = {}
        self._check_maps()

    @property
    def base_url(self) -> str:
        return f"{self.settings.scheme}://{self.settings.host}:{self.settings.port}"

    def _check_maps(self) -> None:
        kind = self.settings.device_type
        for name, spec in self.device.read.items():
            if spec.type == "image":
                raise DriverError(f"read.{name}: the Alpaca driver doesn't download images.")
            read_map = channels.validate(ReadMap, spec.map, channels.default_read(kind, name), f"read.{name}")
            if read_map.states is not None and spec.type == "enum" and set(spec.values) - set(read_map.states):
                raise DriverError(f"read.{name}: the values must come from {read_map.states}.")
            self.reads[name] = read_map
        for name, write_spec in self.device.write.items():
            write_map = channels.validate(WriteMap, write_spec.map, channels.default_write(kind, name), f"write.{name}")
            if write_map.integer and write_spec.type != "number":
                raise DriverError(f"write.{name}: integer only applies to number channels.")
            self.writes[name] = write_map
        for name, action in self.device.actions.items():
            action_map = channels.validate(
                ActionMap, action.map, channels.default_action(kind, name), f"actions.{name}"
            )
            missing = set(action.args) - set(action_map.params)
            if missing:
                raise DriverError(f"actions.{name}: no Alpaca parameter for {sorted(missing)}. Add map.params.")
            unused = set(action_map.params) - set(action.args)
            if unused:
                raise DriverError(f"actions.{name}: {action_map.method} needs the arguments {sorted(unused)}.")
            self.actions[name] = action_map

    def _target(self, item: ReadMap | WriteMap | ActionMap | None = None) -> tuple[str, int]:
        kind = item.device if item is not None and item.device else self.settings.device_type
        number = item.number if item is not None and item.number is not None else self.settings.device_number
        return kind, number

    def _targets(self) -> list[tuple[str, int]]:
        found = {self._target()}
        items: list[ReadMap | WriteMap | ActionMap] = [*self.reads.values(), *self.writes.values()]
        for item in [*items, *self.actions.values()]:
            found.add(self._target(item))
        return sorted(found)

    @staticmethod
    def _path(target: tuple[str, int], member: str) -> str:
        return f"/api/v1/{target[0]}/{target[1]}/{member}"

    def _client(self) -> AlpacaClient:
        if self.client is None:
            raise DriverError(f"{self.device.device_id} is not connected. Connect it first.")
        return self.client

    @classmethod
    async def discover(cls) -> list[Discovered]:
        found: list[Discovered] = []
        for host, port in await discovery.probe(cls.discovery_targets, cls.discovery_wait):
            client = AlpacaClient(f"http://{host}:{port}", timeout=2.0, transport=cls.discovery_transport)
            try:
                server = await client.get("/management/v1/description")
                devices = await client.get("/management/v1/configureddevices")
            except (DriverError, TimeoutError):
                continue
            finally:
                await client.close()
            for item in devices if isinstance(devices, list) else []:
                kind = str(item.get("DeviceType", "")).lower()
                number = item.get("DeviceNumber", 0)
                found.append(
                    Discovered(
                        driver="alpaca",
                        address=f"http://{host}:{port}/api/v1/{kind}/{number}",
                        identifiers={
                            "alpaca.device_type": kind,
                            "alpaca.device_number": str(number),
                            "alpaca.unique_id": str(item.get("UniqueID", "")),
                            "alpaca.server": str(server.get("ServerName", "")) if isinstance(server, dict) else "",
                        },
                        label=str(item.get("DeviceName") or f"Alpaca {kind} {number}"),
                    )
                )
        return found

    async def identify(self) -> dict[str, str]:
        identity = {"server": self.base_url, "device": f"{self.settings.device_type}/{self.settings.device_number}"}
        if self.client is None:
            return identity
        target = self._target()
        for member in ("name", "description", "driverinfo", "driverversion", "interfaceversion"):
            try:
                identity[member] = str(await self.client.get(self._path(target, member)))
            except AlpacaError:
                continue
        if self.server:
            identity["server_name"] = str(self.server.get("ServerName", ""))
            identity["manufacturer"] = str(self.server.get("Manufacturer", ""))
        return identity

    async def connect(self) -> None:
        await self.close()
        self.client = AlpacaClient(self.base_url, timeout=self.settings.timeout, transport=self._transport)
        versions = await self.client.get("/management/apiversions")
        if not isinstance(versions, list) or 1 not in versions:
            raise DriverError(f"The Alpaca server at {self.base_url} doesn't offer API version 1 ({versions!r}).")
        server = await self.client.get("/management/v1/description")
        self.server = server if isinstance(server, dict) else {}
        configured = await self.client.get("/management/v1/configureddevices")
        self.configured = configured if isinstance(configured, list) else []
        offered = {(str(item.get("DeviceType", "")).lower(), item.get("DeviceNumber")) for item in self.configured}
        for target in self._targets():
            if target not in offered:
                listed = ", ".join(f"{kind}/{number}" for kind, number in sorted(offered, key=str)) or "none"
                raise DriverError(f"The Alpaca server has no {target[0]} {target[1]}. It offers {listed}.")
            await self.client.put(self._path(target, "connected"), {"Connected": "True"})
            if await self.client.get(self._path(target, "connected")) is not True:
                raise DriverError(f"The {target[0]} {target[1]} didn't connect. Check its driver on the server.")

    async def read(self, channel: str) -> Reading:
        if channel in self.reads:
            read_map = self.reads[channel]
            raw = await self._get_read(read_map, self.device.read[channel].type)
            return self._reading(channel, raw, read_map.unit, read_map.scale, read_map.states)
        if channel in self.writes:
            write_map = self.writes[channel]
            raw = await self._get_write(write_map, self.device.write[channel].type)
            return self._reading(channel, raw, write_map.unit, write_map.scale, None)
        raise DriverError(f"{self.device.device_id} has no channel {channel!r}.")

    async def _get_read(self, read_map: ReadMap, kind: str) -> Any:
        target = self._target(read_map)
        if read_map.switch is not None:
            member = "getswitch" if kind == "bool" else "getswitchvalue"
            return await self._client().get(self._path(target, member), {"Id": str(read_map.switch)})
        assert read_map.property is not None
        return await self._client().get(self._path(target, read_map.property))

    async def _get_write(self, write_map: WriteMap, kind: str) -> Any:
        target = self._target(write_map)
        if write_map.switch is not None:
            member = "getswitch" if kind == "bool" else "getswitchvalue"
            return await self._client().get(self._path(target, member), {"Id": str(write_map.switch)})
        getter = write_map.readback or write_map.property
        assert getter is not None
        return await self._client().get(self._path(target, getter))

    def _reading(self, channel: str, raw: Any, source: str | None, scale: float, states: list[str] | None) -> Reading:
        spec = self.device.read.get(channel) or self.device.write[channel]
        unit = self.device.channel_unit(channel)
        if spec.type == "bool":
            if not isinstance(raw, bool):
                raise DriverError(f"{channel}: the device sent {raw!r}, not true or false.")
            return Reading(channel, raw, None)
        if spec.type == "number":
            if isinstance(raw, bool) or not isinstance(raw, int | float) or not math.isfinite(raw):
                raise DriverError(f"{channel}: the device sent {raw!r}, not a number.")
            value = _convert(float(raw) * scale, source, unit, channel)
            low_high = getattr(spec, "range", None)
            suspect = low_high is not None and not low_high[0] <= value <= low_high[1]
            return Reading(channel, value, unit, suspect=suspect)
        if states is not None:
            if isinstance(raw, bool) or not isinstance(raw, int) or not 0 <= raw < len(states):
                raise DriverError(f"{channel}: the device reported state {raw!r}, which is not 0 to {len(states) - 1}.")
            raw = states[raw]
        text = str(raw)
        if spec.type == "enum" and text not in spec.values:
            raise DriverError(f"{channel}: the device reported {text!r}, which is not one of {', '.join(spec.values)}.")
        return Reading(channel, text, None)

    def _encode(
        self, value: Any, unit: str | None, target_unit: str | None, scale: float, integer: bool, where: str
    ) -> str:
        if isinstance(value, bool) or not isinstance(value, int | float):
            return form(value)
        number = _convert(float(value), unit, target_unit, where) / scale
        if integer:
            if abs(number - round(number)) > 1e-6:
                raise DriverError(
                    f"{where}: {number:g} is not a whole number, and the device takes integers. Nothing was sent."
                )
            return str(round(number))
        return form(number)

    async def _write(self, channel: str, value: float | bool | str) -> Reading | None:
        write_map = self.writes.get(channel)
        if write_map is None:
            raise DriverError(f"{self.device.device_id} has no write channel {channel!r}.")
        spec = self.device.write[channel]
        target = self._target(write_map)
        text = self._encode(value, spec.unit, write_map.unit, write_map.scale, write_map.integer, channel)
        if write_map.switch is not None:
            member, param = ("setswitch", "State") if spec.type == "bool" else ("setswitchvalue", "Value")
            await self._client().put(self._path(target, member), {"Id": str(write_map.switch), param: text})
        else:
            setter = write_map.property or write_map.method
            assert setter is not None
            assert write_map.param is not None
            await self._client().put(self._path(target, setter), {write_map.param: text})
        return Reading(channel, value, spec.unit)

    async def _action(self, name: str, args: dict[str, Any]) -> Any:
        action_map = self.actions.get(name)
        if action_map is None:
            raise DriverError(f"{self.device.device_id} has no action {name!r}.")
        specs = self.device.actions[name].args
        fields = {
            param.name: self._encode(
                args[arg], specs[arg].unit, param.unit, param.scale, param.integer, f"{name}.{arg}"
            )
            for arg, param in action_map.params.items()
        }
        target = self._target(action_map)
        await self._client().put(self._path(target, action_map.method), fields)
        if action_map.wait is None:
            return {"sent": action_map.method}
        return {"sent": action_map.method, "status": await self._wait(target, action_map.wait)}

    async def _wait(self, target: tuple[str, int], member: str) -> str:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self.settings.action_wait
        while loop.time() < deadline:
            if await self._client().get(self._path(target, member)) is False:
                return "done"
            await asyncio.sleep(POLL_S)
        return "started"

    async def _safe_state(self) -> None:
        problems: list[str] = []
        for target in self._targets():
            methods = channels.SAFE_METHODS.get(target[0], ())
            if self.settings.park_on_stop and target[0] in ("telescope", "dome"):
                methods = (*methods, "park")
            for method in methods:
                try:
                    await self._client().put(self._path(target, method))
                except AlpacaError as exc:
                    if exc.number == INVALID_WHILE_PARKED and method == "abortslew":
                        continue
                    problems.append(f"{target[0]} {method}: {exc}")
                except (DriverError, TimeoutError) as exc:
                    problems.append(f"{target[0]} {method}: {exc}")
        if problems:
            raise DriverError("; ".join(problems))

    async def describe(self) -> dict[str, Any] | None:
        if self.client is None:
            return None
        from openhal.drivers.alpaca.describe import proposal

        return await proposal(self.client, self._target(), self.server)

    async def health(self) -> Health:
        if self.client is None:
            return Health(connected=False, detail="not connected")
        try:
            connected = await self.client.get(self._path(self._target(), "connected"))
        except (DriverError, TimeoutError) as exc:
            return Health(connected=False, detail=str(exc))
        if connected is not True:
            return Health(connected=False, detail="the device reports Connected false. Reconnect it.")
        return Health(connected=True, detail=str(self.server.get("ServerName", self.base_url)))

    async def close(self) -> None:
        client, self.client = self.client, None
        if client is None:
            return
        if self.settings.disconnect_on_close:
            for target in self._targets():
                try:
                    await client.put(self._path(target, "connected"), {"Connected": "False"})
                except (DriverError, TimeoutError):
                    continue
        await client.close()
