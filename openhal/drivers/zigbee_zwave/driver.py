"""Zigbee and Z-Wave devices through the bridges people already run, Zigbee2MQTT and zwave-js-server.

The URL picks the bridge. `mqtt://` or `mqtts://` is the MQTT broker Zigbee2MQTT publishes to, and
the device is named by `friendly_name` (`openhal.drivers.zigbee_zwave.zigbee`). `ws://` or `wss://`
is zwave-js-server, and the device is named by `node` (`openhal.drivers.zigbee_zwave.zwave`).

Bridge rules (docs/drivers/WRITING-A-DRIVER.md rule 9). A device file names one device, and only
the values its channels map are read or set. On connect the driver checks every channel against
what the bridge reports (the Zigbee2MQTT `exposes` list or the zwave-js value metadata) and
refuses a channel the bridge can't serve. The device file's limits apply even where the bridge has
its own, which only show up as suggested limits in `describe()`.

Reads come from what the bridge last pushed, timestamped when it arrived. A value the bridge
hasn't reported reads as no value. Changes return without a reading, because the bridge reports
the device's new state when the device confirms it.

Safe state. From the device file. Neither bridge has an emergency command.
"""

from __future__ import annotations

import hashlib
import os
from collections.abc import Callable
from typing import Annotated, Any, ClassVar, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, ValidationError, model_validator

from openhal.drivers.base import Driver, DriverError, DriverInfo, Health, Reading
from openhal.drivers.zigbee_zwave import common
from openhal.drivers.zigbee_zwave.common import ChannelMap
from openhal.drivers.zigbee_zwave.zigbee import ClientFactory, Zigbee2MqttLink, default_client
from openhal.drivers.zigbee_zwave.zwave import ZWaveJsLink
from openhal.spec.models import DeviceFile, ReadChannel, WriteChannel
from openhal.spec.units import parse_duration


def _seconds(value: Any) -> Any:
    if isinstance(value, int | float) and not isinstance(value, bool):
        return float(value)
    return parse_duration(value)


Duration = Annotated[float, BeforeValidator(_seconds), Field(gt=0, le=60)]


class BridgeParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str = Field(pattern=r"^(mqtts?|wss?)://[^\s/]+(:\d+)?(/\S*)?$")
    friendly_name: str | None = Field(default=None, min_length=1, max_length=200)
    node: int | None = Field(default=None, ge=1, le=4000)
    base_topic: str = Field(default="zigbee2mqtt", pattern=r"^[^#+\s]+$")
    username: str | None = None
    token_env: str | None = Field(default=None, pattern=r"^[A-Z_][A-Z0-9_]{0,63}$")
    ca_file: str | None = None
    timeout: Duration = 5.0

    @property
    def bridge(self) -> Literal["zigbee2mqtt", "zwave-js"]:
        return "zigbee2mqtt" if self.url.startswith("mqtt") else "zwave-js"

    @model_validator(mode="after")
    def _device(self) -> BridgeParams:
        if self.bridge == "zigbee2mqtt":
            if self.friendly_name is None or self.node is not None:
                raise ValueError("Zigbee2MQTT URLs (mqtt://) need friendly_name and no node.")
            if "+" in self.friendly_name or "#" in self.friendly_name:
                raise ValueError("friendly_name can't hold the MQTT wildcards + or #.")
        elif self.node is None or self.friendly_name is not None:
            raise ValueError("zwave-js-server URLs (ws://) need node and no friendly_name.")
        return self


LinkFactory = Callable[[BridgeParams, str | None], Any]


class ZigbeeZWaveDriver(Driver):
    """One Zigbee device through Zigbee2MQTT, or one Z-Wave node through zwave-js-server."""

    info: ClassVar[DriverInfo] = DriverInfo(
        name="zigbee-zwave",
        protocols=("Zigbee2MQTT MQTT API", "zwave-js-server WebSocket API"),
        hazard_default="low",
        summary="Zigbee devices through Zigbee2MQTT and Z-Wave nodes through zwave-js-server.",
        safe_state_support="file",
        conformance="control",
    )
    params_model: ClassVar[type[Any] | None] = BridgeParams

    def __init__(
        self,
        device: DeviceFile,
        *,
        client_factory: ClientFactory = default_client,
        environ: Callable[[str], str | None] = os.environ.get,
    ) -> None:
        super().__init__(device)
        self.settings = BridgeParams.model_validate(device.connect.params)
        self._client_factory = client_factory
        self._environ = environ
        self.link: Any = None
        self.maps: dict[str, ChannelMap] = {}
        if device.actions:
            raise DriverError("The zigbee-zwave driver has no actions. Map each settable value as a channel.")
        specs: dict[str, ReadChannel | WriteChannel] = {**device.read, **device.write}
        for name, spec in specs.items():
            if spec.type == "image":
                raise DriverError(f"{name}: the bridges have no image values.")
            try:
                channel_map = ChannelMap.model_validate(spec.map or {})
            except ValidationError as exc:
                problems = "; ".join(f"{'.'.join(map(str, e['loc'])) or 'map'}: {e['msg']}" for e in exc.errors())
                raise DriverError(f"{name} has an invalid zigbee-zwave map. {problems}") from None
            if self.settings.bridge == "zigbee2mqtt":
                if channel_map.command_class is not None or channel_map.target is not None:
                    raise DriverError(f"{name}: command_class and target are Z-Wave keys. Zigbee maps use property.")
                channel_map = channel_map.model_copy(update={"property": channel_map.property or name})
            elif channel_map.command_class is None or channel_map.property is None:
                raise DriverError(
                    f"{name}: Z-Wave maps need command_class and property, for example "
                    "{ command_class: 37, property: currentValue }. describe() lists them."
                )
            self.maps[name] = channel_map

    def _client_id(self) -> str:
        digest = hashlib.sha256(self.device.device_id.encode()).hexdigest()[:6]
        return f"oh-{self.device.device_id[:13]}-{digest}"

    def _make_link(self) -> Any:
        settings = self.settings
        if settings.bridge == "zwave-js":
            assert settings.node is not None
            return ZWaveJsLink(settings.url, settings.node, timeout=settings.timeout)
        password = None
        if settings.token_env is not None:
            password = self._environ(settings.token_env)
            if not password:
                raise DriverError(f"Set the {settings.token_env} environment variable to the broker password.")
        assert settings.friendly_name is not None
        return Zigbee2MqttLink(
            settings.url,
            settings.friendly_name,
            base_topic=settings.base_topic,
            username=settings.username,
            password=password,
            ca_file=settings.ca_file,
            timeout=settings.timeout,
            client_id=self._client_id(),
            client_factory=self._client_factory,
        )

    async def identify(self) -> dict[str, str]:
        if self.link is not None and self.link.connected:
            identity: dict[str, str] = self.link.identity()
            return identity
        target = self.settings.friendly_name or f"node {self.settings.node}"
        return {"bridge": self.settings.bridge, "url": self.settings.url, "device": target}

    async def connect(self) -> None:
        await self.close()
        link = self._make_link()
        await link.open([channel_map.property or "" for channel_map in self.maps.values()])
        self.link = link
        try:
            self._check_channels()
        except DriverError:
            await self.close()
            raise

    def _check_channels(self) -> None:
        where = self.link.where
        for name, spec in self.device.read.items():
            common.check(name, spec, self.link.feature(self.maps[name]), self.maps[name], sends=False, where=where)
        for name, wspec in self.device.write.items():
            channel_map = self.maps[name]
            common.check(name, wspec, self.link.feature(channel_map, target=True), channel_map, sends=True, where=where)

    async def close(self) -> None:
        link, self.link = self.link, None
        if link is not None:
            await link.close()

    async def health(self) -> Health:
        if self.link is None:
            return Health(connected=False, detail="not connected")
        connected, detail = self.link.health()
        return Health(connected=connected, detail=detail)

    def _open_link(self) -> Any:
        if self.link is None:
            raise DriverError(f"{self.device.device_id} is not connected. Connect it first.")
        return self.link

    async def read(self, channel: str) -> Reading:
        channel_map = self.maps.get(channel)
        if channel_map is None:
            raise DriverError(f"This zigbee-zwave device has no channel {channel!r}.")
        link = self._open_link()
        spec = self.device.write.get(channel) or self.device.read[channel]
        unit = self.device.channel_unit(channel)
        found = link.value(channel_map)
        if found is None:
            return Reading(channel, None, unit=unit)
        raw, at = found
        feature = link.feature(channel_map)
        if feature is common.UNKNOWN:
            feature = link.feature(channel_map, target=True)
        where = f"{link.where}, {channel_map.property}"
        value = common.decode(raw, spec, feature, channel_map, where)
        return Reading(channel, value, unit=unit, at=at, suspect=common.suspect(value, spec))

    async def _write(self, channel: str, value: float | bool | str) -> Reading | None:
        channel_map = self.maps.get(channel)
        if channel_map is None or channel not in self.device.write:
            raise DriverError(f"This zigbee-zwave device has no write channel {channel!r}.")
        link = self._open_link()
        link.check_open()
        feature = link.feature(channel_map, target=True)
        raw = common.encode(value, self.device.write[channel], feature, channel_map, f"write.{channel}")
        await link.send(channel_map, raw)
        return None

    async def describe(self) -> dict[str, Any] | None:
        if self.link is None or not self.link.connected:
            return None
        proposal: dict[str, Any] = self.link.proposal()
        proposal["notes"] = (
            f"Proposed from what {self.settings.bridge} reports for this device. Limits are the bridge's own and "
            "suggested. Keep only the channels you need, because the bridge exposes only the ones the file maps."
        )
        return proposal
