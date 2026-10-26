"""The devices init offers. Library matches and self-described boards, always read-only."""

from __future__ import annotations

import shutil
from collections.abc import Iterator
from pathlib import Path

import pytest

from openhal.demo.plant import example_file
from openhal.drivers import registry
from openhal.drivers.openhal_firmware.simulator import SIMULATORS
from openhal.hub import discovery
from openhal.service import devices
from openhal.spec.loader import load


@pytest.fixture(autouse=True)
def fresh_simulators() -> Iterator[None]:
    yield
    SIMULATORS.clear()


def test_host_and_port_split_for_network_drivers() -> None:
    assert registry.connect_params("esphome", "192.168.1.20:6053") == {"host": "192.168.1.20", "port": 6053}
    assert registry.connect_params("esphome", "kitchen.local") == {"host": "kitchen.local"}
    assert registry.connect_params("openhal-firmware", "sim:desk-fan") == {"port": "sim:desk-fan"}
    assert registry.connect_params("serial", "/dev/ttyUSB0") == {"port": "/dev/ttyUSB0"}


def test_existing_files_are_found_by_id_and_address(tmp_path: Path) -> None:
    folder = tmp_path / "devices"
    folder.mkdir()
    shutil.copy(example_file(), folder / "plant-waterer.hal.yaml")
    (folder / "broken.hal.yaml").write_text("device: [")
    existing = devices.Existing.scan(folder)
    assert existing.ids == {"plant-waterer"}
    assert existing.has("openhal-firmware", "sim:plant-waterer")
    assert not existing.has("openhal-firmware", "/dev/ttyACM0")
    existing.addresses.add(("esphome", "192.168.1.20"))
    assert existing.has("esphome", "192.168.1.20:6053")


def test_a_library_match_drops_every_confirmation(tmp_path: Path) -> None:
    library = tmp_path / "plant-waterer.hal.yaml"
    shutil.copy(example_file(), library)
    match = discovery.Match("/dev/ttyACM0", "openhal-firmware", {}, None, str(library), "plant-waterer", 4)
    offer = devices.from_library(match)
    assert offer.problem is None
    assert offer.data is not None
    assert "confirmed" not in offer.data
    assert offer.data["connect"] == {"openhal-firmware": "/dev/ttyACM0"}
    assert all(spec["suggested"] for spec in offer.data["actions"].values())
    assert offer.data["provenance"]["tool"] == "openhal init"
    missing = discovery.Match("/dev/ttyACM1", "openhal-firmware", {}, None, str(tmp_path / "gone.hal.yaml"), "x", 1)
    assert "didn't load" in (devices.from_library(missing).problem or "")


async def test_a_board_describes_itself() -> None:
    data = await devices.describe("openhal-firmware", "sim:desk-fan")
    assert data["device"] == "Desk fan"
    assert data["connect"] == {"openhal-firmware": "sim:desk-fan"}
    assert data["write"]["fan_speed"]["suggested"] is True
    assert data["provenance"] == {"source": "self-described", "tool": "openhal init"}


def test_save_picks_an_unused_id(tmp_path: Path) -> None:
    folder = tmp_path / "devices"
    existing = devices.Existing()
    offer = devices.Offer("openhal-firmware", "sim:desk-fan", "fan", "self-described")
    offer.data = {"openhal": "0.1", "device": "Desk fan", "connect": {"openhal-firmware": "sim:desk-fan"}}
    first = devices.save(offer, folder, existing)
    second = devices.save(offer, folder, existing)
    assert (first.name, second.name) == ("desk-fan.hal.yaml", "desk-fan-2.hal.yaml")
    assert load(second).device_id == "desk-fan-2"
    assert existing.ids == {"desk-fan", "desk-fan-2"}
    with pytest.raises(ValueError, match="no device file"):
        devices.save(devices.Offer("x", "y", "z", "unknown"), folder, existing)
