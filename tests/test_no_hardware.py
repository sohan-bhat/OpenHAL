"""The guard in tests/no_hardware.py hides every real device and the developer's own hub.

The plant waterer's file connects with `openhal-firmware: auto`, which opens the first board port
it finds. A test that loaded the file on a machine with a board plugged in could reset that board,
so the guard has to make `auto` find nothing.
"""

from __future__ import annotations

import errno
import os
import socket
from pathlib import Path
from types import SimpleNamespace

import pytest
import serial
from serial.tools import list_ports

from openhal._brand import DEFAULT_CONFIG_DIR, DEFAULT_PORT, config_dir
from openhal.client.settings import resolve_token, resolve_url
from openhal.drivers import registry
from openhal.drivers.base import DriverError
from openhal.drivers.openhal_firmware.driver import PORTS_ENV, OpenHalFirmwareDriver
from openhal.drivers.serial import link
from openhal.drivers.uvc.driver import UvcDriver
from openhal.spec import load, loads
from tests import no_hardware

ROOT = Path(__file__).resolve().parents[1]
PLANT_WATERER = ROOT / "examples" / "plant-waterer" / "plant-waterer.hal.yaml"
FAKE_BOARD = "/dev/cu.usbserial-guard"


@pytest.fixture
def board_plugged_in(monkeypatch: pytest.MonkeyPatch) -> str:
    """The OS lists a board on USB serial, as on a machine with a board plugged in."""
    listed = SimpleNamespace(device=FAKE_BOARD, vid=0x1A86, pid=0x7523)
    monkeypatch.setattr(no_hardware, "REAL_COMPORTS", lambda: [listed])
    return FAKE_BOARD


def test_serial_port_listing_finds_no_port() -> None:
    assert list_ports.comports() == []
    assert link.list_serial_ports() == []


async def test_the_plant_waterer_finds_no_board(monkeypatch: pytest.MonkeyPatch, board_plugged_in: str) -> None:
    monkeypatch.delenv(PORTS_ENV, raising=False)
    assert "openhal-firmware: auto" in PLANT_WATERER.read_text(encoding="utf-8")
    with pytest.raises(DriverError, match="No Arduino or ESP32 board was found"):
        await OpenHalFirmwareDriver(load(PLANT_WATERER)).connect()
    assert await OpenHalFirmwareDriver.discover() == []


@pytest.mark.parametrize("port", [FAKE_BOARD, FAKE_BOARD.replace("/dev/cu.", "/dev/tty.")])
def test_a_listed_port_never_opens(board_plugged_in: str, port: str) -> None:
    with pytest.raises(no_hardware.RealHardwareError, match="never open the real serial port"):
        serial.serial_for_url(port, baudrate=115200)


async def test_a_driver_given_a_real_port_fails_the_test(board_plugged_in: str) -> None:
    text = PLANT_WATERER.read_text(encoding="utf-8")
    file = loads(text.replace("openhal-firmware: auto", f'openhal-firmware: "{board_plugged_in}"'))
    with pytest.raises(no_hardware.RealHardwareError):
        await OpenHalFirmwareDriver(file).connect()


def test_a_pyserial_url_still_opens() -> None:
    port = serial.serial_for_url("loop://", timeout=0.1)
    try:
        port.write(b"ping")
        assert port.read(4) == b"ping"
    finally:
        port.close()


@pytest.mark.parametrize("name", [name for name in registry.names() if name != "mock"])
async def test_every_driver_discovers_nothing(name: str) -> None:
    try:
        driver = registry.load(name)
    except registry.UnknownDriver as error:
        if "optional dependency" not in str(error):
            raise
        pytest.skip(f"{name} needs an extra that isn't installed here")
    assert await driver.discover() == []


async def test_a_camera_set_to_auto_never_opens() -> None:
    file = loads(
        "device: Cam\nid: cam\nconnect: { uvc: auto, timeout: 60 }\nread:\n  frame: { type: image }\nhazard: low\n"
    )
    with pytest.raises(DriverError, match="Could not open camera 0"):
        await UvcDriver(file).connect()


def test_tests_never_see_the_real_hub() -> None:
    assert config_dir() != DEFAULT_CONFIG_DIR
    assert resolve_token().token is None
    assert resolve_url() == no_hardware.NO_HUB_URL
    assert os.environ["GPIOZERO_PIN_FACTORY"] == "mock"


def test_pymmcore_plus_logs_into_the_test_folder() -> None:
    log = Path(os.environ["PYMM_LOG_FILE"])
    assert log.parent == Path(os.environ["OPENHAL_HOME"]).parent
    assert not log.is_relative_to(Path.home())


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost"])
def test_a_test_never_connects_to_the_developers_own_hub(host: str) -> None:
    with socket.socket() as sock, pytest.raises(ConnectionRefusedError):
        sock.connect((host, DEFAULT_PORT))
    with socket.socket() as sock:
        assert sock.connect_ex((host, DEFAULT_PORT)) == errno.ECONNREFUSED


def test_other_ports_still_connect() -> None:
    with socket.socket() as server:
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        with socket.create_connection(server.getsockname(), timeout=2):
            pass
