"""The mock driver's conformance case. Other drivers copy this shape."""

from __future__ import annotations

from openhal.conformance import ConformanceCase
from openhal.drivers.base import Driver
from openhal.drivers.mock.driver import MockDriver
from openhal.spec import loads

FILE = loads(
    """
device: Conformance fan
id: conformance-fan
connect: { mock: conformance, simulate: desk-fan }
read:
  temperature: { unit: degC }
write:
  fan_speed: { unit: percent, min: 0, max: 100, max_change_per_s: 50 }
  boost: { type: bool }
safe_state: { fan_speed: 0, boost: false }
hazard: low
confirmed: { by: conformance, at: 2026-10-24 }
"""
)


async def _break(driver: Driver) -> None:
    assert isinstance(driver, MockDriver)
    driver.connected = False


async def _slow(driver: Driver) -> None:
    assert isinstance(driver, MockDriver)
    driver.settings.latency_s = 5.0


def case() -> ConformanceCase:
    return ConformanceCase(name="mock", file=FILE, make=MockDriver, break_connection=_break, make_slow=_slow)
