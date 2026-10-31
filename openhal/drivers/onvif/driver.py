"""ONVIF cameras. Device information and stream URIs as reads, PTZ position as channels, PTZ moves as actions.

Protocol. ONVIF Profile S and T services over SOAP 1.2 (`openhal.drivers.onvif.soap`). The device
service at `/onvif/device_service` gives the clock (GetSystemDateAndTime), the identity
(GetDeviceInformation) and the other services' addresses (GetCapabilities). The media service
lists profiles (GetProfiles) and their stream and snapshot URIs. The PTZ service moves the camera
in the generic spaces, where pan and tilt run from -1 to 1 and zoom from 0 to 1.

Channels.

- `manufacturer`, `model`, `firmware`, `serial`, `hardware_id`, `profile`, `stream_uri` and
  `snapshot_uri` are text read once on connect. URIs are data, never fetched by the driver.
- `pan`, `tilt` and `zoom` read GetStatus. Under `write` they move there with AbsoluteMove, the
  other axes staying where they are. `map: { scale, offset, unit }` turns the normalized space
  into degrees or another unit. `moving` reads whether either axis is moving.
- Actions are named after their operation, or map to one with `map: { operation: ... }`.
  `move` (ContinuousMove, args pan, tilt, zoom as speeds and duration), `step` (RelativeMove,
  args pan, tilt, zoom), `go_to` (AbsoluteMove), `goto_preset` (arg preset), `home`
  (GotoHomePosition) and `stop`.

Limits. The kernel checks every argument against the device file. A relative or continuous move
can still carry the camera past a position limit, so cameras that must stay inside a range should
use the absolute channels and the camera's own PanTiltLimits.

Safe state. Native. Stop on pan, tilt and zoom for the profile in use.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import os
from collections.abc import Callable
from typing import Any, ClassVar

import httpx
from pydantic import ValidationError

from openhal.drivers.base import Discovered, Driver, DriverError, DriverInfo, Health, Reading
from openhal.drivers.onvif import discovery, soap
from openhal.drivers.onvif.maps import AXES, INFO_FIELDS, OPERATIONS, TEXT_FIELDS, ActionMap, OnvifParams, ReadMap
from openhal.spec.models import DeviceFile, ReadChannel, WriteChannel
from openhal.spec.units import Quantity, UnitError, convert, parse_unit

TransportFactory = Callable[[], httpx.AsyncBaseTransport | None]


class OnvifDriver(Driver):
    """An ONVIF camera. Identity and stream URIs to read, PTZ position and moves through the safety kernel."""

    info: ClassVar[DriverInfo] = DriverInfo(
        name="onvif",
        protocols=("ONVIF Profile S and T over SOAP 1.2", "WS-Discovery"),
        hazard_default="low",
        summary="ONVIF IP cameras. Device information and stream URIs, PTZ position, PTZ moves and presets.",
        safe_state_support="native",
        conformance="full",
    )
    params_model: ClassVar[type[Any] | None] = OnvifParams

    def __init__(
        self,
        device: DeviceFile,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        environ: Callable[[str], str | None] = os.environ.get,
    ) -> None:
        super().__init__(device)
        self.settings = OnvifParams.model_validate(device.connect.params)
        self._transport = transport
        self._environ = environ
        self._client: httpx.AsyncClient | None = None
        self._password = ""
        self._offset = dt.timedelta(0)
        self.device_info: dict[str, str] = {}
        self.services: dict[str, str] = {}
        self.profile_token = ""
        self.profile_name = ""
        self.has_ptz = False
        self.uris: dict[str, str | None] = {}
        self.reads: dict[str, ReadMap] = {}
        self.actions: dict[str, str] = {}
        specs: dict[str, ReadChannel | WriteChannel] = {**device.read, **device.write}
        for name, spec in specs.items():
            self.reads[name] = self._read_map(name, spec)
        for name in device.write:
            if self.reads[name].field not in AXES:
                raise DriverError(f"write.{name}: only pan, tilt and zoom can be set. Read the others under read.")
        for name, action in device.actions.items():
            operation = self._action_map(name, action.map).operation if action.map else name
            if operation not in OPERATIONS:
                raise DriverError(
                    f"actions.{name}: name the action after an operation ({', '.join(OPERATIONS)}) "
                    "or add map: { operation: move }."
                )
            allowed = OPERATIONS[operation][1]
            if not set(action.args) <= allowed:
                extra = ", ".join(sorted(set(action.args) - allowed))
                raise DriverError(
                    f"actions.{name}: {operation} takes {', '.join(sorted(allowed)) or 'no arguments'}, not {extra}."
                )
            self.actions[name] = operation

    def _read_map(self, name: str, spec: ReadChannel | WriteChannel) -> ReadMap:
        raw = (
            spec.map if spec.map is not None else ({"field": name} if name in (*TEXT_FIELDS, *AXES, "moving") else None)
        )
        if raw is None:
            raise DriverError(
                f"{name}: name the channel after a field ({', '.join((*TEXT_FIELDS, *AXES, 'moving'))}) "
                "or give map: { field: pan }."
            )
        try:
            read_map = ReadMap.model_validate(raw)
        except ValidationError as exc:
            problems = "; ".join(f"{'.'.join(map(str, e['loc'])) or 'map'}: {e['msg']}" for e in exc.errors())
            raise DriverError(f"{name} has an invalid onvif map. {problems}") from None
        kind = {"moving": "bool", **dict.fromkeys(TEXT_FIELDS, "string"), **dict.fromkeys(AXES, "number")}[
            read_map.field
        ]
        if spec.type != kind:
            raise DriverError(f"{name}: {read_map.field} is a {kind} value, so the channel needs type {kind}.")
        if kind == "number" and read_map.unit and spec.unit:
            try:
                convert(Quantity(1.0, parse_unit(read_map.unit)), spec.unit)
            except UnitError:
                raise DriverError(f"{name}: map.unit {read_map.unit} doesn't convert to {spec.unit}.") from None
        return read_map

    @staticmethod
    def _action_map(name: str, raw: dict[str, Any]) -> ActionMap:
        try:
            return ActionMap.model_validate(raw)
        except ValidationError as exc:
            problems = "; ".join(f"{'.'.join(map(str, e['loc'])) or 'map'}: {e['msg']}" for e in exc.errors())
            raise DriverError(f"actions.{name} has an invalid onvif map. {problems}") from None

    @property
    def _base(self) -> str:
        return f"{self.settings.scheme}://{self.settings.host}:{self.settings.port}"

    @property
    def _where(self) -> str:
        return f"ONVIF camera {self.settings.host}"

    @property
    def needs_ptz(self) -> bool:
        return bool(self.actions) or any(read_map.field in (*AXES, "moving") for read_map in self.reads.values())

    @classmethod
    async def discover(cls) -> list[Discovered]:
        """One WS-Discovery Probe for NetworkVideoTransmitter devices. Nothing else is sent."""
        return await discovery.search()

    async def identify(self) -> dict[str, str]:
        identity = {"host": self.settings.host}
        identity.update({key: value for key, value in self.device_info.items() if value})
        if self.profile_token:
            identity["profile"] = self.profile_token
        return identity

    async def _post(self, url: str, body: str, *, auth: bool = True) -> Any:
        client = self._client
        if client is None:
            raise DriverError(f"{self._where} is not connected. Connect it first.")
        header = ""
        if auth and self.settings.username is not None:
            header = soap.security_header(
                self.settings.username, self._password, dt.datetime.now(dt.UTC) + self._offset
            )
        name = body.split(">", 1)[0].lstrip("<").split(":")[-1]
        headers = {"Content-Type": "application/soap+xml; charset=utf-8"}
        try:
            response = await asyncio.wait_for(
                client.post(url, content=soap.envelope(body, header), headers=headers), self.settings.timeout + 1
            )
        except (httpx.TimeoutException, TimeoutError):
            raise TimeoutError(f"{self._where} sent no reply to {name} within {self.settings.timeout:g} s.") from None
        except httpx.HTTPError as exc:
            raise DriverError(f"Could not reach {self._where} for {name} ({exc}). Check host and port.") from None
        if response.status_code == 401:
            raise DriverError(
                f"{self._where} did not accept the credentials for {name}. "
                f"Check username and {self.settings.token_env}."
            )
        try:
            return soap.parse(response.content)
        except soap.SoapFaultError as fault:
            if fault.not_authorized:
                raise DriverError(
                    f"{self._where} did not accept the credentials for {name} ({fault.reason or fault.subcode}). "
                    f"Check username, {self.settings.token_env} and the camera's clock."
                ) from None
            raise DriverError(f"{self._where} returned an error for {name} ({fault}).") from None
        except ValueError as exc:
            raise DriverError(f"{self._where} sent a reply to {name} that isn't SOAP ({exc}).") from None

    async def connect(self) -> None:
        await self.close()
        if self.settings.username is not None:
            if self.settings.token_env is None:
                raise DriverError("username needs token_env, the variable that holds the camera password.")
            password = self._environ(self.settings.token_env)
            if not password:
                raise DriverError(f"Set the {self.settings.token_env} environment variable to the camera password.")
            self._password = password
        self._client = httpx.AsyncClient(timeout=self.settings.timeout, transport=self._transport)
        try:
            await self._handshake()
        except BaseException:
            await self.close()
            raise

    async def _handshake(self) -> None:
        device_url = f"{self._base}{self.settings.device_path}"
        clock = await self._post(device_url, soap.call(soap.DEVICE, "GetSystemDateAndTime"), auth=False)
        camera_time = soap.device_time(clock)
        self._offset = camera_time - dt.datetime.now(dt.UTC) if camera_time is not None else dt.timedelta(0)
        info = await self._post(device_url, soap.call(soap.DEVICE, "GetDeviceInformation"))
        self.device_info = {key: soap.text(info, tag) or "" for key, tag in INFO_FIELDS.items()}
        capabilities = await self._post(
            device_url, soap.call(soap.DEVICE, "GetCapabilities", "<tds:Category>All</tds:Category>")
        )
        self.services = {"device": device_url}
        for service in ("Media", "PTZ"):
            address = soap.text(capabilities, service, "XAddr")
            if address:
                self.services[service.lower()] = address
        if "media" not in self.services:
            raise DriverError(f"{self._where} reports no media service, so it has no profiles to stream.")
        profiles = await self._post(self.services["media"], soap.call(soap.MEDIA, "GetProfiles"))
        self._pick_profile(profiles)
        if self.needs_ptz and ("ptz" not in self.services or not self.has_ptz):
            raise DriverError(
                f"{self._where} profile {self.profile_token} has no PTZ, "
                "but the device file uses pan, tilt, zoom or moves."
            )
        self.uris = {}
        wanted = {read_map.field for read_map in self.reads.values()}
        if "stream_uri" in wanted:
            setup = (
                "<trt:StreamSetup><tt:Stream>RTP-Unicast</tt:Stream><tt:Transport><tt:Protocol>RTSP</tt:Protocol>"
                f"</tt:Transport></trt:StreamSetup>{soap.element('trt:ProfileToken', self.profile_token)}"
            )
            reply = await self._post(self.services["media"], soap.call(soap.MEDIA, "GetStreamUri", setup))
            self.uris["stream_uri"] = soap.text(reply, "MediaUri", "Uri")
        if "snapshot_uri" in wanted:
            token = soap.element("trt:ProfileToken", self.profile_token)
            reply = await self._post(self.services["media"], soap.call(soap.MEDIA, "GetSnapshotUri", token))
            self.uris["snapshot_uri"] = soap.text(reply, "MediaUri", "Uri")

    def _pick_profile(self, body: Any) -> None:
        profiles = soap.find_all(body, "Profiles")
        if not profiles:
            raise DriverError(f"{self._where} has no media profiles.")
        wanted = self.settings.profile
        chosen = profiles[0]
        if wanted is not None:
            match = next((item for item in profiles if wanted in (item.get("token"), soap.text(item, "Name"))), None)
            if match is None:
                names = ", ".join(str(item.get("token")) for item in profiles)
                raise DriverError(f"{self._where} has no profile {wanted!r}. It has {names}.")
            chosen = match
        self.profile_token = str(chosen.get("token") or "")
        self.profile_name = soap.text(chosen, "Name") or self.profile_token
        self.has_ptz = soap.find(chosen, "PTZConfiguration") is not None

    async def close(self) -> None:
        client, self._client = self._client, None
        if client is not None:
            await client.aclose()

    async def health(self) -> Health:
        if self._client is None:
            return Health(connected=False, detail=f"{self._where} not connected")
        try:
            await self._post(
                self.services.get("device", f"{self._base}{self.settings.device_path}"),
                soap.call(soap.DEVICE, "GetSystemDateAndTime"),
                auth=False,
            )
        except (DriverError, TimeoutError) as exc:
            return Health(connected=False, detail=str(exc))
        return Health(connected=True, detail=f"{self._where}, profile {self.profile_token}")

    async def _status(self) -> tuple[dict[str, float | None], bool]:
        body = await self._post(
            self.services["ptz"],
            soap.call(soap.PTZ, "GetStatus", soap.element("tptz:ProfileToken", self.profile_token)),
        )
        position = soap.find(body, "Position")
        if position is None:
            raise DriverError(f"{self._where} sent a PTZ status without a position.")
        axes = {
            "pan": soap.attribute(soap.find(position, "PanTilt"), "x"),
            "tilt": soap.attribute(soap.find(position, "PanTilt"), "y"),
            "zoom": soap.attribute(soap.find(position, "Zoom"), "x"),
        }
        moving = any(
            (soap.text(body, "MoveStatus", axis) or "IDLE").upper() == "MOVING" for axis in ("PanTilt", "Zoom")
        )
        return axes, moving

    async def read(self, channel: str) -> Reading:
        read_map = self.reads.get(channel)
        if read_map is None:
            raise DriverError(f"This onvif device has no channel {channel!r}.")
        if self._client is None:
            raise DriverError(f"{self._where} is not connected. Connect it first.")
        unit = self.device.channel_unit(channel)
        field = read_map.field
        if field in INFO_FIELDS:
            return Reading(channel, self.device_info.get(field) or None)
        if field == "profile":
            return Reading(channel, self.profile_name)
        if field in ("stream_uri", "snapshot_uri"):
            return Reading(channel, self.uris.get(field))
        axes, moving = await self._status()
        if field == "moving":
            return Reading(channel, moving)
        raw = axes[field]
        if raw is None:
            return Reading(channel, None, unit=unit)
        spec = self.device.write.get(channel) or self.device.read[channel]
        value = raw * read_map.scale + read_map.offset
        if read_map.unit and spec.unit and read_map.unit != spec.unit:
            value = convert(Quantity(value, parse_unit(read_map.unit)), spec.unit)
        limits = getattr(spec, "range", None)
        suspect = bool(limits is not None and not limits[0] <= value <= limits[1])
        return Reading(channel, value, unit=unit, suspect=suspect)

    def _normalized(self, channel: str, value: float) -> float:
        read_map = self.reads[channel]
        spec = self.device.write[channel]
        number = float(value)
        if read_map.unit and spec.unit and read_map.unit != spec.unit:
            number = convert(Quantity(number, parse_unit(spec.unit)), read_map.unit)
        return (number - read_map.offset) / read_map.scale

    async def _write(self, channel: str, value: float | bool | str) -> Reading | None:
        if channel not in self.device.write:
            raise DriverError(f"This onvif device has no write channel {channel!r}.")
        axis = self.reads[channel].field
        target = self._normalized(channel, float(value))
        current, _ = await self._status()
        position = {**current, axis: target}
        if axis in ("pan", "tilt") and (position["pan"] is None or position["tilt"] is None):
            raise DriverError(f"{self._where} didn't report a pan and tilt position, so {channel} can't move alone.")
        pan_tilt = (position["pan"], position["tilt"]) if axis in ("pan", "tilt") else (None, None)
        zoom = position["zoom"] if axis == "zoom" else None
        inner = (
            soap.element("tptz:ProfileToken", self.profile_token)
            + f"<tptz:Position>{soap.vector(*pan_tilt, zoom)}</tptz:Position>"
        )
        await self._post(self.services["ptz"], soap.call(soap.PTZ, "AbsoluteMove", inner))
        return None

    async def _action(self, name: str, args: dict[str, Any]) -> Any:
        operation = self.actions.get(name)
        if operation is None:
            raise DriverError(f"This onvif device has no action {name!r}.")
        soap_name = OPERATIONS[operation][0]
        token = soap.element("tptz:ProfileToken", self.profile_token)
        axes = [float(args[axis]) if axis in args else None for axis in AXES]
        if operation == "move":
            seconds = float(args.get("duration", self.settings.move_timeout))
            inner = (
                token
                + f"<tptz:Velocity>{soap.vector(*axes)}</tptz:Velocity><tptz:Timeout>PT{seconds:g}S</tptz:Timeout>"
            )
        elif operation == "step":
            inner = token + f"<tptz:Translation>{soap.vector(*axes)}</tptz:Translation>"
        elif operation == "go_to":
            if axes[0] is None or axes[1] is None:
                current, _ = await self._status()
                axes = [
                    axes[0] if axes[0] is not None else current["pan"],
                    axes[1] if axes[1] is not None else current["tilt"],
                    axes[2],
                ]
            inner = token + f"<tptz:Position>{soap.vector(*axes)}</tptz:Position>"
        elif operation == "goto_preset":
            inner = token + soap.element("tptz:PresetToken", args["preset"])
        elif operation == "home":
            inner = token
        else:
            inner = token + "<tptz:PanTilt>true</tptz:PanTilt><tptz:Zoom>true</tptz:Zoom>"
        await self._post(self.services["ptz"], soap.call(soap.PTZ, soap_name, inner))
        return {"sent": soap_name}

    async def _safe_state(self) -> None:
        if "ptz" in self.services and self.has_ptz:
            inner = (
                soap.element("tptz:ProfileToken", self.profile_token)
                + "<tptz:PanTilt>true</tptz:PanTilt><tptz:Zoom>true</tptz:Zoom>"
            )
            await self._post(self.services["ptz"], soap.call(soap.PTZ, "Stop", inner))

    async def describe(self) -> dict[str, Any] | None:
        if self._client is None:
            return None
        read: dict[str, Any] = {
            name: {"type": "string"} for name in ("manufacturer", "model", "firmware", "stream_uri", "snapshot_uri")
        }
        write: dict[str, Any] = {}
        actions: dict[str, Any] = {}
        if self.has_ptz and "ptz" in self.services:
            read["moving"] = {"type": "bool"}
            for axis in AXES:
                write[axis] = {"unit": "dimensionless", "min": 0 if axis == "zoom" else -1, "max": 1, "suggested": True}
            speed = {"unit": "dimensionless", "min": -1, "max": 1}
            actions["move"] = {
                "args": {"pan": speed, "tilt": speed, "zoom": speed, "duration": {"unit": "s", "min": 0.1, "max": 5}},
                "suggested": True,
            }
            actions["stop"] = {"suggested": True}
            actions["home"] = {"suggested": True}
            presets = await self._presets()
            if presets:
                actions["goto_preset"] = {"args": {"preset": {"type": "enum", "values": presets}}, "suggested": True}
        name = " ".join(part for part in (self.device_info.get("manufacturer"), self.device_info.get("model")) if part)
        device: dict[str, Any] = {"name": name or self._where}
        if self.device_info.get("manufacturer"):
            device["manufacturer"] = self.device_info["manufacturer"]
        return {
            "device": device,
            "read": read,
            "write": write,
            "actions": actions,
            "notes": f"Proposed from profile {self.profile_token}. PTZ values are in ONVIF's normalized spaces.",
        }

    async def _presets(self) -> list[str]:
        try:
            body = await self._post(
                self.services["ptz"],
                soap.call(soap.PTZ, "GetPresets", soap.element("tptz:ProfileToken", self.profile_token)),
            )
        except (DriverError, TimeoutError):
            return []
        return [str(item.get("token")) for item in soap.find_all(body, "Preset") if item.get("token")]
