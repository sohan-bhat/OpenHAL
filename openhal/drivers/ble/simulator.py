"""A fake BLE peripheral and a fake BleakClient and BleakScanner that talk to it. No radio.

The fake implements exactly the bleak calls the driver uses: `connect`, `disconnect`,
`is_connected`, `services` (iterable services with `uuid` and `characteristics`, and
`get_characteristic`), `read_gatt_char`, `write_gatt_char`, `start_notify`, `stop_notify`, the
`disconnected_callback`, and `BleakScanner.discover(return_adv=True)`.

The simulated peripheral is a room sensor with the standard Environmental Sensing service
(temperature 0x2A6E, humidity 0x2A6F, pressure 0x2A6D), the Battery service (0x2A19), Device
Information (0x2A29, 0x2A24, 0x2A26), and a vendor service with a writable LED brightness
characteristic and a writable mode byte.

Fault injection. `drop()` disconnects and calls the disconnected callback, `delay_s` makes every
GATT operation slow, `fail_reads` makes reads raise, and `refuse_connect` makes connect fail.
"""

from __future__ import annotations

import asyncio
import struct
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from bleak.exc import BleakError

BASE = "-0000-1000-8000-00805f9b34fb"
VENDOR_SERVICE = "6e400001-b5a3-f393-e0a9-e50e24dcca9e"
LED_CHAR = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"
MODE_CHAR = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"
SECRET_CHAR = "6e400004-b5a3-f393-e0a9-e50e24dcca9e"  # noqa: S105 (a UUID)


def uuid16(short: str) -> str:
    return f"0000{short.lower()}{BASE}"


class FakeError(BleakError):
    """The errors bleak raises, so the driver handles fake and real failures the same way."""


@dataclass
class FakeCharacteristic:
    uuid: str
    properties: list[str]
    handle: int
    value: bytes = b""
    description: str = ""


@dataclass
class FakeService:
    uuid: str
    characteristics: list[FakeCharacteristic]
    description: str = ""


@dataclass
class FakePeripheral:
    """The device. Values live here and outlive any one connection."""

    address: str = "C0:FF:EE:00:00:01"
    name: str = "ENV-desk"
    temperature_c: float = 22.5
    humidity: float = 40.0
    pressure_pa: float = 101325.0
    battery: int = 87
    delay_s: float = 0.0
    fail_reads: bool = False
    refuse_connect: bool = False
    writes: list[tuple[str, bytes, bool]] = field(default_factory=list)
    connections: int = 0
    services: list[FakeService] = field(default_factory=list)
    client: FakeBleakClient | None = None

    def __post_init__(self) -> None:
        handle = iter(range(10, 1000))
        self.services = [
            FakeService(
                uuid16("181a"),
                [
                    FakeCharacteristic(uuid16("2a6e"), ["read", "notify"], next(handle)),
                    FakeCharacteristic(uuid16("2a6f"), ["read", "notify"], next(handle)),
                    FakeCharacteristic(uuid16("2a6d"), ["read"], next(handle)),
                ],
                "Environmental Sensing",
            ),
            FakeService(uuid16("180f"), [FakeCharacteristic(uuid16("2a19"), ["read", "notify"], next(handle))]),
            FakeService(
                uuid16("180a"),
                [
                    FakeCharacteristic(uuid16("2a29"), ["read"], next(handle), b"OpenHAL Labs"),
                    FakeCharacteristic(uuid16("2a24"), ["read"], next(handle), b"ENV-1"),
                    FakeCharacteristic(uuid16("2a26"), ["read"], next(handle), b"3.2.0"),
                ],
            ),
            FakeService(
                VENDOR_SERVICE,
                [
                    FakeCharacteristic(LED_CHAR, ["read", "write"], next(handle), b"\x00"),
                    FakeCharacteristic(MODE_CHAR, ["read", "write-without-response"], next(handle), b"\x00"),
                    FakeCharacteristic(SECRET_CHAR, ["write"], next(handle)),
                ],
            ),
        ]
        self.refresh()

    def characteristic(self, uuid: str) -> FakeCharacteristic | None:
        for service in self.services:
            for char in service.characteristics:
                if char.uuid == uuid.lower():
                    return char
        return None

    def refresh(self) -> None:
        """Encode the physical values into their characteristics, as the firmware would."""
        values = {
            "2a6e": struct.pack("<h", round(self.temperature_c * 100)),
            "2a6f": struct.pack("<H", round(self.humidity * 100)),
            "2a6d": struct.pack("<I", round(self.pressure_pa * 10)),
            "2a19": bytes([self.battery]),
        }
        for short, data in values.items():
            char = self.characteristic(uuid16(short))
            assert char is not None
            char.value = data

    def notify(self, uuid: str, data: bytes | None = None) -> None:
        """Send a notification for a characteristic to the connected client."""
        char = self.characteristic(uuid)
        assert char is not None
        if data is not None:
            char.value = data
        if self.client is not None:
            self.client.deliver(char)

    def drop(self) -> None:
        """The link goes away, as when the device walks out of range."""
        if self.client is not None:
            self.client.lost()


class FakeBleakClient:
    """Implements the subset of bleak.BleakClient the driver calls."""

    def __init__(
        self,
        peripheral: FakePeripheral,
        address_or_ble_device: Any,
        disconnected_callback: Callable[[Any], None] | None = None,
        *,
        timeout: float = 10.0,
        **_: Any,
    ) -> None:
        self.peripheral = peripheral
        self.address = getattr(address_or_ble_device, "address", address_or_ble_device)
        self._disconnected_callback = disconnected_callback
        self.timeout = timeout
        self.is_connected = False
        self._callbacks: dict[str, Callable[[Any, bytearray], Any]] = {}

    @property
    def services(self) -> list[FakeService]:
        if not self.is_connected:
            raise FakeError("Service discovery has not been performed yet")
        return self.peripheral.services

    async def _wait(self) -> None:
        if self.peripheral.delay_s:
            await asyncio.sleep(self.peripheral.delay_s)

    async def connect(self, **_: Any) -> None:
        await self._wait()
        if self.peripheral.refuse_connect or self.address.upper() != self.peripheral.address.upper():
            raise FakeError(f"Device with address {self.address} was not found.")
        self.is_connected = True
        self.peripheral.client = self
        self.peripheral.connections += 1

    async def disconnect(self) -> None:
        self.is_connected = False
        self._callbacks.clear()
        if self.peripheral.client is self:
            self.peripheral.client = None

    def lost(self) -> None:
        self.is_connected = False
        self._callbacks.clear()
        self.peripheral.client = None
        if self._disconnected_callback is not None:
            self._disconnected_callback(self)

    def _char(self, specifier: Any) -> FakeCharacteristic:
        if not self.is_connected:
            raise FakeError("Not connected")
        uuid = getattr(specifier, "uuid", specifier)
        char = self.peripheral.characteristic(str(uuid))
        if char is None:
            raise FakeError(f"Characteristic {uuid} was not found!")
        return char

    async def read_gatt_char(self, specifier: Any, **_: Any) -> bytearray:
        await self._wait()
        char = self._char(specifier)
        if self.peripheral.fail_reads:
            raise FakeError("Read failed, error 0x0e (unlikely error)")
        if "read" not in char.properties:
            raise FakeError("Read not permitted")
        return bytearray(char.value)

    async def write_gatt_char(self, specifier: Any, data: Any, response: bool | None = None) -> None:
        await self._wait()
        char = self._char(specifier)
        if response is True:
            allowed = "write" in char.properties
        elif response is False:
            allowed = "write-without-response" in char.properties
        else:
            allowed = "write" in char.properties or "write-without-response" in char.properties
        if not allowed:
            raise FakeError("Write not permitted")
        char.value = bytes(data)
        self.peripheral.writes.append((char.uuid, bytes(data), bool(response)))

    async def start_notify(self, specifier: Any, callback: Callable[[Any, bytearray], Any], **_: Any) -> None:
        await self._wait()
        char = self._char(specifier)
        if "notify" not in char.properties and "indicate" not in char.properties:
            raise FakeError("Notify not permitted")
        self._callbacks[char.uuid] = callback

    async def stop_notify(self, specifier: Any) -> None:
        char = self._char(specifier)
        self._callbacks.pop(char.uuid, None)

    def deliver(self, char: FakeCharacteristic) -> None:
        callback = self._callbacks.get(char.uuid)
        if callback is not None:
            callback(char, bytearray(char.value))


@dataclass
class FakeDevice:
    address: str
    name: str | None


@dataclass
class FakeAdvertisement:
    local_name: str | None
    service_uuids: list[str]
    rssi: int = -60


class FakeScanner:
    """Implements BleakScanner.discover(timeout, return_adv=True) over a list of peripherals."""

    def __init__(self, *peripherals: FakePeripheral) -> None:
        self.peripherals = list(peripherals)

    async def discover(self, timeout: float = 5.0, *, return_adv: bool = False, **_: Any) -> Any:  # noqa: ASYNC109
        found = {
            p.address: (FakeDevice(p.address, p.name), FakeAdvertisement(p.name, [uuid16("181a")]))
            for p in self.peripherals
        }
        if return_adv:
            return found
        return [device for device, _ in found.values()]


def client_factory(peripheral: FakePeripheral) -> Callable[..., FakeBleakClient]:
    """A drop-in for bleak.BleakClient that connects to `peripheral`."""

    def make(address_or_ble_device: Any, disconnected_callback: Any = None, **kwargs: Any) -> FakeBleakClient:
        return FakeBleakClient(peripheral, address_or_ble_device, disconnected_callback, **kwargs)

    return make
