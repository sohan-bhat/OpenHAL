"""The driver catalog claims only what the tests back.

A driver listed as implemented (tested on simulator) has a simulator in its package, a conformance
case the suite runs, and tests of its own. Anything less is planned. The README and the website
count drivers from drivers/catalog.json, and the reference driver (tier 0) is never counted.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

from openhal.drivers import registry

ROOT = Path(__file__).resolve().parents[2]
CATALOG = json.loads((ROOT / "drivers" / "catalog.json").read_text(encoding="utf-8"))["drivers"]
TEST = re.compile(r"^(?:async )?def test_", re.M)
MIN_TESTS = 10


def _package(entry: dict[str, Any]) -> Path:
    return ROOT / "openhal" / "drivers" / entry["name"].replace("-", "_")


def _own_tests(entry: dict[str, Any]) -> int:
    package = entry["name"].replace("-", "_")
    folder = ROOT / "tests" / "drivers"
    files = [*(folder / package).glob("test_*.py"), folder / f"test_{package}.py"]
    return sum(len(TEST.findall(path.read_text(encoding="utf-8"))) for path in files if path.is_file())


DEVICE_DRIVERS = [entry for entry in CATALOG if entry["tier"] >= 1]


@pytest.mark.parametrize("entry", DEVICE_DRIVERS, ids=lambda entry: entry["name"])
def test_an_implemented_driver_has_a_simulator_a_conformance_case_and_tests(entry: dict[str, Any]) -> None:
    if entry["status"] == "planned":
        return
    package = _package(entry)
    assert (package / "simulator.py").is_file(), f"{entry['name']} is listed as {entry['status']} with no simulator"
    assert (package / "conformance.py").is_file(), f"{entry['name']} has no conformance case"
    assert entry["name"] in registry.names()
    assert _own_tests(entry) >= MIN_TESTS, f"{entry['name']} has fewer than {MIN_TESTS} tests of its own"


def test_no_device_driver_claims_hardware_verification_without_a_report() -> None:
    reports = ROOT / "docs" / "hardware-tests" / "reports"
    for entry in DEVICE_DRIVERS:
        if entry["status"] == "verified":
            assert any(reports.glob(f"{entry['name']}-*.md")), f"{entry['name']} is verified with no report"


def test_the_readme_counts_device_drivers_only() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    rows = re.findall(r"^\| `([a-z0-9-]+)` \|", readme, re.M)
    listed = {entry["name"] for entry in DEVICE_DRIVERS if entry["status"] != "planned"}
    assert set(rows) == listed
    assert "mock" not in rows


STATUS_WORDS = {"implemented": "tested on simulator", "verified": "verified on hardware", "planned": "planned"}


def test_the_coverage_plan_shows_the_catalog_status() -> None:
    coverage = (ROOT / "docs" / "drivers" / "COVERAGE.md").read_text(encoding="utf-8")
    statuses = {entry["name"]: STATUS_WORDS.get(entry["status"], entry["status"]) for entry in DEVICE_DRIVERS}
    seen = set()
    for line in coverage.splitlines():
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if cells and cells[0] in statuses:
            seen.add(cells[0])
            assert statuses[cells[0]] in cells, (
                f"COVERAGE.md shows {cells[0]} as {cells}, the catalog says {statuses[cells[0]]}"
            )
    assert seen == set(statuses), f"COVERAGE.md is missing {sorted(set(statuses) - seen)}"
