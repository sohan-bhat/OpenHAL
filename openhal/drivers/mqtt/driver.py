"""MQTT driver. Devices that publish their state and take commands on broker topics, through paho-mqtt.

Protocol. MQTT 3.1.1 (OASIS standard) through a broker. Each channel's `map` names a state topic
the device publishes on and, for write channels, a command topic the driver publishes to, plus
how the payload is written (a raw number or word, or JSON with a path to the value). This covers
the common firmware conventions (Tasmota `cmnd/.../POWER` and `stat/.../POWER`, Zigbee2MQTT
`<device>/set` with JSON, ESPHome and Shelly MQTT topics) without device-specific code.

Behavior worth knowing.

- MQTT is push only. The driver subscribes to every state topic and keeps the latest message per
  topic. A read returns that message, timestamped when it arrived. Retained messages seed reads
  right after connecting. A channel that has never had a message reads as None (unknown), which
  the kernel treats as unknown in interlocks.
- Commands are never queued. A write while disconnected fails instead of being delivered later,
  and paho's automatic reconnect is turned off so in-flight commands are not replayed on a new
  connection. The hub's heartbeat reconnects with a fresh client.
- QoS 1 commands wait for the broker's PUBACK. That proves the broker has the message, not that
  the device acted. Read the state topic to see what the device did.
- There is no protocol-level safe state. The device file's safe state is published like any other
  command, and only works while the broker and the device are up.
"""

from __future__ import annotations

import asyncio
import json
import os
import threading
import time
from collections.abc import Callable
from typing import Annotated, Any, ClassVar, Final, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, ValidationError, field_validator

from openhal.drivers.base import Discovered, Driver, DriverError, DriverInfo, Health, Reading
from openhal.drivers.http import values as v
from openhal.spec.models import DeviceFile
from openhal.spec.units import parse_duration

_SETTLE_S: Final = 0.5
_DESCRIBE_LIMIT: Final = 64


def _seconds(value: Any) -> Any:
    if isinstance(value, int | float) and not isinstance(value, bool):
        return float(value)
    return parse_duration(value)


Duration = Annotated[float, BeforeValidator(_seconds), Field(gt=0, le=60)]
Scalar = str | int | float | bool


def _check_topic(value: str | None, *, wildcards: bool = False) -> str | None:
    if value is None:
        return None
    if not value or len(value.encode()) > 65535 or "\x00" in value:
        raise ValueError("A topic must be a non-empty UTF-8 string.")
    if not wildcards and ("+" in value or "#" in value):
        raise ValueError(f"Topic {value!r} has a wildcard. State and command topics must be exact topics.")
    return value


class MqttParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    host: str = Field(min_length=1)
    port: int = Field(default=1883, ge=1, le=65535)
    client_id: str | None = Field(default=None, max_length=23)
    username: str | None = None
    token_env: str | None = Field(default=None, pattern=r"^[A-Z_][A-Z0-9_]*$")
    tls: bool = False
    ca_file: str | None = None
    keepalive: int = Field(default=30, ge=5, le=3600)
    timeout: Duration = 5.0
    qos: Literal[0, 1] = 1
    prefix: str = ""
    retain_commands: bool = False
    discover_topic: str = "#"

    @field_validator("discover_topic")
    @classmethod
    def _discover(cls, value: str) -> str:
        _check_topic(value, wildcards=True)
        return value


class _Payload(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    format: Literal["raw", "json"] = "raw"
    json_path: str | None = Field(default=None, alias="json")
    on: Scalar | list[Scalar] | None = None
    off: Scalar | list[Scalar] | None = None
    scale: float = 1.0
    offset: float = 0.0

    @field_validator("json_path")
    @classmethod
    def _path(cls, value: str | None) -> str | None:
        if value is not None:
            v.parse_path(value)
        return value

    @field_validator("scale")
    @classmethod
    def _scale(cls, value: float) -> float:
        if value == 0:
            raise ValueError("scale can't be zero.")
        return value


class ReadMap(_Payload):
    state: str

    @field_validator("state")
    @classmethod
    def _state(cls, value: str) -> str:
        _check_topic(value)
        return value


class WriteMap(_Payload):
    state: str | None = None
    command: str
    template: Any = None
    qos: Literal[0, 1] | None = None
    retain: bool | None = None

    @field_validator("state", "command")
    @classmethod
    def _topics(cls, value: str | None) -> str | None:
        return _check_topic(value)


ClientFactory = Callable[[str], Any]


def _default_client(client_id: str) -> Any:
    import paho.mqtt.client as mqtt
    from paho.mqtt.enums import CallbackAPIVersion, MQTTProtocolVersion

    return mqtt.Client(
        callback_api_version=CallbackAPIVersion.VERSION2,
        client_id=client_id,
        clean_session=True,
        protocol=MQTTProtocolVersion.MQTTv311,
        reconnect_on_failure=False,
    )


class MqttDriver(Driver):
    """MQTT devices through a broker. Topics and payload formats come from each channel's map."""

    info: ClassVar[DriverInfo] = DriverInfo(
        name="mqtt",
        protocols=("MQTT 3.1.1",),
        hazard_default="medium",
        summary="Devices that publish state and take commands on MQTT topics (Tasmota, Zigbee2MQTT, DIY boards).",
    )
    params_model: ClassVar[type[Any] | None] = MqttParams

    def __init__(
        self,
        device: DeviceFile,
        *,
        client_factory: ClientFactory = _default_client,
        environ: Callable[[str], str | None] = os.environ.get,
    ) -> None:
        super().__init__(device)
        self.settings = MqttParams.model_validate(device.connect.params)
        self._factory = client_factory
        self._environ = environ
        self._client: Any = None
        self._connected = threading.Event()
        self._lock = threading.Lock()
        self._latest: dict[str, tuple[bytes, float]] = {}
        self._seen: dict[str, bytes] | None = None
        self._written: dict[str, float | bool | str] = {}
        self._disconnect_reason = ""
        self.reads: dict[str, ReadMap] = {}
        self.writes: dict[str, WriteMap] = {}
        for name, spec in device.read.items():
            if spec.type == "image":
                raise DriverError(f"{name} is an image channel, which the mqtt driver doesn't support.")
            self.reads[name] = self._parse(ReadMap, name, spec.map)
        for name, wspec in device.write.items():
            wmap = self._parse(WriteMap, name, wspec.map)
            if v.placeholders(wmap.template) - {"value"}:
                raise DriverError(f"write.{name} template can only use {{value}}.")
            self.writes[name] = wmap
        if device.actions:
            raise DriverError("The mqtt driver has no actions. Model each command topic as a write channel.")

    @staticmethod
    def _parse[M: BaseModel](model: type[M], name: str, raw: dict[str, Any] | None) -> M:
        if raw is None:
            raise DriverError(f"{name} needs a map with a state topic, for example map: {{ state: home/fan/speed }}.")
        try:
            return model.model_validate(raw)
        except ValidationError as exc:
            problems = "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors())
            raise DriverError(f"{name} has an invalid mqtt map. {problems}") from None

    def _topic(self, topic: str) -> str:
        return f"{self.settings.prefix}{topic}"

    @property
    def state_topics(self) -> set[str]:
        topics = {self._topic(rmap.state) for rmap in self.reads.values()}
        topics |= {self._topic(wmap.state) for wmap in self.writes.values() if wmap.state}
        return topics

    @property
    def _where(self) -> str:
        return f"MQTT broker {self.settings.host}:{self.settings.port}"

    # ------------------------------------------------------------------ paho callbacks (paho's thread)

    def _on_connect(self, client: Any, userdata: Any, flags: Any, reason: Any, properties: Any) -> None:
        if getattr(reason, "is_failure", False):
            self._disconnect_reason = f"the broker refused the connection ({reason})"
            return
        topics = sorted(self.state_topics)
        if topics:
            client.subscribe([(topic, 0) for topic in topics])
        self._connected.set()

    def _on_disconnect(self, client: Any, userdata: Any, flags: Any, reason: Any, properties: Any) -> None:
        self._connected.clear()
        self._disconnect_reason = f"disconnected ({reason})"

    def _on_message(self, client: Any, userdata: Any, message: Any) -> None:
        payload = bytes(message.payload)
        with self._lock:
            if message.topic in self.state_topics:
                self._latest[message.topic] = (payload, time.time())
            if self._seen is not None and len(self._seen) < 256:
                self._seen.setdefault(message.topic, payload)

    # ------------------------------------------------------------------ lifecycle

    @classmethod
    async def discover(cls) -> list[Discovered]:
        # Brokers are found by mDNS (_mqtt._tcp) in the hub. Devices behind a broker are only
        # visible by listening, which describe() does for a configured broker.
        return []

    async def identify(self) -> dict[str, str]:
        return {"broker": f"{self.settings.host}:{self.settings.port}", "client_id": self._client_id()}

    def _client_id(self) -> str:
        return self.settings.client_id or f"openhal-{self.device.device_id}"[:23]

    async def connect(self) -> None:
        await self.close()
        client = self._factory(self._client_id())
        client.on_connect = self._on_connect
        client.on_disconnect = self._on_disconnect
        client.on_message = self._on_message
        client.connect_timeout = self.settings.timeout
        if self.settings.username is not None or self.settings.token_env is not None:
            password = None
            if self.settings.token_env is not None:
                password = self._environ(self.settings.token_env)
                if not password:
                    raise DriverError(
                        f"The environment variable {self.settings.token_env} is not set. "
                        "Set it to the broker password before starting the hub."
                    )
            client.username_pw_set(self.settings.username or "", password)
        if self.settings.tls:
            client.tls_set(ca_certs=self.settings.ca_file)
        self._connected.clear()
        self._disconnect_reason = ""
        with self._lock:
            self._latest.clear()
        try:
            await asyncio.wait_for(
                asyncio.to_thread(client.connect, self.settings.host, self.settings.port, self.settings.keepalive),
                self.settings.timeout + 1,
            )
        except TimeoutError:
            raise TimeoutError(
                f"{self._where} did not accept a connection within {self.settings.timeout:g} s."
            ) from None
        except OSError as exc:
            raise DriverError(f"Could not reach the {self._where} ({exc}). Check host and port.") from None
        client.loop_start()
        self._client = client
        deadline = time.monotonic() + self.settings.timeout
        while not self._connected.is_set():
            if self._disconnect_reason or time.monotonic() > deadline:
                reason = self._disconnect_reason or "no CONNACK in time"
                await self.close()
                raise DriverError(f"The {self._where} did not accept the connection, {reason}. Check the credentials.")
            await asyncio.sleep(0.02)
        # Retained state arrives right after the subscription. Give it a moment so the first
        # reads see it, but don't wait on topics that have nothing retained.
        settle = time.monotonic() + min(_SETTLE_S, self.settings.timeout)
        while time.monotonic() < settle:
            with self._lock:
                if self.state_topics <= set(self._latest):
                    break
            await asyncio.sleep(0.02)

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
        """True while the broker connection is up."""
        return self._client is not None and self._connected.is_set()

    async def health(self) -> Health:
        if not self.connected:
            return Health(connected=False, detail=f"{self._where} {self._disconnect_reason or 'not connected'}")
        return Health(connected=True, detail=self._where)

    # ------------------------------------------------------------------ reads

    async def read(self, channel: str) -> Reading:
        if channel in self.reads:
            spec = self.device.read[channel]
            return self._decode(channel, self.reads[channel], self.reads[channel].state, spec.type, spec.values)
        if channel in self.writes:
            wmap = self.writes[channel]
            wspec = self.device.write[channel]
            if wmap.state is None:
                if self._client is None:
                    raise DriverError(f"The {self._where} is not connected.")
                return Reading(channel, self._written.get(channel), unit=wspec.unit)
            return self._decode(channel, wmap, wmap.state, wspec.type, wspec.values)
        raise DriverError(f"This mqtt device has no channel {channel!r}.")

    def _decode(self, channel: str, pmap: _Payload, state: str, kind: str, allowed: list[str]) -> Reading:
        if self._client is None:
            raise DriverError(f"The {self._where} is not connected.")
        topic = self._topic(state)
        unit = self.device.channel_unit(channel)
        with self._lock:
            latest = self._latest.get(topic)
        if latest is None:
            # Nothing retained and nothing published since connecting. The value is unknown.
            return Reading(channel, None, unit=unit)
        payload, at = latest
        where = f"topic {topic} for {channel}"
        raw: Any = payload
        if pmap.format == "json":
            try:
                raw = json.loads(payload)
            except (json.JSONDecodeError, UnicodeDecodeError):
                raise DriverError(f"{where} carried {payload[:60]!r}, which is not JSON. Check format.") from None
            if pmap.json_path:
                raw = v.extract(raw, v.parse_path(pmap.json_path), where)
        value: float | bool | str
        if kind == "number":
            value = v.to_number(raw, where) * pmap.scale + pmap.offset
        elif kind == "bool":
            value = v.to_bool(raw, v.words(pmap.on, v.DEFAULT_ON), v.words(pmap.off, v.DEFAULT_OFF), where)
        else:
            value = v.to_text(raw)
            if kind == "enum" and value not in allowed:
                raise DriverError(f"{where} reported {value[:60]!r}, which is not one of {', '.join(allowed)}.")
        spec = self.device.read.get(channel)
        suspect = bool(
            spec is not None
            and spec.range is not None
            and isinstance(value, float)
            and not spec.range[0] <= value <= spec.range[1]
        )
        return Reading(channel, value, unit=unit, at=at, suspect=suspect)

    # ------------------------------------------------------------------ writes

    def _payload(self, wmap: WriteMap, value: float | bool | str) -> bytes:
        item: Any = value
        if isinstance(value, bool):
            chosen = wmap.on if value else wmap.off
            if isinstance(chosen, list):
                chosen = chosen[0] if chosen else None
            if chosen is not None:
                item = chosen
            elif wmap.format == "raw":
                item = "ON" if value else "OFF"
        elif isinstance(value, int | float):
            item = v.device_number(value, wmap.scale, wmap.offset)
        if wmap.template is not None:
            document = v.render(wmap.template, {"value": item})
            return (document if isinstance(document, str) else json.dumps(document, separators=(",", ":"))).encode()
        if wmap.format == "json":
            if wmap.json_path:
                return json.dumps(v.build_nested(v.parse_path(wmap.json_path), item), separators=(",", ":")).encode()
            return json.dumps(item).encode()
        return v.show(item).encode()

    async def _write(self, channel: str, value: float | bool | str) -> Reading | None:
        wmap = self.writes.get(channel)
        if wmap is None:
            raise DriverError(f"This mqtt device has no write channel {channel!r}.")
        client = self._client
        if client is None or not self._connected.is_set():
            raise DriverError(f"The {self._where} is not connected, so the command was not sent (it is never queued).")
        try:
            payload = self._payload(wmap, value)
        except ValueError as exc:
            raise DriverError(f"Could not build the payload for {channel}. {exc}") from None
        qos = self.settings.qos if wmap.qos is None else wmap.qos
        retain = self.settings.retain_commands if wmap.retain is None else wmap.retain
        info = client.publish(self._topic(wmap.command), payload, qos=qos, retain=retain)
        if getattr(info, "rc", 0) != 0:
            raise DriverError(f"The {self._where} refused the publish to {wmap.command} (code {info.rc}).")
        if qos == 1:
            try:
                await asyncio.wait_for(
                    asyncio.to_thread(info.wait_for_publish, self.settings.timeout), self.settings.timeout + 1
                )
            except (RuntimeError, ValueError) as exc:
                raise DriverError(f"The publish to {wmap.command} failed ({exc}).") from None
            except TimeoutError:
                pass
            if not info.is_published():
                # The broker never confirmed. Drop the client so paho can't replay the command later.
                await self.close()
                raise TimeoutError(
                    f"The {self._where} didn't acknowledge the command on {wmap.command} within "
                    f"{self.settings.timeout:g} s. The connection was closed so the command can't arrive late."
                )
        self._written[channel] = value
        return None if wmap.state else Reading(channel, value, unit=self.device.channel_unit(channel))

    # ------------------------------------------------------------------ describe

    async def describe(self, listen_s: float = 2.0) -> dict[str, Any] | None:
        """Listen on `discover_topic` and propose a read channel for each topic with a value."""
        client = self._client
        if client is None or not self._connected.is_set():
            return None
        pattern = (
            self._topic(self.settings.discover_topic)
            if self.settings.discover_topic != "#"
            else (f"{self.settings.prefix}#" if self.settings.prefix else "#")
        )
        with self._lock:
            self._seen = {}
        client.subscribe(pattern, 0)
        await asyncio.sleep(listen_s)
        client.unsubscribe(pattern)
        with self._lock:
            seen, self._seen = self._seen or {}, None
        return describe_topics(seen, self.settings.prefix)


def describe_topics(seen: dict[str, bytes], prefix: str = "") -> dict[str, Any]:
    """Propose read channels from topic payloads. Numbers, on/off words and JSON objects."""
    reads: dict[str, Any] = {}
    taken: set[str] = set()

    def name_for(*parts: str) -> str:
        import re

        slug = re.sub(r"[^a-z0-9]+", "_", "_".join(parts).lower()).strip("_")
        if not slug or not slug[0].isalpha():
            slug = f"ch_{slug}".strip("_")
        slug = slug[:48].rstrip("_")
        candidate, index = slug, 2
        while candidate in taken:
            candidate = f"{slug[:44]}_{index}"
            index += 1
        taken.add(candidate)
        return candidate

    for topic, payload in sorted(seen.items()):
        if len(reads) >= _DESCRIBE_LIMIT:
            break
        relative = topic[len(prefix) :] if prefix and topic.startswith(prefix) else topic
        text = payload.decode("utf-8", "replace").strip()
        try:
            document: Any = json.loads(text)
        except json.JSONDecodeError:
            document = None
        if isinstance(document, dict):
            for key, item in document.items():
                if len(reads) >= _DESCRIBE_LIMIT or not isinstance(key, str) or not key.isidentifier():
                    continue
                path = f"$.{key}"
                if isinstance(item, bool):
                    reads[name_for(relative, key)] = {
                        "type": "bool",
                        "map": {"state": relative, "format": "json", "json": path},
                    }
                elif isinstance(item, int | float):
                    reads[name_for(relative, key)] = {
                        "unit": "dimensionless",
                        "map": {"state": relative, "format": "json", "json": path},
                    }
            continue
        if isinstance(document, int | float) and not isinstance(document, bool):
            reads[name_for(relative)] = {"unit": "dimensionless", "map": {"state": relative}}
        elif text.lower() in v.DEFAULT_ON + v.DEFAULT_OFF:
            reads[name_for(relative)] = {"type": "bool", "map": {"state": relative}}
    notes = (
        f"Proposed from {len(seen)} topics seen while listening. Numbers use dimensionless until you set the real "
        "unit. Command topics can't be seen by listening, so add write channels from the device's documentation."
    )
    result: dict[str, Any] = {"notes": notes}
    if reads:
        result["read"] = reads
    return result
