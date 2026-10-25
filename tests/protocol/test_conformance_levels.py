"""Drivers declare a conformance level, and the suite tests that level and nothing above it."""

from __future__ import annotations

import json

import pytest

from openhal.conformance import run
from openhal.drivers import catalog, registry

CONTROL_CHECKS = {
    "write inside limits",
    "write outside limits is blocked before the driver",
    "no write without a kernel grant",
    "concurrent access",
    "safe state",
}


@pytest.mark.parametrize("name", ["uvc", "rpi-camera"])
def test_read_only_camera_drivers_are_core(name: str) -> None:
    assert registry.load(name).info.conformance == "core"


def test_other_drivers_default_to_control() -> None:
    for name in ("mock", "serial", "mqtt", "modbus"):
        assert registry.load(name).info.conformance == "control"


async def test_a_core_driver_is_tested_for_core_only() -> None:
    from openhal.drivers.uvc import conformance

    report = await run(conformance.case())
    assert report.level == "core"
    assert report.ok
    skipped = {result.name for result in report.results if result.skipped}
    assert skipped >= CONTROL_CHECKS
    for result in report.results:
        if result.name in CONTROL_CHECKS:
            assert result.detail == "above the declared core level"
    assert "(core)" in report.summary()


async def test_a_case_can_test_a_lower_level_than_the_driver_declares() -> None:
    from dataclasses import replace

    from openhal.drivers.mock import conformance

    report = await run(replace(conformance.case(), level="core"))
    names = {result.name for result in report.results if result.skipped}
    assert names >= CONTROL_CHECKS
    full = await run(conformance.case())
    assert full.level == "control"
    assert not {result.name for result in full.results if result.skipped} & CONTROL_CHECKS


def test_catalog_lists_each_drivers_conformance() -> None:
    document = json.loads(catalog.TARGET.read_text())
    levels = {entry["name"]: entry["conformance"] for entry in document["drivers"]}
    assert levels["uvc"] == "core"
    assert levels["rpi-camera"] == "core"
    assert levels["mock"] == "control"
    assert set(levels.values()) <= {"core", "control", "full"}


def test_catalog_prefers_a_declared_level() -> None:
    assert catalog.conformance_for({"name": "mock", "conformance": "full"}) == "full"
    assert catalog.conformance_for({"name": "not-a-driver"}) == catalog.DEFAULT_CONFORMANCE
