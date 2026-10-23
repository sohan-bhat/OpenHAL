"""Klipper printers through the Moonraker API.

Protocol (moonraker.readthedocs.io, web_api and printer_objects pages).

- Moonraker exposes JSON-RPC methods over WebSocket (`/websocket`) and the same methods over
  HTTP (`GET /printer/objects/query?extruder=temperature,target`, `POST /printer/gcode/script`).
  `transport: http` (the default) polls. `transport: websocket` subscribes to every object the
  device file uses with `printer.objects.subscribe` and keeps a cache that
  `notify_status_update` messages refresh, so reads cost no round trip.
- An API key, when Moonraker requires one, comes from the environment variable named in
  `token_env` and is sent as `X-Api-Key`.
- Writes are Klipper G-code. Heater targets use `SET_HEATER_TEMPERATURE HEATER=<name>
  TARGET=<degC>`, the part fan uses `M106 S<0..255>` and generic fans use `SET_FAN_SPEED`.
  Klipper itself refuses targets above the heater's `max_temp` and the error is passed on.
- G-code requests only return when Klipper finishes. Homing can outlast the hub's 10 s driver
  timeout, so `home` returns `started` after `action_wait` and finishes in the background.
- When Klippy is not `ready` (shutdown after an MCU error, or still starting) the health check
  reports the printer as disconnected with Klipper's own message.

Mapping. Channel names map to printer objects by convention, and `map` can override them.

    read   state, klippy_state, extruder_temp, bed_temp, chamber_temp, progress, homed_axes,
           position_x, position_y, position_z, filename
           map { object: "temperature_sensor chamber", field: temperature, index: 2, scale: 100 }
    write  extruder_target, bed_target   map { heater: extruder | heater_bed | <heater_generic name> }
           fan_speed (percent)           map { fan: fan | <fan_generic name> }
    action home (arg axes: x, y, z, xy, all), pause, resume, cancel   map { command: ... }

Safe state. Native. `TURN_OFF_HEATERS`, then the device file's own steps. With
`emergency_stop_on_stop: true` the driver also calls `printer.emergency_stop`, after which
Klipper needs a FIRMWARE_RESTART.
"""

from __future__ import annotations

import asyncio
import contextlib
import itertools
import json
import os
import re
from typing import Any, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from openhal.drivers.base import Driver, DriverError, DriverInfo, Health, Reading
from openhal.drivers.serial import mapping
from openhal.spec.models import DeviceFile
from openhal.spec.units import Quantity, UnitError, convert, parse_unit

NAME = r"^[a-z][a-z0-9_]{0,47}$"
OBJECT = r"^[a-z_]+( [A-Za-z0-9_]+)?$"
HOME_DEADLINE_S = 300.0
PRINT_STATES = ["standby", "printing", "paused", "complete", "cancelled", "error"]
HOME_AXES = {"x": "G28 X", "y": "G28 Y", "z": "G28 Z", "xy": "G28 X Y", "all": "G28"}
PRINT_METHODS = {"pause": "printer.print.pause", "resume": "printer.print.resume", "cancel": "printer.print.cancel"}
HTTP_ROUTES = {
    "server.info": ("GET", "/server/info"),
    "printer.info": ("GET", "/printer/info"),
    "printer.objects.list": ("GET", "/printer/objects/list"),
    "printer.objects.query": ("GET", "/printer/objects/query"),
    "printer.gcode.script": ("POST", "/printer/gcode/script"),
    "printer.print.pause": ("POST", "/printer/print/pause"),
    "printer.print.resume": ("POST", "/printer/print/resume"),
    "printer.print.cancel": ("POST", "/printer/print/cancel"),
    "printer.emergency_stop": ("POST", "/printer/emergency_stop"),
}


class MoonrakerParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    host: str = Field(min_length=1, max_length=253)
    port: int = Field(default=7125, ge=1, le=65535)
    scheme: Literal["http", "https"] = "http"
    transport: Literal["http", "websocket"] = "http"
    token_env: str | None = Field(default=None, pattern=r"^[A-Z_][A-Z0-9_]{0,63}$")
    timeout: float = 5.0
    action_wait: float = 8.0
    emergency_stop_on_stop: bool = False

    @field_validator("timeout", "action_wait", mode="before")
    @classmethod
    def _duration(cls, value: Any) -> float:
        return mapping.duration(value)

    @model_validator(mode="after")
    def _ranges(self) -> MoonrakerParams:
        if not 0.1 <= self.timeout <= 60:
            raise ValueError("timeout must be between 100 ms and 60 s.")
        if not 0.1 <= self.action_wait <= 9:
            raise ValueError("action_wait must be between 100 ms and 9 s.")
        return self


class ReadMap(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    object: str = Field(pattern=OBJECT)
    field: str = Field(pattern=r"^[a-z_]+$")
    index: int | None = Field(default=None, ge=0, le=16)
    scale: float = 1.0


class WriteMap(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    heater: str | None = Field(default=None, pattern=NAME)
    fan: str | None = Field(default=None, pattern=NAME)

    @model_validator(mode="after")
    def _one(self) -> WriteMap:
        if (self.heater is None) == (self.fan is None):
            raise ValueError("give exactly one of heater or fan.")
        return self


class ActionMap(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    command: Literal["home", "pause", "resume", "cancel"]


READ_DEFAULTS: dict[str, dict[str, Any]] = {
    "state": {"object": "print_stats", "field": "state"},
    "klippy_state": {"object": "webhooks", "field": "state"},
    "filename": {"object": "print_stats", "field": "filename"},
    "extruder_temp": {"object": "extruder", "field": "temperature"},
    "bed_temp": {"object": "heater_bed", "field": "temperature"},
    "chamber_temp": {"object": "temperature_sensor chamber", "field": "temperature"},
    "progress": {"object": "virtual_sdcard", "field": "progress", "scale": 100},
    "homed_axes": {"object": "toolhead", "field": "homed_axes"},
    "position_x": {"object": "toolhead", "field": "position", "index": 0},
    "position_y": {"object": "toolhead", "field": "position", "index": 1},
    "position_z": {"object": "toolhead", "field": "position", "index": 2},
}
WRITE_DEFAULTS: dict[str, dict[str, Any]] = {
    "extruder_target": {"heater": "extruder"},
    "bed_target": {"heater": "heater_bed"},
    "fan_speed": {"fan": "fan"},
}


def heater_object(name: str) -> str:
    return name if name == "heater_bed" or re.fullmatch(r"extruder\d*", name) else f"heater_generic {name}"


def fan_object(name: str) -> str:
    return "fan" if name == "fan" else f"fan_generic {name}"


def _validate(model: type[BaseModel], raw: dict[str, Any] | None, default: dict[str, Any] | None, where: str) -> Any:
    data = raw if raw is not None else default
    if data is None:
        raise DriverError(
            f"{where} is not a Moonraker channel the driver knows. Add a map, see docs/drivers/moonraker.md."
        )
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        problems = "; ".join(f"{'.'.join(str(p) for p in e['loc']) or 'map'}: {e['msg']}" for e in exc.errors())
        raise DriverError(f"{where}.map is not valid for the Moonraker driver ({problems}).") from exc


class MoonrakerDriver(Driver):
    """Klipper printers through the Moonraker HTTP and WebSocket API."""

    info: ClassVar[DriverInfo] = DriverInfo(
        name="moonraker",
        protocols=("Moonraker JSON-RPC over HTTP", "Moonraker JSON-RPC over WebSocket"),
        hazard_default="medium",
        summary="Klipper 3D printers through Moonraker. Temperatures, targets, fans, homing and print control.",
        safe_state_support="native",
    )
    params_model: ClassVar[type[Any] | None] = MoonrakerParams

    def __init__(self, device: DeviceFile, *, http_transport: Any = None) -> None:
        super().__init__(device)
        self.settings = MoonrakerParams.model_validate(device.connect.params)
        self._http_transport = http_transport
        self.reads: dict[str, ReadMap] = {}
        self.writes: dict[str, WriteMap] = {}
        self.actions: dict[str, ActionMap] = {}
        self.printer_info: dict[str, Any] = {}
        self.cache: dict[str, dict[str, Any]] = {}
        self._client: Any = None
        self._ws: Any = None
        self._ws_task: asyncio.Task[None] | None = None
        self._pending: dict[int, asyncio.Future[Any]] = {}
        self._ids = itertools.count(1)
        self._lost: str | None = None
        self._background: set[asyncio.Task[Any]] = set()
        self._check_maps()

    def _check_maps(self) -> None:
        for name, spec in self.device.read.items():
            if spec.type == "image":
                raise DriverError(f"read.{name}: the Moonraker driver doesn't read images.")
            self.reads[name] = _validate(ReadMap, spec.map, READ_DEFAULTS.get(name), f"read.{name}")
        for name, write_spec in self.device.write.items():
            write_map = _validate(WriteMap, write_spec.map, WRITE_DEFAULTS.get(name), f"write.{name}")
            if write_spec.type != "number":
                raise DriverError(f"write.{name}: Moonraker heater and fan channels are numbers.")
            wanted = "degC" if write_map.heater else "percent"
            if wanted == "percent" and write_spec.unit not in ("percent", "%"):
                raise DriverError(f"write.{name}: fan channels must be in percent.")
            self._convertible(name, write_spec.unit, wanted)
            self.writes[name] = write_map
        for name, action in self.device.actions.items():
            known = {"command": name} if name in PRINT_METHODS or name == "home" else None
            action_map = _validate(ActionMap, action.map, known, f"actions.{name}")
            if action_map.command == "home" and set(action.args) - {"axes"}:
                raise DriverError(f"actions.{name}: home takes only an axes argument.")
            self.actions[name] = action_map

    def _convertible(self, name: str, unit: str | None, wanted: str) -> None:
        try:
            convert(Quantity(1, parse_unit(unit or "")), wanted)
        except UnitError:
            raise DriverError(f"write.{name} needs a unit that converts to {wanted}.") from None

    def _objects(self) -> dict[str, list[str]]:
        """Every printer object and field the device file uses, for queries and subscriptions."""
        wanted: dict[str, set[str]] = {"webhooks": {"state", "state_message"}}
        for read_map in self.reads.values():
            wanted.setdefault(read_map.object, set()).add(read_map.field)
        for write_map in self.writes.values():
            if write_map.heater:
                wanted.setdefault(heater_object(write_map.heater), set()).add("target")
            else:
                wanted.setdefault(fan_object(write_map.fan or "fan"), set()).add("speed")
        return {name: sorted(fields) for name, fields in wanted.items()}

    # ------------------------------------------------------------------ transport

    def _token(self) -> str | None:
        if self.settings.token_env is None:
            return None
        token = os.environ.get(self.settings.token_env)
        if not token:
            raise DriverError(f"Set the {self.settings.token_env} environment variable to the Moonraker API key.")
        return token

    async def connect(self) -> None:
        import httpx

        await self.close()
        token = self._token()
        headers = {"X-Api-Key": token} if token else {}
        base = f"{self.settings.scheme}://{self.settings.host}:{self.settings.port}"
        self._client = httpx.AsyncClient(
            base_url=base, headers=headers, timeout=self.settings.timeout, transport=self._http_transport
        )
        self._lost = None
        self.cache.clear()
        if self.settings.transport == "websocket":
            await self._open_websocket(headers)
        self.printer_info = await self._rpc("printer.info")
        if self.device.match.moonraker:
            self._check_match()
        if self.settings.transport == "websocket":
            result = await self._rpc("printer.objects.subscribe", {"objects": self._objects()})
            self._merge(result.get("status", {}))

    def _check_match(self) -> None:
        import fnmatch

        for key, pattern in self.device.match.moonraker.items():
            value = str(self.printer_info.get(key, ""))
            if not fnmatch.fnmatch(value, pattern):
                raise DriverError(
                    f"This Moonraker reports {key}={value!r}, which doesn't match match.moonraker {pattern!r}."
                )

    async def _open_websocket(self, headers: dict[str, str]) -> None:
        from websockets.asyncio.client import connect

        scheme = "wss" if self.settings.scheme == "https" else "ws"
        url = f"{scheme}://{self.settings.host}:{self.settings.port}/websocket"
        try:
            self._ws = await connect(url, additional_headers=headers, open_timeout=self.settings.timeout, proxy=None)
        except (OSError, TimeoutError) as exc:
            raise DriverError(f"Could not open the Moonraker WebSocket at {url} ({exc}).") from exc
        except Exception as exc:  # websockets raises InvalidStatus, InvalidHandshake and others
            raise DriverError(f"Moonraker refused the WebSocket at {url} ({exc}). Check token_env.") from exc
        self._ws_task = asyncio.create_task(self._ws_reader(self._ws))

    async def _ws_reader(self, ws: Any) -> None:
        try:
            async for raw in ws:
                self._ws_message(raw)
            self._lost = "Moonraker closed the WebSocket"
        except Exception as exc:  # noqa: BLE001 (any failure ends the session)
            self._lost = f"the WebSocket failed ({exc})"
        for future in self._pending.values():
            if not future.done():
                future.set_exception(DriverError(f"Moonraker disconnected ({self._lost}). Reconnect it."))
                future.exception()
        self._pending.clear()

    def _ws_message(self, raw: str | bytes) -> None:
        try:
            message = json.loads(raw)
        except ValueError:
            return
        if not isinstance(message, dict):
            return
        if message.get("method") == "notify_status_update":
            params = message.get("params") or [{}]
            if params and isinstance(params[0], dict):
                self._merge(params[0])
            return
        if message.get("method") in ("notify_klippy_shutdown", "notify_klippy_disconnected"):
            self.cache.setdefault("webhooks", {})["state"] = "shutdown"
            return
        future = self._pending.pop(message.get("id", -1), None) if isinstance(message.get("id"), int) else None
        if future is None or future.done():
            return
        if "error" in message:
            error = message["error"] or {}
            future.set_exception(DriverError(f"Moonraker refused the request ({error.get('message', error)})."))
            future.exception()
        else:
            future.set_result(message.get("result"))

    def _merge(self, status: dict[str, Any]) -> None:
        for name, fields in status.items():
            if isinstance(fields, dict):
                self.cache.setdefault(name, {}).update(fields)

    async def _rpc(self, method: str, params: dict[str, Any] | None = None, *, deadline: float | None = None) -> Any:
        if self._client is None:
            raise DriverError(f"{self.device.device_id} is not connected. Connect it first.")
        if self._lost:
            raise DriverError(f"Moonraker disconnected ({self._lost}). Reconnect it.")
        wait = deadline or self.settings.timeout
        if self._ws is not None:
            return await self._ws_call(method, params, wait)
        return await self._http_call(method, params or {}, wait)

    async def _ws_call(self, method: str, params: dict[str, Any] | None, wait: float) -> Any:
        ident = next(self._ids)
        future: asyncio.Future[Any] = asyncio.get_running_loop().create_future()
        self._pending[ident] = future
        request = {"jsonrpc": "2.0", "method": method, "id": ident, "params": params or {}}
        try:
            await self._ws.send(json.dumps(request))
            return await asyncio.wait_for(future, wait)
        except TimeoutError:
            raise TimeoutError(f"Moonraker didn't answer {method} within {wait:g} s.") from None
        except DriverError:
            raise
        except Exception as exc:
            self._lost = f"sending failed ({exc})"
            raise DriverError(f"Moonraker disconnected while sending {method} ({exc}).") from exc
        finally:
            self._pending.pop(ident, None)

    async def _http_call(self, method: str, params: dict[str, Any], wait: float) -> Any:
        import httpx

        verb, path = HTTP_ROUTES[method]
        if method == "printer.objects.query":
            query = {name: ",".join(fields) for name, fields in params["objects"].items()}
            request = self._client.get(path, params=query)
        elif verb == "POST":
            request = self._client.post(path, json=params or None, timeout=wait)
        else:
            request = self._client.get(path)
        try:
            response = await asyncio.wait_for(request, wait)
        except (httpx.TimeoutException, TimeoutError):
            raise TimeoutError(f"Moonraker didn't answer {method} within {wait:g} s.") from None
        except httpx.HTTPError as exc:
            raise DriverError(
                f"Could not reach Moonraker at {self.settings.host}:{self.settings.port} ({exc}). "
                "Check that the printer's host is on and on the network."
            ) from exc
        try:
            body = response.json()
        except ValueError:
            raise DriverError(
                f"Moonraker sent a reply to {method} that is not JSON (HTTP {response.status_code})."
            ) from None
        if response.status_code == 401:
            raise DriverError("Moonraker wants an API key. Set token_env to a variable that holds it.")
        if response.status_code >= 400 or not isinstance(body, dict) or "result" not in body:
            error = body.get("error", {}) if isinstance(body, dict) else {}
            message = error.get("message", body) if isinstance(error, dict) else error
            raise DriverError(f"Moonraker refused {method} ({message}).")
        return body["result"]

    async def _gcode(self, script: str, *, deadline: float | None = None) -> None:
        mapping.plain_text(script, "G-code")
        await self._rpc("printer.gcode.script", {"script": script}, deadline=deadline)

    # ------------------------------------------------------------------ identity and describe

    async def identify(self) -> dict[str, str]:
        if self._client is None:
            return {"host": self.settings.host}
        info = await self._rpc("printer.info")
        return {
            "host": self.settings.host,
            **{key: str(info[key]) for key in ("hostname", "software_version", "state") if key in info},
        }

    async def describe(self) -> dict[str, Any] | None:
        if self._client is None:
            return None
        objects = (await self._rpc("printer.objects.list")).get("objects", [])
        query = {"configfile": ["settings"]} if "configfile" in objects else {}
        settings = {}
        if query:
            status = (await self._rpc("printer.objects.query", {"objects": query})).get("status", {})
            settings = status.get("configfile", {}).get("settings", {})
        return _proposal(objects, settings, self.printer_info)

    # ------------------------------------------------------------------ reads

    async def _status(self, objects: dict[str, list[str]]) -> dict[str, Any]:
        if self._ws is not None and all(name in self.cache for name in objects):
            if self._lost:
                raise DriverError(f"Moonraker disconnected ({self._lost}). Reconnect it.")
            return self.cache
        result = await self._rpc("printer.objects.query", {"objects": objects})
        status = result.get("status", {}) if isinstance(result, dict) else {}
        if self._ws is not None:
            self._merge(status)
        return dict(status)

    async def _field(self, obj: str, field: str, channel: str) -> Any:
        status = await self._status({obj: [field]})
        if obj not in status:
            raise DriverError(f"Klipper has no object {obj!r}, so {channel} can't be read. Check printer.cfg.")
        if field not in status[obj]:
            raise DriverError(f"Klipper's {obj!r} has no field {field!r}.")
        return status[obj][field]

    async def read(self, channel: str) -> Reading:
        unit = self.device.channel_unit(channel)
        if channel in self.reads:
            read_map = self.reads[channel]
            raw = await self._field(read_map.object, read_map.field, channel)
            if read_map.index is not None:
                if not isinstance(raw, list) or read_map.index >= len(raw):
                    raise DriverError(f"{read_map.object}.{read_map.field} has no index {read_map.index}.")
                raw = raw[read_map.index]
            return Reading(channel, self._value(channel, raw, read_map), unit)
        if channel in self.writes:
            write_map = self.writes[channel]
            if write_map.heater:
                raw = await self._field(heater_object(write_map.heater), "target", channel)
                return Reading(channel, self._number(raw, "degC", unit, channel), unit)
            raw = await self._field(fan_object(write_map.fan or "fan"), "speed", channel)
            return Reading(channel, self._number(raw, "percent", unit, channel, scale=100.0), unit)
        raise DriverError(f"{self.device.device_id} has no channel {channel!r}.")

    def _value(self, channel: str, raw: Any, read_map: ReadMap) -> float | bool | str | None:
        spec = self.device.read[channel]
        if spec.type == "number":
            protocol_unit = "degC" if read_map.field in ("temperature", "target") else spec.unit or "dimensionless"
            if read_map.field == "position":
                protocol_unit = "mm"
            return self._number(raw, protocol_unit, spec.unit, channel, scale=read_map.scale)
        if spec.type == "bool":
            if not isinstance(raw, bool):
                raise DriverError(f"{channel}: expected true or false from Klipper, got {raw!r}.")
            return raw
        text = str(raw)
        if spec.type == "enum" and text not in spec.values:
            raise DriverError(f"{channel}: Klipper reported {text!r}, which is not one of {', '.join(spec.values)}.")
        return text

    def _number(self, raw: Any, protocol_unit: str, unit: str | None, channel: str, *, scale: float = 1.0) -> float:
        if isinstance(raw, bool) or not isinstance(raw, int | float):
            raise DriverError(f"{channel}: expected a number from Klipper, got {raw!r}.")
        value = float(raw) * scale
        if unit and protocol_unit != unit:
            try:
                return convert(Quantity(value, parse_unit(protocol_unit)), unit)
            except UnitError as exc:
                raise DriverError(f"{channel}: {exc}") from exc
        return value

    # ------------------------------------------------------------------ writes and actions

    async def _write(self, channel: str, value: float | bool | str) -> Reading | None:
        write_map = self.writes.get(channel)
        if write_map is None or isinstance(value, bool) or not isinstance(value, int | float):
            raise DriverError(f"{self.device.device_id} has no numeric write channel {channel!r}.")
        unit = self.device.channel_unit(channel)
        if write_map.heater:
            celsius = convert(Quantity(float(value), parse_unit(unit or "degC")), "degC")
            await self._gcode(f"SET_HEATER_TEMPERATURE HEATER={write_map.heater} TARGET={celsius:.1f}")
        elif write_map.fan == "fan":
            await self._gcode(f"M106 S{max(0, min(255, round(float(value) * 255 / 100)))}")
        else:
            await self._gcode(f"SET_FAN_SPEED FAN={write_map.fan} SPEED={max(0.0, min(1.0, float(value) / 100)):.3f}")
        return Reading(channel, value, unit)

    async def _action(self, name: str, args: dict[str, Any]) -> Any:
        action_map = self.actions.get(name)
        if action_map is None:
            raise DriverError(f"{self.device.device_id} has no action {name!r}.")
        if action_map.command in PRINT_METHODS:
            await self._rpc(PRINT_METHODS[action_map.command])
            return {"sent": PRINT_METHODS[action_map.command]}
        axes = str(args.get("axes", "all"))
        if axes not in HOME_AXES:
            raise DriverError(f"home can't take axes {axes!r}. Use one of {', '.join(HOME_AXES)}.")
        task = asyncio.create_task(self._gcode(HOME_AXES[axes], deadline=HOME_DEADLINE_S))
        try:
            await asyncio.wait_for(asyncio.shield(task), self.settings.action_wait)
        except TimeoutError:
            self._background.add(task)
            task.add_done_callback(self._finished)
            return {"sent": HOME_AXES[axes], "status": "started"}
        return {"sent": HOME_AXES[axes], "status": "done"}

    def _finished(self, task: asyncio.Task[Any]) -> None:
        self._background.discard(task)
        if not task.cancelled():
            task.exception()

    async def _safe_state(self) -> None:
        await self._gcode("TURN_OFF_HEATERS")
        if self.settings.emergency_stop_on_stop:
            await self._rpc("printer.emergency_stop")

    async def health(self) -> Health:
        if self._client is None:
            return Health(connected=False, detail="not connected")
        if self._lost:
            return Health(connected=False, detail=self._lost)
        try:
            if self._ws is not None and "webhooks" in self.cache:
                webhooks = self.cache["webhooks"]
            else:
                webhooks = await self._rpc("printer.info")
        except (DriverError, TimeoutError) as exc:
            return Health(connected=False, detail=str(exc))
        if webhooks.get("state") != "ready":
            detail = f"Klippy is {webhooks.get('state')}: {webhooks.get('state_message', '')}"
            return Health(connected=False, detail=detail)
        return Health(connected=True, detail=str(self.printer_info.get("hostname", "")))

    async def close(self) -> None:
        for background in list(self._background):
            background.cancel()
        ws, task, client = self._ws, self._ws_task, self._client
        self._ws = None
        self._ws_task = None
        self._client = None
        if ws is not None:
            with contextlib.suppress(Exception):
                await ws.close()
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
        if client is not None:
            await client.aclose()


def _alias(name: str) -> str:
    alias = name.split(" ", 1)[-1].lower()
    alias = {"heater_bed": "bed"}.get(alias, alias)
    alias = re.sub(r"[^a-z0-9_]", "_", alias)
    return alias if re.match(r"^[a-z]", alias) else f"h_{alias}"


def _proposal(objects: list[str], settings: dict[str, Any], info: dict[str, Any]) -> dict[str, Any]:
    read: dict[str, Any] = {}
    write: dict[str, Any] = {}
    actions: dict[str, Any] = {}
    if "print_stats" in objects:
        read["state"] = {"type": "enum", "values": PRINT_STATES, "every": "1 s"}
    for name in objects:
        heater = name == "heater_bed" or re.fullmatch(r"extruder\d*", name) or name.startswith("heater_generic ")
        if heater:
            alias = _alias(name)
            gcode_name = name.split(" ", 1)[-1]
            read[f"{alias}_temp"] = {"unit": "degC", "every": "1 s", "map": {"object": name, "field": "temperature"}}
            top = float(settings.get(name.lower(), {}).get("max_temp", 0)) or None
            if top:
                write[f"{alias}_target"] = {
                    "unit": "degC",
                    "min": 0,
                    "max": top,
                    "max_change_per_s": 20,
                    "suggested": True,
                    "map": {"heater": gcode_name},
                }
        elif name.startswith("temperature_sensor "):
            read[f"{_alias(name)}_temp"] = {"unit": "degC", "map": {"object": name, "field": "temperature"}}
        elif name == "fan":
            write["fan_speed"] = {"unit": "percent", "min": 0, "max": 100, "suggested": True, "map": {"fan": "fan"}}
        elif name.startswith("fan_generic "):
            write[f"{_alias(name)}_fan"] = {
                "unit": "percent",
                "min": 0,
                "max": 100,
                "suggested": True,
                "map": {"fan": name.split(" ", 1)[1]},
            }
    if "virtual_sdcard" in objects:
        read["progress"] = {"unit": "percent", "every": "5 s"}
    if "toolhead" in objects:
        read["homed_axes"] = {"type": "string"}
        actions["home"] = {
            "args": {"axes": {"type": "enum", "values": list(HOME_AXES)}},
            "require": ["state != printing"] if "state" in read else [],
            "confirm": "confirm",
            "suggested": True,
        }
    if "print_stats" in objects:
        actions["pause"] = {"require": ["state == printing"], "suggested": True}
        actions["resume"] = {"require": ["state == paused"], "suggested": True}
        actions["cancel"] = {"confirm": "confirm", "suggested": True}
    proposal: dict[str, Any] = {
        "device": {"name": str(info.get("hostname") or "Klipper printer")},
        "read": read,
        "write": write,
        "actions": actions,
        "notes": "Proposed from printer.objects.list. Heater maxima come from printer.cfg max_temp. Lower them.",
    }
    if info.get("hostname"):
        proposal["match"] = {"moonraker": {"hostname": str(info["hostname"])}}
    return proposal
