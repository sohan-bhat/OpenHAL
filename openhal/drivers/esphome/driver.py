"""ESPHome devices over the native API, through aioesphomeapi.

Protocol (esphome.io native API component, and aioesphomeapi's documentation). The device
listens on TCP 6053. With `api: encryption: key:` in its YAML the session uses the Noise
protocol and the 32-byte base64 key, which the driver reads from the environment variable named
in `noise_psk_env`. The client says hello, reads the device info, lists entities and subscribes
to their states. Commands are fire-and-forget messages, and the device answers with a state
update once it has acted.

Mapping. Channels bind to entities by `object_id`, which by default is the channel name. A name
ending in `_brightness`, `_speed` or `_preset` binds to the entity named by the rest of it.
`map: { object_id: pump, attribute: state }` sets both explicitly.

    sensor          read number, converted from unit_of_measurement, or string
    text_sensor     read string or enum
    binary_sensor   read bool
    switch          write bool
    light           write bool (state), number in percent (brightness, 0 to 1 on the wire)
    fan             write bool (state), percent (speed, as speed_level of supported_speed_count), enum (preset)
    number          write number, converted to unit_of_measurement
    select          write enum
    button          action

Writes are verified. After a command the driver waits up to `timeout` for the state update that
shows the new value, and fails the write if the device doesn't report it. Fan speeds snap to the
nearest supported level, and the reading after the write is the speed the fan really has.

Safe state. From the device file. ESPHome can define its own failsafes on the device (for
example `api: reboot_timeout` or an `on_client_disconnected` automation), which the hub can't see.
"""

from __future__ import annotations

import asyncio
import contextlib
import fnmatch
import math
import os
from collections.abc import Callable
from typing import Any, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from openhal.drivers.base import Discovered, Driver, DriverError, DriverInfo, Health, Reading
from openhal.drivers.serial import mapping
from openhal.spec.models import Action, DeviceFile, ReadChannel, WriteChannel
from openhal.spec.units import Quantity, UnitError, convert, parse_unit

SERVICE_TYPE = "_esphomelib._tcp.local."
DISCOVERY_S = 2.0
SUFFIXES = {"_brightness": "brightness", "_speed": "speed", "_preset": "preset"}
KINDS = {
    "SensorInfo": "sensor",
    "TextSensorInfo": "text_sensor",
    "BinarySensorInfo": "binary_sensor",
    "SwitchInfo": "switch",
    "LightInfo": "light",
    "FanInfo": "fan",
    "NumberInfo": "number",
    "SelectInfo": "select",
    "ButtonInfo": "button",
}
# (kind, attribute) -> channel type it needs, and whether it can be written
ROLES: dict[tuple[str, str], tuple[str | None, bool]] = {
    ("sensor", "state"): (None, False),
    ("text_sensor", "state"): (None, False),
    ("binary_sensor", "state"): ("bool", False),
    ("switch", "state"): ("bool", True),
    ("light", "state"): ("bool", True),
    ("light", "brightness"): ("number", True),
    ("fan", "state"): ("bool", True),
    ("fan", "speed"): ("number", True),
    ("fan", "preset"): ("enum", True),
    ("number", "state"): ("number", True),
    ("select", "state"): ("enum", True),
}
BRIGHTNESS_MODES = frozenset({2, 3, 7, 11, 19, 35, 39, 47, 51})
"""ESPHome ColorMode values that include brightness (BRIGHTNESS and every color mode)."""


class EspHomeParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    host: str = Field(min_length=1, max_length=253)
    port: int = Field(default=6053, ge=1, le=65535)
    noise_psk_env: str | None = Field(default=None, pattern=r"^[A-Z_][A-Z0-9_]{0,63}$")
    password_env: str | None = Field(default=None, pattern=r"^[A-Z_][A-Z0-9_]{0,63}$")
    timeout: float = 5.0

    @field_validator("timeout", mode="before")
    @classmethod
    def _duration(cls, value: Any) -> float:
        seconds = mapping.duration(value)
        if not 0.1 <= seconds <= 60:
            raise ValueError("timeout must be between 100 ms and 60 s.")
        return seconds


class EntityMap(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    object_id: str | None = Field(default=None, pattern=r"^[a-z0-9_]{1,64}$")
    attribute: Literal["state", "brightness", "speed", "preset"] | None = None


class _Binding:
    def __init__(self, name: str, object_id: str, attribute: str) -> None:
        self.name = name
        self.object_id = object_id
        self.attribute = attribute
        self.info: Any = None
        self.kind = ""


def _entity_map(raw: dict[str, Any] | None, where: str) -> EntityMap:
    try:
        return EntityMap.model_validate(raw or {})
    except ValidationError as exc:
        problems = "; ".join(f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors())
        raise DriverError(f"{where}.map is not valid for the ESPHome driver ({problems}).") from exc


def _bind(name: str, entity_map: EntityMap) -> _Binding:
    if entity_map.object_id is not None:
        return _Binding(name, entity_map.object_id, entity_map.attribute or "state")
    for suffix, attribute in SUFFIXES.items():
        if name.endswith(suffix) and entity_map.attribute in (None, attribute):
            return _Binding(name, name.removesuffix(suffix), attribute)
    return _Binding(name, name, entity_map.attribute or "state")


async def _browse(seconds: float) -> list[tuple[str, str, int, dict[str, str]]]:
    """Browse mDNS for ESPHome nodes. Read-only, returns (name, address, port, txt)."""
    from zeroconf import ServiceStateChange
    from zeroconf.asyncio import AsyncServiceBrowser, AsyncServiceInfo, AsyncZeroconf

    names: set[str] = set()

    def on_change(**kwargs: Any) -> None:
        if kwargs.get("state_change") is ServiceStateChange.Added:
            names.add(str(kwargs["name"]))

    aiozc = AsyncZeroconf()
    browser = AsyncServiceBrowser(aiozc.zeroconf, [SERVICE_TYPE], handlers=[on_change])
    try:
        await asyncio.sleep(seconds)
        found = []
        for name in sorted(names):
            info = AsyncServiceInfo(SERVICE_TYPE, name)
            if not await info.async_request(aiozc.zeroconf, 1000):
                continue
            addresses = info.parsed_addresses()
            txt = {key.decode(): (value or b"").decode() for key, value in (info.properties or {}).items()}
            found.append(
                (name.removesuffix(f".{SERVICE_TYPE}"), addresses[0] if addresses else "", info.port or 6053, txt)
            )
        return found
    finally:
        await browser.async_cancel()
        await aiozc.async_close()


class EspHomeDriver(Driver):
    """ESPHome nodes over the native API. Sensors, switches, lights, fans, numbers, selects, buttons."""

    info: ClassVar[DriverInfo] = DriverInfo(
        name="esphome",
        protocols=("ESPHome native API (plaintext or Noise encrypted)",),
        hazard_default="low",
        summary="ESPHome devices over the native API. Entities map to channels and buttons to actions.",
    )
    params_model: ClassVar[type[Any] | None] = EspHomeParams

    def __init__(self, device: DeviceFile, *, client_factory: Callable[..., Any] | None = None) -> None:
        super().__init__(device)
        self.settings = EspHomeParams.model_validate(device.connect.params)
        self._client_factory = client_factory
        self.client: Any = None
        self.device_info: Any = None
        self.entities: list[Any] = []
        self.states: dict[int, Any] = {}
        self.bindings: dict[str, _Binding] = {}
        self.action_bindings: dict[str, _Binding] = {}
        self._lost: str | None = None
        self._updated = asyncio.Event()
        channels: dict[str, ReadChannel | WriteChannel] = {**self.device.read, **self.device.write}
        for name, spec in channels.items():
            self.bindings[name] = _bind(name, _entity_map(spec.map, name))
        for name, action in self.device.actions.items():
            if action.args:
                raise DriverError(f"actions.{name}: ESPHome buttons take no arguments.")
            self.action_bindings[name] = _bind(name, _entity_map(action.map, f"actions.{name}"))

    # ------------------------------------------------------------------ discovery and identity

    @classmethod
    async def discover(cls) -> list[Discovered]:
        try:
            found = await _browse(DISCOVERY_S)
        except Exception:  # noqa: BLE001 (discovery never fails the caller)
            return []
        return [
            Discovered(
                driver="esphome",
                address=f"{address}:{port}",
                identifiers={"esphome.name": name, **{f"esphome.{key}": value for key, value in txt.items()}},
                label=txt.get("friendly_name") or name,
            )
            for name, address, port, txt in found
        ]

    async def identify(self) -> dict[str, str]:
        info = self.device_info
        if info is None:
            return {"host": self.settings.host}
        fields = ("name", "friendly_name", "model", "manufacturer", "esphome_version", "mac_address", "project_name")
        return {
            "host": self.settings.host,
            **{key: str(getattr(info, key)) for key in fields if getattr(info, key, "")},
        }

    # ------------------------------------------------------------------ connection

    def _secret(self, env: str | None, what: str) -> str | None:
        if env is None:
            return None
        value = os.environ.get(env)
        if not value:
            raise DriverError(f"Set the {env} environment variable to the device's {what}.")
        return value

    async def connect(self) -> None:
        await self.close()
        from aioesphomeapi.client import APIClient
        from aioesphomeapi.core import APIConnectionError

        noise = self._secret(self.settings.noise_psk_env, "API encryption key")
        password = self._secret(self.settings.password_env, "API password")
        factory = self._client_factory or APIClient
        client = factory(self.settings.host, self.settings.port, password, noise_psk=noise, client_info="openhal")
        self._lost = None
        self.states.clear()

        async def on_stop(expected: bool) -> None:
            if not expected:
                self._lost = "the device closed the connection"

        try:
            await asyncio.wait_for(client.connect(on_stop=on_stop, login=password is not None), self.settings.timeout)
            self.device_info = await asyncio.wait_for(client.device_info(), self.settings.timeout)
            entities, _ = await asyncio.wait_for(client.list_entities_services(), self.settings.timeout)
        except TimeoutError:
            await self._drop(client)
            raise TimeoutError(
                f"{self.settings.host}:{self.settings.port} didn't finish the ESPHome handshake within "
                f"{self.settings.timeout:g} s."
            ) from None
        except APIConnectionError as exc:
            await self._drop(client)
            hint = " Check noise_psk_env." if "encrypt" in str(exc).lower() or "noise" in str(exc).lower() else ""
            raise DriverError(f"Could not connect to ESPHome at {self.settings.host} ({exc}).{hint}") from exc
        except OSError as exc:
            await self._drop(client)
            raise DriverError(f"Could not reach ESPHome at {self.settings.host}:{self.settings.port} ({exc}).") from exc
        self.client = client
        self.entities = list(entities)
        try:
            self._check_match()
            self._resolve()
        except DriverError:
            await self.close()
            raise
        client.subscribe_states(self._on_state)

    async def _drop(self, client: Any) -> None:
        with contextlib.suppress(Exception):
            await client.disconnect(force=True)

    def _check_match(self) -> None:
        for key, pattern in self.device.match.esphome.items():
            value = str(getattr(self.device_info, key, ""))
            if not fnmatch.fnmatch(value, pattern):
                raise DriverError(f"The device reports {key}={value!r}, which doesn't match match.esphome {pattern!r}.")

    def _resolve(self) -> None:
        by_id = {entity.object_id: entity for entity in self.entities}
        available = ", ".join(sorted(by_id)) or "none"
        for binding in [*self.bindings.values(), *self.action_bindings.values()]:
            entity = by_id.get(binding.object_id)
            if entity is None:
                raise DriverError(
                    f"{binding.name}: the device has no entity {binding.object_id!r}. It has {available}."
                )
            binding.info = entity
            binding.kind = KINDS.get(type(entity).__name__, "")
        for name, binding in self.bindings.items():
            spec = self.device.write.get(name) or self.device.read[name]
            self._check_role(name, binding, spec, writable=name in self.device.write)
        for name, binding in self.action_bindings.items():
            if binding.kind != "button":
                raise DriverError(f"actions.{name}: {binding.object_id} is a {binding.kind}, not a button.")

    def _check_role(self, name: str, binding: _Binding, spec: ReadChannel | WriteChannel, *, writable: bool) -> None:
        role = ROLES.get((binding.kind, binding.attribute))
        if role is None:
            raise DriverError(f"{name}: a {binding.kind or 'unknown'} entity has no {binding.attribute} channel.")
        wanted, can_write = role
        if writable and not can_write:
            raise DriverError(f"write.{name}: {binding.object_id} is a {binding.kind}, which is read-only.")
        if wanted and spec.type != wanted:
            raise DriverError(f"{name}: {binding.object_id} needs a channel of type {wanted}, not {spec.type}.")
        if binding.attribute in ("brightness", "speed") and spec.unit not in ("percent", "%"):
            raise DriverError(f"{name}: {binding.attribute} channels are in percent.")

    def _on_state(self, state: Any) -> None:
        self.states[state.key] = state
        self._updated.set()

    # ------------------------------------------------------------------ reads

    def _check_open(self) -> None:
        if self.client is None:
            raise DriverError(f"{self.device.device_id} is not connected. Connect it first.")
        if self._lost:
            raise DriverError(f"{self.settings.host} disconnected ({self._lost}). Reconnect it.")

    async def _wait_state(self, key: int, accept: Callable[[Any], bool], what: str) -> Any:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self.settings.timeout
        while True:
            self._check_open()
            state = self.states.get(key)
            if state is not None and accept(state):
                return state
            remaining = deadline - loop.time()
            if remaining <= 0:
                raise TimeoutError(f"{self.settings.host} didn't report {what} within {self.settings.timeout:g} s.")
            self._updated.clear()
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._updated.wait(), min(remaining, 0.25))

    async def read(self, channel: str) -> Reading:
        binding = self.bindings.get(channel)
        if binding is None:
            raise DriverError(f"{self.device.device_id} has no channel {channel!r}.")
        self._check_open()
        spec = self.device.write.get(channel) or self.device.read[channel]
        state = await self._wait_state(binding.info.key, lambda _: True, f"a state for {binding.object_id}")
        value = self._decode(binding, spec, state)
        return Reading(channel, value, spec.unit if isinstance(value, float) else None)

    def _decode(self, binding: _Binding, spec: ReadChannel | WriteChannel, state: Any) -> Any:
        if getattr(state, "missing_state", False):
            return None
        kind, attribute = binding.kind, binding.attribute
        if attribute == "brightness":
            return round(float(state.brightness) * 100, 3) if state.state else 0.0
        if attribute == "speed":
            count = max(1, int(binding.info.supported_speed_count or 1))
            return round(100.0 * state.speed_level / count, 3) if state.state else 0.0
        if attribute == "preset":
            preset = state.preset_mode or None
            if preset is not None and spec.values and preset not in spec.values:
                raise DriverError(
                    f"{binding.object_id} reports preset {preset!r}, which is not in the channel's values."
                )
            return preset
        value = state.state
        if kind in ("sensor", "number") and spec.type == "number":
            number = float(value)
            if not math.isfinite(number):
                return None
            source = mapping.device_unit(binding.info.unit_of_measurement)
            return self._convert(number, source, spec.unit, binding)
        if spec.type == "bool":
            return bool(value)
        text = f"{value:g}" if isinstance(value, float) else str(value)
        if spec.type == "enum" and text not in spec.values:
            raise DriverError(f"{binding.object_id} reports {text!r}, which is not one of {', '.join(spec.values)}.")
        return text

    def _convert(self, value: float, source: str | None, unit: str | None, binding: _Binding) -> float:
        if not source or not unit or source == unit:
            return value
        try:
            return convert(Quantity(value, parse_unit(source)), unit)
        except UnitError:
            raise DriverError(f"{binding.object_id} reports {source}, which doesn't convert to {unit}.") from None

    # ------------------------------------------------------------------ writes and actions

    async def _write(self, channel: str, value: float | bool | str) -> Reading | None:
        binding = self.bindings.get(channel)
        if binding is None or channel not in self.device.write:
            raise DriverError(f"{self.device.device_id} has no write channel {channel!r}.")
        self._check_open()
        spec = self.device.write[channel]
        key = binding.info.key
        number = float(value) if isinstance(value, int | float) and not isinstance(value, bool) else 0.0
        accept: Callable[[Any], bool]
        if binding.kind == "switch":
            self.client.switch_command(key, bool(value))
            accept = lambda s: s.state == bool(value)  # noqa: E731
        elif binding.kind == "light" and binding.attribute == "state":
            self.client.light_command(key, state=bool(value))
            accept = lambda s: s.state == bool(value)  # noqa: E731
        elif binding.kind == "light":
            level = max(0.0, min(1.0, number / 100))
            if level > 0:
                self.client.light_command(key, state=True, brightness=level)
                accept = lambda s: s.state and abs(s.brightness - level) < 0.01  # noqa: E731
            else:
                self.client.light_command(key, state=False)
                accept = lambda s: not s.state  # noqa: E731
        elif binding.kind == "fan" and binding.attribute == "state":
            self.client.fan_command(key, state=bool(value))
            accept = lambda s: s.state == bool(value)  # noqa: E731
        elif binding.kind == "fan" and binding.attribute == "speed":
            count = max(1, int(binding.info.supported_speed_count or 1))
            speed = round(number / 100 * count)
            if speed > 0:
                self.client.fan_command(key, state=True, speed_level=speed)
                accept = lambda s: s.state and s.speed_level == speed  # noqa: E731
            else:
                self.client.fan_command(key, state=False)
                accept = lambda s: not s.state  # noqa: E731
        elif binding.kind == "fan":
            self.client.fan_command(key, preset_mode=str(value))
            accept = lambda s: s.preset_mode == str(value)  # noqa: E731
        elif binding.kind == "number":
            target = self._convert(number, spec.unit, mapping.device_unit(binding.info.unit_of_measurement), binding)
            self.client.number_command(key, target)
            tolerance = max(abs(target) * 1e-6, float(binding.info.step or 0) / 2, 1e-9)
            accept = lambda s: abs(float(s.state) - target) <= tolerance  # noqa: E731
        elif binding.kind == "select":
            self.client.select_command(key, str(value))
            accept = lambda s: s.state == str(value)  # noqa: E731
        else:
            raise DriverError(f"{channel} is read-only on this device.")
        state = await self._wait_state(key, accept, f"{binding.object_id} = {value}")
        reported = self._decode(binding, spec, state)
        return Reading(channel, reported, spec.unit if isinstance(reported, float) else None)

    async def _action(self, name: str, args: dict[str, Any]) -> Any:
        binding = self.action_bindings.get(name)
        if binding is None:
            raise DriverError(f"{self.device.device_id} has no action {name!r}.")
        self._check_open()
        self.client.button_command(binding.info.key)
        return {"pressed": binding.object_id}

    # ------------------------------------------------------------------ describe, health, close

    async def describe(self) -> dict[str, Any] | None:
        if self.client is None:
            return None
        return _proposal(self.device_info, self.entities)

    async def health(self) -> Health:
        if self.client is None:
            return Health(connected=False, detail="not connected")
        if self._lost:
            return Health(connected=False, detail=self._lost)
        return Health(connected=True, detail=str(getattr(self.device_info, "name", "")))

    async def close(self) -> None:
        client, self.client = self.client, None
        if client is not None:
            await self._drop(client)


def _proposal(info: Any, entities: list[Any]) -> dict[str, Any]:
    read: dict[str, Any] = {}
    write: dict[str, Any] = {}
    actions: dict[str, Action | dict[str, Any]] = {}
    for entity in entities:
        kind, oid = KINDS.get(type(entity).__name__), entity.object_id
        if kind == "sensor":
            unit = mapping.device_unit(entity.unit_of_measurement)
            read[oid] = {"unit": unit or "dimensionless"}
        elif kind == "text_sensor":
            read[oid] = {"type": "string"}
        elif kind == "binary_sensor":
            read[oid] = {"type": "bool"}
        elif kind == "switch":
            write[oid] = {"type": "bool", "suggested": True}
        elif kind == "light":
            write[oid] = {"type": "bool", "suggested": True}
            if set(entity.supported_color_modes) & BRIGHTNESS_MODES:
                write[f"{oid}_brightness"] = {"unit": "percent", "min": 0, "max": 100, "suggested": True}
        elif kind == "fan":
            write[oid] = {"type": "bool", "suggested": True}
            if entity.supports_speed and entity.supported_speed_count:
                step = round(100 / entity.supported_speed_count, 4)
                write[f"{oid}_speed"] = {"unit": "percent", "min": 0, "max": 100, "suggested": True, "step": step}
            if entity.supported_preset_modes:
                write[f"{oid}_preset"] = {
                    "type": "enum",
                    "values": list(entity.supported_preset_modes),
                    "suggested": True,
                }
        elif kind == "number":
            spec: dict[str, Any] = {
                "unit": mapping.device_unit(entity.unit_of_measurement) or "dimensionless",
                "min": entity.min_value,
                "max": entity.max_value,
                "suggested": True,
            }
            if entity.step:
                spec["step"] = entity.step
            write[oid] = spec
        elif kind == "select" and entity.options:
            write[oid] = {"type": "enum", "values": list(entity.options), "suggested": True}
        elif kind == "button":
            actions[oid] = {"description": entity.name, "confirm": "confirm", "suggested": True}
    name = str(getattr(info, "friendly_name", "") or getattr(info, "name", "") or "ESPHome device")
    device: dict[str, Any] = {"name": name}
    if getattr(info, "model", ""):
        device["model"] = info.model
    if getattr(info, "manufacturer", ""):
        device["manufacturer"] = info.manufacturer
    return {
        "device": device,
        "match": {"mdns": "_esphomelib._tcp", "esphome": {"name": str(getattr(info, "name", ""))}},
        "read": read,
        "write": write,
        "actions": actions,
        "notes": "Proposed from the device's entity list. Limits on numbers come from the device and are suggested.",
    }
