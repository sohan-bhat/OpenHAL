"""OPC UA servers through asyncua, for PLCs, process equipment and LADS lab devices.

Protocol (OPC UA Parts 4, 6 and 8, through the asyncua client). The maps are in `channels.py`,
units in `units.py` and the describe() proposal in `describe.py`.

- One device file is one OPC UA server endpoint. Channels name variable nodes and actions name
  methods, with node ids in the standard string form. `nsu=` ids are resolved on connect.
- connect() checks every node the file names. Variables must exist, changed ones must be
  writable for this user, and methods must exist with as many inputs as the map lists.
- Units come from each variable's EngineeringUnits (UNECE codes), unless the map gives one.
  A channel whose unit can't be converted from the node's unit fails on connect, so a
  degF node can never be read as degC by mistake.
- Reads check the value's status. Bad fails the read, Uncertain marks it suspect.
- Changes send a Variant of the node's own data type. Integer nodes return an error for values
  that aren't whole. Method calls send inputs in the order the map's `inputs` lists them.

Safe state. OPC UA has no general emergency behavior, so the driver has none of its own. Put the
equipment's own stop (a method or setpoints of 0) in the device file's safe state.
"""

from __future__ import annotations

import asyncio
import contextlib
import math
import os
from collections.abc import Awaitable
from typing import Any, ClassVar, TypeVar

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from openhal.drivers.base import Discovered, Driver, DriverError, DriverInfo, Health, Reading
from openhal.drivers.opcua import channels, units
from openhal.drivers.opcua.channels import ActionMap, ReadMap, WriteMap
from openhal.drivers.serial import mapping
from openhal.spec.models import DeviceFile
from openhal.spec.units import Quantity, UnitError, convert, parse_unit

T = TypeVar("T")
SERVER_STATE = "i=2259"
BUILD_INFO = {
    "product": "i=2261",
    "product_uri": "i=2262",
    "manufacturer": "i=2263",
    "version": "i=2264",
    "build": "i=2265",
}
INTEGERS = {
    "SByte": (-(2**7), 2**7 - 1),
    "Byte": (0, 2**8 - 1),
    "Int16": (-(2**15), 2**15 - 1),
    "UInt16": (0, 2**16 - 1),
    "Int32": (-(2**31), 2**31 - 1),
    "UInt32": (0, 2**32 - 1),
    "Int64": (-(2**63), 2**63 - 1),
    "UInt64": (0, 2**64 - 1),
}


class OpcuaParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    endpoint: str = Field(pattern=r"^opc\.tcp://[^\s/]+(/\S*)?$", max_length=300)
    timeout: float = 4.0
    user: str | None = Field(default=None, max_length=120)
    token_env: str | None = Field(default=None, pattern=r"^[A-Z_][A-Z0-9_]{0,63}$")
    security: str | None = Field(default=None, max_length=500, description="asyncua security string")
    browse_depth: int = Field(default=3, ge=1, le=6)

    @field_validator("timeout", mode="before")
    @classmethod
    def _duration(cls, value: Any) -> float:
        return mapping.duration(value)

    @model_validator(mode="after")
    def _ranges(self) -> OpcuaParams:
        if not 0.1 <= self.timeout <= 30:
            raise ValueError("timeout must be between 100 ms and 30 s.")
        if self.token_env and not self.user:
            raise ValueError("token_env holds the password for user, so give user too.")
        return self


def _convert(value: float, source: str | None, target: str | None, where: str) -> float:
    if not source or not target or source == target:
        return value
    try:
        return convert(Quantity(value, parse_unit(source)), target)
    except UnitError as exc:
        raise DriverError(f"{where}: {exc}") from exc


class _Variable:
    """A checked variable node with its unit, range and data type."""

    def __init__(self, node: Any, unit: str | None, span: tuple[float, float] | None, kind: Any) -> None:
        self.node = node
        self.unit = unit
        self.span = span
        self.kind = kind


class OpcuaDriver(Driver):
    """Variables and methods on an OPC UA server."""

    info: ClassVar[DriverInfo] = DriverInfo(
        name="opcua",
        protocols=("OPC UA binary over TCP (opc.tcp)",),
        hazard_default="medium",
        summary="OPC UA servers. Variables with engineering units as channels, methods as actions.",
        safe_state_support="file",
        conformance="full",
    )
    params_model: ClassVar[type[Any] | None] = OpcuaParams
    discovery_urls: ClassVar[list[str]] = ["opc.tcp://127.0.0.1:4840"]

    def __init__(self, device: DeviceFile) -> None:
        super().__init__(device)
        self.settings = OpcuaParams.model_validate(device.connect.params)
        self.client: Any = None
        self.namespaces: list[str] = []
        self.reads: dict[str, ReadMap] = {}
        self.writes: dict[str, WriteMap] = {}
        self.actions: dict[str, ActionMap] = {}
        self.variables: dict[str, _Variable] = {}
        self.methods: dict[str, tuple[Any, Any, list[Any]]] = {}
        for name, spec in device.read.items():
            if spec.type == "image":
                raise DriverError(f"read.{name}: the OPC UA driver doesn't read images.")
            self.reads[name] = channels.validate(ReadMap, spec.map, f"read.{name}")
        for name, write_spec in device.write.items():
            self.writes[name] = channels.validate(WriteMap, write_spec.map, f"write.{name}")
        for name, action in device.actions.items():
            action_map = channels.validate(ActionMap, action.map, f"actions.{name}")
            if sorted(action_map.inputs) != sorted(action.args) or len(set(action_map.inputs)) != len(
                action_map.inputs
            ):
                raise DriverError(f"actions.{name}: map.inputs must list each argument once, in the method's order.")
            self.actions[name] = action_map

    async def request(self, call: Awaitable[T], what: str) -> T:
        """Run one asyncua call and turn its failures into DriverError or TimeoutError."""
        from asyncua.ua.uaerrors import UaError, UaStatusCodeError

        try:
            return await asyncio.wait_for(call, self.settings.timeout)
        except TimeoutError:
            raise TimeoutError(
                f"The OPC UA server sent no reply to {what} within {self.settings.timeout:g} s."
            ) from None
        except UaStatusCodeError as exc:
            raise DriverError(f"The OPC UA server returned an error for {what} ({type(exc).__name__}, {exc}).") from exc
        except (ConnectionError, OSError, UaError) as exc:
            raise DriverError(f"The OPC UA connection failed during {what} ({exc}). Reconnect it.") from exc

    def _client(self) -> Any:
        if self.client is None:
            raise DriverError(f"{self.device.device_id} is not connected. Connect it first.")
        return self.client

    @classmethod
    async def discover(cls) -> list[Discovered]:
        from asyncua.client.client import Client

        found: list[Discovered] = []
        for url in cls.discovery_urls:
            client = Client(url, timeout=1.0)
            try:
                servers = await asyncio.wait_for(client.connect_and_find_servers(), 2.0)
            except Exception:  # noqa: BLE001, S112
                continue
            for server in servers:
                name = getattr(getattr(server, "ApplicationName", None), "Text", None) or ""
                for address in server.DiscoveryUrls or []:
                    found.append(
                        Discovered(
                            driver="opcua",
                            address=str(address),
                            identifiers={
                                "opcua.application_uri": str(server.ApplicationUri or ""),
                                "opcua.product_uri": str(server.ProductUri or ""),
                            },
                            label=str(name) or str(address),
                        )
                    )
        return found

    async def identify(self) -> dict[str, str]:
        identity = {"endpoint": self.settings.endpoint}
        if self.client is None:
            return identity
        for key, node in BUILD_INFO.items():
            with contextlib.suppress(DriverError, TimeoutError):
                identity[key] = str(await self.request(self.client.get_node(node).read_value(), f"BuildInfo {key}"))
        return identity

    async def connect(self) -> None:
        from asyncua.client.client import Client

        await self.close()
        client = Client(self.settings.endpoint, timeout=self.settings.timeout)
        if self.settings.user:
            client.set_user(self.settings.user)
            if self.settings.token_env:
                password = os.environ.get(self.settings.token_env)
                if not password:
                    raise DriverError(f"Set the {self.settings.token_env} environment variable to the OPC UA password.")
                client.set_password(password)
        if self.settings.security:
            await self.request(client.set_security_string(self.settings.security), "setting up security")
        await self.request(client.connect(), f"the connection to {self.settings.endpoint}")
        self.client = client
        try:
            self.namespaces = list(await self.request(client.get_namespace_array(), "the namespace array"))
            await self._check_nodes(client)
        except BaseException:
            await self.close()
            raise

    async def _check_nodes(self, client: Any) -> None:
        from asyncua import ua

        self.variables.clear()
        self.methods.clear()
        for name, item in [*self.reads.items(), *self.writes.items()]:
            node = client.get_node(channels.resolve(item.node, self.namespaces))
            where = f"{name} ({item.node})"
            node_class = await self.request(node.read_node_class(), f"the node class of {where}")
            if node_class != ua.NodeClass.Variable:
                raise DriverError(f"{where} is a {node_class.name}, not a variable.")
            eu, span = await self.properties(node, where, strict=item.unit is None)
            unit = item.unit or eu
            channel_unit = self.device.channel_unit(name)
            if unit and channel_unit:
                try:
                    convert(Quantity(1.0, parse_unit(unit)), channel_unit)
                except UnitError:
                    raise DriverError(
                        f"{where} is in {unit}, which doesn't convert to the file's {channel_unit}."
                    ) from None
            kind = await self.request(node.read_data_type_as_variant_type(), f"the data type of {where}")
            if name in self.writes:
                access = await self.request(node.get_user_access_level(), f"the access level of {where}")
                if ua.AccessLevel.CurrentWrite not in access:
                    raise DriverError(f"{where} is read only for this user, so it can't be a write channel.")
            self.variables[name] = _Variable(node, unit, span, kind)
        for name, action in self.actions.items():
            parent = client.get_node(channels.resolve(action.object, self.namespaces))
            method = client.get_node(channels.resolve(action.method, self.namespaces))
            where = f"actions.{name} ({action.method})"
            node_class = await self.request(method.read_node_class(), f"the node class of {where}")
            if node_class != ua.NodeClass.Method:
                raise DriverError(f"{where} is a {node_class.name}, not a method.")
            arguments = await self._inputs(method, where)
            if len(arguments) != len(action.inputs):
                raise DriverError(f"{where} takes {len(arguments)} inputs, and map.inputs lists {len(action.inputs)}.")
            self.methods[name] = (parent, method, arguments)

    async def properties(
        self, node: Any, where: str, *, strict: bool = True
    ) -> tuple[str | None, tuple[float, float] | None]:
        """The node's unit from EngineeringUnits and its EURange. Unknown units raise unless `strict` is off."""
        eu: str | None = None
        span: tuple[float, float] | None = None
        for prop in await self.request(node.get_properties(), f"the properties of {where}"):
            name = (await self.request(prop.read_browse_name(), f"a property of {where}")).Name
            if name == "EngineeringUnits":
                information = await self.request(prop.read_value(), f"the EngineeringUnits of {where}")
                eu = units.from_eu(information)
                if eu is None and strict:
                    text = getattr(getattr(information, "DisplayName", None), "Text", information)
                    raise DriverError(
                        f"{where} reports the unit {text!r}, which OpenHAL doesn't support. Set map.unit."
                    )
            elif name == "EURange":
                value = await self.request(prop.read_value(), f"the EURange of {where}")
                low, high = getattr(value, "Low", None), getattr(value, "High", None)
                if isinstance(low, int | float) and isinstance(high, int | float) and low <= high:
                    span = (float(low), float(high))
        return eu, span

    async def _inputs(self, method: Any, where: str) -> list[Any]:
        from asyncua import ua

        for prop in await self.request(method.get_properties(), f"the properties of {where}"):
            if (await self.request(prop.read_browse_name(), f"a property of {where}")).Name == "InputArguments":
                arguments = await self.request(prop.read_value(), f"the InputArguments of {where}")
                kinds = []
                for argument in arguments or []:
                    data_type = getattr(argument, "DataType", None)
                    identifier = getattr(data_type, "Identifier", None)
                    namespace = getattr(data_type, "NamespaceIndex", 0)
                    kinds.append(
                        ua.VariantType(identifier)
                        if namespace == 0 and isinstance(identifier, int) and 0 < identifier <= 25
                        else None
                    )
                return kinds
        return []

    async def read(self, channel: str) -> Reading:
        variable = self.variables.get(channel)
        if variable is None:
            if channel not in self.reads and channel not in self.writes:
                raise DriverError(f"{self.device.device_id} has no channel {channel!r}.")
            raise DriverError(f"{self.device.device_id} is not connected. Connect it first.")
        self._client()
        item = self.reads.get(channel) or self.writes[channel]
        value = await self.request(variable.node.read_data_value(raise_on_bad_status=False), f"reading {channel}")
        status = value.StatusCode
        if status is not None and status.is_bad():
            raise DriverError(f"{channel} reads as {status.name} on the server. Check the device behind it.")
        uncertain = status is not None and status.is_uncertain()
        raw = value.Value.Value if value.Value is not None else None
        spec = self.device.read.get(channel) or self.device.write[channel]
        unit = self.device.channel_unit(channel)
        at = value.SourceTimestamp.timestamp() if value.SourceTimestamp else None
        stamp = {"at": at} if at else {}
        if spec.type == "number":
            if isinstance(raw, bool) or not isinstance(raw, int | float) or not math.isfinite(raw):
                raise DriverError(f"{channel}: the server sent {raw!r}, not a number.")
            number = _convert(float(raw) * item.scale, variable.unit, unit, channel)
            span = getattr(spec, "range", None)
            outside = span is not None and not span[0] <= number <= span[1]
            return Reading(channel, number, unit, suspect=uncertain or outside, **stamp)
        if spec.type == "bool":
            if not isinstance(raw, bool):
                raise DriverError(f"{channel}: the server sent {raw!r}, not true or false.")
            return Reading(channel, raw, None, suspect=uncertain, **stamp)
        text = str(raw)
        if spec.type == "enum" and text not in spec.values:
            raise DriverError(f"{channel}: the server reported {text!r}, which is not one of {', '.join(spec.values)}.")
        return Reading(channel, text, None, suspect=uncertain, **stamp)

    def _variant(self, value: Any, kind: Any, where: str) -> Any:
        from asyncua import ua

        name = getattr(kind, "name", "")
        if name == "Boolean":
            if not isinstance(value, bool):
                raise DriverError(f"{where} is a Boolean node and needs true or false. Nothing was sent.")
            return ua.Variant(value, kind)
        if name in INTEGERS:
            if isinstance(value, bool) or not isinstance(value, int | float) or abs(value - round(value)) > 1e-6:
                raise DriverError(
                    f"{where} is an {name} node and needs a whole number, not {value!r}. Nothing was sent."
                )
            low, high = INTEGERS[name]
            if not low <= round(value) <= high:
                raise DriverError(f"{where}: {round(value)} doesn't fit in {name}. Nothing was sent.")
            return ua.Variant(round(value), kind)
        if name in ("Float", "Double"):
            if isinstance(value, bool) or not isinstance(value, int | float):
                raise DriverError(f"{where} is a {name} node and needs a number. Nothing was sent.")
            return ua.Variant(float(value), kind)
        if name in ("String", "LocalizedText"):
            return ua.Variant(str(value), ua.VariantType.String)
        if kind is None:
            return ua.Variant(value)
        raise DriverError(f"{where} has the data type {name}, which this driver can't send.")

    async def _write(self, channel: str, value: float | bool | str) -> Reading | None:
        from asyncua import ua

        variable = self.variables.get(channel)
        item = self.writes.get(channel)
        if item is None:
            raise DriverError(f"{self.device.device_id} has no write channel {channel!r}.")
        if variable is None:
            raise DriverError(f"{self.device.device_id} is not connected. Connect it first.")
        spec = self.device.write[channel]
        raw: Any = value
        if spec.type == "number" and not isinstance(value, bool) and isinstance(value, int | float):
            raw = _convert(float(value), spec.unit, variable.unit, channel) / item.scale
        variant = self._variant(raw, variable.kind, channel)
        await self.request(variable.node.write_value(ua.DataValue(variant)), f"the change to {channel}")
        return Reading(channel, value, spec.unit)

    async def _action(self, name: str, args: dict[str, Any]) -> Any:
        action = self.actions.get(name)
        if action is None or name not in self.methods:
            raise DriverError(f"{self.device.device_id} has no action {name!r}, or it is not connected.")
        parent, method, kinds = self.methods[name]
        inputs = [self._variant(args[arg], kinds[index], f"{name}.{arg}") for index, arg in enumerate(action.inputs)]
        result = await self.request(parent.call_method(method, *inputs), f"the method {action.method}")
        return {"sent": action.method, "result": _jsonable(result)}

    async def describe(self) -> dict[str, Any] | None:
        if self.client is None:
            return None
        from openhal.drivers.opcua.describe import proposal

        return await proposal(self, self.client, self.settings.browse_depth)

    async def health(self) -> Health:
        if self.client is None:
            return Health(connected=False, detail="not connected")
        try:
            state = await self.request(self.client.get_node(SERVER_STATE).read_value(), "the server state")
        except (DriverError, TimeoutError) as exc:
            return Health(connected=False, detail=str(exc))
        if int(state) != 0:
            return Health(connected=False, detail=f"the server state is {getattr(state, 'name', state)}, not Running")
        return Health(connected=True, detail=self.settings.endpoint)

    async def close(self) -> None:
        client, self.client = self.client, None
        self.variables.clear()
        self.methods.clear()
        if client is not None:
            with contextlib.suppress(Exception):
                await asyncio.wait_for(client.disconnect(), 2.0)


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, bool | int | float | str):
        return value
    if isinstance(value, list | tuple):
        return [_jsonable(item) for item in value]
    return str(value)
