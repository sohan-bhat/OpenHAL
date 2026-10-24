"""HID driver. USB HID devices with a documented report format, through hidapi.

Protocol. USB Device Class Definition for HID 1.11. A HID device sends input reports (buttons,
knobs, sensors) on its interrupt endpoint, takes output reports (LEDs, actuators) and exposes
feature reports (configuration) through control transfers. Each channel's `map` names the report
id, the kind of report, a byte offset into the report (after the report id byte), a number format
and an optional bit mask.

Behavior worth knowing.

- A reader thread takes input reports as they arrive and keeps the newest one per report id. A
  read of an input channel decodes that report, timestamped when it arrived, or reports None
  (unknown) until the device has sent one.
- Feature channels are read with a GET_REPORT request each time.
- Output reports are whole reports. The driver keeps one buffer per output report, starting at
  zero (or the map's `fill`), changes only the masked bits of the channel being written, and sends
  the whole buffer. Write channels on output reports report the last value written.
- hidapi always expects the report id as the first byte, and 0 for devices without report ids.
- HID has no emergency behavior. The device file's safe state is sent as ordinary reports.
"""

from __future__ import annotations

import asyncio
import contextlib
import struct
import threading
import time
from collections.abc import Callable
from typing import Annotated, Any, ClassVar, Final, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, ValidationError, field_validator

from openhal.drivers.base import Discovered, Driver, DriverError, DriverInfo, Health, Reading
from openhal.drivers.hid import descriptor
from openhal.spec.models import DeviceFile
from openhal.spec.units import parse_duration

Format = Literal["uint8", "int8", "uint16", "int16", "uint32", "int32"]
_STRUCT: Final = {"uint8": "B", "int8": "b", "uint16": "H", "int16": "h", "uint32": "I", "int32": "i"}
_SIZE: Final = {"uint8": 1, "int8": 1, "uint16": 2, "int16": 2, "uint32": 4, "int32": 4}


def _seconds(value: Any) -> Any:
    if isinstance(value, int | float) and not isinstance(value, bool):
        return float(value)
    return parse_duration(value)


def _int(value: Any) -> Any:
    if isinstance(value, str):
        return int(value, 0)
    return value


Duration = Annotated[float, BeforeValidator(_seconds), Field(gt=0, le=30)]
Word = Annotated[int, BeforeValidator(_int), Field(ge=0, le=0xFFFF)]


class HidParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = "auto"
    vid: Word | None = None
    pid: Word | None = None
    serial: str | None = None
    path: str | None = None
    usage_page: Word | None = None
    interface: int | None = Field(default=None, ge=0, le=255)
    report_length: int = Field(default=64, ge=1, le=4096)
    timeout: Duration = 1.0


class HidMap(BaseModel):
    model_config = ConfigDict(extra="forbid")

    report: int = Field(default=0, ge=0, le=255)
    kind: Literal["input", "output", "feature"] = "input"
    byte: int = Field(default=0, ge=0, le=4095)
    format: Format = "uint8"
    byteorder: Literal["little", "big"] = "little"
    mask: int | None = Field(default=None, ge=1)
    scale: float = 1.0
    offset: float = 0.0
    on: int | None = None
    off: int = 0
    values: dict[str, int] = {}
    length: int | None = Field(default=None, ge=1, le=4096)
    fill: list[Annotated[int, Field(ge=0, le=255)]] = []

    @field_validator("scale")
    @classmethod
    def _scale(cls, value: float) -> float:
        if value == 0:
            raise ValueError("scale can't be zero.")
        return value

    @property
    def end(self) -> int:
        return self.byte + _SIZE[self.format]

    def bits(self) -> int:
        return self.mask if self.mask is not None else (1 << (8 * _SIZE[self.format])) - 1

    def shift(self) -> int:
        mask = self.bits()
        return (mask & -mask).bit_length() - 1


def _hid_module() -> Any:
    import hid  # type: ignore[import-not-found]

    return hid


class HidDriver(Driver):
    """USB HID devices. Report ids, offsets, formats and masks come from each channel's map."""

    info: ClassVar[DriverInfo] = DriverInfo(
        name="hid",
        protocols=("USB HID 1.11",),
        hazard_default="low",
        summary="USB HID devices such as buttons, knobs, macropads and custom HID gadgets.",
    )
    params_model: ClassVar[type[Any] | None] = HidParams

    def __init__(self, device: DeviceFile, *, hid_module: Any = None) -> None:
        super().__init__(device)
        self.settings = HidParams.model_validate(device.connect.params)
        self._hid_module = hid_module
        self._device: Any = None
        self._info: dict[str, Any] = {}
        self._reader: threading.Thread | None = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._latest: dict[int, tuple[bytes, float]] = {}
        self._error = ""
        self._buffers: dict[tuple[str, int], bytearray] = {}
        self._written: dict[str, float | bool | str] = {}
        self.maps: dict[str, HidMap] = {}
        for name, spec in device.read.items():
            self.maps[name] = self._check(name, spec.type, spec.map, spec.values, writable=False)
        for name, wspec in device.write.items():
            self.maps[name] = self._check(name, wspec.type, wspec.map, wspec.values, writable=True)
        self._layout()
        if device.actions:
            raise DriverError("The hid driver has no actions. Model each report field as a write channel.")

    def _check(self, name: str, kind: str, raw: dict[str, Any] | None, values: list[str], *, writable: bool) -> HidMap:
        if raw is None:
            raise DriverError(f"{name} needs a map, for example map: {{ report: 1, byte: 0, mask: 1 }}.")
        try:
            hmap = HidMap.model_validate(raw)
        except ValidationError as exc:
            problems = "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors())
            raise DriverError(f"{name} has an invalid hid map. {problems}") from None
        if kind not in ("number", "bool", "enum"):
            raise DriverError(f"{name} is a {kind} channel. HID report fields are numbers, bools or enums.")
        if writable and hmap.kind == "input":
            raise DriverError(f"{name} is a write channel, so its map needs kind: output or kind: feature.")
        if not writable and hmap.kind == "output":
            raise DriverError(f"{name} reads an output report, which devices don't send. Make it a write channel.")
        if hmap.mask is not None and hmap.mask >= 1 << (8 * _SIZE[hmap.format]):
            raise DriverError(f"{name} has a mask wider than its {hmap.format} format.")
        if kind == "enum" and set(values) - set(hmap.values):
            raise DriverError(
                f"{name} is an enum, so its map needs values for {', '.join(sorted(set(values) - set(hmap.values)))}."
            )
        if hmap.end > self.settings.report_length and hmap.kind != "output":
            raise DriverError(f"{name} reads past report_length ({self.settings.report_length} bytes).")
        return hmap

    def _layout(self) -> None:
        """Size each output and feature buffer to fit every write channel that shares it."""
        for name in self.device.write:
            hmap = self.maps[name]
            key = (hmap.kind, hmap.report)
            length = max(hmap.length or 0, hmap.end, len(hmap.fill))
            buffer = self._buffers.setdefault(key, bytearray())
            if len(buffer) < length:
                buffer.extend(bytes(length - len(buffer)))
            for index, byte in enumerate(hmap.fill):
                buffer[index] = byte

    @property
    def hid(self) -> Any:
        if self._hid_module is None:
            self._hid_module = _hid_module()
        return self._hid_module

    @property
    def _uses_ids(self) -> bool:
        return any(hmap.report != 0 for hmap in self.maps.values())

    # ------------------------------------------------------------------ finding and opening

    @classmethod
    async def discover(cls, *, hid_module: Any = None) -> list[Discovered]:
        """List HID interfaces. Enumeration reads the OS device list and never opens a device."""
        module = hid_module or _hid_module()
        found = []
        for entry in await asyncio.to_thread(module.enumerate):
            path = entry.get("path", b"")
            address = path.decode("utf-8", "replace") if isinstance(path, bytes) else str(path)
            identifiers = {
                "usb": f"{entry.get('vendor_id', 0):04x}:{entry.get('product_id', 0):04x}",
                "usb_class": "hid",
            }
            if entry.get("serial_number"):
                identifiers["serial_number"] = str(entry["serial_number"])
            label = " ".join(filter(None, [entry.get("manufacturer_string"), entry.get("product_string")])) or None
            found.append(Discovered(driver="hid", address=address, identifiers=identifiers, label=label))
        return found

    def _ids(self) -> tuple[int | None, int | None]:
        if self.settings.vid is not None or self.settings.pid is not None:
            return self.settings.vid, self.settings.pid
        if len(self.device.match.usb) == 1:
            vid, pid = self.device.match.usb[0].split(":")
            return int(vid, 16), int(pid, 16)
        return None, None

    def _select(self, entries: list[dict[str, Any]]) -> dict[str, Any]:
        s = self.settings
        vid, pid = self._ids()
        chosen = []
        for entry in entries:
            path = entry.get("path", b"")
            text = path.decode("utf-8", "replace") if isinstance(path, bytes) else str(path)
            if s.path is not None and text != s.path:
                continue
            if vid is not None and entry.get("vendor_id") != vid:
                continue
            if pid is not None and entry.get("product_id") != pid:
                continue
            if s.serial is not None and entry.get("serial_number") != s.serial:
                continue
            if s.usage_page is not None and entry.get("usage_page") != s.usage_page:
                continue
            if s.interface is not None and entry.get("interface_number") != s.interface:
                continue
            product = str(entry.get("product_string") or "")
            if s.name != "auto" and s.name.lower() not in product.lower():
                continue
            chosen.append(entry)
        if len(chosen) != 1:
            listing = ", ".join(
                f"{e.get('vendor_id', 0):04x}:{e.get('product_id', 0):04x} {e.get('product_string') or ''}".strip()
                for e in chosen
            )
            raise DriverError(
                f"{len(chosen)} HID interfaces match ({listing or 'none'}). Set vid and pid, or narrow name, "
                "serial, usage_page or interface."
            )
        return chosen[0]

    async def connect(self) -> None:
        await self.close()
        entries = await asyncio.to_thread(self.hid.enumerate)
        entry = self._select(entries)
        handle = self.hid.device()
        try:
            await asyncio.to_thread(handle.open_path, entry["path"])
        except (OSError, ValueError) as exc:
            raise DriverError(
                f"Could not open the HID device ({exc}). Another program may hold it, or on Linux your user "
                "needs a udev rule for it."
            ) from None
        self._device, self._info = handle, entry
        self._error = ""
        self._stop.clear()
        with self._lock:
            self._latest.clear()
        if any(hmap.kind == "input" for hmap in self.maps.values()):
            self._reader = threading.Thread(target=self._read_loop, name="openhal-hid-reader", daemon=True)
            self._reader.start()

    def _read_loop(self) -> None:
        handle = self._device
        while not self._stop.is_set():
            try:
                data = handle.read(self.settings.report_length + 1, 100)
            except (OSError, ValueError) as exc:
                self._error = f"the device stopped answering ({exc})"
                return
            if not data:
                continue
            report = bytes(data)
            report_id = report[0] if self._uses_ids else 0
            payload = report[1:] if self._uses_ids else report
            with self._lock:
                self._latest[report_id] = (payload, time.time())

    async def close(self) -> None:
        self._stop.set()
        reader, self._reader = self._reader, None
        if reader is not None:
            await asyncio.to_thread(reader.join, 1.0)
        handle, self._device = self._device, None
        if handle is not None:
            with contextlib.suppress(OSError, ValueError):
                await asyncio.to_thread(handle.close)

    @property
    def connected(self) -> bool:
        """True while the device is open and the reader has seen no failure."""
        return self._device is not None and not self._error

    async def health(self) -> Health:
        if self._device is None:
            return Health(connected=False, detail="HID device is not open")
        if self._error:
            return Health(connected=False, detail=f"HID device {self._error}")
        try:
            await asyncio.to_thread(self._device.get_product_string)
        except (OSError, ValueError) as exc:
            return Health(connected=False, detail=f"HID device is gone ({exc})")
        return Health(connected=True, detail=str(self._info.get("product_string") or "HID device"))

    async def identify(self) -> dict[str, str]:
        if self._device is None:
            vid, pid = self._ids()
            identity = {"name": self.settings.name}
            if vid is not None and pid is not None:
                identity["usb"] = f"{vid:04x}:{pid:04x}"
            return identity
        identity = {"usb": f"{self._info.get('vendor_id', 0):04x}:{self._info.get('product_id', 0):04x}"}
        for key, getter in (
            ("manufacturer", "get_manufacturer_string"),
            ("product", "get_product_string"),
            ("serial", "get_serial_number_string"),
        ):
            try:
                value = await asyncio.to_thread(getattr(self._device, getter))
            except (OSError, ValueError):
                continue
            if value:
                identity[key] = str(value)[:120]
        return identity

    # ------------------------------------------------------------------ decoding

    def _extract(self, payload: bytes, hmap: HidMap) -> int:
        chunk = payload[hmap.byte : hmap.end]
        if len(chunk) < _SIZE[hmap.format]:
            raise ValueError(f"the report has {len(payload)} bytes, the map reads up to byte {hmap.end}")
        order = "<" if hmap.byteorder == "little" else ">"
        raw = struct.unpack(order + _STRUCT[hmap.format], chunk)[0]
        if hmap.mask is None:
            return int(raw)
        unsigned = int.from_bytes(chunk, hmap.byteorder)
        return (unsigned & hmap.mask) >> hmap.shift()

    def _value(self, channel: str, raw: int, hmap: HidMap) -> float | bool | str:
        kind, allowed = self._kind(channel)
        if kind == "bool":
            return raw != hmap.off
        if kind == "enum":
            names = [name for name in allowed if hmap.values[name] == raw]
            if not names:
                raise DriverError(f"{channel} read raw value {raw}, which is not in its values map.")
            return names[0]
        return raw * hmap.scale + hmap.offset

    def _kind(self, channel: str) -> tuple[str, list[str]]:
        if channel in self.device.read:
            return self.device.read[channel].type, self.device.read[channel].values
        return self.device.write[channel].type, self.device.write[channel].values

    # ------------------------------------------------------------------ reads

    def _require(self) -> Any:
        if self._device is None:
            raise DriverError("The HID device is not open.")
        if self._error:
            raise DriverError(f"The HID device {self._error}. The hub will reopen it.")
        return self._device

    async def read(self, channel: str) -> Reading:
        hmap = self.maps.get(channel)
        if hmap is None:
            raise DriverError(f"This hid device has no channel {channel!r}.")
        handle = self._require()
        unit = self.device.channel_unit(channel)
        if channel in self.device.write and hmap.kind == "output":
            return Reading(channel, self._written.get(channel), unit=unit)
        if hmap.kind == "feature":
            try:
                data = await asyncio.wait_for(
                    asyncio.to_thread(handle.get_feature_report, hmap.report, self.settings.report_length + 1),
                    self.settings.timeout,
                )
            except TimeoutError:
                raise TimeoutError(f"The HID device didn't answer the feature report {hmap.report} request.") from None
            except (OSError, ValueError) as exc:
                raise DriverError(f"Reading feature report {hmap.report} failed ({exc}).") from None
            payload, at = bytes(data)[1:], time.time()
        else:
            with self._lock:
                latest = self._latest.get(hmap.report)
            if latest is None:
                return Reading(channel, None, unit=unit)
            payload, at = latest
        try:
            raw = self._extract(payload, hmap)
        except ValueError as exc:
            raise DriverError(f"{channel} can't be decoded, {exc}.") from None
        value = self._value(channel, raw, hmap)
        spec = self.device.read.get(channel)
        suspect = bool(
            spec is not None
            and spec.range is not None
            and isinstance(value, float)
            and not spec.range[0] <= value <= spec.range[1]
        )
        return Reading(channel, value, unit=unit, at=at, suspect=suspect)

    # ------------------------------------------------------------------ writes

    def _raw(self, channel: str, value: float | bool | str, hmap: HidMap) -> tuple[int, float | bool | str]:
        kind, _ = self._kind(channel)
        if kind == "bool":
            on = hmap.on if hmap.on is not None else 1
            return (on if value else hmap.off), bool(value)
        if kind == "enum":
            return hmap.values[str(value)], str(value)
        raw = round((float(value) - hmap.offset) / hmap.scale)
        return raw, raw * hmap.scale + hmap.offset

    def _place(self, buffer: bytearray, raw: int, hmap: HidMap) -> None:
        size = _SIZE[hmap.format]
        width = hmap.bits() >> hmap.shift()
        signed = hmap.format.startswith("int") and hmap.mask is None
        low, high = (-(1 << (8 * size - 1)), (1 << (8 * size - 1)) - 1) if signed else (0, width)
        if not low <= raw <= high:
            raise DriverError(f"{raw} doesn't fit in the field ({low} to {high}).")
        if hmap.mask is None:
            order = "<" if hmap.byteorder == "little" else ">"
            buffer[hmap.byte : hmap.end] = struct.pack(order + _STRUCT[hmap.format], raw)
            return
        current = int.from_bytes(buffer[hmap.byte : hmap.end], hmap.byteorder)
        updated = (current & ~hmap.mask) | ((raw << hmap.shift()) & hmap.mask)
        buffer[hmap.byte : hmap.end] = updated.to_bytes(size, hmap.byteorder)

    async def _write(self, channel: str, value: float | bool | str) -> Reading | None:
        hmap = self.maps.get(channel)
        if hmap is None or channel not in self.device.write:
            raise DriverError(f"This hid device has no write channel {channel!r}.")
        handle = self._require()
        raw, sent = self._raw(channel, value, hmap)
        buffer = self._buffers[(hmap.kind, hmap.report)]
        candidate = bytearray(buffer)
        self._place(candidate, raw, hmap)
        report = bytes([hmap.report]) + bytes(candidate)
        sender = handle.write if hmap.kind == "output" else handle.send_feature_report
        try:
            result = await asyncio.wait_for(asyncio.to_thread(sender, report), self.settings.timeout)
        except TimeoutError:
            raise TimeoutError(f"The HID device didn't take {hmap.kind} report {hmap.report} in time.") from None
        except (OSError, ValueError) as exc:
            raise DriverError(f"Sending {hmap.kind} report {hmap.report} failed ({exc}).") from None
        if isinstance(result, int) and result < 0:
            raise DriverError(
                f"The HID device refused {hmap.kind} report {hmap.report}. Check the report id and length."
            )
        buffer[:] = candidate
        self._written[channel] = sent
        return Reading(channel, sent, unit=self.device.channel_unit(channel))

    # ------------------------------------------------------------------ describe

    async def describe(self) -> dict[str, Any] | None:
        if self._device is None:
            return None
        getter: Callable[..., Any] | None = getattr(self._device, "get_report_descriptor", None)
        if getter is None:
            return {"notes": "This hidapi version can't read report descriptors. Map the reports by hand."}
        try:
            raw = bytes(await asyncio.to_thread(getter, 4096))
            parsed = descriptor.parse(raw)
        except (OSError, ValueError) as exc:
            return {"notes": f"The report descriptor could not be read ({exc}). Map the reports by hand."}
        result = descriptor.propose(parsed)
        vid, pid = self._info.get("vendor_id", 0), self._info.get("product_id", 0)
        result["match"] = {"usb": [f"{vid:04x}:{pid:04x}"], "usb_class": "hid"}
        product = self._info.get("product_string")
        if product:
            device: dict[str, str] = {"name": str(product)[:120]}
            if self._info.get("manufacturer_string"):
                device["manufacturer"] = str(self._info["manufacturer_string"])[:120]
            result["device"] = device
        return result
