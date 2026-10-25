"""openhal-firmware discovery probes the ports in OPENHAL_FIRMWARE_PORTS, simulated boards included."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from openhal.drivers.openhal_firmware import driver
from openhal.drivers.openhal_firmware.driver import PORTS_ENV, OpenHalFirmwareDriver, discovery_ports
from openhal.drivers.openhal_firmware.protocol import decode
from openhal.drivers.openhal_firmware.simulator import SIMULATORS, PlantWatererSimulator, SimTransport
from openhal.hub.discovery import discover

NAMES = ("discovery-a", "discovery-b")


@pytest.fixture(autouse=True)
def no_usb(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """No test here may reach a real serial port."""
    monkeypatch.setattr(driver, "_board_ports", lambda: [("/dev/ttyACM9", "2341:0043")])
    monkeypatch.setattr(driver, "SerialLineTransport", _NoSerial)
    yield
    for name in NAMES:
        SIMULATORS.pop(name, None)


class _NoSerial:
    def __init__(self, port: str, baud: int) -> None:
        raise AssertionError(f"Discovery opened the serial port {port}.")


def test_the_port_list_defaults_to_known_usb_boards(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(PORTS_ENV, raising=False)
    assert discovery_ports() == [("/dev/ttyACM9", {"usb": "2341:0043"})]


def test_the_port_list_takes_auto_paths_urls_and_simulators(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(PORTS_ENV, " sim:discovery-a, auto,,socket://10.0.0.5:7000 , sim:discovery-a")
    assert discovery_ports() == [
        ("sim:discovery-a", {}),
        ("/dev/ttyACM9", {"usb": "2341:0043"}),
        ("socket://10.0.0.5:7000", {}),
    ]


async def test_a_listed_simulated_board_is_found_with_hello_only(monkeypatch: pytest.MonkeyPatch) -> None:
    board = SIMULATORS["discovery-a"] = PlantWatererSimulator()
    monkeypatch.setenv(PORTS_ENV, "sim:discovery-a")
    found = await OpenHalFirmwareDriver.discover()
    assert [(item.driver, item.address, item.identifiers, item.label) for item in found] == [
        (
            "openhal-firmware",
            "sim:discovery-a",
            {"firmware.product": "plant-waterer", "firmware.version": "1.0.0"},
            "OpenHAL board plant-waterer",
        )
    ]
    assert [decode(line).verb for line in board.received] == ["HELLO"]
    assert board.open_links == 0


async def test_a_board_another_link_holds_is_left_alone(monkeypatch: pytest.MonkeyPatch) -> None:
    board = SIMULATORS["discovery-a"] = PlantWatererSimulator()
    monkeypatch.setenv(PORTS_ENV, "sim:discovery-a")
    held = SimTransport(board)
    await held.connect()
    assert board.open_links == 1
    assert await OpenHalFirmwareDriver.discover() == []
    assert board.received == []
    await held.close()
    await held.close()
    assert board.open_links == 0
    assert len(await OpenHalFirmwareDriver.discover()) == 1


async def test_a_board_that_does_not_answer_is_skipped(monkeypatch: pytest.MonkeyPatch) -> None:
    SIMULATORS["discovery-a"] = PlantWatererSimulator(silent=True)
    SIMULATORS["discovery-b"] = PlantWatererSimulator(product="greenhouse")
    monkeypatch.setenv(PORTS_ENV, "sim:discovery-a,sim:discovery-b")
    found = await OpenHalFirmwareDriver.discover()
    assert [(item.address, item.identifiers["firmware.product"]) for item in found] == [
        ("sim:discovery-b", "greenhouse")
    ]


async def test_the_hub_lists_a_found_board_for_the_driver_writer(monkeypatch: pytest.MonkeyPatch) -> None:
    SIMULATORS["discovery-a"] = PlantWatererSimulator()
    monkeypatch.setenv(PORTS_ENV, "sim:discovery-a")
    result = await discover(["openhal-firmware"], library=[])
    assert result.errors == []
    assert result.matched == []
    assert [(item.driver, item.address) for item in result.unknown] == [("openhal-firmware", "sim:discovery-a")]
