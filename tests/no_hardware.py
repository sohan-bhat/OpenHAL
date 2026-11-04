"""No test reaches real hardware or the real hub.

A developer's machine can have a board on USB, a camera, MIDI and HID devices, a Bluetooth radio
and devices on the home network, and a hub of its own on port 7420. A test that finds any of these
could reset a board, move a motor or read the developer's own devices.

Every place a driver looks for real devices finds nothing during tests. That covers each driver's
`discover()` and each `auto` connection setting, such as `openhal-firmware: auto`. Tests that need
a device pass their own fake, a simulator or a temporary path, and those keep working. Opening a
real serial port, HID device, MIDI port, Bluetooth device or Raspberry Pi camera fails the test with
`RealHardwareError`.

`isolate_environment()` points the hub's home at a temporary folder and the hub address at a
loopback port nothing listens on, so a test, and every process a test starts, never reads the real
`~/.openhal`, never sends the developer's token and never reaches a running hub. A developer's own
OPENHAL_FIRMWARE_PORTS is cleared too, so no exported list of real boards reaches discovery, and
pymmcore-plus writes its log file into the temporary folder instead of the developer's data folder.
"""

from __future__ import annotations

import atexit
import functools
import glob
import importlib
import os
import pkgutil
import shutil
import tempfile
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

NO_HUB_URL = "http://127.0.0.1:9"
DRIVERS = "openhal.drivers"


class RealHardwareError(AssertionError):
    """A test tried to open a real device."""


def _refuse(what: str) -> Callable[..., Any]:
    def refuse(*args: object, **kwargs: object) -> Any:
        raise RealHardwareError(f"Tests never open {what}. Give the driver a fake or a simulator. Got {args}.")

    return refuse


def _nothing(*args: object, **kwargs: object) -> list[Any]:
    return []


async def _nothing_async(*args: object, **kwargs: object) -> list[Any]:
    return []


def _real(target: str) -> Any:
    module, _, name = target.rpartition(".")
    return getattr(importlib.import_module(module), name)


def _real_serial_lister() -> Callable[[], list[Any]]:
    try:
        from serial.tools import list_ports
    except ImportError:
        return _nothing
    lister: Callable[[], list[Any]] = list_ports.comports
    return lister


REAL_COMPORTS = _real_serial_lister()
"""pyserial's own port listing, kept before the guard replaces it. Listing never opens a port."""


def real_serial_ports() -> set[str]:
    """The serial ports the OS lists right now, with the /dev/tty twin of each macOS /dev/cu port, all resolved."""
    listed = {port.device for port in REAL_COMPORTS()}
    listed |= {name.replace("/dev/cu.", "/dev/tty.", 1) for name in listed}
    return {os.path.realpath(name) for name in listed}


def _serial_without_real_ports() -> Callable[..., Any]:
    real_open = _real("serial.serial_for_url")

    def open_port(url: str, *args: object, **kwargs: object) -> Any:
        if "://" not in url and os.path.realpath(url) in real_serial_ports():
            raise RealHardwareError(f"Tests never open the real serial port {url}. Use sim:, loop:// or a pty.")
        return real_open(url, *args, **kwargs)

    return open_port


def _no_visa_resources(self: object, session: object, query: str = "?*::INSTR") -> tuple[str, ...]:
    """pyvisa-py's listing, which finds no USB, serial or network instrument. A resource a test names still opens."""
    return ()


def _no_pi_cameras() -> Callable[[], Any]:
    real = _real(f"{DRIVERS}.rpi_camera.driver._picamera2_class")

    def picamera2_class() -> Any:
        real()
        return _NoPiCameras

    return picamera2_class


def _skip_real_path(module: str, function: str, constant: str, empty: Any) -> tuple[str, Callable[[], Any]]:
    """A row for a driver function that reads a system path. The real path finds nothing, a test's own path works."""

    def make() -> Callable[[Path], Any]:
        owner = importlib.import_module(module)
        real, path = getattr(owner, function), getattr(owner, constant)

        def wrapper(given: Path) -> Any:
            return empty if Path(given) == path else real(given)

        return wrapper

    return f"{module}.{function}", make


def _no_hid_devices() -> Any:
    return SimpleNamespace(enumerate=_nothing, device=_refuse("a HID device"), Device=_refuse("a HID device"))


def _no_midi_ports(name: str | None = None) -> Any:
    refuse = _refuse("a MIDI port")
    return SimpleNamespace(get_input_names=_nothing, get_output_names=_nothing, open_input=refuse, open_output=refuse)


def _no_dev_nodes() -> Any:
    return SimpleNamespace(glob=lambda pattern: [] if pattern.startswith("/dev/") else glob.glob(pattern))


class _NoAdvertisements:
    """A Bluetooth scanner that hears nothing."""

    @staticmethod
    async def discover(*args: object, **kwargs: object) -> dict[str, Any]:
        return {}


class _NoGateways:
    """A KNXnet/IP gateway search that finds nothing."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        pass

    async def scan(self) -> list[Any]:
        return []


class _NoPiCameras:
    """Picamera2 on a board with no camera."""

    @staticmethod
    def global_camera_info() -> list[Any]:
        return []

    def __init__(self, *args: object, **kwargs: object) -> None:
        _refuse("a Raspberry Pi camera")(*args)


class _ClosedCamera:
    """A cv2.VideoCapture that never opens."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        pass

    def isOpened(self) -> bool:  # noqa: N802 (cv2's method name)
        return False

    def release(self) -> None:
        pass


def _cv2_without_cameras() -> Any:
    import cv2

    return SimpleNamespace(**{**vars(cv2), "VideoCapture": _ClosedCamera})


PATCHES: tuple[tuple[str, Callable[[], Any]], ...] = (
    ("serial.tools.list_ports.comports", lambda: _nothing),
    ("serial.serial_for_url", _serial_without_real_ports),
    ("pyvisa_py.highlevel.PyVisaLibrary.list_resources", lambda: _no_visa_resources),
    ("can.detect_available_configs", lambda: _nothing),
    ("async_upnp_client.search.async_search", lambda: _nothing_async),
    ("xknx.io.GatewayScanner", lambda: _NoGateways),
    (f"{DRIVERS}.hid.driver._hid_module", lambda: _no_hid_devices),
    (f"{DRIVERS}.midi.driver._default_backend", lambda: _no_midi_ports),
    (f"{DRIVERS}.ble.driver._bleak_scanner", lambda: lambda: _NoAdvertisements),
    (f"{DRIVERS}.ble.driver._bleak_client", lambda: _refuse("a Bluetooth device")),
    (f"{DRIVERS}.uvc.driver._cv2", lambda: _cv2_without_cameras),
    _skip_real_path(f"{DRIVERS}.uvc.driver", "_scan_sysfs", "SYSFS", []),
    (f"{DRIVERS}.rpi_camera.driver._picamera2_class", _no_pi_cameras),
    _skip_real_path(f"{DRIVERS}.rpi_gpio.driver", "_board_model", "MODEL_FILE", None),
    (f"{DRIVERS}.pi_i2c_spi.driver.glob", _no_dev_nodes),
    (f"{DRIVERS}.esphome.driver._browse", lambda: _nothing_async),
    (f"{DRIVERS}.sila2.driver.Sila2Driver._browse", lambda: classmethod(_nothing_async)),
    (f"{DRIVERS}.alpaca.driver.AlpacaDriver.discovery_targets", lambda: []),
    (f"{DRIVERS}.onvif.discovery.GROUP", lambda: "127.0.0.1"),
    (f"{DRIVERS}.bambu.driver.DISCOVERY_S", lambda: 0.0),
    (f"{DRIVERS}.opcua.driver.OpcuaDriver.discovery_urls", lambda: []),
    (f"{DRIVERS}.indi.driver.IndiDriver.discovery_hosts", lambda: []),
    (f"{DRIVERS}.micromanager.driver._core_class", lambda: _refuse("a Micro-Manager configuration")),
    (f"{DRIVERS}.seabreeze.driver._list_devices", lambda: _nothing),
    (f"{DRIVERS}.seabreeze.driver._spectrometers", lambda: _refuse("a seabreeze spectrometer")),
)
"""Each place a driver finds or opens real devices, and what it gets during tests instead."""


@functools.cache
def _replacements() -> tuple[tuple[Any, str, Any], ...]:
    """Each owner, attribute and replacement, resolved once. A library that isn't installed has no devices to hide."""
    made = []
    for target, make in PATCHES:
        owner, _, name = target.rpartition(".")
        try:
            made.append((pkgutil.resolve_name(owner), name, make()))
        except ImportError:
            continue
    return tuple(made)


def guard(monkeypatch: pytest.MonkeyPatch) -> None:
    """Hide every real device for one test."""
    for owner, name, value in _replacements():
        monkeypatch.setattr(owner, name, value)


def isolate_environment() -> None:
    """Point the hub's home, token and address away from the developer's own, here and in child processes."""
    folder = Path(tempfile.mkdtemp(prefix="openhal-tests-"))
    atexit.register(shutil.rmtree, folder, ignore_errors=True)
    os.environ["OPENHAL_HOME"] = str(folder / "home")
    os.environ["OPENHAL_URL"] = NO_HUB_URL
    os.environ["GPIOZERO_PIN_FACTORY"] = "mock"
    os.environ["PYMM_LOG_FILE"] = str(folder / "pymmcore-plus.log")
    for name in ("OPENHAL_TOKEN", "OPENHAL_FIRMWARE_PORTS"):
        os.environ.pop(name, None)
