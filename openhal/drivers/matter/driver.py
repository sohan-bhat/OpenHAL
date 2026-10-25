"""Matter devices through the Matter Server WebSocket API (python-matter-server and the matter.js server).

The Matter Server owns the Matter fabric. OpenHAL is a client of the server, so commissioning,
Thread and Wi-Fi credentials and OTA updates stay in the server and its frontend. The protocol
client is `openhal.drivers.matter.api`.

How channels map to Matter.

- A read channel names an attribute by `endpoint`, `cluster` and `attribute` (or `path:
  1/6/0`), with `scale`, `offset` and the device `unit`, a `bit` to read one flag of a bitmap, or
  a `lookup` from enum numbers to words. Reads come from the server's subscription, so they cost
  no round trip and carry the time the value arrived.
- A channel under `write` either writes its attribute with `write_attribute`, or runs a cluster
  command with `device_command`. `command` and `payload` send one command with `{value}` in the
  payload, and `on_command` and `off_command` pick a command for bool channels. The attribute is
  read back for the channel's value.
- An action runs one cluster command with its arguments placed in `payload` by `{name}`.

Values are rounded to whole raw units, because Matter attributes are integers.

Safe state. From the device file. Matter has no fabric-wide emergency command.
"""

from __future__ import annotations

import math
import re
import time
from typing import Annotated, Any, ClassVar, Final

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, ValidationError, field_validator, model_validator

from openhal.drivers.base import Driver, DriverError, DriverInfo, Health, Reading
from openhal.drivers.http import values as v
from openhal.drivers.matter import clusters
from openhal.drivers.matter.api import MatterClient
from openhal.spec.models import ArgSpec, DeviceFile, ReadChannel, WriteChannel
from openhal.spec.units import Quantity, UnitError, convert, parse_duration, parse_unit

PATH: Final = re.compile(r"^(\d{1,3})/(\d{1,10})/(\d{1,10})$")
STATUS: Final = {
    0x01: "FAILURE",
    0x7E: "UNSUPPORTED_ACCESS",
    0x81: "UNSUPPORTED_COMMAND",
    0x86: "UNSUPPORTED_ATTRIBUTE",
    0x87: "CONSTRAINT_ERROR",
    0x88: "UNSUPPORTED_WRITE",
    0x8C: "NOT_FOUND",
    0xC6: "NEEDS_TIMED_INTERACTION",
}


def _seconds(value: Any) -> Any:
    if isinstance(value, int | float) and not isinstance(value, bool):
        return float(value)
    return parse_duration(value)


Duration = Annotated[float, BeforeValidator(_seconds), Field(gt=0, le=60)]


class MatterParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str = Field(pattern=r"^wss?://[^\s/]+(:\d+)?(/\S*)?$")
    node: int = Field(ge=1)
    timeout: Duration = 5.0


class _Target(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    path: str | None = None
    endpoint: int | None = Field(default=None, ge=0, le=65534)
    cluster: int | None = Field(default=None, ge=0)
    attribute: int | None = Field(default=None, ge=0)

    @model_validator(mode="before")
    @classmethod
    def _resolve(cls, data: Any) -> Any:
        if not isinstance(data, dict) or data.get("path") is None:
            return data
        match = PATH.match(str(data["path"]))
        if match is None:
            raise ValueError("path must be endpoint/cluster/attribute in decimal, such as 1/6/0.")
        if any(data.get(key) is not None for key in ("endpoint", "cluster", "attribute")):
            raise ValueError("give path or endpoint, cluster and attribute, not both.")
        endpoint, cluster, attribute = (int(part) for part in match.groups())
        return {**data, "endpoint": endpoint, "cluster": cluster, "attribute": attribute}

    @property
    def key(self) -> str:
        return f"{self.endpoint}/{self.cluster}/{self.attribute}"


class ReadMap(_Target):
    scale: float = 1.0
    offset: float = 0.0
    unit: str | None = None
    bit: int | None = Field(default=None, ge=0, le=63)
    lookup: dict[int, str] = {}

    @field_validator("scale")
    @classmethod
    def _scale(cls, value: float) -> float:
        if value == 0 or not math.isfinite(value):
            raise ValueError("scale must be a finite number other than zero.")
        return value

    @field_validator("unit")
    @classmethod
    def _unit(cls, value: str | None) -> str | None:
        if value is not None:
            try:
                parse_unit(value)
            except UnitError as exc:
                raise ValueError(str(exc)) from exc
        return value

    @model_validator(mode="after")
    def _complete(self) -> ReadMap:
        if None in (self.endpoint, self.cluster, self.attribute):
            raise ValueError("name the attribute with path, or with endpoint, cluster and attribute.")
        return self


class WriteMap(ReadMap):
    command: str | None = Field(default=None, pattern=r"^[A-Z][A-Za-z0-9]{0,63}$")
    payload: dict[str, Any] = {}
    on_command: str | None = Field(default=None, pattern=r"^[A-Z][A-Za-z0-9]{0,63}$")
    off_command: str | None = Field(default=None, pattern=r"^[A-Z][A-Za-z0-9]{0,63}$")
    timed_ms: int | None = Field(default=None, ge=1, le=10_000)


class ActionMap(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    endpoint: int = Field(ge=0, le=65534)
    cluster: int = Field(ge=0)
    command: str = Field(pattern=r"^[A-Z][A-Za-z0-9]{0,63}$")
    payload: dict[str, Any] = {}
    timed_ms: int | None = Field(default=None, ge=1, le=10_000)


class MatterDriver(Driver):
    """One Matter node through a Matter Server. Attributes as channels, cluster commands as actions."""

    info: ClassVar[DriverInfo] = DriverInfo(
        name="matter",
        protocols=("Matter through the Matter Server WebSocket API",),
        hazard_default="low",
        summary="Matter lights, plugs, sensors, thermostats and covers through a Matter Server.",
        safe_state_support="file",
        conformance="full",
    )
    params_model: ClassVar[type[Any] | None] = MatterParams

    def __init__(self, device: DeviceFile) -> None:
        super().__init__(device)
        self.settings = MatterParams.model_validate(device.connect.params)
        self.client: MatterClient | None = None
        self.reads: dict[str, ReadMap] = {}
        self.writes: dict[str, WriteMap] = {}
        self.actions: dict[str, ActionMap] = {}
        for name, spec in device.read.items():
            self.reads[name] = self._parse(ReadMap, f"read.{name}", spec.map)
            self._check_type(f"read.{name}", spec, self.reads[name])
        for name, wspec in device.write.items():
            write_map = self._parse(WriteMap, f"write.{name}", wspec.map)
            self._check_type(f"write.{name}", wspec, write_map)
            if (write_map.on_command is None) != (write_map.off_command is None):
                raise DriverError(f"write.{name}: give both on_command and off_command, or neither.")
            if write_map.on_command is not None and wspec.type != "bool":
                raise DriverError(f"write.{name}: on_command and off_command are for bool channels.")
            if write_map.command is not None and "value" not in v.placeholders(write_map.payload):
                raise DriverError(f"write.{name}: payload needs a {{value}} placeholder for the channel's value.")
            if v.placeholders(write_map.payload) - {"value"}:
                raise DriverError(f"write.{name}: payload can only use {{value}}.")
            self.writes[name] = write_map
        for name, action in device.actions.items():
            action_map = self._parse(ActionMap, f"actions.{name}", action.map)
            used = v.placeholders(action_map.payload)
            if used != set(action.args):
                raise DriverError(
                    f"actions.{name}: payload must place every argument the action declares "
                    f"({', '.join(sorted(action.args)) or 'none'}) with {{name}}, and no others."
                )
            self.actions[name] = action_map

    @staticmethod
    def _parse[M: BaseModel](model: type[M], where: str, raw: dict[str, Any] | None) -> M:
        if raw is None:
            raise DriverError(f"{where} needs a map, for example map: {{ path: 1/6/0 }}. describe() proposes them.")
        try:
            return model.model_validate(raw)
        except ValidationError as exc:
            problems = "; ".join(f"{'.'.join(map(str, e['loc'])) or 'map'}: {e['msg']}" for e in exc.errors())
            raise DriverError(f"{where} has an invalid matter map. {problems}") from None

    @staticmethod
    def _check_type(where: str, spec: ReadChannel | WriteChannel, read_map: ReadMap) -> None:
        if spec.type == "image":
            raise DriverError(f"{where}: Matter attributes are not images.")
        if spec.type == "enum":
            missing = [value for value in spec.values if value not in read_map.lookup.values()]
            if not read_map.lookup or missing:
                raise DriverError(f"{where} needs map.lookup from attribute numbers to {', '.join(spec.values)}.")
        if read_map.bit is not None and spec.type != "bool":
            raise DriverError(f"{where}: bit reads one flag, so the channel needs type bool.")
        if spec.type == "number" and read_map.unit and spec.unit:
            try:
                convert(Quantity(1.0, parse_unit(read_map.unit)), spec.unit)
            except UnitError:
                raise DriverError(f"{where}: map.unit {read_map.unit} doesn't convert to {spec.unit}.") from None

    @property
    def _where(self) -> str:
        return f"Matter node {self.settings.node} on {self.settings.url}"

    async def identify(self) -> dict[str, str]:
        identity = {"server": self.settings.url, "node": str(self.settings.node)}
        client = self.client
        if client is None:
            return identity
        for key, path in (("vendor", "0/40/1"), ("product", "0/40/3"), ("software", "0/40/10"), ("serial", "0/40/15")):
            if client.attributes.get(path) not in (None, ""):
                identity[key] = str(client.attributes[path])
        if client.server.get("sdk_version"):
            identity["sdk"] = str(client.server["sdk_version"])
        return identity

    async def connect(self) -> None:
        await self.close()
        client = MatterClient(self.settings.url, self.settings.node, timeout=self.settings.timeout)
        await client.open()
        self.client = client
        try:
            self._check_node(client)
        except DriverError:
            await self.close()
            raise

    def _check_node(self, client: MatterClient) -> None:
        clusters_seen = {"/".join(key.split("/")[:2]) for key in client.attributes}
        for name, read_map in [*self.reads.items(), *self.writes.items()]:
            if read_map.key not in client.attributes:
                raise DriverError(
                    f"{name}: node {self.settings.node} has no attribute {read_map.key}. describe() lists them."
                )
        for name, write_map in self.writes.items():
            if (
                write_map.command or write_map.on_command
            ) and f"{write_map.endpoint}/{write_map.cluster}" not in clusters_seen:
                raise DriverError(f"write.{name}: endpoint {write_map.endpoint} has no cluster {write_map.cluster}.")
        for name, action_map in self.actions.items():
            if f"{action_map.endpoint}/{action_map.cluster}" not in clusters_seen:
                raise DriverError(
                    f"actions.{name}: endpoint {action_map.endpoint} has no cluster {action_map.cluster}."
                )

    async def close(self) -> None:
        client, self.client = self.client, None
        if client is not None:
            await client.close()

    async def health(self) -> Health:
        client = self.client
        if client is None:
            return Health(connected=False, detail="not connected")
        if not client.connected:
            return Health(connected=False, detail=f"{self._where} {client.lost}")
        if not client.available:
            return Health(connected=False, detail=f"{self._where} is unavailable. Check its power and network.")
        return Health(connected=True, detail=self._where)

    def _open(self) -> MatterClient:
        client = self.client
        if client is None or not client.connected:
            raise DriverError(f"{self._where} is not connected. Connect it first.")
        return client

    async def read(self, channel: str) -> Reading:
        read_map = self.reads.get(channel) or self.writes.get(channel)
        if read_map is None:
            raise DriverError(f"This matter device has no channel {channel!r}.")
        client = self._open()
        if not client.available:
            raise DriverError(f"{self._where} is unavailable, so {channel} has no current value.")
        spec = self.device.write.get(channel) or self.device.read[channel]
        unit = self.device.channel_unit(channel)
        raw = client.attributes.get(read_map.key)
        at = client.stamps.get(read_map.key, time.time())
        if raw is None:
            return Reading(channel, None, unit=unit, at=at)
        value = self._decode(raw, spec, read_map, f"{read_map.key} for {channel}")
        suspect = isinstance(value, float) and spec.type == "number" and _outside(value, spec)
        return Reading(channel, value, unit=unit, at=at, suspect=suspect)

    @staticmethod
    def _decode(raw: Any, spec: ReadChannel | WriteChannel, read_map: ReadMap, where: str) -> float | bool | str:
        if spec.type == "bool":
            if read_map.bit is not None:
                if isinstance(raw, bool) or not isinstance(raw, int):
                    raise DriverError(f"{where} reported {raw!r}, not a bitmap.")
                return bool((raw >> read_map.bit) & 1)
            if isinstance(raw, bool) or raw in (0, 1):
                return bool(raw)
            raise DriverError(f"{where} reported {raw!r}, which is not true or false.")
        if spec.type == "enum":
            if isinstance(raw, bool) or not isinstance(raw, int) or raw not in read_map.lookup:
                raise DriverError(f"{where} reported {raw!r}, which map.lookup doesn't name.")
            return read_map.lookup[raw]
        if spec.type == "string":
            return v.to_text(raw)
        value = v.to_number(raw, where) * read_map.scale + read_map.offset
        if read_map.unit and spec.unit and read_map.unit != spec.unit:
            value = convert(Quantity(value, parse_unit(read_map.unit)), spec.unit)
        return value

    @staticmethod
    def _raw(value: Any, spec: WriteChannel | ArgSpec, read_map: ReadMap | None) -> Any:
        if isinstance(value, bool) or spec.type != "number":
            if spec.type == "enum" and read_map is not None:
                return next(number for number, word in read_map.lookup.items() if word == value)
            return value
        number = float(value)
        if read_map is None:
            return round(number) if abs(number - round(number)) < 1e-9 else number
        if read_map.unit and spec.unit and read_map.unit != spec.unit:
            number = convert(Quantity(number, parse_unit(spec.unit)), read_map.unit)
        return round((number - read_map.offset) / read_map.scale)

    async def _command(
        self, endpoint: int, cluster: int, command: str, payload: dict[str, Any], timed_ms: int | None
    ) -> Any:
        client = self._open()
        args: dict[str, Any] = {
            "node_id": self.settings.node,
            "endpoint_id": endpoint,
            "cluster_id": cluster,
            "command_name": command,
            "payload": payload,
        }
        if timed_ms is not None:
            args["timed_request_timeout_ms"] = timed_ms
        return await client.call("device_command", **args)

    async def _write(self, channel: str, value: float | bool | str) -> Reading | None:
        write_map = self.writes.get(channel)
        if write_map is None:
            raise DriverError(f"This matter device has no write channel {channel!r}.")
        client = self._open()
        spec = self.device.write[channel]
        endpoint, cluster = write_map.endpoint, write_map.cluster
        assert endpoint is not None
        assert cluster is not None
        if write_map.on_command is not None and write_map.off_command is not None:
            command = write_map.on_command if value else write_map.off_command
            await self._command(endpoint, cluster, command, {}, write_map.timed_ms)
            return None
        raw = self._raw(value, spec, write_map)
        if write_map.command is not None:
            payload = v.render(write_map.payload, {"value": raw})
            await self._command(endpoint, cluster, write_map.command, payload, write_map.timed_ms)
            return None
        result = await client.call(
            "write_attribute", node_id=self.settings.node, attribute_path=write_map.key, value=raw
        )
        for status in result if isinstance(result, list) else []:
            code = status.get("Status", 0) if isinstance(status, dict) else 0
            if code:
                name = STATUS.get(code, f"status 0x{code:02X}")
                raise DriverError(f"{self._where} refused the value for {write_map.key} ({name}).")
        return None

    async def _action(self, name: str, args: dict[str, Any]) -> Any:
        action_map = self.actions.get(name)
        if action_map is None:
            raise DriverError(f"This matter device has no action {name!r}.")
        spec = self.device.actions[name]
        filled = {arg: self._raw(value, spec.args[arg], None) for arg, value in args.items()}
        payload = v.render(action_map.payload, filled)
        result = await self._command(
            action_map.endpoint, action_map.cluster, action_map.command, payload, action_map.timed_ms
        )
        return {"sent": action_map.command, "result": result}

    async def describe(self) -> dict[str, Any] | None:
        client = self.client
        if client is None or not client.connected:
            return None
        sections: dict[str, dict[str, Any]] = {"read": {}, "write": {}, "actions": {}}
        seen = sorted(
            {(int(key.split("/")[0]), int(key.split("/")[1])) for key in client.attributes if PATH.match(key)}
        )
        for endpoint, cluster in seen:
            for key, spec in clusters.proposals(endpoint, cluster).items():
                section, name = key.split(".", 1)
                channel = name if endpoint <= 1 else f"{name}_ep{endpoint}"
                if section != "read":
                    spec = {**spec, "suggested": True}
                sections[section].setdefault(channel, spec)
        product = client.attributes.get("0/40/3") or f"Matter node {self.settings.node}"
        device = {"name": str(product), "manufacturer": client.attributes.get("0/40/1")}
        return {
            "device": {key: value for key, value in device.items() if value},
            **{section: entries for section, entries in sections.items() if entries},
            "notes": "Proposed from the node's clusters. Scales follow the Matter specification. Limits are suggested.",
        }


def _outside(value: float, spec: ReadChannel | WriteChannel) -> bool:
    limits = getattr(spec, "range", None)
    return bool(limits is not None and not limits[0] <= value <= limits[1])
