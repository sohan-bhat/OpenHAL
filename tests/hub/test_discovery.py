"""Discovery and library matching."""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from openhal.drivers import registry
from openhal.drivers.base import Discovered, DriverInfo, Reading
from openhal.drivers.mock import MockDriver
from openhal.hub.discovery import discover, load_library, score
from openhal.spec import loads

DESK_FAN_LIBRARY = """
device: Desk fan
id: desk-fan
match:
  firmware: { product: desk-fan }
connect: { mock: fan }
write:
  fan_speed: { unit: percent, min: 0, max: 100, suggested: true }
"""

PSU_LIBRARY = """
device: { name: Bench supply, model: DP832, manufacturer: Rigol }
id: bench-psu
match:
  usb: ["1ab1:0e11"]
  scpi_idn: "^RIGOL TECHNOLOGIES,DP832"
connect: { mock: psu }
read:
  v: { unit: V }
"""


class Finder(MockDriver):
    info: ClassVar[DriverInfo] = DriverInfo(name="mock", protocols=("t",), hazard_default="low", summary="t")

    @classmethod
    async def discover(cls) -> list[Discovered]:
        return [
            Discovered("mock", "usb://1", {"usb": "1AB1:0E11", "scpi_idn": "RIGOL TECHNOLOGIES,DP832,DP8B1,00.01"}),
            Discovered("mock", "usb://2", {"usb": "dead:beef"}, label="Mystery box"),
        ]

    async def read(self, channel: str) -> Reading:  # pragma: no cover
        return Reading(channel, 0.0)


def library(tmp_path: Path) -> list:  # type: ignore[type-arg]
    (tmp_path / "fan.hal.yaml").write_text(DESK_FAN_LIBRARY)
    (tmp_path / "psu.hal.yaml").write_text(PSU_LIBRARY)
    (tmp_path / "broken.hal.yaml").write_text("device: x\n")
    return load_library([tmp_path])


async def test_mock_discovery_matches_library(tmp_path: Path) -> None:
    result = await discover(["mock"], library=library(tmp_path))
    assert [item.device_id for item in result.matched] == ["desk-fan"]
    assert result.unknown == []


async def test_scoring_prefers_specific_identifiers(tmp_path: Path) -> None:
    entries = library(tmp_path)
    psu = next(file for _, file in entries if file.device_id == "bench-psu")
    strong = Discovered("mock", "x", {"usb": "1ab1:0e11", "scpi_idn": "RIGOL TECHNOLOGIES,DP832,1,2"})
    weak = Discovered("mock", "x", {"usb": "1ab1:0e11"})
    other_driver = Discovered("scpi", "x", {"usb": "1ab1:0e11"})
    assert score(psu, strong) > score(psu, weak) > 0
    assert score(psu, other_driver) == 0


async def test_unknown_devices_and_errors(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(
        registry,
        "load",
        lambda name: Finder if name == "mock" else (_ for _ in ()).throw(registry.UnknownDriver(f"no {name}")),
    )
    result = await discover(["mock", "ghost"], library=library(tmp_path))
    assert [item.device_id for item in result.matched] == ["bench-psu"]
    assert [item.label for item in result.unknown] == ["Mystery box"]
    assert result.errors == [{"driver": "ghost", "error": "no ghost"}]
    view = result.view()
    assert view["unknown"][0]["id"] == result.unknown[0].id


async def test_registered_devices_are_not_offered_again(tmp_path: Path) -> None:
    result = await discover(["mock"], library=library(tmp_path), registered={"desk-fan"})
    assert result.matched == []


def test_library_loader_skips_duplicates(tmp_path: Path) -> None:
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    (tmp_path / "a" / "fan.hal.yaml").write_text(DESK_FAN_LIBRARY)
    (tmp_path / "b" / "fan.hal.yaml").write_text(DESK_FAN_LIBRARY)
    assert len(load_library([tmp_path / "a", tmp_path / "b"])) == 1
    assert loads(DESK_FAN_LIBRARY).writable is False
