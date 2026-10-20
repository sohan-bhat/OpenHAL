"""Conformance case for the openhal-firmware driver, against the simulated desk fan board."""

from __future__ import annotations

from openhal.conformance import ConformanceCase
from openhal.drivers.base import Driver
from openhal.drivers.openhal_firmware.driver import OpenHalFirmwareDriver
from openhal.drivers.openhal_firmware.simulator import SIMULATORS
from openhal.spec import DeviceFile, loads

FILE = loads(
    """
device: Desk fan controller
id: firmware-fan
match:
  firmware: { product: conformance }
connect: { openhal-firmware: "sim:conformance", timeout_s: 0.3 }
read:
  temperature: { unit: degC, range: [-20, 80] }
write:
  fan_speed: { unit: percent, min: 0, max: 100, max_change_per_s: 20 }
safe_state: { fan_speed: 0 }
hazard: low
confirmed: { by: conformance, at: 2026-10-24 }
"""
)


async def _unplug(driver: Driver) -> None:
    """Close the simulated port underneath the driver, as pulling the cable would."""
    assert isinstance(driver, OpenHalFirmwareDriver)
    link = driver._link  # noqa: SLF001 (the test reaches under the driver on purpose)
    assert link is not None
    await link.transport.close()


async def _silence(driver: Driver) -> None:
    SIMULATORS["conformance"].silent = True


async def _cleanup() -> None:
    SIMULATORS.pop("conformance", None)


def _make(file: DeviceFile) -> Driver:
    return OpenHalFirmwareDriver(file)


def case() -> ConformanceCase:
    SIMULATORS.pop("conformance", None)
    return ConformanceCase(
        name="openhal-firmware",
        file=FILE,
        make=_make,
        break_connection=_unplug,
        make_slow=_silence,
        cleanup=_cleanup,
    )
