"""SiLA 2 lab devices through the official sila2 Python package.

Protocol (SiLA 2 Part A and Part B, through sila2's dynamic SilaClient). The maps and SiLA data
types are in `channels.py`.

- One device file is one SiLA server. The client loads every feature the server implements from
  its Feature Definitions, so no generated code is needed.
- connect() checks every feature, property, command and parameter the file names, and their
  types. Units come from SiLA Unit constraints unless the map gives one, and a channel whose unit
  can't be converted from the SiLA unit fails on connect.
- Unobservable properties are read on demand. Observable properties are streams. The driver
  subscribes on connect and keeps the newest value, so a read costs no round trip. Until the
  first value arrives, a read requests the current one from the server.
- SiLA properties are read only. A channel changes through a command with one parameter and is
  read back from a property. Actions run commands. An observable command runs up to
  `action_wait` and returns `done`, or returns `started` and keeps running on the server.
- Defined execution errors fail the command with the error's identifier and message.

The sila2 client is blocking gRPC, so every call runs in a worker thread with a deadline.

Safe state. SiLA has no general emergency behavior, so the driver has none of its own. Put the
device's own stop commands in the device file's safe state.
"""

from __future__ import annotations

import asyncio
import contextlib
import math
import os
import time
from pathlib import Path
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from openhal.drivers.base import Discovered, Driver, DriverError, DriverInfo, Health, Reading
from openhal.drivers.serial import mapping
from openhal.drivers.serial.mapping import device_unit
from openhal.drivers.sila2 import bootstrap, channels
from openhal.drivers.sila2.channels import ActionMap, ReadMap, WriteMap
from openhal.spec.models import DeviceFile
from openhal.spec.units import Quantity, UnitError, convert, parse_unit

POLL_S = 0.05
CONNECT_BUDGET_S = 8.0
SUPPORTED = frozenset({"Real", "Integer", "Boolean", "String", "Structure"})


class Sila2Params(BaseModel):
    model_config = ConfigDict(extra="forbid")

    host: str = Field(min_length=1, max_length=253)
    port: int = Field(default=50052, ge=1, le=65535)
    insecure: bool = False
    ca_env: str | None = Field(default=None, pattern=r"^[A-Z_][A-Z0-9_]{0,63}$")
    timeout: float = 5.0
    action_wait: float = 8.0

    @field_validator("timeout", "action_wait", mode="before")
    @classmethod
    def _duration(cls, value: Any) -> float:
        return mapping.duration(value)

    @model_validator(mode="after")
    def _ranges(self) -> Sila2Params:
        if not 0.1 <= self.timeout <= 30:
            raise ValueError("timeout must be between 100 ms and 30 s.")
        if not 0.1 <= self.action_wait <= 9:
            raise ValueError("action_wait must be between 100 ms and 9 s.")
        if self.insecure and self.ca_env:
            raise ValueError("ca_env is for encrypted connections, so drop it or insecure.")
        return self


def _convert(value: float, source: str | None, target: str | None, where: str) -> float:
    if not source or not target or source == target:
        return value
    try:
        return convert(Quantity(value, parse_unit(source)), target)
    except UnitError as exc:
        raise DriverError(f"{where}: {exc}") from exc


class _Binding:
    """A checked property or command with its SiLA type and unit."""

    def __init__(self, member: Any, kind: str, unit: str | None, observable: bool = False) -> None:
        self.member = member
        self.kind = kind
        self.unit = unit
        self.observable = observable


class Sila2Driver(Driver):
    """SiLA 2 servers. Properties as reads, observable properties as streams, commands as actions."""

    info: ClassVar[DriverInfo] = DriverInfo(
        name="sila2",
        protocols=("SiLA 2 over gRPC",),
        hazard_default="medium",
        summary="SiLA 2 lab devices. Properties, observable property streams and commands.",
        safe_state_support="file",
        conformance="full",
    )
    params_model: ClassVar[type[Any] | None] = Sila2Params
    discovery_wait: ClassVar[float] = 2.0

    def __init__(self, device: DeviceFile) -> None:
        super().__init__(device)
        self.settings = Sila2Params.model_validate(device.connect.params)
        self.client: Any = None
        self.reads: dict[str, ReadMap] = {}
        self.writes: dict[str, WriteMap] = {}
        self.actions: dict[str, ActionMap] = {}
        self.bindings: dict[str, _Binding] = {}
        self.params: dict[str, dict[str, tuple[str, str | None]]] = {}
        self.latest: dict[str, tuple[Any, float]] = {}
        self.sent: dict[str, Reading] = {}
        self.running: dict[str, Any] = {}
        self._subscriptions: list[Any] = []
        self._loop: asyncio.AbstractEventLoop | None = None
        for name, spec in device.read.items():
            if spec.type == "image":
                raise DriverError(f"read.{name}: the SiLA 2 driver doesn't read images.")
            self.reads[name] = channels.validate(ReadMap, spec.map, f"read.{name}")
        for name, write_spec in device.write.items():
            self.writes[name] = channels.validate(WriteMap, write_spec.map, f"write.{name}")
        for name, action in device.actions.items():
            action_map = channels.validate(ActionMap, action.map, f"actions.{name}")
            if set(action_map.parameters) != set(action.args):
                raise DriverError(f"actions.{name}: map.parameters must name a SiLA parameter for each argument.")
            self.actions[name] = action_map

    async def _call(self, function: Any, *args: Any, what: str, budget: float | None = None, **kwargs: Any) -> Any:
        """Run one blocking sila2 call in a thread and turn its errors into DriverError or TimeoutError."""
        import grpc  # type: ignore[import-untyped]
        from sila2.framework.abc.sila_error import SilaError
        from sila2.framework.errors.defined_execution_error import DefinedExecutionError
        from sila2.framework.errors.sila_connection_error import SilaConnectionError
        from sila2.framework.errors.validation_error import ValidationError

        try:
            return await asyncio.wait_for(asyncio.to_thread(function, *args, **kwargs), budget or self.settings.timeout)
        except TimeoutError:
            wait = budget or self.settings.timeout
            raise TimeoutError(f"The SiLA server sent no reply to {what} within {wait:g} s.") from None
        except DefinedExecutionError as exc:
            raise DriverError(f"The device returned {exc.identifier} for {what} ({exc.message}).") from exc
        except ValidationError as exc:
            raise DriverError(
                f"The SiLA server returned an error for the parameters of {what} ({exc.message})."
            ) from exc
        except SilaConnectionError as exc:
            raise DriverError(f"The SiLA connection failed during {what} ({exc}). Reconnect it.") from exc
        except SilaError as exc:
            raise DriverError(f"The SiLA server failed {what} ({type(exc).__name__}, {exc}).") from exc
        except grpc.RpcError as exc:
            raise DriverError(f"The SiLA connection failed during {what} ({exc}). Reconnect it.") from exc
        except (ValueError, RuntimeError, OSError) as exc:
            raise DriverError(f"The SiLA client failed during {what} ({type(exc).__name__}, {exc}).") from exc

    def _feature(self, client: Any, identifier: str) -> Any:
        short = identifier.split("/")[-2] if identifier.count("/") >= 2 else identifier
        feature = getattr(client, short, None)
        if feature is None or not hasattr(feature, "fully_qualified_identifier"):
            names = sorted(name for name in getattr(client, "_features", {}) if name != "SiLAService")
            raise DriverError(
                f"The SiLA server doesn't implement {identifier}. It implements {', '.join(names) or 'nothing else'}."
            )
        if identifier.count("/") >= 2 and str(feature.fully_qualified_identifier) != identifier:
            raise DriverError(f"The server implements {feature.fully_qualified_identifier}, not {identifier}.")
        return feature

    def _unit(self, label: str | None, override: str | None, channel_unit: str | None, where: str) -> str | None:
        unit = override or device_unit(label)
        if label and unit is None:
            raise DriverError(f"{where} is in {label!r}, which OpenHAL doesn't support. Set map.unit.")
        if unit and channel_unit:
            try:
                convert(Quantity(1.0, parse_unit(unit)), channel_unit)
            except UnitError:
                raise DriverError(
                    f"{where} is in {unit}, which doesn't convert to the file's {channel_unit}."
                ) from None
        return unit

    @classmethod
    async def discover(cls) -> list[Discovered]:
        found = []
        for name, host, port, properties in await cls._browse(cls.discovery_wait):
            identifiers = {"sila.server_name": name, **{f"sila.{key}": value for key, value in properties.items()}}
            found.append(
                Discovered(driver="sila2", address=f"sila://{host}:{port}", identifiers=identifiers, label=name)
            )
        return found

    @classmethod
    async def _browse(cls, wait: float) -> list[tuple[str, str, int, dict[str, str]]]:
        """Listen for `_sila._tcp.local.` services with mDNS. Listening only, nothing is sent to devices."""
        from zeroconf import ServiceStateChange
        from zeroconf.asyncio import AsyncServiceBrowser, AsyncServiceInfo, AsyncZeroconf

        names: set[str] = set()

        def seen(zeroconf: Any, service_type: str, name: str, state_change: Any) -> None:
            if state_change is ServiceStateChange.Added:
                names.add(name)

        zc = AsyncZeroconf()
        browser = AsyncServiceBrowser(zc.zeroconf, "_sila._tcp.local.", handlers=[seen])
        try:
            await asyncio.sleep(wait)
            results = []
            for name in sorted(names):
                info = AsyncServiceInfo("_sila._tcp.local.", name)
                if not await info.async_request(zc.zeroconf, 1000) or not info.parsed_addresses() or not info.port:
                    continue
                properties = {
                    key.decode(): (value or b"").decode(errors="replace") for key, value in info.properties.items()
                }
                results.append((name.split(".")[0], info.parsed_addresses()[0], int(info.port), properties))
            return results
        finally:
            await browser.async_cancel()
            await zc.async_close()

    async def identify(self) -> dict[str, str]:
        identity = {"server": f"{self.settings.host}:{self.settings.port}"}
        if self.client is None:
            return identity
        service = self.client.SiLAService
        for key in ("ServerName", "ServerType", "ServerUUID", "ServerVersion", "ServerVendorURL"):
            with contextlib.suppress(DriverError, TimeoutError):
                identity[key] = str(await self._call(getattr(service, key).get, what=f"SiLAService.{key}"))
        return identity

    async def connect(self) -> None:
        bootstrap.ensure()
        from sila2.client import SilaClient

        await self.close()
        self._loop = asyncio.get_running_loop()
        certificate = None
        if self.settings.ca_env:
            certificate = await asyncio.to_thread(_certificate, self.settings.ca_env)
        options: dict[str, Any] = {"insecure": True} if self.settings.insecure else {"root_certs": certificate}
        self.client = await self._call(
            SilaClient,
            self.settings.host,
            self.settings.port,
            what="the connection",
            budget=max(self.settings.timeout, CONNECT_BUDGET_S),
            **options,
        )
        try:
            self._bind(self.client)
            for name, binding in self.bindings.items():
                if binding.observable and name in self.reads:
                    subscription = await self._call(binding.member.subscribe, what=f"the subscription for {name}")
                    subscription.add_callback(lambda value, channel=name: self._push(channel, value))
                    self._subscriptions.append(subscription)
        except BaseException:
            await self.close()
            raise

    def _push(self, channel: str, value: Any) -> None:
        loop = self._loop
        if loop is not None and not loop.is_closed():
            with contextlib.suppress(RuntimeError):
                loop.call_soon_threadsafe(self.latest.__setitem__, channel, (value, time.time()))

    def _bind(self, client: Any) -> None:
        from sila2.client import ClientObservableProperty, ClientUnobservableProperty

        self.bindings.clear()
        self.params.clear()
        for name, read_map in self.reads.items():
            feature = self._feature(client, read_map.feature)
            member = getattr(feature, read_map.property, None)
            if not isinstance(member, ClientObservableProperty | ClientUnobservableProperty):
                raise DriverError(f"read.{name}: {read_map.feature} has no property {read_map.property}.")
            kind, label, _ = channels.type_info(member._wrapped_property.data_type)  # noqa: SLF001
            if kind not in SUPPORTED:
                raise DriverError(f"read.{name}: {read_map.property} is a {kind}, which this driver doesn't read.")
            if kind == "Structure" and read_map.field is None:
                raise DriverError(f"read.{name}: {read_map.property} is a structure, so the map needs a field.")
            unit = self._unit(
                None if read_map.field else label, read_map.unit, self.device.channel_unit(name), f"read.{name}"
            )
            self.bindings[name] = _Binding(member, kind, unit, isinstance(member, ClientObservableProperty))
        for name, write_map in self.writes.items():
            feature = self._feature(client, write_map.feature)
            command = self._command(feature, write_map.command, f"write.{name}")
            fields = self._fields(command, f"write.{name}")
            if write_map.parameter not in fields:
                raise DriverError(f"write.{name}: {write_map.command} has no parameter {write_map.parameter}.")
            missing = set(fields) - {write_map.parameter} - set(write_map.base)
            if missing:
                raise DriverError(
                    f"write.{name}: {write_map.command} also needs {sorted(missing)}. Put them in map.base."
                )
            kind, label = fields[write_map.parameter]
            unit = self._unit(label, write_map.unit, self.device.channel_unit(name), f"write.{name}")
            self.bindings[name] = _Binding(command, kind, unit)
            self.params[name] = fields
            if write_map.readback is not None:
                readback = getattr(feature, write_map.readback, None)
                if not isinstance(readback, ClientObservableProperty | ClientUnobservableProperty):
                    raise DriverError(
                        f"write.{name}: {write_map.feature} has no property {write_map.readback} to read back."
                    )
                self.bindings[f"{name}.readback"] = _Binding(readback, kind, unit)
        for name, action in self.actions.items():
            feature = self._feature(client, action.feature)
            command = self._command(feature, action.command, f"actions.{name}")
            fields = self._fields(command, f"actions.{name}")
            unknown = set(action.parameters.values()) - set(fields)
            if unknown:
                raise DriverError(f"actions.{name}: {action.command} has no parameters {sorted(unknown)}.")
            missing = set(fields) - set(action.parameters.values()) - set(action.base)
            if missing:
                raise DriverError(
                    f"actions.{name}: {action.command} also needs {sorted(missing)}. Put them in map.base."
                )
            self.bindings[name] = _Binding(command, "Command", None)
            self.params[name] = fields

    @staticmethod
    def _command(feature: Any, identifier: str, where: str) -> Any:
        from sila2.client import ClientObservableCommand, ClientUnobservableCommand

        command = getattr(feature, identifier, None)
        if not isinstance(command, ClientObservableCommand | ClientUnobservableCommand):
            raise DriverError(f"{where}: the feature has no command {identifier}.")
        return command

    @staticmethod
    def _fields(command: Any, where: str) -> dict[str, tuple[str, str | None]]:
        fields: dict[str, tuple[str, str | None]] = {}
        for parameter in command._wrapped_command.parameters.fields:  # noqa: SLF001
            identifier = str(parameter._identifier)  # noqa: SLF001
            kind, label, _ = channels.type_info(parameter.data_type)
            if kind not in SUPPORTED - {"Structure"}:
                raise DriverError(f"{where}: parameter {identifier} is a {kind}, which this driver can't send.")
            fields[identifier] = (kind, label)
        return fields

    def _client(self) -> Any:
        if self.client is None:
            raise DriverError(f"{self.device.device_id} is not connected. Connect it first.")
        return self.client

    async def read(self, channel: str) -> Reading:
        self._client()
        unit = self.device.channel_unit(channel)
        if channel in self.writes:
            readback = self.bindings.get(f"{channel}.readback")
            if readback is None:
                sent = self.sent.get(channel)
                return sent if sent is not None else Reading(channel, None, unit)
            raw = await self._call(readback.member.get, what=f"reading {channel}")
            return self._reading(channel, raw, readback.unit, self.writes[channel].scale, time.time())
        binding = self.bindings.get(channel)
        read_map = self.reads.get(channel)
        if binding is None or read_map is None:
            raise DriverError(f"{self.device.device_id} has no channel {channel!r}.")
        if binding.observable and channel in self.latest:
            raw, at = self.latest[channel]
        elif binding.observable:
            raw, at = await self._call(binding.member.get, what=f"reading {channel}"), time.time()
        else:
            raw, at = await self._call(binding.member.get, what=f"reading {channel}"), time.time()
        try:
            raw = channels.get_field(raw, read_map.field)
        except KeyError:
            raise DriverError(f"{channel}: {read_map.property} has no field {read_map.field}.") from None
        return self._reading(channel, raw, binding.unit, read_map.scale, at)

    def _reading(self, channel: str, raw: Any, source: str | None, scale: float, at: float) -> Reading:
        spec = self.device.read.get(channel) or self.device.write[channel]
        unit = self.device.channel_unit(channel)
        if spec.type == "number":
            if isinstance(raw, bool) or not isinstance(raw, int | float) or not math.isfinite(raw):
                raise DriverError(f"{channel}: the SiLA server sent {raw!r}, not a number.")
            value = _convert(float(raw) * scale, source, unit, channel)
            span = getattr(spec, "range", None)
            return Reading(channel, value, unit, at=at, suspect=span is not None and not span[0] <= value <= span[1])
        if spec.type == "bool":
            if not isinstance(raw, bool):
                raise DriverError(f"{channel}: the SiLA server sent {raw!r}, not true or false.")
            return Reading(channel, raw, None, at=at)
        text = str(raw)
        if spec.type == "enum" and text not in spec.values:
            raise DriverError(
                f"{channel}: the SiLA server reported {text!r}, which is not one of {', '.join(spec.values)}."
            )
        return Reading(channel, text, None, at=at)

    @staticmethod
    def _encode(value: Any, kind: str, unit: str | None, sila_unit: str | None, scale: float, where: str) -> Any:
        if kind == "Boolean":
            if not isinstance(value, bool):
                raise DriverError(f"{where} needs true or false. Nothing was sent.")
            return value
        if kind == "String":
            return str(value)
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise DriverError(f"{where} needs a number. Nothing was sent.")
        number = _convert(float(value), unit, sila_unit, where) / scale
        if kind == "Integer":
            if abs(number - round(number)) > 1e-6:
                raise DriverError(
                    f"{where}: {number:g} is not a whole number, and SiLA requires an Integer. Nothing was sent."
                )
            return round(number)
        return number

    async def _write(self, channel: str, value: float | bool | str) -> Reading | None:
        write_map = self.writes.get(channel)
        binding = self.bindings.get(channel)
        if write_map is None or binding is None:
            raise DriverError(f"{self.device.device_id} has no write channel {channel!r}, or it is not connected.")
        spec = self.device.write[channel]
        encoded = self._encode(value, binding.kind, spec.unit, binding.unit, write_map.scale, channel)
        self.sent.pop(channel, None)
        await self._run(binding.member, {**write_map.base, write_map.parameter: encoded}, f"{write_map.command}")
        reading = Reading(channel, value, spec.unit)
        self.sent[channel] = reading
        return reading

    async def _run(self, command: Any, parameters: dict[str, Any], what: str) -> Any:
        from sila2.client import ClientObservableCommand

        result = await self._call(command, what=what, **parameters)
        if not isinstance(command, ClientObservableCommand):
            return {"responses": _jsonable(result)}
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self.settings.action_wait
        while loop.time() < deadline:
            if result.done:
                responses = await self._call(result.get_responses, what=f"the result of {what}")
                return {"status": "done", "responses": _jsonable(responses)}
            await asyncio.sleep(POLL_S)
        self.running[str(result.execution_uuid)] = result
        return {"status": "started", "execution": str(result.execution_uuid)}

    async def _action(self, name: str, args: dict[str, Any]) -> Any:
        action = self.actions.get(name)
        binding = self.bindings.get(name)
        if action is None or binding is None:
            raise DriverError(f"{self.device.device_id} has no action {name!r}, or it is not connected.")
        specs = self.device.actions[name].args
        fields = self.params[name]
        parameters = dict(action.base)
        for arg, identifier in action.parameters.items():
            kind, label = fields[identifier]
            sila_unit = device_unit(label) if label else None
            parameters[identifier] = self._encode(args[arg], kind, specs[arg].unit, sila_unit, 1.0, f"{name}.{arg}")
        return {"sent": action.command, **await self._run(binding.member, parameters, action.command)}

    async def describe(self) -> dict[str, Any] | None:
        if self.client is None:
            return None
        from openhal.drivers.sila2.describe import proposal

        return proposal(self.client)

    async def health(self) -> Health:
        if self.client is None:
            return Health(connected=False, detail="not connected")
        try:
            name = await self._call(self.client.SiLAService.ServerName.get, what="SiLAService.ServerName")
        except (DriverError, TimeoutError) as exc:
            return Health(connected=False, detail=str(exc))
        return Health(connected=True, detail=f"{name} at {self.settings.host}:{self.settings.port}")

    async def close(self) -> None:
        client, self.client = self.client, None
        subscriptions, self._subscriptions = self._subscriptions, []
        for subscription in subscriptions:
            with contextlib.suppress(Exception):
                subscription.cancel()
        self.latest.clear()
        self.running.clear()
        if client is not None:
            with contextlib.suppress(Exception):
                await asyncio.wait_for(asyncio.to_thread(client.close), 2.0)


def _certificate(variable: str) -> bytes:
    """The CA certificate at the path in an environment variable. A device file never names a path."""
    path = os.environ.get(variable)
    if not path:
        raise DriverError(f"Set the {variable} environment variable to the path of the server's CA certificate.")
    try:
        return Path(path).expanduser().read_bytes()
    except OSError as exc:
        raise DriverError(f"Could not read the CA certificate named by {variable} ({exc}).") from exc


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, bool | int | float | str):
        return value
    if hasattr(value, "_asdict"):
        return {key: _jsonable(item) for key, item in value._asdict().items()}
    if isinstance(value, list | tuple):
        return [_jsonable(item) for item in value]
    return str(value)
