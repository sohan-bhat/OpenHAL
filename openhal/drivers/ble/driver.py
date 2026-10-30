"""BLE driver. GATT characteristics of Bluetooth Low Energy peripherals, through bleak.

Protocol. Bluetooth Core Specification v5.4, Vol 3, Part G (GATT). Each channel's `map` names a
characteristic UUID (16-bit SIG UUIDs such as `2a6e` are expanded with the Bluetooth base UUID),
the value format from the GATT Specification Supplement, a byte offset and a linear scale.

Behavior worth knowing.

- `stream: true` read channels subscribe to notifications (or indications) when the driver
  connects, and a read returns the newest notified value. Until the first notification, a read
  falls back to a GATT read if the characteristic allows it, or reports None (unknown).
- Other channels do a GATT read every time.
- Writes use write with response when the characteristic supports it, unless the map sets
  `response: false`. Write without response gives no confirmation that the device got the value.
- `address: auto` scans for `scan_timeout` and picks the one peripheral that matches the device
  file's `match.ble_name` and `match.ble_services`. Scanning only listens to advertisements.
- On macOS, CoreBluetooth hides MAC addresses and gives each peripheral a UUID instead. Use that
  UUID as `address` there.
- BLE has no emergency behavior of its own. The device file's safe state is written like any
  other value, and only works while the link is up.
"""

from __future__ import annotations

import asyncio
import re
import time
from collections.abc import Callable
from typing import Annotated, Any, ClassVar, Final

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, ValidationError, field_validator

from openhal.drivers.base import Discovered, Driver, DriverError, DriverInfo, Health, Reading
from openhal.drivers.ble import codec
from openhal.spec.models import DeviceFile
from openhal.spec.units import parse_duration

BASE_UUID: Final = "-0000-1000-8000-00805f9b34fb"
_UUID: Final = re.compile(r"^(?:[0-9a-f]{4}|[0-9a-f]{8}|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})$")

KNOWN: Final[dict[str, tuple[str, codec.Format, float, str | None, str]]] = {
    "2a6e": ("temperature", "sint16", 0.01, "degC", "number"),
    "2a6f": ("humidity", "uint16", 0.01, "percent", "number"),
    "2a6d": ("pressure", "uint32", 0.1, "Pa", "number"),
    "2a76": ("uv_index", "uint8", 1.0, "dimensionless", "number"),
    "2a6c": ("elevation", "sint24", 0.01, "m", "number"),
    "2a19": ("battery_level", "uint8", 1.0, "percent", "number"),
}
SERVICES: Final = {
    "181a": "Environmental Sensing",
    "180f": "Battery",
    "180a": "Device Information",
    "1800": "Generic Access",
    "1801": "Generic Attribute",
}
DEVICE_INFO: Final = {
    "2a29": "manufacturer",
    "2a24": "model",
    "2a25": "serial_number",
    "2a26": "firmware",
    "2a27": "hardware",
    "2a28": "software",
}


def normalize_uuid(value: str) -> str:
    """Full lowercase 128-bit UUID. 16-bit and 32-bit SIG UUIDs use the Bluetooth base UUID."""
    text = value.strip().lower()
    if text.startswith("0x"):
        text = text[2:]
    if not _UUID.match(text):
        raise ValueError(f"{value!r} is not a BLE UUID. Use a 16-bit UUID such as 2a6e or a full 128-bit UUID.")
    if len(text) == 4:
        return f"0000{text}{BASE_UUID}"
    if len(text) == 8:
        return f"{text}{BASE_UUID}"
    return text


def short_uuid(uuid: str) -> str:
    """The 16-bit form of a SIG UUID, or the full UUID for vendor UUIDs."""
    if uuid.endswith(BASE_UUID) and uuid.startswith("0000"):
        return uuid[4:8]
    return uuid


def _seconds(value: Any) -> Any:
    if isinstance(value, int | float) and not isinstance(value, bool):
        return float(value)
    return parse_duration(value)


Duration = Annotated[float, BeforeValidator(_seconds), Field(gt=0, le=120)]


class BleParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    address: str = "auto"
    scan_timeout: Duration = 5.0
    timeout: Duration = 10.0
    pair: bool = False


class CharMap(BaseModel):
    model_config = ConfigDict(extra="forbid")

    characteristic: str
    service: str | None = None
    format: codec.Format = "uint8"
    byte: int = Field(default=0, ge=0, le=511)
    byteorder: codec.Order = "little"
    scale: float = 1.0
    offset: float = 0.0
    on: int = Field(default=1, ge=0)
    off: int = Field(default=0, ge=0)
    values: dict[str, int] = {}
    response: bool | None = None

    @field_validator("characteristic", "service")
    @classmethod
    def _uuid(cls, value: str | None) -> str | None:
        return None if value is None else normalize_uuid(value)

    @field_validator("scale")
    @classmethod
    def _scale(cls, value: float) -> float:
        if value == 0:
            raise ValueError("scale can't be zero.")
        return value


ClientFactory = Callable[..., Any]


def _bleak_client(address: Any, disconnected_callback: Any = None, **kwargs: Any) -> Any:
    from bleak import BleakClient

    return BleakClient(address, disconnected_callback, **kwargs)


def _bleak_scanner() -> Any:
    from bleak import BleakScanner

    return BleakScanner


def _errors() -> tuple[type[BaseException], ...]:
    from bleak.exc import BleakError

    return (BleakError, OSError, EOFError)


def _errors_or_timeout() -> tuple[type[BaseException], ...]:
    return (TimeoutError, *_errors())


class BleDriver(Driver):
    """BLE GATT peripherals. Characteristics, formats and scales come from each channel's map."""

    info: ClassVar[DriverInfo] = DriverInfo(
        name="ble",
        protocols=("Bluetooth Low Energy GATT",),
        hazard_default="low",
        summary="BLE peripherals with standard or documented GATT characteristics.",
    )
    params_model: ClassVar[type[Any] | None] = BleParams

    def __init__(
        self,
        device: DeviceFile,
        *,
        client_factory: ClientFactory = _bleak_client,
        scanner: Any = None,
    ) -> None:
        super().__init__(device)
        self.settings = BleParams.model_validate(device.connect.params)
        self._factory = client_factory
        self._scanner = scanner
        self._client: Any = None
        self._address: str | None = None if self.settings.address == "auto" else self.settings.address
        self._latest: dict[str, tuple[bytes, float]] = {}
        self._written: dict[str, float | bool | str] = {}
        self._lost = ""
        self.maps: dict[str, CharMap] = {}
        for name, spec in device.read.items():
            self.maps[name] = self._check(name, spec.type, spec.map, spec.values)
        for name, wspec in device.write.items():
            self.maps[name] = self._check(name, wspec.type, wspec.map, wspec.values)
            if self.maps[name].byte:
                raise DriverError(f"{name} uses byte, which only works for reads. Writes replace the whole value.")
        if device.actions:
            raise DriverError("The ble driver has no actions. Model each writable characteristic as a write channel.")

    def _check(self, name: str, kind: str, raw: dict[str, Any] | None, values: list[str]) -> CharMap:
        if raw is None:
            raise DriverError(f"{name} needs a map with a characteristic, for example map: {{ characteristic: 2a6e }}.")
        try:
            cmap = CharMap.model_validate(raw)
        except ValidationError as exc:
            problems = "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors())
            raise DriverError(f"{name} has an invalid ble map. {problems}") from None
        if kind == "image":
            raise DriverError(f"{name} is an image channel, which the ble driver doesn't support.")
        if kind == "string" and cmap.format != "utf8":
            raise DriverError(f"{name} is a string channel, so its map needs format: utf8.")
        if kind in ("number", "bool", "enum") and cmap.format == "utf8":
            raise DriverError(f"{name} is a {kind} channel, so its format can't be utf8.")
        if kind == "enum":
            missing = set(values) - set(cmap.values)
            if missing:
                raise DriverError(f"{name} is an enum, so its map needs values for {', '.join(sorted(missing))}.")
        return cmap

    @property
    def _streams(self) -> dict[str, CharMap]:
        return {name: self.maps[name] for name, spec in self.device.read.items() if spec.stream}

    @property
    def _where(self) -> str:
        return f"BLE device {self._address or 'auto'}"

    @classmethod
    async def discover(cls, *, scanner: Any = None, listen_s: float = 5.0) -> list[Discovered]:
        """Listen to advertisements. Scanning never connects to anything."""
        found = await (scanner or _bleak_scanner()).discover(timeout=listen_s, return_adv=True)
        results: list[Discovered] = []
        for address, (device, advertisement) in found.items():
            name = getattr(advertisement, "local_name", None) or getattr(device, "name", None)
            services = [short_uuid(str(uuid).lower()) for uuid in getattr(advertisement, "service_uuids", [])]
            identifiers = {"ble_services": ",".join(services)} if services else {}
            if name:
                identifiers["ble_name"] = str(name)
            results.append(Discovered(driver="ble", address=str(address), identifiers=identifiers, label=name))
        return results

    async def _resolve(self) -> str:
        if self._address is not None:
            return self._address
        match = self.device.match
        if match.ble_name is None and not match.ble_services:
            raise DriverError("address is auto, so the device file needs match.ble_name or match.ble_services.")
        candidates = []
        for found in await self.discover(scanner=self._scanner, listen_s=self.settings.scan_timeout):
            name = found.identifiers.get("ble_name", "")
            services = set(filter(None, found.identifiers.get("ble_services", "").split(",")))
            if match.ble_name is not None and not re.search(match.ble_name, name):
                continue
            wanted = {short_uuid(normalize_uuid(uuid)) for uuid in match.ble_services}
            if not wanted <= services:
                continue
            candidates.append(found)
        if len(candidates) != 1:
            listing = ", ".join(f"{item.address} ({item.label})" for item in candidates) or "none"
            raise DriverError(
                f"address is auto and {len(candidates)} advertising devices matched ({listing}). "
                "Set address to one of them, or narrow match.ble_name."
            )
        self._address = candidates[0].address
        return self._address

    async def identify(self) -> dict[str, str]:
        identity = {"address": self._address or self.settings.address}
        if self._client is None:
            return identity
        for uuid, key in DEVICE_INFO.items():
            data = await self._try_read(normalize_uuid(uuid))
            if data is not None:
                identity[key] = data.decode("utf-8", "replace").rstrip("\x00")[:120]
        return identity

    async def _try_read(self, uuid: str) -> bytes | None:
        """Read a characteristic if the device has it and allows reads. For identify and describe."""
        char = self._find(uuid)
        if char is None or "read" not in getattr(char, "properties", []):
            return None
        try:
            return bytes(await asyncio.wait_for(self._client.read_gatt_char(char), self.settings.timeout))
        except _errors_or_timeout():
            return None

    def _on_disconnect(self, client: Any) -> None:
        self._lost = "the link dropped"

    def _on_notify(self, uuid: str) -> Callable[[Any, bytearray], None]:
        def callback(sender: Any, data: bytearray) -> None:
            self._latest[uuid] = (bytes(data), time.time())

        return callback

    async def connect(self) -> None:
        await self.close()
        address = await self._resolve()
        client = self._factory(address, self._on_disconnect, timeout=self.settings.timeout, pair=self.settings.pair)
        self._lost = ""
        self._latest.clear()
        try:
            await asyncio.wait_for(client.connect(), self.settings.timeout + 1)
        except TimeoutError:
            raise TimeoutError(f"{self._where} did not connect within {self.settings.timeout:g} s.") from None
        except _errors() as exc:
            raise DriverError(
                f"Could not connect to {self._where} ({exc}). Check it is advertising, in range and not "
                "connected to another central, such as a phone app."
            ) from None
        self._client = client
        for name, cmap in self._streams.items():
            char = self._find(cmap.characteristic, cmap.service)
            if char is None:
                await self.close()
                raise DriverError(f"{self._where} has no characteristic {cmap.characteristic} for {name}.")
            properties = getattr(char, "properties", [])
            if "notify" not in properties and "indicate" not in properties:
                continue
            try:
                await asyncio.wait_for(
                    client.start_notify(char, self._on_notify(cmap.characteristic)), self.settings.timeout
                )
            except _errors_or_timeout() as exc:
                await self.close()
                raise DriverError(f"Could not subscribe to {cmap.characteristic} for {name} ({exc}).") from None

    async def close(self) -> None:
        client, self._client = self._client, None
        if client is not None and client.is_connected:
            try:
                await asyncio.wait_for(client.disconnect(), self.settings.timeout)
            except _errors_or_timeout():
                return

    async def health(self) -> Health:
        if self._client is None or not self._client.is_connected:
            return Health(connected=False, detail=f"{self._where} {self._lost or 'not connected'}")
        return Health(connected=True, detail=self._where)

    def _find(self, uuid: str, service: str | None = None) -> Any:
        if self._client is None:
            return None
        for svc in self._client.services:
            if service is not None and str(svc.uuid).lower() != service:
                continue
            for char in svc.characteristics:
                if str(char.uuid).lower() == uuid:
                    return char
        return None

    def _require(self) -> Any:
        if self._client is None or not self._client.is_connected:
            raise DriverError(f"{self._where} is not connected.")
        return self._client

    async def read(self, channel: str) -> Reading:
        cmap = self.maps.get(channel)
        if cmap is None:
            raise DriverError(f"This ble device has no channel {channel!r}.")
        client = self._require()
        char = self._find(cmap.characteristic, cmap.service)
        if char is None:
            raise DriverError(f"{self._where} has no characteristic {cmap.characteristic} for {channel}.")
        unit = self.device.channel_unit(channel)
        latest = self._latest.get(cmap.characteristic) if channel in self._streams else None
        if latest is not None:
            data, at = latest
        elif "read" in getattr(char, "properties", []):
            try:
                data = bytes(await asyncio.wait_for(client.read_gatt_char(char), self.settings.timeout))
            except TimeoutError:
                raise TimeoutError(f"{self._where} sent no reply to a read of {cmap.characteristic}.") from None
            except _errors() as exc:
                raise DriverError(f"Reading {cmap.characteristic} for {channel} failed ({exc}).") from None
            at = time.time()
        elif channel in self.device.write:
            return Reading(channel, self._written.get(channel), unit=unit)
        else:
            return Reading(channel, None, unit=unit)
        return self._decode(channel, cmap, data, at, unit)

    def _decode(self, channel: str, cmap: CharMap, data: bytes, at: float, unit: str | None) -> Reading:
        kind, allowed = self._kind(channel)
        try:
            raw = codec.decode(data, cmap.format, cmap.byte, cmap.byteorder)
        except ValueError as exc:
            raise DriverError(f"{cmap.characteristic} for {channel} {exc} ({data.hex() or 'empty'}).") from None
        value: float | bool | str
        if isinstance(raw, str):
            value = raw
        elif kind == "bool":
            value = raw != cmap.off
        elif kind == "enum":
            names = [name for name in allowed if cmap.values[name] == raw]
            if not names:
                raise DriverError(f"{channel} read raw value {raw:g}, which is not in its values map.")
            value = names[0]
        else:
            value = raw * cmap.scale + cmap.offset
        spec = self.device.read.get(channel)
        suspect = bool(
            spec is not None
            and spec.range is not None
            and isinstance(value, float)
            and not spec.range[0] <= value <= spec.range[1]
        )
        return Reading(channel, value, unit=unit, at=at, suspect=suspect)

    def _kind(self, channel: str) -> tuple[str, list[str]]:
        if channel in self.device.read:
            return self.device.read[channel].type, self.device.read[channel].values
        return self.device.write[channel].type, self.device.write[channel].values

    async def _write(self, channel: str, value: float | bool | str) -> Reading | None:
        cmap = self.maps.get(channel)
        if cmap is None or channel not in self.device.write:
            raise DriverError(f"This ble device has no write channel {channel!r}.")
        client = self._require()
        char = self._find(cmap.characteristic, cmap.service)
        if char is None:
            raise DriverError(f"{self._where} has no characteristic {cmap.characteristic} for {channel}.")
        kind, _ = self._kind(channel)
        sent: float | bool | str = value
        try:
            if kind == "bool":
                payload = codec.encode(cmap.on if value else cmap.off, cmap.format, cmap.byteorder)
            elif kind == "enum":
                payload = codec.encode(cmap.values[str(value)], cmap.format, cmap.byteorder)
            elif kind == "string":
                payload = codec.encode(str(value), "utf8")
            else:
                exact = (float(value) - cmap.offset) / cmap.scale
                raw = exact if cmap.format in ("float32", "float64") else float(round(exact))
                payload = codec.encode(raw, cmap.format, cmap.byteorder)
                sent = raw * cmap.scale + cmap.offset
        except ValueError as exc:
            raise DriverError(f"Can't encode {value!r} for {channel}, {exc}.") from None
        try:
            await asyncio.wait_for(client.write_gatt_char(char, payload, response=cmap.response), self.settings.timeout)
        except TimeoutError:
            raise TimeoutError(f"{self._where} didn't confirm the write to {cmap.characteristic}.") from None
        except _errors() as exc:
            raise DriverError(f"Writing {cmap.characteristic} for {channel} failed ({exc}).") from None
        self._written[channel] = sent
        return Reading(channel, sent, unit=self.device.channel_unit(channel))

    async def describe(self) -> dict[str, Any] | None:
        if self._client is None or not self._client.is_connected:
            return None
        reads: dict[str, Any] = {}
        notes: list[str] = []
        services: list[str] = []
        device: dict[str, str] = {}
        for svc in self._client.services:
            service = short_uuid(str(svc.uuid).lower())
            if service not in ("1800", "1801"):
                services.append(service)
            for char in svc.characteristics:
                uuid = short_uuid(str(char.uuid).lower())
                properties = list(getattr(char, "properties", []))
                if uuid in KNOWN:
                    name, fmt, scale, unit, _ = KNOWN[uuid]
                    if name in reads:
                        name = f"{name}_{char.handle}"
                    channel: dict[str, Any] = {"unit": unit, "map": {"characteristic": uuid, "format": fmt}}
                    if scale != 1.0:
                        channel["map"]["scale"] = scale
                    if "notify" in properties or "indicate" in properties:
                        channel["stream"] = True
                    reads[name] = channel
                elif uuid in DEVICE_INFO:
                    data = await self._try_read(normalize_uuid(uuid))
                    if data:
                        device[DEVICE_INFO[uuid]] = data.decode("utf-8", "replace").rstrip("\x00")[:120]
                elif service not in ("1800", "1801"):
                    notes.append(f"{uuid} ({', '.join(properties) or 'no properties'})")
        result: dict[str, Any] = {"match": {"ble_services": services}}
        if device:
            identity: dict[str, str] = {"name": device.get("model") or "BLE device"}
            if "manufacturer" in device:
                identity["manufacturer"] = device["manufacturer"]
            if "model" in device:
                identity["model"] = device["model"]
            result["device"] = identity
        if reads:
            result["read"] = reads
        text = "Mapped the standard Environmental Sensing and Battery characteristics."
        if notes:
            text += (
                " These characteristics are not standard, so the driver has no record of their format. Add them "
                f"by hand from the device's documentation: {'; '.join(notes[:30])}."
            )
        if "firmware" in device:
            text += f" Firmware {device['firmware']}."
        result["notes"] = text
        return result
