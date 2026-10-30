"""Zigbee devices through Zigbee2MQTT, over its MQTT API with paho-mqtt.

Zigbee2MQTT publishes one JSON object per device on `<base>/<friendly_name>`, the retained device
list with each device's `exposes` on `<base>/bridge/devices`, the bridge state on
`<base>/bridge/state` and, with availability turned on, `<base>/<friendly_name>/availability`.
It takes changes as JSON on `<base>/<friendly_name>/set` and refresh requests on
`<base>/<friendly_name>/get`. Each exposed feature has an `access` mask, where 1 means it is
published, 2 means it can be set and 4 means it can be requested with `/get`.
"""

from __future__ import annotations

import asyncio
import json
import threading
import time
from collections.abc import Callable
from typing import Any
from urllib.parse import urlsplit

from openhal.drivers.base import DriverError
from openhal.drivers.zigbee_zwave.common import UNKNOWN, ChannelMap, Feature

ClientFactory = Callable[[str], Any]
PUBLISHED, SETTABLE, GETTABLE = 1, 2, 4


def default_client(client_id: str) -> Any:
    """A paho client for MQTT 3.1.1 with automatic reconnect off."""
    import paho.mqtt.client as mqtt
    from paho.mqtt.enums import CallbackAPIVersion, MQTTProtocolVersion

    return mqtt.Client(
        callback_api_version=CallbackAPIVersion.VERSION2,
        client_id=client_id,
        clean_session=True,
        protocol=MQTTProtocolVersion.MQTTv311,
        reconnect_on_failure=False,
    )


def features(exposes: list[Any], parent: str = "") -> dict[str, Feature]:
    """Flatten a Zigbee2MQTT exposes list into features by property. Composite children get dotted names."""
    found: dict[str, Feature] = {}
    for item in exposes:
        if not isinstance(item, dict):
            continue
        kind = item.get("type")
        prop = item.get("property")
        name = f"{parent}.{prop}" if parent and prop else prop
        nested = item.get("features")
        if isinstance(nested, list):
            found.update(features(nested, name if kind == "composite" and name else parent))
            continue
        if not isinstance(name, str):
            continue
        access = int(item.get("access") or 0)
        common: dict[str, Any] = {
            "readable": bool(access & (PUBLISHED | GETTABLE)),
            "writable": bool(access & SETTABLE),
            "label": str(item.get("label") or item.get("name") or name),
        }
        if kind == "binary":
            found[name] = Feature("bool", on=item.get("value_on", True), off=item.get("value_off", False), **common)
        elif kind == "numeric":
            found[name] = Feature(
                "number",
                unit=item.get("unit"),
                minimum=item.get("value_min"),
                maximum=item.get("value_max"),
                step=item.get("value_step"),
                **common,
            )
        elif kind == "enum":
            found[name] = Feature("enum", values=tuple(str(value) for value in item.get("values") or ()), **common)
        elif kind == "text":
            found[name] = Feature("string", **common)
    return found


def _get(document: dict[str, Any], path: str) -> Any:
    current: Any = document
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def _nest(path: str, value: Any) -> dict[str, Any]:
    result: Any = value
    for part in reversed(path.split(".")):
        result = {part: result}
    assert isinstance(result, dict)
    return result


class Zigbee2MqttLink:
    """One Zigbee2MQTT device, by friendly name."""

    def __init__(
        self,
        url: str,
        friendly_name: str,
        *,
        base_topic: str,
        username: str | None,
        password: str | None,
        ca_file: str | None,
        timeout: float,
        client_id: str,
        client_factory: ClientFactory,
    ) -> None:
        parts = urlsplit(url)
        self.host = parts.hostname or ""
        self.tls = parts.scheme == "mqtts"
        self.port = parts.port or (8883 if self.tls else 1883)
        self.name = friendly_name
        self.base = base_topic
        self.username = username
        self.password = password
        self.ca_file = ca_file
        self.timeout = timeout
        self.client_id = client_id
        self._factory = client_factory
        self._client: Any = None
        self._connected = threading.Event()
        self._lock = threading.Lock()
        self._state: dict[str, Any] = {}
        self._stamps: dict[str, float] = {}
        self._devices: list[Any] | None = None
        self._availability: str | None = None
        self._bridge: str | None = None
        self._lost = ""
        self._refused = ""
        self.device: dict[str, Any] = {}
        self.features: dict[str, Feature] = {}

    @property
    def where(self) -> str:
        return f"Zigbee2MQTT device {self.name} on {self.host}:{self.port}"

    @property
    def state_topic(self) -> str:
        return f"{self.base}/{self.name}"

    def _on_connect(self, client: Any, userdata: Any, flags: Any, reason: Any, properties: Any) -> None:
        if getattr(reason, "is_failure", False):
            self._refused = f"the broker returned a connection error ({reason})"
            return
        topics = [self.state_topic, f"{self.state_topic}/availability", f"{self.base}/bridge/devices"]
        client.subscribe([(topic, 0) for topic in [*topics, f"{self.base}/bridge/state"]])
        self._connected.set()

    def _on_disconnect(self, client: Any, userdata: Any, flags: Any, reason: Any, properties: Any) -> None:
        self._connected.clear()
        self._lost = f"disconnected ({reason})"

    def _on_message(self, client: Any, userdata: Any, message: Any) -> None:
        payload = bytes(message.payload)
        try:
            document: Any = json.loads(payload) if payload else None
        except (ValueError, UnicodeDecodeError):
            document = payload.decode("utf-8", "replace").strip()
        now = time.time()
        with self._lock:
            if message.topic == self.state_topic and isinstance(document, dict):
                self._state.update(document)
                for key in document:
                    self._stamps[key] = now
            elif message.topic == f"{self.state_topic}/availability":
                self._availability = str(document.get("state") if isinstance(document, dict) else document)
            elif message.topic == f"{self.base}/bridge/state":
                self._bridge = str(document.get("state") if isinstance(document, dict) else document)
            elif message.topic == f"{self.base}/bridge/devices" and isinstance(document, list):
                self._devices = document

    async def open(self, wanted: list[str]) -> None:
        """Connect, find the device in the bridge's device list and request a report of the `wanted` properties."""
        client = self._factory(self.client_id)
        client.on_connect = self._on_connect
        client.on_disconnect = self._on_disconnect
        client.on_message = self._on_message
        client.connect_timeout = self.timeout
        if self.username is not None or self.password is not None:
            client.username_pw_set(self.username or "", self.password)
        if self.tls:
            client.tls_set(ca_certs=self.ca_file)
        self._connected.clear()
        self._lost = self._refused = ""
        with self._lock:
            self._state.clear()
            self._stamps.clear()
            self._devices = None
            self._availability = self._bridge = None
        try:
            await asyncio.wait_for(asyncio.to_thread(client.connect, self.host, self.port, 30), self.timeout + 1)
        except TimeoutError:
            raise TimeoutError(f"The MQTT broker {self.host}:{self.port} sent no reply.") from None
        except OSError as exc:
            raise DriverError(f"Could not reach the MQTT broker {self.host}:{self.port} ({exc}).") from None
        client.loop_start()
        self._client = client
        deadline = time.monotonic() + self.timeout
        while not self._connected.is_set() or self._devices is None:
            if self._refused:
                await self.close()
                raise DriverError(f"{self.where}: {self._refused}. Check the user name and token_env.")
            if time.monotonic() > deadline:
                missing = (
                    "no CONNACK" if not self._connected.is_set() else f"nothing retained on {self.base}/bridge/devices"
                )
                await self.close()
                raise DriverError(f"{self.where}: {missing}. Check the URL and base_topic, and that Zigbee2MQTT runs.")
            await asyncio.sleep(0.02)
        entry = next(
            (item for item in self._devices or [] if isinstance(item, dict) and item.get("friendly_name") == self.name),
            None,
        )
        if entry is None:
            await self.close()
            raise DriverError(f"Zigbee2MQTT has no device named {self.name!r}. Check friendly_name.")
        self.device = entry
        definition = entry.get("definition") or {}
        self.features = features(definition.get("exposes") or [])
        gettable = [name for name in wanted if name in self.features and self._gettable(definition, name)]
        if gettable:
            request: dict[str, Any] = {}
            for name in gettable:
                request.update(_nest(name, ""))
            client.publish(f"{self.state_topic}/get", json.dumps(request), qos=0)

    def _gettable(self, definition: dict[str, Any], name: str) -> bool:
        stack: list[Any] = list(definition.get("exposes") or [])
        while stack:
            item = stack.pop()
            if isinstance(item, dict):
                if item.get("property") == name.split(".")[0] and int(item.get("access") or 0) & GETTABLE:
                    return True
                stack.extend(item.get("features") or [])
        return False

    async def close(self) -> None:
        client, self._client = self._client, None
        self._connected.clear()
        if client is None:
            return
        try:
            client.disconnect()
        finally:
            await asyncio.to_thread(client.loop_stop)

    @property
    def connected(self) -> bool:
        return self._client is not None and self._connected.is_set()

    def health(self) -> tuple[bool, str]:
        if not self.connected:
            return False, f"{self.where} {self._lost or 'not connected'}"
        if self._bridge == "offline":
            return False, f"{self.where}, Zigbee2MQTT reports itself offline"
        if self._availability == "offline":
            return False, f"{self.where} is offline in Zigbee2MQTT"
        return True, self.where

    def check_open(self) -> Any:
        if not self.connected:
            raise DriverError(f"{self.where} is not connected{f', {self._lost}' if self._lost else ''}. Reconnect it.")
        return self._client

    def feature(self, channel_map: ChannelMap, *, target: bool = False) -> Feature:
        return self.features.get(channel_map.property or "", UNKNOWN)

    def value(self, channel_map: ChannelMap) -> tuple[Any, float] | None:
        self.check_open()
        name = channel_map.property or ""
        top = name.split(".")[0]
        with self._lock:
            if top not in self._state:
                return None
            return _get(self._state, name), self._stamps.get(top, time.time())

    async def send(self, channel_map: ChannelMap, raw: Any) -> None:
        client = self.check_open()
        topic = f"{self.state_topic}/set"
        info = client.publish(topic, json.dumps(_nest(channel_map.property or "", raw)), qos=1)
        if getattr(info, "rc", 0) != 0:
            raise DriverError(f"The MQTT broker returned an error for the publish to {topic} (code {info.rc}).")
        try:
            await asyncio.wait_for(asyncio.to_thread(info.wait_for_publish, self.timeout), self.timeout + 1)
        except (RuntimeError, ValueError) as exc:
            raise DriverError(f"The publish to {topic} failed ({exc}).") from None
        except TimeoutError:
            pass
        if not info.is_published():
            await self.close()
            raise TimeoutError(
                f"The MQTT broker didn't acknowledge the command on {topic} within {self.timeout:g} s. "
                "The connection was closed so the command can't arrive late."
            )

    def identity(self) -> dict[str, str]:
        definition = self.device.get("definition") or {}
        identity = {"bridge": "zigbee2mqtt", "friendly_name": self.name}
        for key, value in (
            ("ieee_address", self.device.get("ieee_address")),
            ("vendor", definition.get("vendor")),
            ("model", definition.get("model")),
        ):
            if value:
                identity[key] = str(value)
        return identity

    def proposal(self) -> dict[str, Any]:
        read: dict[str, Any] = {}
        write: dict[str, Any] = {}
        for name, feature in sorted(self.features.items()):
            channel = name.replace(".", "_")[:48]
            spec = _spec(feature)
            if spec is None:
                continue
            spec["map"] = {"property": name}
            if feature.writable:
                write[channel] = {**spec, "suggested": True}
            elif feature.readable:
                read[channel] = spec
        definition = self.device.get("definition") or {}
        device = {"name": self.name, "manufacturer": definition.get("vendor"), "model": definition.get("model")}
        return {"device": {key: value for key, value in device.items() if value}, "read": read, "write": write}


def _spec(feature: Feature) -> dict[str, Any] | None:
    from openhal.drivers.serial import mapping

    if feature.kind == "bool":
        return {"type": "bool"}
    if feature.kind == "enum" and feature.values:
        return {"type": "enum", "values": list(feature.values)}
    if feature.kind == "string":
        return {"type": "string", "max_length": 255} if feature.writable else {"type": "string"}
    if feature.kind == "number":
        spec: dict[str, Any] = {"unit": mapping.device_unit(feature.unit) or "dimensionless"}
        if feature.writable:
            spec["min"] = feature.minimum if feature.minimum is not None else 0
            spec["max"] = feature.maximum if feature.maximum is not None else 100
        return spec
    return None
