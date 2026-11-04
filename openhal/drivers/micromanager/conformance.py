"""The micromanager driver's conformance case, against its own simulated microscope."""

from __future__ import annotations

from openhal.conformance import ConformanceCase
from openhal.drivers.base import Driver
from openhal.drivers.micromanager.driver import MicromanagerDriver
from openhal.drivers.micromanager.simulator import microscope_for
from openhal.spec import loads
from openhal.spec.models import DeviceFile

FILE = loads(
    """
device: Conformance microscope
id: conformance-microscope
connect: { micromanager: "sim:conformance", timeout: 2 s, action_wait: 2 s }
read:
  image: { type: image }
  pixel_size: { unit: um }
  busy: { type: bool }
write:
  x: { unit: um, min: -150, max: 150 }
  y: { unit: um, min: -110, max: 110 }
  z: { unit: um, min: 1000, max: 1650 }
  exposure: { unit: ms, min: 1, max: 1000 }
  objective:
    type: enum
    values: [20x Plan-Apochromat 0.8, 40x Plan-Apochromat 0.95, 63x Plan-Apochromat 1.4 Oil]
    map: { state: Objective }
  filter: { type: enum, values: [DAPI, GFP, DAPI-GFP, TRITC], map: { state: Filter } }
  shutter: { type: bool }
  light: { unit: percent, min: 0, max: 100, map: { device: LED, property: Intensity } }
actions:
  stop: {}
  move_xy:
    args: { x: { unit: um, min: -150, max: 150 }, y: { unit: um, min: -110, max: 110 } }
    effects: [x, y]
  autofocus:
    args: { span: { unit: um, min: 5, max: 100 } }
    effects: [z]
safe_state: { shutter: false }
hazard: medium
confirmed: { by: conformance, at: 2026-11-03 }
"""
)


def case() -> ConformanceCase:
    scope = microscope_for("conformance")

    def make(file: DeviceFile) -> Driver:
        return MicromanagerDriver(file)

    async def broken(driver: Driver) -> None:
        scope.unplug()
        await driver.health()
        scope.plug_in()

    async def slow(driver: Driver) -> None:
        scope.delay_s = 3.0

    async def cleanup() -> None:
        scope.delay_s = 0.0

    return ConformanceCase(
        name="micromanager", file=FILE, make=make, break_connection=broken, make_slow=slow, cleanup=cleanup
    )
