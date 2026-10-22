"""Printers run through OctoPrint, over its REST API.

Protocol (docs.octoprint.org, REST API pages for version, printer operations and job operations).

- Every request carries the API key from the environment variable named in `token_env` as
  `X-Api-Key`. OctoPrint answers 403 for a missing or wrong key.
- Temperatures come from `GET /api/printer?exclude=sd` (`temperature.tool0.actual`, `.target`,
  `bed`, `chamber`) and the state from its `state.flags`. While the printer is not connected to
  OctoPrint these endpoints answer 409, which the driver reports as a disconnected device.
- Heater targets are `POST /api/printer/tool` with `{"command": "target", "targets": {...}}`,
  and the same for `/bed` and `/chamber`. OctoPrint has no fan endpoint, so the part fan is set
  with `POST /api/printer/command` and `M106 P<n> S<0..255>`, and can't be read back.
- Homing is `POST /api/printer/printhead` with `{"command": "home", "axes": [...]}`. OctoPrint
  queues the G28 and answers at once.
- Pause, resume and cancel are `POST /api/job`, for prints OctoPrint streams itself.

Mapping. Channel names follow the moonraker driver where the API allows it.

    read   state (enum of standby, printing, paused, cancelling, error, offline), state_text,
           extruder_temp, bed_temp, chamber_temp, progress, filename
           map { heater: tool0 | tool1 | bed | chamber, field: actual | target }
    write  extruder_target, bed_target, chamber_target   map { heater: tool1 }
           fan_speed (percent)                           map { fan: 0 }
    action home (arg axes: x, y, z, xy, all), pause, resume, cancel   map { command: ... }

Safe state. Native. Every heater named in the file, plus tool0 and the bed, gets target 0.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from openhal.drivers.base import Driver, DriverError, DriverInfo, Health, Reading
from openhal.drivers.serial import mapping
from openhal.spec.models import DeviceFile
from openhal.spec.units import Quantity, UnitError, convert, parse_unit

HEATER = r"^(tool[0-9]|bed|chamber)$"
STATES = ["standby", "printing", "paused", "cancelling", "error", "offline"]
HOME_AXES = {"x": ["x"], "y": ["y"], "z": ["z"], "xy": ["x", "y"], "all": ["x", "y", "z"]}
JOB_COMMANDS = {
    "pause": {"command": "pause", "action": "pause"},
    "resume": {"command": "pause", "action": "resume"},
    "cancel": {"command": "cancel"},
}


class OctoPrintParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    host: str = Field(min_length=1, max_length=253)
    port: int = Field(default=80, ge=1, le=65535)
    scheme: Literal["http", "https"] = "http"
    path: str = Field(default="", max_length=100, pattern=r"^(/[A-Za-z0-9._~-]+)*$")
    token_env: str = Field(default="OCTOPRINT_API_KEY", pattern=r"^[A-Z_][A-Z0-9_]{0,63}$")
    timeout: float = 5.0

    @field_validator("timeout", mode="before")
    @classmethod
    def _duration(cls, value: Any) -> float:
        seconds = mapping.duration(value)
        if not 0.1 <= seconds <= 60:
            raise ValueError("timeout must be between 100 ms and 60 s.")
        return seconds


class ReadMap(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    heater: str = Field(pattern=HEATER)
    field: Literal["actual", "target"] = "actual"


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


SPECIAL_READS = {"state", "state_text", "progress", "filename"}
READ_DEFAULTS: dict[str, dict[str, Any]] = {
    "extruder_temp": {"heater": "tool0"},
    "bed_temp": {"heater": "bed"},
    "chamber_temp": {"heater": "chamber"},
}
WRITE_DEFAULTS: dict[str, dict[str, Any]] = {
    "extruder_target": {"heater": "tool0"},
    "bed_target": {"heater": "bed"},
    "chamber_target": {"heater": "chamber"},
    "fan_speed": {"fan": 0},
}


def _validate(model: type[BaseModel], raw: dict[str, Any] | None, default: dict[str, Any] | None, where: str) -> Any:
    data = raw if raw is not None else default
    if data is None:
        raise DriverError(
            f"{where} is not an OctoPrint channel the driver knows. Add a map, see docs/drivers/octoprint.md."
        )
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        problems = "; ".join(f"{'.'.join(str(p) for p in e['loc']) or 'map'}: {e['msg']}" for e in exc.errors())
        raise DriverError(f"{where}.map is not valid for the OctoPrint driver ({problems}).") from exc


def state_from_flags(flags: dict[str, Any]) -> str:
    if flags.get("closedOrError"):
        return "error" if flags.get("error") else "offline"
    if flags.get("error"):
        return "error"
    if flags.get("cancelling"):
        return "cancelling"
    if flags.get("paused") or flags.get("pausing"):
        return "paused"
    if flags.get("printing"):
        return "printing"
    return "standby"


class OctoPrintDriver(Driver):
    """Printers connected to an OctoPrint server."""

    info: ClassVar[DriverInfo] = DriverInfo(
        name="octoprint",
        protocols=("OctoPrint REST API",),
        hazard_default="medium",
        summary="3D printers run through OctoPrint. Temperatures, targets, fan, homing and job control.",
        safe_state_support="native",
    )
    params_model: ClassVar[type[Any] | None] = OctoPrintParams

    def __init__(self, device: DeviceFile, *, http_transport: Any = None) -> None:
        super().__init__(device)
        self.settings = OctoPrintParams.model_validate(device.connect.params)
        self._http_transport = http_transport
        self._client: Any = None
        self.version: dict[str, Any] = {}
        self.reads: dict[str, ReadMap | None] = {}
        self.writes: dict[str, WriteMap] = {}
        self.actions: dict[str, ActionMap] = {}
        self._fan_sent: dict[str, Reading] = {}
        self._check_maps()

    def _check_maps(self) -> None:
        for name, spec in self.device.read.items():
            if name in SPECIAL_READS and spec.map is None:
                self.reads[name] = None
                if name == "state" and (spec.type != "enum" or set(spec.values) - set(STATES)):
                    raise DriverError(f"read.state must be an enum with values from {', '.join(STATES)}.")
                continue
            if spec.type != "number":
                raise DriverError(f"read.{name}: OctoPrint temperature channels are numbers.")
            self.reads[name] = _validate(ReadMap, spec.map, READ_DEFAULTS.get(name), f"read.{name}")
            self._convertible(name, spec.unit, "degC")
        for name, write_spec in self.device.write.items():
            write_map = _validate(WriteMap, write_spec.map, WRITE_DEFAULTS.get(name), f"write.{name}")
            if write_spec.type != "number":
                raise DriverError(f"write.{name}: OctoPrint heater and fan channels are numbers.")
            if write_map.fan is not None and write_spec.unit not in ("percent", "%"):
                raise DriverError(f"write.{name}: fan channels must be in percent.")
            if write_map.heater is not None:
                self._convertible(name, write_spec.unit, "degC")
            self.writes[name] = write_map
        for name, action in self.device.actions.items():
            known = {"command": name} if name in JOB_COMMANDS or name == "home" else None
            action_map = _validate(ActionMap, action.map, known, f"actions.{name}")
            if action_map.command == "home" and set(action.args) - {"axes"}:
                raise DriverError(f"actions.{name}: home takes only an axes argument.")
            self.actions[name] = action_map

    def _convertible(self, name: str, unit: str | None, wanted: str) -> None:
        try:
            convert(Quantity(1, parse_unit(unit or "")), wanted)
        except UnitError:
            raise DriverError(f"{name} needs a unit that converts to {wanted}.") from None

    # ------------------------------------------------------------------ HTTP

    async def connect(self) -> None:
        import httpx

        await self.close()
        token = os.environ.get(self.settings.token_env)
        if not token:
            raise DriverError(f"Set the {self.settings.token_env} environment variable to an OctoPrint API key.")
        base = f"{self.settings.scheme}://{self.settings.host}:{self.settings.port}{self.settings.path}"
        self._client = httpx.AsyncClient(
            base_url=base,
            headers={"X-Api-Key": token},
            timeout=self.settings.timeout,
            transport=self._http_transport,
        )
        self._fan_sent.clear()
        self.version = await self._request("GET", "/api/version")

    async def _request(self, verb: str, path: str, body: dict[str, Any] | None = None) -> Any:
        import httpx

        if self._client is None:
            raise DriverError(f"{self.device.device_id} is not connected. Connect it first.")
        try:
            response = await asyncio.wait_for(self._client.request(verb, path, json=body), self.settings.timeout)
        except (httpx.TimeoutException, TimeoutError):
            raise TimeoutError(f"OctoPrint didn't answer {verb} {path} within {self.settings.timeout:g} s.") from None
        except httpx.HTTPError as exc:
            raise DriverError(
                f"Could not reach OctoPrint at {self.settings.host}:{self.settings.port} ({exc}). "
                "Check that the server is on and on the network."
            ) from exc
        if response.status_code in (401, 403):
            raise DriverError(f"OctoPrint refused the API key in {self.settings.token_env}. Create a new key.")
        if response.status_code == 409:
            raise DriverError(f"OctoPrint says the printer can't do this now ({_error(response)}).")
        if response.status_code >= 400:
            raise DriverError(f"OctoPrint refused {verb} {path} (HTTP {response.status_code}, {_error(response)}).")
        if response.status_code == 204 or not response.content:
            return None
        try:
            return response.json()
        except ValueError:
            raise DriverError(f"OctoPrint sent a reply to {path} that is not JSON.") from None

    # ------------------------------------------------------------------ identity and describe

    async def identify(self) -> dict[str, str]:
        if self._client is None:
            return {"host": self.settings.host}
        version = await self._request("GET", "/api/version")
        return {"host": self.settings.host, "server": str(version.get("server")), "api": str(version.get("api"))}

    async def describe(self) -> dict[str, Any] | None:
        if self._client is None:
            return None
        profiles: dict[str, Any] = (await self._request("GET", "/api/printerprofiles")).get("profiles", {})
        current = [item for item in profiles.values() if item.get("current")]
        profile: dict[str, Any] = (current or list(profiles.values()) or [{}])[0]
        read: dict[str, Any] = {
            "state": {"type": "enum", "values": STATES, "every": "1 s"},
            "progress": {"unit": "percent"},
        }
        write: dict[str, Any] = {}
        count = int(profile.get("extruder", {}).get("count", 1))
        for index in range(count):
            alias = "extruder" if index == 0 else f"extruder{index}"
            read[f"{alias}_temp"] = {"unit": "degC", "every": "2 s", "map": {"heater": f"tool{index}"}}
            write[f"{alias}_target"] = {
                "unit": "degC",
                "min": 0,
                "max": 250,
                "max_change_per_s": 50,
                "suggested": True,
                "map": {"heater": f"tool{index}"},
            }
        for kind, top in (("bed", 100), ("chamber", 60)):
            if profile.get(f"heated{kind.title()}"):
                read[f"{kind}_temp"] = {"unit": "degC", "every": "2 s"}
                write[f"{kind}_target"] = {"unit": "degC", "min": 0, "max": top, "suggested": True}
        write["fan_speed"] = {"unit": "percent", "min": 0, "max": 100, "suggested": True}
        actions = {
            "home": {
                "args": {"axes": {"type": "enum", "values": list(HOME_AXES)}},
                "require": ["state != printing"],
                "confirm": "confirm",
                "suggested": True,
            },
            "pause": {"require": ["state == printing"], "suggested": True},
            "resume": {"require": ["state == paused"], "suggested": True},
            "cancel": {"confirm": "confirm", "suggested": True},
        }
        return {
            "device": {"name": str(profile.get("name") or "OctoPrint printer"), "model": profile.get("model")},
            "read": read,
            "write": write,
            "actions": actions,
            "notes": "Proposed from the current OctoPrint printer profile. The heater maxima are placeholders.",
        }

    # ------------------------------------------------------------------ reads

    async def read(self, channel: str) -> Reading:
        unit = self.device.channel_unit(channel)
        if channel in self.reads:
            read_map = self.reads[channel]
            if read_map is None:
                return await self._special(channel, unit)
            value = await self._heater_value(read_map.heater, read_map.field, channel)
            return Reading(channel, self._from(value, unit), unit)
        if channel in self.writes:
            write_map = self.writes[channel]
            if write_map.heater is not None:
                value = await self._heater_value(write_map.heater, "target", channel)
                return Reading(channel, self._from(value, unit), unit)
            if self._client is None:
                raise DriverError(f"{self.device.device_id} is not connected. Connect it first.")
            # OctoPrint can't report fan speed. Report what this driver last sent, or unknown.
            return self._fan_sent.get(channel) or Reading(channel, None, unit)
        raise DriverError(f"{self.device.device_id} has no channel {channel!r}.")

    async def _special(self, channel: str, unit: str | None) -> Reading:
        if channel in ("progress", "filename"):
            job = await self._request("GET", "/api/job")
            if channel == "filename":
                return Reading(channel, ((job.get("job") or {}).get("file") or {}).get("name") or "", None)
            completion = (job.get("progress") or {}).get("completion")
            return Reading(channel, None if completion is None else float(completion), unit)
        try:
            printer = await self._request("GET", "/api/printer?exclude=temperature,sd")
        except DriverError as exc:
            if "can't do this now" not in str(exc):
                raise
            state: dict[str, Any] = {"text": "Offline", "flags": {"closedOrError": True}}
        else:
            state = printer.get("state", {})
        if channel == "state_text":
            return Reading(channel, str(state.get("text", "")), None)
        value = state_from_flags(state.get("flags", {}))
        spec = self.device.read[channel]
        if value not in spec.values:
            raise DriverError(f"OctoPrint reports the printer as {value}, which is not in read.state values.")
        return Reading(channel, value, None)

    async def _heater_value(self, heater: str, field: str, channel: str) -> float:
        temps = (await self._request("GET", "/api/printer?exclude=state,sd")).get("temperature", {})
        reading = temps.get(heater)
        if not isinstance(reading, dict) or not isinstance(reading.get(field), int | float):
            raise DriverError(f"OctoPrint reports no {field} for {heater}, so {channel} can't be read.")
        return float(reading[field])

    def _from(self, celsius: float, unit: str | None) -> float:
        if not unit or unit == "degC":
            return celsius
        return convert(Quantity(celsius, parse_unit("degC")), unit)

    # ------------------------------------------------------------------ writes and actions

    async def _set_target(self, heater: str, celsius: float) -> None:
        if heater.startswith("tool"):
            await self._request("POST", "/api/printer/tool", {"command": "target", "targets": {heater: celsius}})
        else:
            await self._request("POST", f"/api/printer/{heater}", {"command": "target", "target": celsius})

    async def _write(self, channel: str, value: float | bool | str) -> Reading | None:
        write_map = self.writes.get(channel)
        if write_map is None or isinstance(value, bool) or not isinstance(value, int | float):
            raise DriverError(f"{self.device.device_id} has no numeric write channel {channel!r}.")
        unit = self.device.channel_unit(channel)
        if write_map.heater is not None:
            celsius = convert(Quantity(float(value), parse_unit(unit or "degC")), "degC")
            await self._set_target(write_map.heater, round(celsius, 1))
        else:
            pwm = max(0, min(255, round(float(value) * 255 / 100)))
            self._fan_sent.pop(channel, None)
            await self._request("POST", "/api/printer/command", {"commands": [f"M106 P{write_map.fan} S{pwm}"]})
            self._fan_sent[channel] = Reading(channel, value, unit)
        return Reading(channel, value, unit)

    async def _action(self, name: str, args: dict[str, Any]) -> Any:
        action_map = self.actions.get(name)
        if action_map is None:
            raise DriverError(f"{self.device.device_id} has no action {name!r}.")
        if action_map.command in JOB_COMMANDS:
            await self._request("POST", "/api/job", JOB_COMMANDS[action_map.command])
            return {"sent": action_map.command}
        axes = str(args.get("axes", "all"))
        if axes not in HOME_AXES:
            raise DriverError(f"home can't take axes {axes!r}. Use one of {', '.join(HOME_AXES)}.")
        await self._request("POST", "/api/printer/printhead", {"command": "home", "axes": HOME_AXES[axes]})
        return {"sent": "home", "axes": HOME_AXES[axes], "status": "queued"}

    async def _safe_state(self) -> None:
        heaters = {item.heater for item in self.writes.values() if item.heater} | {"tool0", "bed"}
        tools = {heater: 0 for heater in sorted(heaters) if heater.startswith("tool")}
        await self._request("POST", "/api/printer/tool", {"command": "target", "targets": tools})
        for heater in sorted(heaters - set(tools)):
            await self._set_target(heater, 0)

    async def health(self) -> Health:
        if self._client is None:
            return Health(connected=False, detail="not connected")
        try:
            printer = await self._request("GET", "/api/printer?exclude=temperature,sd")
        except (DriverError, TimeoutError) as exc:
            return Health(connected=False, detail=str(exc))
        state = printer.get("state", {})
        if not state.get("flags", {}).get("operational"):
            return Health(connected=False, detail=f"OctoPrint reports {state.get('text', 'not operational')}")
        return Health(connected=True, detail=str(self.version.get("text", "OctoPrint")))

    async def close(self) -> None:
        client, self._client = self._client, None
        if client is not None:
            await client.aclose()


def _error(response: Any) -> str:
    try:
        body = response.json()
    except ValueError:
        return response.text[:200] or "no details"
    if isinstance(body, dict) and "error" in body:
        return str(body["error"])
    return str(body)[:200]
