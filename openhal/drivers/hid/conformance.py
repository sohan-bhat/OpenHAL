"""The hid driver's conformance case, against the fake hidapi module and simulated macropad."""

from __future__ import annotations

import asyncio

from openhal.conformance import ConformanceCase
from openhal.drivers.base import Driver
from openhal.drivers.hid.driver import HidDriver
from openhal.drivers.hid.simulator import FakeHid, SimulatedMacropad
from openhal.spec import loads
from openhal.spec.models import DeviceFile

FILE = loads(
    """
device: { name: Conformance macropad, manufacturer: OpenHAL Labs }
id: conformance-hid
match: { usb: ["1209:4d48"], usb_class: hid }
connect: { hid: auto }
read:
  button_1: { type: bool, stream: true, map: { report: 1, byte: 0, mask: 0x01 } }
  button_4: { type: bool, stream: true, map: { report: 1, byte: 0, mask: 0x08 } }
  dial: { unit: percent, stream: true, map: { report: 1, byte: 1, scale: 0.392156862745098 } }
  slider: { unit: dimensionless, stream: true, range: [0, 1023], map: { report: 1, byte: 2, format: uint16 } }
write:
  led_1: { type: bool, map: { report: 2, kind: output, byte: 0, mask: 0x01, length: 2 } }
  led_3: { type: bool, map: { report: 2, kind: output, byte: 0, mask: 0x04, length: 2 } }
  brightness: { unit: dimensionless, min: 0, max: 255, step: 1, map: { report: 2, kind: output, byte: 1 } }
  mode:
    type: enum
    values: [quiet, normal, party]
    map: { report: 3, kind: feature, values: { quiet: 0, normal: 1, party: 2 } }
safe_state: { led_1: false, led_3: false, brightness: 0 }
hazard: low
confirmed: { by: conformance, at: 2026-10-24 }
"""
)


class _Case:
    def __init__(self) -> None:
        self.pad = SimulatedMacropad()
        self.pad.turn(dial=128, slider=512)

    def make(self, file: DeviceFile) -> Driver:
        return HidDriver(file, hid_module=FakeHid(self.pad))

    async def break_connection(self, driver: Driver) -> None:
        # Unplug and plug back in. The open handle stays dead until the driver reopens it.
        assert isinstance(driver, HidDriver)
        self.pad.unplug()
        for _ in range(100):
            if not driver.connected:
                break
            await asyncio.sleep(0.02)
        self.pad.plug_in()
        self.pad.turn()


def case() -> ConformanceCase:
    state = _Case()
    return ConformanceCase(name="hid", file=FILE, make=state.make, break_connection=state.break_connection)
