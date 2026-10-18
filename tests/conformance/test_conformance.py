"""Every registered driver with a conformance case must pass the suite."""

from __future__ import annotations

import importlib

import pytest

from openhal.conformance import run
from openhal.drivers import registry

CASES = {name: f"{registry.package_for(name)}.conformance" for name in registry.names() if registry.package_for(name)}


@pytest.mark.parametrize("name", sorted(CASES))
async def test_driver_passes_conformance(name: str) -> None:
    try:
        module = importlib.import_module(CASES[name])
    except ModuleNotFoundError as exc:
        pytest.fail(f"driver {name} has no conformance module ({exc.name}). Every driver needs one.")
    report = await run(module.case())
    failures = [f"{result.name}: {result.detail}" for result in report.results if not result.ok and not result.skipped]
    assert report.ok, "\n".join(failures)


async def test_suite_catches_a_driver_that_ignores_limits() -> None:
    """A driver whose file has no limits on a channel still can't take a write the kernel blocks."""
    from openhal.drivers.mock import conformance

    case = conformance.case()
    report = await run(case)
    names = [result.name for result in report.results]
    assert "write outside limits is blocked before the driver" in names
    assert "no write without a kernel grant" in names
    assert report.ok
