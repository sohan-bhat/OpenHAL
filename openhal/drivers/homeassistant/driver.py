"""Home Assistant bridge over the REST and WebSocket APIs.

Protocol (developers.home-assistant.io, REST API and WebSocket API pages).

- REST. `GET /api/states/<entity_id>` returns the state and attributes. `POST
  /api/services/<domain>/<service>` with `{"entity_id": ...}` calls a service. Requests carry a
  long-lived access token as `Authorization: Bearer <token>`.
- WebSocket (`transport: websocket`). After `auth_required` the client sends `auth`, then
  `subscribe_entities` for the selected entities only. Events carry compressed states (`a` for
  full states, `c` with `+` and `-` for changes), which the driver keeps in a cache so reads need
  no round trip. Services go through `call_service`.
- The token comes from the environment variable named in `token_env`, never from the file.

Bridge rules (docs/drivers/WRITING-A-DRIVER.md rule 9). Only the entities named in the device
file are reachable. `entity` or `entities` lists them, and a channel `map.entity` must be one of
them. If neither is given, the entities named in channel maps are the list. The device file's
limits apply even where Home Assistant has its own, and Home Assistant's limits only show up as
`suggested` values in `describe()`.

Channel roles, from the entity domain and the channel name or `map.attribute`.

    light           power (bool), brightness (percent), color_temp (K, attribute color_temp_kelvin)
    switch, input_boolean   power (bool)
    fan             power (bool), speed (percent, attribute percentage), preset (enum, preset_mode)
    number, input_number    value (number, converted from unit_of_measurement)
    select, input_select    option (enum)
    sensor          value (number or string, converted from unit_of_measurement)
    binary_sensor   state (bool)
    any domain      map { attribute: name } reads one attribute

An entity whose state is `unavailable` fails its reads and makes `health()` report the device
disconnected. `unknown` reads as no value.

Safe state. From the device file. Home Assistant has no emergency command of its own.
"""

from __future__ import annotations

import asyncio
import contextlib
import fnmatch
import itertools
import json
import math
import os
import re
from typing import Any, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from openhal.drivers.base import Driver, DriverError, DriverInfo, Health, Reading
from openhal.drivers.serial import mapping
from openhal.spec.models import DeviceFile, ReadChannel, WriteChannel
from openhal.spec.units import Quantity, UnitError, convert, parse_unit

ENTITY = r"^[a-z_]+\.[a-z0-9_]+$"
NAME_ATTRIBUTE = {
    "power": None,
    "state": None,
    "value": None,
    "option": None,
    "brightness": "brightness",
    "color_temp": "color_temp_kelvin",
    "speed": "percentage",
    "percentage": "percentage",
    "preset": "preset_mode",
}
ROLES = {
    ("light", None): "onoff",
    ("light", "brightness"): "brightness",
    ("light", "color_temp_kelvin"): "color_temp",
    ("switch", None): "onoff",
    ("input_boolean", None): "onoff",
    ("fan", None): "onoff",
    ("fan", "percentage"): "fan_percentage",
    ("fan", "preset_mode"): "fan_preset",
    ("number", None): "number",
    ("input_number", None): "number",
    ("select", None): "option",
    ("input_select", None): "option",
    ("sensor", None): "sensor",
    ("binary_sensor", None): "binary",
}
WRITE_ROLES = {
    "onoff": "bool",
    "brightness": "number",
    "color_temp": "number",
    "fan_percentage": "number",
    "fan_preset": "enum",
    "number": "number",
    "option": "enum",
}


class HomeAssistantParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    host: str = Field(min_length=1, max_length=253)
    port: int = Field(default=8123, ge=1, le=65535)
    scheme: Literal["http", "https"] = "http"
    token_env: str = Field(default="HA_TOKEN", pattern=r"^[A-Z_][A-Z0-9_]{0,63}$")
    entity: str | None = Field(default=None, pattern=ENTITY)
    entities: list[str] = Field(default=[], max_length=64)
    transport: Literal["rest", "websocket"] = "rest"
    timeout: float = 5.0

    @field_validator("timeout", mode="before")
    @classmethod
    def _duration(cls, value: Any) -> float:
        seconds = mapping.duration(value)
        if not 0.1 <= seconds <= 60:
            raise ValueError("timeout must be between 100 ms and 60 s.")
        return seconds

    @field_validator("entities")
    @classmethod
    def _entities(cls, value: list[str]) -> list[str]:
        for item in value:
            if not re.fullmatch(ENTITY, item):
                raise ValueError(f"{item!r} is not an entity id such as light.desk_lamp.")
        return value

    @model_validator(mode="after")
    def _one_way(self) -> HomeAssistantParams:
        if self.entity and self.entities:
            raise ValueError("give entity or entities, not both.")
        return self


class ChannelMap(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    entity: str | None = Field(default=None, pattern=ENTITY)
    attribute: str | None = Field(default=None, pattern=r"^[a-z_]{1,64}$")


class _Channel:
    def __init__(self, name: str, entity: str, attribute: str | None, role: str) -> None:
        self.name = name
        self.entity = entity
        self.attribute = attribute
        self.role = role
        self.domain = entity.split(".", 1)[0]


def _name_attribute(name: str) -> str | None:
    """The attribute a channel name implies, from the name or its last word (desk_lamp_brightness)."""
    if name in NAME_ATTRIBUTE:
        return NAME_ATTRIBUTE[name]
    for word, attribute in NAME_ATTRIBUTE.items():
        if name.endswith(f"_{word}"):
            return attribute
    return None


def ha_unit(text: Any) -> str | None:
    """Home Assistant's unit_of_measurement as a unit the OpenHAL registry knows, if any."""
    return mapping.device_unit(text)


class HomeAssistantDriver(Driver):
    """A bridge to the Home Assistant entities a device file selects."""

    info: ClassVar[DriverInfo] = DriverInfo(
        name="homeassistant",
        protocols=("Home Assistant REST API", "Home Assistant WebSocket API"),
        hazard_default="low",
        summary="Selected Home Assistant entities: lights, switches, fans, numbers, selects and sensors.",
    )
    params_model: ClassVar[type[Any] | None] = HomeAssistantParams

    def __init__(self, device: DeviceFile, *, http_transport: Any = None) -> None:
        super().__init__(device)
        self.settings = HomeAssistantParams.model_validate(device.connect.params)
        self._http_transport = http_transport
        self.channels: dict[str, _Channel] = {}
        self.allowed: list[str] = []
        self.ha_version: str | None = None
        self.cache: dict[str, dict[str, Any]] = {}
        self._client: Any = None
        self._ws: Any = None
        self._ws_task: asyncio.Task[None] | None = None
        self._pending: dict[int, asyncio.Future[Any]] = {}
        self._ids = itertools.count(1)
        self._lost: str | None = None
        self._check_maps()

    # ------------------------------------------------------------------ channel mapping

    def _check_maps(self) -> None:
        maps: dict[str, ChannelMap] = {}
        specs: dict[str, ReadChannel | WriteChannel] = {**self.device.read, **self.device.write}
        for name, spec in specs.items():
            try:
                maps[name] = ChannelMap.model_validate(spec.map or {})
            except ValidationError as exc:
                problems = "; ".join(f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors())
                raise DriverError(f"{name}.map is not valid for the Home Assistant driver ({problems}).") from exc
        listed = [self.settings.entity] if self.settings.entity else list(self.settings.entities)
        named = [item.entity for item in maps.values() if item.entity]
        self.allowed = listed or sorted(set(named))
        pattern = self.device.match.homeassistant
        for selected in self.allowed:
            if pattern and not fnmatch.fnmatch(selected, pattern):
                raise DriverError(f"{selected} doesn't match match.homeassistant {pattern!r}.")
        for name, spec in specs.items():
            channel_map = maps[name]
            if channel_map.entity is None and len(self.allowed) != 1:
                raise DriverError(f"{name} needs map.entity, because the file selects {len(self.allowed)} entities.")
            entity: str = channel_map.entity or self.allowed[0]
            if entity not in self.allowed:
                raise DriverError(
                    f"{name} uses {entity}, which the file doesn't select. "
                    "Add it to entities, or the bridge won't expose it."
                )
            attribute = channel_map.attribute if spec.map and "attribute" in spec.map else _name_attribute(name)
            domain = entity.split(".", 1)[0]
            role = ROLES.get((domain, attribute))
            if role is None:
                if attribute is None or name in self.device.write:
                    raise DriverError(
                        f"{name}: the driver doesn't know how to use {entity} this way. "
                        "See docs/drivers/homeassistant.md."
                    )
                role = "attribute"
            self._check_type(name, spec, role)
            self.channels[name] = _Channel(name, entity, attribute, role)

    def _check_type(self, name: str, spec: ReadChannel | WriteChannel, role: str) -> None:
        writable = name in self.device.write
        if writable and role not in WRITE_ROLES:
            raise DriverError(f"write.{name}: {role} entities are read-only in Home Assistant.")
        expected = WRITE_ROLES.get(role) or {"binary": "bool", "sensor": None, "attribute": None}.get(role)
        if expected and spec.type != expected:
            raise DriverError(f"{name}: a {role} channel must have type {expected}, not {spec.type}.")
        units = {"brightness": "percent", "fan_percentage": "percent", "color_temp": "K"}
        if role in units and spec.unit:
            try:
                convert(Quantity(1, parse_unit(spec.unit)), units[role])
            except UnitError:
                raise DriverError(f"{name}: a {role} channel needs a unit that converts to {units[role]}.") from None

    # ------------------------------------------------------------------ transport

    async def connect(self) -> None:
        import httpx

        await self.close()
        token = os.environ.get(self.settings.token_env)
        if not token:
            raise DriverError(
                f"Set the {self.settings.token_env} environment variable to a Home Assistant access token."
            )
        base = f"{self.settings.scheme}://{self.settings.host}:{self.settings.port}"
        self._client = httpx.AsyncClient(
            base_url=base,
            headers={"Authorization": f"Bearer {token}"},
            timeout=self.settings.timeout,
            transport=self._http_transport,
        )
        self._lost = None
        self.cache.clear()
        if self.settings.transport == "websocket":
            await self._open_websocket(token)
            return
        config = await self._rest("GET", "/api/config")
        self.ha_version = str(config.get("version", ""))

    async def _rest(self, verb: str, path: str, body: dict[str, Any] | None = None) -> Any:
        import httpx

        if self._client is None:
            raise DriverError(f"{self.device.device_id} is not connected. Connect it first.")
        try:
            response = await asyncio.wait_for(self._client.request(verb, path, json=body), self.settings.timeout)
        except (httpx.TimeoutException, TimeoutError):
            raise TimeoutError(
                f"Home Assistant didn't answer {verb} {path} within {self.settings.timeout:g} s."
            ) from None
        except httpx.HTTPError as exc:
            raise DriverError(
                f"Could not reach Home Assistant at {self.settings.host}:{self.settings.port} ({exc})."
            ) from exc
        if response.status_code == 401:
            raise DriverError(f"Home Assistant refused the token in {self.settings.token_env}. Create a new one.")
        try:
            data = response.json()
        except ValueError:
            raise DriverError(f"Home Assistant sent a reply to {path} that is not JSON.") from None
        if response.status_code == 404:
            raise DriverError(f"Home Assistant has no {path.rsplit('/', 1)[-1]}. Check the entity id.")
        if response.status_code >= 400:
            message = data.get("message", data) if isinstance(data, dict) else data
            raise DriverError(f"Home Assistant refused {path} ({message}).")
        return data

    async def _open_websocket(self, token: str) -> None:
        from websockets.asyncio.client import connect

        scheme = "wss" if self.settings.scheme == "https" else "ws"
        url = f"{scheme}://{self.settings.host}:{self.settings.port}/api/websocket"
        try:
            ws = await connect(url, open_timeout=self.settings.timeout, proxy=None)
        except (OSError, TimeoutError) as exc:
            raise DriverError(f"Could not open the Home Assistant WebSocket at {url} ({exc}).") from exc
        except Exception as exc:  # websockets raises InvalidStatus, InvalidHandshake and others
            raise DriverError(f"Home Assistant refused the WebSocket at {url} ({exc}).") from exc
        try:
            hello = json.loads(await asyncio.wait_for(ws.recv(), self.settings.timeout))
            await ws.send(json.dumps({"type": "auth", "access_token": token}))
            answer = json.loads(await asyncio.wait_for(ws.recv(), self.settings.timeout))
        except Exception as exc:
            await ws.close()
            raise DriverError(f"The Home Assistant WebSocket handshake failed ({exc}).") from exc
        if answer.get("type") != "auth_ok":
            await ws.close()
            raise DriverError(
                f"Home Assistant refused the token in {self.settings.token_env} ({answer.get('message')})."
            )
        self.ha_version = str(answer.get("ha_version") or hello.get("ha_version") or "")
        self._ws = ws
        self._ws_task = asyncio.create_task(self._ws_reader(ws))
        await self._ws_call({"type": "subscribe_entities", "entity_ids": self.allowed})

    async def _ws_reader(self, ws: Any) -> None:
        try:
            async for raw in ws:
                self._ws_message(raw)
            self._lost = "Home Assistant closed the WebSocket"
        except Exception as exc:  # noqa: BLE001 (any failure ends the session)
            self._lost = f"the WebSocket failed ({exc})"
        for future in self._pending.values():
            if not future.done():
                future.set_exception(DriverError(f"Home Assistant disconnected ({self._lost}). Reconnect it."))
                future.exception()
        self._pending.clear()

    def _ws_message(self, raw: str | bytes) -> None:
        try:
            message = json.loads(raw)
        except ValueError:
            return
        if not isinstance(message, dict):
            return
        if message.get("type") == "event":
            self._apply_event(message.get("event") or {})
            return
        if message.get("type") != "result":
            return
        future = self._pending.pop(message.get("id", -1), None)
        if future is None or future.done():
            return
        if message.get("success") is True:
            future.set_result(message.get("result"))
        elif message.get("success") is False:
            error = message.get("error") or {}
            future.set_exception(DriverError(f"Home Assistant refused the call ({error.get('message', error)})."))
            future.exception()
        else:
            future.set_exception(DriverError("Home Assistant sent a malformed result."))
            future.exception()

    def _apply_event(self, event: dict[str, Any]) -> None:
        for entity_id, state in (event.get("a") or {}).items():
            if entity_id in self.allowed:
                self.cache[entity_id] = {"state": state.get("s"), "attributes": dict(state.get("a") or {})}
        for entity_id, change in (event.get("c") or {}).items():
            if entity_id not in self.allowed or entity_id not in self.cache:
                continue
            entry = self.cache[entity_id]
            added = change.get("+") or {}
            if "s" in added:
                entry["state"] = added["s"]
            entry["attributes"].update(added.get("a") or {})
            for key in (change.get("-") or {}).get("a") or []:
                entry["attributes"].pop(key, None)
        for entity_id in event.get("r") or []:
            self.cache.pop(entity_id, None)

    async def _ws_call(self, message: dict[str, Any]) -> Any:
        ident = next(self._ids)
        future: asyncio.Future[Any] = asyncio.get_running_loop().create_future()
        self._pending[ident] = future
        try:
            await self._ws.send(json.dumps({"id": ident, **message}))
            return await asyncio.wait_for(future, self.settings.timeout)
        except TimeoutError:
            raise TimeoutError(
                f"Home Assistant didn't answer {message['type']} within {self.settings.timeout:g} s."
            ) from None
        except DriverError:
            raise
        except Exception as exc:
            self._lost = f"sending failed ({exc})"
            raise DriverError(f"Home Assistant disconnected while sending {message['type']} ({exc}).") from exc
        finally:
            self._pending.pop(ident, None)

    def _check_open(self) -> None:
        if self._client is None:
            raise DriverError(f"{self.device.device_id} is not connected. Connect it first.")
        if self._lost:
            raise DriverError(f"Home Assistant disconnected ({self._lost}). Reconnect it.")

    async def _state(self, entity_id: str) -> dict[str, Any]:
        self._check_open()
        if entity_id not in self.allowed:
            raise DriverError(f"{entity_id} is not selected in the device file.")
        if self._ws is not None:
            state = self.cache.get(entity_id)
            if state is None:
                raise DriverError(f"Home Assistant has no entity {entity_id}, or it hasn't reported yet.")
            return state
        data = await self._rest("GET", f"/api/states/{entity_id}")
        return {"state": data.get("state"), "attributes": data.get("attributes") or {}}

    async def _service(self, domain: str, service: str, entity_id: str, data: dict[str, Any] | None = None) -> None:
        self._check_open()
        if entity_id not in self.allowed:
            raise DriverError(f"{entity_id} is not selected in the device file.")
        if self._ws is not None:
            await self._ws_call(
                {
                    "type": "call_service",
                    "domain": domain,
                    "service": service,
                    "service_data": data or {},
                    "target": {"entity_id": entity_id},
                }
            )
            return
        await self._rest("POST", f"/api/services/{domain}/{service}", {"entity_id": entity_id, **(data or {})})

    # ------------------------------------------------------------------ identity and describe

    async def identify(self) -> dict[str, str]:
        identity = {"host": self.settings.host, "entities": ", ".join(self.allowed)}
        if self.ha_version:
            identity["version"] = self.ha_version
        return identity

    async def describe(self) -> dict[str, Any] | None:
        if self._client is None:
            return None
        read: dict[str, Any] = {}
        write: dict[str, Any] = {}
        prefix = len(self.allowed) > 1
        names: list[str] = []
        for entity_id in self.allowed:
            try:
                state = await self._state(entity_id)
            except DriverError:
                continue
            names.append(str((state.get("attributes") or {}).get("friendly_name") or entity_id))
            for name, section, spec in _entity_channels(entity_id, state):
                key = f"{entity_id.split('.', 1)[1]}_{name}"[:48] if prefix else name
                (write if section == "write" else read)[key] = spec
        proposal: dict[str, Any] = {
            "device": {"name": names[0] if len(names) == 1 else self.device.device.name},
            "read": read,
            "write": write,
            "notes": (
                "Proposed from the selected Home Assistant entities. Limits come from Home Assistant and are suggested."
            ),
        }
        if len(self.allowed) == 1:
            proposal["match"] = {"homeassistant": self.allowed[0]}
        return proposal

    # ------------------------------------------------------------------ reads

    async def read(self, channel: str) -> Reading:
        mapped = self.channels.get(channel)
        if mapped is None:
            raise DriverError(f"{self.device.device_id} has no channel {channel!r}.")
        unit = self.device.channel_unit(channel)
        state = await self._state(mapped.entity)
        raw, attrs = state.get("state"), state.get("attributes") or {}
        if raw == "unavailable":
            raise DriverError(f"{mapped.entity} is unavailable in Home Assistant. Check the device behind it.")
        spec = self.device.write.get(channel) or self.device.read[channel]
        if raw in ("unknown", None) and mapped.attribute is None:
            return Reading(channel, None, unit)
        value = self._decode(mapped, spec, raw, attrs)
        return Reading(channel, value, unit if isinstance(value, float) else None)

    def _decode(self, mapped: _Channel, spec: ReadChannel | WriteChannel, raw: Any, attrs: dict[str, Any]) -> Any:
        role = mapped.role
        if role in ("onoff", "binary"):
            if raw not in ("on", "off"):
                raise DriverError(f"{mapped.entity} reports {raw!r}, expected on or off.")
            return raw == "on"
        if role == "brightness":
            if raw == "off":
                return self._to_unit(0.0, "percent", spec.unit, mapped)
            level = attrs.get("brightness")
            return (
                None
                if level is None
                else self._to_unit(round(float(level) * 100 / 255, 2), "percent", spec.unit, mapped)
            )
        if role in ("color_temp", "fan_percentage"):
            level = attrs.get(mapped.attribute or "")
            if level is None:
                return None
            source = "K" if role == "color_temp" else "percent"
            return self._to_unit(float(level), source, spec.unit, mapped)
        if role in ("fan_preset", "option"):
            text = attrs.get("preset_mode") if role == "fan_preset" else raw
            if text is None:
                return None
            if spec.values and text not in spec.values:
                raise DriverError(f"{mapped.entity} reports {text!r}, which is not one of {', '.join(spec.values)}.")
            return str(text)
        if role == "attribute":
            value = attrs.get(mapped.attribute or "")
            return self._plain(mapped, spec, value, None)
        return self._plain(mapped, spec, raw, ha_unit(attrs.get("unit_of_measurement")))

    def _plain(self, mapped: _Channel, spec: ReadChannel | WriteChannel, value: Any, source_unit: str | None) -> Any:
        if value is None:
            return None
        if spec.type == "number":
            try:
                number = float(value)
            except (TypeError, ValueError):
                raise DriverError(f"{mapped.entity} reports {value!r}, which is not a number.") from None
            if not math.isfinite(number):
                raise DriverError(f"{mapped.entity} reports {value!r}, which is not a finite number.")
            return self._to_unit(number, source_unit, spec.unit, mapped)
        if spec.type == "bool":
            if isinstance(value, bool):
                return value
            if value in ("on", "off"):
                return value == "on"
            raise DriverError(f"{mapped.entity} reports {value!r}, expected on or off.")
        text = str(value)
        if spec.type == "enum" and text not in spec.values:
            raise DriverError(f"{mapped.entity} reports {text!r}, which is not one of {', '.join(spec.values)}.")
        return text

    def _to_unit(self, value: float, source: str | None, unit: str | None, mapped: _Channel) -> float:
        if not unit or not source or source == unit:
            return value
        try:
            return convert(Quantity(value, parse_unit(source)), unit)
        except UnitError:
            raise DriverError(
                f"{mapped.entity} reports {source}, which doesn't convert to {mapped.name}'s {unit}."
            ) from None

    # ------------------------------------------------------------------ writes

    async def _write(self, channel: str, value: float | bool | str) -> Reading | None:
        mapped = self.channels.get(channel)
        if mapped is None or channel not in self.device.write:
            raise DriverError(f"{self.device.device_id} has no write channel {channel!r}.")
        unit = self.device.channel_unit(channel)
        domain, entity = mapped.domain, mapped.entity
        number = float(value) if isinstance(value, int | float) and not isinstance(value, bool) else 0.0
        if mapped.role == "onoff":
            await self._service(domain, "turn_on" if value else "turn_off", entity)
        elif mapped.role == "brightness":
            percent = self._to_unit(number, unit, "percent", mapped)
            await self._service("light", "turn_on", entity, {"brightness_pct": round(percent, 1)})
        elif mapped.role == "color_temp":
            kelvin = self._to_unit(number, unit, "K", mapped)
            await self._service("light", "turn_on", entity, {"color_temp_kelvin": round(kelvin)})
        elif mapped.role == "fan_percentage":
            percent = self._to_unit(number, unit, "percent", mapped)
            await self._service("fan", "set_percentage", entity, {"percentage": round(percent)})
        elif mapped.role == "fan_preset":
            await self._service("fan", "set_preset_mode", entity, {"preset_mode": str(value)})
        elif mapped.role == "number":
            state = await self._state(entity)
            target = ha_unit((state.get("attributes") or {}).get("unit_of_measurement"))
            await self._service(domain, "set_value", entity, {"value": self._to_unit(number, unit, target, mapped)})
        elif mapped.role == "option":
            await self._service(domain, "select_option", entity, {"option": str(value)})
        else:
            raise DriverError(f"{channel} is read-only in Home Assistant.")
        return Reading(channel, value, unit)

    # ------------------------------------------------------------------ health and close

    async def health(self) -> Health:
        if self._client is None:
            return Health(connected=False, detail="not connected")
        if self._lost:
            return Health(connected=False, detail=self._lost)
        try:
            if self._ws is None:
                await self._rest("GET", "/api/")
            for entity_id in self.allowed:
                if (await self._state(entity_id)).get("state") == "unavailable":
                    return Health(connected=False, detail=f"{entity_id} is unavailable in Home Assistant")
        except (DriverError, TimeoutError) as exc:
            return Health(connected=False, detail=str(exc))
        return Health(connected=True, detail=f"Home Assistant {self.ha_version or ''}".strip())

    async def close(self) -> None:
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


def _entity_channels(entity_id: str, state: dict[str, Any]) -> list[tuple[str, str, dict[str, Any]]]:
    """Proposed channels for one entity. Writes and their limits are always suggested."""
    domain = entity_id.split(".", 1)[0]
    attrs = state.get("attributes") or {}
    base = {"map": {"entity": entity_id}}
    found: list[tuple[str, str, dict[str, Any]]] = []
    if domain in ("light", "switch", "input_boolean", "fan"):
        found.append(("power", "write", {"type": "bool", "suggested": True, **base}))
    if domain == "light":
        modes = set(attrs.get("supported_color_modes") or [])
        if modes - {"onoff"}:
            brightness = {"entity": entity_id, "attribute": "brightness"}
            found.append(
                ("brightness", "write", {"unit": "percent", "min": 1, "max": 100, "suggested": True, "map": brightness})
            )
        if "color_temp" in modes and attrs.get("min_color_temp_kelvin"):
            found.append(
                (
                    "color_temp",
                    "write",
                    {
                        "unit": "K",
                        "min": attrs["min_color_temp_kelvin"],
                        "max": attrs["max_color_temp_kelvin"],
                        "suggested": True,
                        "map": {"entity": entity_id, "attribute": "color_temp_kelvin"},
                    },
                )
            )
    if domain == "fan":
        step = attrs.get("percentage_step")
        speed: dict[str, Any] = {
            "unit": "percent",
            "min": 0,
            "max": 100,
            "suggested": True,
            "map": {"entity": entity_id, "attribute": "percentage"},
        }
        if step:
            speed["step"] = step
        found.append(("speed", "write", speed))
        if attrs.get("preset_modes"):
            preset = {"entity": entity_id, "attribute": "preset_mode"}
            values = list(attrs["preset_modes"])
            found.append(("preset", "write", {"type": "enum", "values": values, "suggested": True, "map": preset}))
    if domain in ("number", "input_number"):
        number_unit = ha_unit(attrs.get("unit_of_measurement")) or "dimensionless"
        spec = {
            "unit": number_unit,
            "min": attrs.get("min", 0),
            "max": attrs.get("max", 100),
            "suggested": True,
            **base,
        }
        if attrs.get("step"):
            spec["step"] = attrs["step"]
        found.append(("value", "write", spec))
    if domain in ("select", "input_select") and attrs.get("options"):
        found.append(("option", "write", {"type": "enum", "values": list(attrs["options"]), "suggested": True, **base}))
    if domain == "sensor":
        unit = ha_unit(attrs.get("unit_of_measurement"))
        try:
            float(state.get("state"))  # type: ignore[arg-type]
            numeric = unit is not None
        except (TypeError, ValueError):
            numeric = False
        found.append(("value", "read", {"unit": unit, **base} if numeric else {"type": "string", **base}))
    if domain == "binary_sensor":
        found.append(("state", "read", {"type": "bool", **base}))
    return found
