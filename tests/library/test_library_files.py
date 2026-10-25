"""Every file in library/ is a starter file that a person still has to confirm (docs/guide/library.md)."""

from __future__ import annotations

from functools import cache
from pathlib import Path
from typing import Any, ClassVar

import pytest
import yaml

from openhal.drivers import registry
from openhal.drivers.base import Discovered, Driver, DriverInfo, Reading
from openhal.hub.discovery import discover, load_library, score
from openhal.spec import validate_path
from openhal.spec.models import DeviceFile
from tests.library.samples import KIND_KEYS, identifiers, specific_keys

ROOT = Path(__file__).resolve().parents[2]
LIBRARY = ROOT / "library"
FILES = sorted(LIBRARY.rglob("*.hal.yaml"))
NOTE = "Suggested limits. A person must confirm every limit before this device can be written."
PROVENANCE = {
    "source": "library",
    "by": "OpenHAL starter library",
    "at": "2026-10-25",
    "verification": {"status": "unverified"},
}
NO_MATCH_KEY = {
    "rpi-gpio": "discovery reports the Pi model, and match has no key for a board or a HAT",
    "rpi-camera": "discovery reports the libcamera sensor model, and match has no key for it",
    "alpaca": "discovery reports alpaca.* identifiers, and match has no alpaca section",
    "mqtt": "discovery finds nothing, and match has no key for MQTT topics",
}
"""Drivers whose discovery can't report anything a match key holds. Proposed spec changes are in the report."""


def name(path: Path) -> str:
    return str(path.relative_to(LIBRARY))


@cache
def load(path: Path) -> DeviceFile:
    report = validate_path(path)
    assert report.ok, report.problems
    assert report.file is not None
    return report.file


@pytest.fixture(scope="module")
def files() -> dict[Path, DeviceFile]:
    return {path: load(path) for path in FILES}


@cache
def raw(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def keys(data: Any) -> set[str]:
    if isinstance(data, dict):
        return {str(key) for key in data} | {item for value in data.values() for item in keys(value)}
    if isinstance(data, list):
        return {item for value in data for item in keys(value)}
    return set()


def test_the_library_has_at_least_30_files() -> None:
    assert len(FILES) >= 30


@pytest.mark.parametrize("path", FILES, ids=name)
def test_each_file_validates_and_constructs_its_driver(path: Path) -> None:
    file = load(path)
    driver = registry.load(file.connect.driver)(file)
    assert driver.device is file


@pytest.mark.parametrize("path", FILES, ids=name)
def test_each_file_lives_under_its_driver_package_and_is_named_by_its_id(path: Path) -> None:
    file = load(path)
    package = registry.package_for(file.connect.driver)
    assert package is not None
    assert path.parent.name == package.rsplit(".", 1)[-1]
    assert path.name == f"{file.device_id}.hal.yaml"
    assert file.id == file.device_id


@pytest.mark.parametrize("path", FILES, ids=name)
def test_each_file_loads_read_only_with_every_write_suggested(path: Path) -> None:
    file = load(path)
    assert "confirmed" not in keys(raw(path))
    unconfirmed = set(file.unconfirmed())
    for kind, entries in (("write", file.write), ("actions", file.actions)):
        for entry_name, entry in entries.items():
            assert entry.suggested, f"{kind}.{entry_name} is not suggested"
            assert entry.confirmed is None
            assert f"{kind}.{entry_name}" in unconfirmed
    if file.write or file.actions:
        assert not file.writable


@pytest.mark.parametrize("path", FILES, ids=name)
def test_each_file_has_library_provenance_notes_and_a_hazard(path: Path) -> None:
    file = load(path)
    assert file.provenance.model_dump(mode="json", by_alias=True, exclude_none=True) == PROVENANCE
    assert file.notes is not None
    assert file.notes.startswith(NOTE)
    assert file.hazard is not None


@pytest.mark.parametrize("path", FILES, ids=name)
def test_limits_are_numbers_in_the_channel_unit(path: Path) -> None:
    data = raw(path)
    specs = list(data.get("write", {}).values())
    specs += [arg for action in (data.get("actions") or {}).values() for arg in (action.get("args") or {}).values()]
    limits = [spec[key] for spec in specs for key in ("min", "max", "step", "max_change_per_s") if key in spec]
    assert all(type(value) in (int, float) for value in limits), limits


@pytest.mark.parametrize("path", FILES, ids=name)
def test_writes_on_medium_and_high_hazard_devices_need_a_person(path: Path) -> None:
    file = load(path)
    if file.effective_hazard == "low":
        return
    assert file.safe_state or file.safe_state_note
    if file.effective_hazard == "medium":
        quiet = [channel for channel, spec in file.write.items() if spec.confirm == "none"]
        assert not quiet, f"{quiet} need a confirmation tier"


def test_ids_are_unique(files: dict[Path, DeviceFile]) -> None:
    ids = [file.device_id for file in files.values()]
    assert len(ids) == len(set(ids))


@pytest.mark.parametrize("path", FILES, ids=name)
def test_each_file_has_a_product_identifier_unless_its_driver_cannot_report_one(path: Path) -> None:
    file = load(path)
    if file.connect.driver in NO_MATCH_KEY:
        assert not specific_keys(file.match), "this driver now reports identifiers, so drop it from NO_MATCH_KEY"
        return
    assert specific_keys(file.match), "match needs an identifier that names the product"


def test_every_driver_without_a_match_key_has_a_library_file(files: dict[Path, DeviceFile]) -> None:
    assert set(NO_MATCH_KEY) <= {file.connect.driver for file in files.values()}


def matchable(files: dict[Path, DeviceFile]) -> dict[Path, DeviceFile]:
    return {path: file for path, file in files.items() if file.connect.driver not in NO_MATCH_KEY}


def found_for(path: Path, file: DeviceFile) -> Discovered:
    return Discovered(file.connect.driver, f"synthetic://{name(path)}", identifiers(file.match), file.device.name)


def test_each_file_scores_highest_for_its_own_identifiers(files: dict[Path, DeviceFile]) -> None:
    for path, file in matchable(files).items():
        found = found_for(path, file)
        own = score(file, found)
        others = {name(other): score(entry, found) for other, entry in files.items() if other != path}
        best = max(others, key=lambda key: others[key])
        assert own > others[best], f"{name(path)} scores {own}, but {best} scores {others[best]}"


def test_kind_identifiers_alone_never_match(files: dict[Path, DeviceFile]) -> None:
    for path, file in files.items():
        kinds = {key: value for key, value in identifiers(file.match).items() if key in KIND_KEYS}
        found = Discovered(file.connect.driver, "synthetic://kind", kinds)
        assert all(score(entry, found) == 0 for entry in files.values()), name(path)


async def test_discovery_offers_each_library_file(
    files: dict[Path, DeviceFile], monkeypatch: pytest.MonkeyPatch
) -> None:
    by_driver: dict[str, list[Discovered]] = {}
    for path, file in matchable(files).items():
        by_driver.setdefault(file.connect.driver, []).append(found_for(path, file))

    def fake(driver_name: str) -> type[Driver]:
        class Finder(Driver):
            info: ClassVar[DriverInfo] = DriverInfo(
                name=driver_name, protocols=("test",), hazard_default="low", summary="test"
            )

            @classmethod
            async def discover(cls) -> list[Discovered]:
                return by_driver[driver_name]

            async def connect(self) -> None:  # pragma: no cover
                return None

            async def read(self, channel: str) -> Reading:  # pragma: no cover
                return Reading(channel, None)

            async def _write(self, channel: str, value: float | bool | str) -> Reading | None:  # pragma: no cover
                return None

        return Finder

    monkeypatch.setattr(registry, "load", fake)
    result = await discover(sorted(by_driver), library=load_library([LIBRARY]))
    assert result.errors == []
    assert result.unknown == []
    offered = {match.address: Path(match.library_file).name for match in result.matched}
    assert offered == {f"synthetic://{name(path)}": path.name for path in matchable(files)}
