"""UPnP devices through their SOAP actions, with SSDP discovery, through async-upnp-client.

Protocol (UPnP Device Architecture 2.0). A device publishes an XML description at its
`location` URL, listing services, and each service's SCPD lists actions with in and out
arguments tied to state variables. Actions are SOAP calls to the service's control URL. The
driver fetches the description once on connect, and every channel is one action call.

- A read channel names a service, an action such as `GetVolume`, its in-arguments and the
  out-argument to read, such as `CurrentVolume`. Reads call the action each time, because most
  devices answer queries faster than they push GENA events.
- A channel under `write` calls an action such as `SetVolume` with `{value}` in one argument, and
  reads back through its `state` map, or returns the last value sent.
- An action calls one SOAP action with the action's arguments placed by `{name}`.
- On connect every map is checked against the device's SCPD. Every in-argument must be given,
  the out-argument must exist, and enum channels must use the state variable's allowed values.

Discovery sends one SSDP M-SEARCH, which only asks devices to announce themselves.

Safe state. From the device file. UPnP has no emergency action of its own.
"""

from __future__ import annotations

import asyncio
import math
from typing import Annotated, Any, ClassVar

from async_upnp_client.client import UpnpAction, UpnpDevice, UpnpRequester, UpnpService
from async_upnp_client.client_factory import UpnpFactory
from async_upnp_client.const import HttpRequest
from async_upnp_client.exceptions import (
    UpnpActionError,
    UpnpCommunicationError,
    UpnpConnectionTimeoutError,
    UpnpError,
    UpnpValueError,
)
from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, ValidationError, field_validator

from openhal.drivers.base import Discovered, Driver, DriverError, DriverInfo, Health, Reading
from openhal.drivers.http import values as v
from openhal.drivers.upnp.proposals import FLOAT_TYPES, INTEGER_TYPES, propose
from openhal.spec.models import ArgSpec, DeviceFile, ReadChannel, WriteChannel
from openhal.spec.units import Quantity, UnitError, convert, parse_duration, parse_unit


def _seconds(value: Any) -> Any:
    if isinstance(value, int | float) and not isinstance(value, bool):
        return float(value)
    return parse_duration(value)


Duration = Annotated[float, BeforeValidator(_seconds), Field(gt=0, le=60)]


def default_requester(timeout: float) -> UpnpRequester:
    """The aiohttp requester async-upnp-client ships with."""
    from async_upnp_client.aiohttp import AiohttpRequester

    return AiohttpRequester(timeout=max(1, math.ceil(timeout)))


class UpnpParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    location: str = Field(pattern=r"^https?://\S+$")
    timeout: Duration = 5.0


class CallMap(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    service: str = Field(min_length=1, max_length=200)
    action: str = Field(pattern=r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")
    args: dict[str, Any] = {}


class _Value(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    scale: float = 1.0
    offset: float = 0.0
    unit: str | None = None

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


class ReadMap(CallMap, _Value):
    output: str = Field(pattern=r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")


class WriteMap(CallMap, _Value):
    state: ReadMap | None = None


class ActionMap(CallMap):
    """One SOAP action. `args` holds fixed values and `{name}` places for the action's arguments."""


def find_service(device: UpnpDevice, name: str) -> UpnpService | None:
    """A service by its id, its type, or the short name inside either (`RenderingControl`)."""
    for service in device.all_services:
        short_type = service.service_type.split(":")[-2] if service.service_type.count(":") >= 2 else ""
        if name in (service.service_id, service.service_type, service.service_id.rsplit(":", 1)[-1], short_type):
            return service
    return None


class UpnpDriver(Driver):
    """A UPnP device by its description URL. SOAP actions as channels and actions."""

    info: ClassVar[DriverInfo] = DriverInfo(
        name="upnp",
        protocols=("UPnP Device Architecture SOAP actions", "SSDP discovery"),
        hazard_default="low",
        summary="UPnP devices such as media renderers, speakers and routers, through their SOAP actions.",
        safe_state_support="file",
        conformance="full",
    )
    params_model: ClassVar[type[Any] | None] = UpnpParams

    def __init__(self, device: DeviceFile, *, requester: UpnpRequester | None = None) -> None:
        super().__init__(device)
        self.settings = UpnpParams.model_validate(device.connect.params)
        self._requester = requester
        self.upnp: UpnpDevice | None = None
        self._lost = ""
        self._sent: dict[str, float | bool | str] = {}
        self.reads: dict[str, ReadMap] = {}
        self.writes: dict[str, WriteMap] = {}
        self.actions: dict[str, ActionMap] = {}
        for name, spec in device.read.items():
            if spec.type == "image":
                raise DriverError(f"read.{name}: UPnP actions don't return images. Read the image URL as a string.")
            self.reads[name] = self._parse(ReadMap, f"read.{name}", spec.map)
        for name, wspec in device.write.items():
            write_map = self._parse(WriteMap, f"write.{name}", wspec.map)
            if v.placeholders(write_map.args) != {"value"}:
                raise DriverError(
                    f"write.{name}: args must use {{value}}, and only {{value}}, for the channel's value."
                )
            self.writes[name] = write_map
        for name, action in device.actions.items():
            action_map = self._parse(ActionMap, f"actions.{name}", action.map)
            if v.placeholders(action_map.args) != set(action.args):
                raise DriverError(
                    f"actions.{name}: args must place every argument the action declares "
                    f"({', '.join(sorted(action.args)) or 'none'}) with {{name}}, and no others."
                )
            self.actions[name] = action_map

    @staticmethod
    def _parse[M: BaseModel](model: type[M], where: str, raw: dict[str, Any] | None) -> M:
        if raw is None:
            raise DriverError(
                f"{where} needs a map, for example map: {{ service: RenderingControl, action: GetVolume, "
                "args: { InstanceID: 0, Channel: Master }, output: CurrentVolume }. describe() proposes them."
            )
        try:
            return model.model_validate(raw)
        except ValidationError as exc:
            problems = "; ".join(f"{'.'.join(map(str, e['loc'])) or 'map'}: {e['msg']}" for e in exc.errors())
            raise DriverError(f"{where} has an invalid upnp map. {problems}") from None

    @property
    def _where(self) -> str:
        return f"UPnP device at {self.settings.location}"

    @classmethod
    async def discover(cls) -> list[Discovered]:
        """Send one SSDP M-SEARCH for every root device and collect the answers for two seconds."""
        from async_upnp_client.search import async_search

        found: dict[str, Discovered] = {}

        async def answer(headers: Any) -> None:
            location = headers.get("location")
            if not location or location in found:
                return
            identifiers = {key: str(headers[key]) for key in ("st", "usn", "server") if headers.get(key)}
            found[location] = Discovered("upnp", location, identifiers, identifiers.get("server", "UPnP device"))

        try:
            await asyncio.wait_for(async_search(answer, timeout=2, search_target="upnp:rootdevice"), 5)
        except (OSError, TimeoutError, UpnpError):
            return list(found.values())
        return list(found.values())

    async def identify(self) -> dict[str, str]:
        identity = {"location": self.settings.location}
        if self.upnp is not None:
            identity.update(
                {
                    "friendly_name": self.upnp.friendly_name,
                    "manufacturer": self.upnp.manufacturer,
                    "model": self.upnp.model_name,
                    "udn": self.upnp.udn,
                }
            )
        return identity

    def _requester_now(self) -> UpnpRequester:
        if self._requester is None:
            self._requester = default_requester(self.settings.timeout)
        return self._requester

    async def connect(self) -> None:
        await self.close()
        factory = UpnpFactory(self._requester_now(), non_strict=True)
        try:
            device = await asyncio.wait_for(
                factory.async_create_device(self.settings.location), self.settings.timeout * 2
            )
        except (TimeoutError, UpnpConnectionTimeoutError):
            raise TimeoutError(f"{self._where} didn't send its description in time.") from None
        except UpnpCommunicationError as exc:
            raise DriverError(f"Could not fetch the description from {self._where} ({exc}). Check location.") from None
        except UpnpError as exc:
            raise DriverError(f"{self._where} sent a description that doesn't parse ({exc}).") from None
        self._check(device)
        self.upnp = device
        self._lost = ""
        self._sent.clear()

    def _resolve(self, device: UpnpDevice, call: CallMap, where: str) -> UpnpAction:
        service = find_service(device, call.service)
        if service is None:
            known = ", ".join(sorted(service.service_id.rsplit(":", 1)[-1] for service in device.all_services))
            raise DriverError(f"{where}: the device has no service {call.service}. It has {known}.")
        if not service.has_action(call.action):
            known = ", ".join(sorted(service.actions))
            raise DriverError(f"{where}: {call.service} has no action {call.action}. It has {known}.")
        action = service.action(call.action)
        wanted = {argument.name for argument in action.in_arguments()}
        if set(call.args) != wanted:
            missing = sorted(wanted - set(call.args))
            extra = sorted(set(call.args) - wanted)
            parts = [f"missing {', '.join(missing)}"] if missing else []
            parts += [f"unknown {', '.join(extra)}"] if extra else []
            raise DriverError(f"{where}: {call.action} arguments don't match its SCPD ({'; '.join(parts)}).")
        return action

    def _check_output(self, action: UpnpAction, read_map: ReadMap, spec: Any, where: str) -> None:
        argument = action.argument(read_map.output, "out")
        if argument is None:
            outputs = ", ".join(argument.name for argument in action.out_arguments())
            raise DriverError(f"{where}: {read_map.action} has no output {read_map.output}. It has {outputs}.")
        self._check_type(argument.related_state_variable, spec, where)

    @staticmethod
    def _check_type(variable: Any, spec: Any, where: str) -> None:
        data_type = variable.data_type
        if spec.type == "number" and data_type not in INTEGER_TYPES | FLOAT_TYPES:
            raise DriverError(f"{where}: {variable.name} is {data_type}, not a number.")
        if spec.type == "bool" and data_type != "boolean":
            raise DriverError(f"{where}: {variable.name} is {data_type}, not boolean.")
        if spec.type == "enum":
            allowed = {str(value) for value in variable.allowed_values}
            unknown = [value for value in spec.values if allowed and value not in allowed]
            if not allowed or unknown:
                raise DriverError(
                    f"{where}: {variable.name} allows {', '.join(sorted(allowed)) or 'any text'}, "
                    f"not {', '.join(unknown or spec.values)}."
                )

    def _check(self, device: UpnpDevice) -> None:
        for name, read_map in self.reads.items():
            action = self._resolve(device, read_map, f"read.{name}")
            self._check_output(action, read_map, self.device.read[name], f"read.{name}")
        for name, write_map in self.writes.items():
            action = self._resolve(device, write_map, f"write.{name}")
            target = next(arg for arg, value in write_map.args.items() if v.placeholders(value) == {"value"})
            argument = action.argument(target, "in")
            assert argument is not None
            self._check_type(argument.related_state_variable, self.device.write[name], f"write.{name}")
            if write_map.state is not None:
                state_action = self._resolve(device, write_map.state, f"write.{name}.state")
                self._check_output(state_action, write_map.state, self.device.write[name], f"write.{name}.state")
        for name, action_map in self.actions.items():
            self._resolve(device, action_map, f"actions.{name}")

    async def close(self) -> None:
        self.upnp = None

    def _open(self) -> UpnpDevice:
        if self.upnp is None:
            raise DriverError(f"{self._where} is not connected. Connect it first.")
        if self._lost:
            raise DriverError(f"{self._where} stopped answering ({self._lost}). Reconnect it.")
        return self.upnp

    async def health(self) -> Health:
        if self.upnp is None:
            return Health(connected=False, detail=f"{self._where} not connected")
        request = HttpRequest("GET", self.settings.location, {}, None, timeout=self.settings.timeout)
        try:
            response = await asyncio.wait_for(
                self._requester_now().async_http_request(request), self.settings.timeout + 1
            )
        except (TimeoutError, UpnpError, OSError) as exc:
            self._lost = str(exc) or type(exc).__name__
            return Health(connected=False, detail=f"{self._where} {self._lost}")
        if response.status_code != 200:
            self._lost = f"HTTP {response.status_code} for the description"
            return Health(connected=False, detail=f"{self._where} {self._lost}")
        self._lost = ""
        return Health(connected=True, detail=f"{self._where}, {self.upnp.friendly_name}")

    async def _call(self, call: CallMap, args: dict[str, Any], where: str) -> dict[str, Any]:
        device = self._open()
        service = find_service(device, call.service)
        assert service is not None
        action = service.action(call.action)
        try:
            result = await asyncio.wait_for(
                action.async_call(request_timeout=self.settings.timeout, **args), self.settings.timeout + 1
            )
        except (TimeoutError, UpnpConnectionTimeoutError):
            raise TimeoutError(
                f"{self._where} didn't answer {call.action} within {self.settings.timeout:g} s."
            ) from None
        except UpnpActionError as exc:
            raise DriverError(
                f"{self._where} refused {call.action} "
                f"(UPnP error {exc.error_code}, {exc.error_desc or 'no description'})."
            ) from None
        except UpnpValueError as exc:
            raise DriverError(f"{where}: {call.action} can't take {exc}.") from None
        except UpnpCommunicationError as exc:
            self._lost = str(exc) or type(exc).__name__
            raise DriverError(f"{self._where} didn't answer {call.action} ({exc}).") from None
        except UpnpError as exc:
            raise DriverError(f"{self._where} sent a reply to {call.action} that doesn't parse ({exc}).") from None
        return dict(result)

    async def read(self, channel: str) -> Reading:
        unit = self.device.channel_unit(channel)
        if channel in self.writes:
            state = self.writes[channel].state
            if state is None:
                self._open()
                return Reading(channel, self._sent.get(channel), unit=unit)
            return await self._read(channel, state, self.device.write[channel])
        read_map = self.reads.get(channel)
        if read_map is None:
            raise DriverError(f"This upnp device has no channel {channel!r}.")
        return await self._read(channel, read_map, self.device.read[channel])

    async def _read(self, channel: str, read_map: ReadMap, spec: ReadChannel | WriteChannel) -> Reading:
        result = await self._call(read_map, dict(read_map.args), f"read.{channel}")
        raw = result.get(read_map.output)
        unit = self.device.channel_unit(channel)
        if raw is None:
            return Reading(channel, None, unit=unit)
        where = f"{read_map.action} {read_map.output} for {channel}"
        if spec.type == "number":
            value: Any = v.to_number(raw, where) * read_map.scale + read_map.offset
            if read_map.unit and spec.unit and read_map.unit != spec.unit:
                value = convert(Quantity(value, parse_unit(read_map.unit)), spec.unit)
            limits = getattr(spec, "range", None)
            suspect = bool(limits is not None and not limits[0] <= value <= limits[1])
            return Reading(channel, value, unit=unit, suspect=suspect)
        if spec.type == "bool":
            return Reading(channel, v.to_bool(raw, v.DEFAULT_ON, v.DEFAULT_OFF, where))
        text = v.to_text(raw)
        if spec.type == "enum" and text not in spec.values:
            raise DriverError(f"{where} reported {text[:60]!r}, which is not one of {', '.join(spec.values)}.")
        return Reading(channel, text)

    def _raw(self, value: Any, spec: WriteChannel | ArgSpec, value_map: _Value | None, variable: Any) -> Any:
        if spec.type != "number" or isinstance(value, bool):
            return value
        number = float(value)
        if value_map is not None:
            if value_map.unit and spec.unit and value_map.unit != spec.unit:
                number = convert(Quantity(number, parse_unit(spec.unit)), value_map.unit)
            number = (number - value_map.offset) / value_map.scale
        if variable is not None and variable.data_type in INTEGER_TYPES:
            return round(number)
        if variable is None and number.is_integer():
            return int(number)
        return number

    async def _write(self, channel: str, value: float | bool | str) -> Reading | None:
        write_map = self.writes.get(channel)
        if write_map is None:
            raise DriverError(f"This upnp device has no write channel {channel!r}.")
        device = self._open()
        service = find_service(device, write_map.service)
        assert service is not None
        target = next(arg for arg, item in write_map.args.items() if v.placeholders(item) == {"value"})
        argument = service.action(write_map.action).argument(target, "in")
        variable = argument.related_state_variable if argument is not None else None
        raw = self._raw(value, self.device.write[channel], write_map, variable)
        await self._call(write_map, v.render(write_map.args, {"value": raw}), f"write.{channel}")
        self._sent[channel] = value
        return None if write_map.state is not None else Reading(channel, value, unit=self.device.channel_unit(channel))

    async def _action(self, name: str, args: dict[str, Any]) -> Any:
        action_map = self.actions.get(name)
        if action_map is None:
            raise DriverError(f"This upnp device has no action {name!r}.")
        spec = self.device.actions[name]
        filled = {arg: self._raw(value, spec.args[arg], None, None) for arg, value in args.items()}
        result = await self._call(action_map, v.render(action_map.args, filled), f"actions.{name}")
        return {"sent": action_map.action, "result": {key: str(item) for key, item in result.items()}}

    async def describe(self) -> dict[str, Any] | None:
        device = self.upnp
        if device is None:
            return None
        read: dict[str, Any] = {}
        write: dict[str, Any] = {}
        actions: dict[str, Any] = {}
        for service in device.all_services:
            short = service.service_id.rsplit(":", 1)[-1]
            for action in service.actions.values():
                proposal = propose(short, service, action)
                for section, name, spec in proposal:
                    {"read": read, "write": write, "actions": actions}[section].setdefault(name, spec)
        return {
            "device": {"name": device.friendly_name, "manufacturer": device.manufacturer, "model": device.model_name},
            "read": read,
            "write": write,
            "actions": actions,
            "notes": (
                "Proposed from the device's service descriptions. Limits come from allowedValueRange and are suggested."
            ),
        }
