"""The PyLabRobot driver's conformance case, on the recording chatterbox backend."""

from __future__ import annotations

from openhal.conformance import ConformanceCase
from openhal.drivers.base import Driver
from openhal.drivers.pylabrobot.driver import PyLabRobotDriver
from openhal.spec import loads
from openhal.spec.models import DeviceFile

FILE = loads(
    """
device: Simulated liquid handler
id: pylabrobot-sim
connect:
  pylabrobot: chatterbox
  num_channels: 8
  action_wait: 1 s
  layout:
    - { name: tips, resource: hamilton_96_tiprack_1000uL_filter, rails: 3 }
    - { name: plate, resource: cor_96_wellplate_360uL_Fb, rails: 9 }
read:
  initialized: { type: bool }
  tips_mounted: { unit: dimensionless, range: [0, 8] }
  a1_volume: { unit: uL, map: { container: "plate:A1" } }
actions:
  initialize: { confirm: confirm-each-time }
  pick_up_tips: { args: { tips: { type: enum, values: ["tips:A1", "tips:A1:H1"] } }, confirm: confirm-each-time }
  return_tips: { confirm: confirm-each-time }
hazard: high
confirmed: { by: conformance, at: 2026-10-24 }
"""
)


def case() -> ConformanceCase:
    def make(file: DeviceFile) -> Driver:
        return PyLabRobotDriver(file)

    async def broken(driver: Driver) -> None:
        assert isinstance(driver, PyLabRobotDriver)
        driver.backend.lost = True

    return ConformanceCase(name="pylabrobot", file=FILE, make=make, break_connection=broken)
