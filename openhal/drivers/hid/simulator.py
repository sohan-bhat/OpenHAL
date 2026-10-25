"""A fake hidapi module with a simulated USB HID macropad. No USB, no hardware.

The fake implements the cython-hidapi calls the driver uses: `enumerate()`, `device()`,
`open_path`, `open`, `read(max_length, timeout_ms)`, `write`, `get_feature_report`,
`send_feature_report`, the string getters, `get_report_descriptor` and `close`.

The macropad's reports, as its report descriptor (`DESCRIPTOR`) declares them.

| Report | Kind | Bytes after the id | Meaning |
|---|---|---|---|
| 1 | input | 0, bits 0 to 3 | buttons 1 to 4 |
| 1 | input | 1 | dial, 0 to 255 |
| 1 | input | 2 and 3 | slider, 0 to 1023, little-endian |
| 2 | output | 0, bits 0 to 2 | three LEDs |
| 2 | output | 1 | LED brightness, 0 to 255 |
| 3 | feature | 0 | mode byte |

Fault injection. `unplug()` makes every call fail as hidapi does when the device goes away, and
`silent` stops input reports.
"""

from __future__ import annotations

import queue
import threading
from dataclasses import dataclass, field
from typing import Any

VID, PID = 0x1209, 0x4D48
PATH = b"sim-hid-0001"

DESCRIPTOR = bytes.fromhex(
    "05010907a101"
    "8501"
    "05091901290415002501750195048102"
    "750495018103"
    "05010937150026ff00750895018102"
    "0936150026ff03751095018102"
    "8502"
    "05081901290315002501750195039102"
    "750595019103"
    "0600ff0901150026ff00750895019102"
    "8503"
    "0600ff0902150026ff0075089501b102"
    "c0"
)


@dataclass
class SimulatedMacropad:
    """The device. Inputs are queued as reports, outputs and features land here."""

    path: bytes = PATH
    vendor_id: int = VID
    product_id: int = PID
    serial: str = "MP-0001"
    manufacturer: str = "OpenHAL Labs"
    product: str = "Sim Macropad"
    buttons: int = 0
    dial: int = 0
    slider: int = 0
    mode: int = 1
    leds: int = 0
    brightness: int = 0
    plugged: bool = True
    silent: bool = False
    opened: bool = False
    writes: list[bytes] = field(default_factory=list)
    features: list[bytes] = field(default_factory=list)
    reports: queue.Queue[bytes] = field(default_factory=queue.Queue)

    def info(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "vendor_id": self.vendor_id,
            "product_id": self.product_id,
            "serial_number": self.serial,
            "release_number": 0x0100,
            "manufacturer_string": self.manufacturer,
            "product_string": self.product,
            "usage_page": 0x01,
            "usage": 0x07,
            "interface_number": 0,
        }

    def send_input(self) -> None:
        if not self.silent:
            self.reports.put(
                bytes([1, self.buttons & 0x0F, self.dial & 0xFF]) + (self.slider & 0xFFFF).to_bytes(2, "little")
            )

    def press(self, button: int) -> None:
        self.buttons |= 1 << (button - 1)
        self.send_input()

    def release(self, button: int) -> None:
        self.buttons &= ~(1 << (button - 1))
        self.send_input()

    def turn(self, dial: int | None = None, slider: int | None = None) -> None:
        if dial is not None:
            self.dial = dial
        if slider is not None:
            self.slider = slider
        self.send_input()

    def unplug(self) -> None:
        self.plugged = False

    def plug_in(self) -> None:
        self.plugged = True


class FakeHidDevice:
    """Stands in for `hid.device()`."""

    def __init__(self, module: FakeHid) -> None:
        self._module = module
        self._pad: SimulatedMacropad | None = None
        self._lock = threading.Lock()

    def _require(self) -> SimulatedMacropad:
        if self._pad is None:
            raise ValueError("not open")
        if not self._pad.plugged:
            raise OSError("read error")
        return self._pad

    def open_path(self, path: bytes) -> None:
        for pad in self._module.pads:
            if pad.path == path and pad.plugged:
                if pad.opened:
                    raise OSError("open failed")
                pad.opened = True
                self._pad = pad
                return
        raise OSError("open failed")

    def open(self, vendor_id: int = 0, product_id: int = 0, serial_number: str | None = None) -> None:
        for pad in self._module.pads:
            if (pad.vendor_id, pad.product_id) == (vendor_id, product_id) and serial_number in (None, pad.serial):
                self.open_path(pad.path)
                return
        raise OSError("open failed")

    def close(self) -> None:
        if self._pad is not None:
            self._pad.opened = False
        self._pad = None

    def read(self, max_length: int, timeout_ms: int = 0) -> list[int]:
        pad = self._require()
        try:
            report = pad.reports.get(timeout=max(timeout_ms, 0) / 1000) if timeout_ms else pad.reports.get_nowait()
        except queue.Empty:
            if not pad.plugged:
                raise OSError("read error") from None
            return []
        return list(report[:max_length])

    def write(self, data: Any) -> int:
        pad = self._require()
        payload = bytes(data)
        if payload[0] != 2 or len(payload) < 3:
            return -1
        pad.writes.append(payload)
        pad.leds, pad.brightness = payload[1] & 0x07, payload[2]
        return len(payload)

    def get_feature_report(self, report_num: int, max_length: int) -> list[int]:
        pad = self._require()
        if report_num != 3:
            raise OSError("get feature report failed")
        return [3, pad.mode][:max_length]

    def send_feature_report(self, data: Any) -> int:
        pad = self._require()
        payload = bytes(data)
        if payload[0] != 3 or len(payload) < 2:
            return -1
        pad.features.append(payload)
        pad.mode = payload[1]
        return len(payload)

    def get_manufacturer_string(self) -> str:
        return self._require().manufacturer

    def get_product_string(self) -> str:
        return self._require().product

    def get_serial_number_string(self) -> str:
        return self._require().serial

    def get_report_descriptor(self, max_length: int = 4096) -> list[int]:
        self._require()
        return list(DESCRIPTOR[:max_length])

    def error(self) -> str:
        return "simulated error"


class FakeHid:
    """Stands in for the `hid` module."""

    def __init__(self, *pads: SimulatedMacropad) -> None:
        self.pads = list(pads)

    def enumerate(self, vendor_id: int = 0, product_id: int = 0) -> list[dict[str, Any]]:
        return [
            pad.info()
            for pad in self.pads
            if pad.plugged and vendor_id in (0, pad.vendor_id) and product_id in (0, pad.product_id)
        ]

    def device(self) -> FakeHidDevice:
        return FakeHidDevice(self)
