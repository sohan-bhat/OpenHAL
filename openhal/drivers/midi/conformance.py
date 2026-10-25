"""The midi driver's conformance case, against the fake backend and simulated pad controller."""

from __future__ import annotations

from openhal.conformance import ConformanceCase
from openhal.drivers.base import Driver
from openhal.drivers.midi.driver import MidiDriver
from openhal.drivers.midi.simulator import FakeMidiBackend, SimulatedController
from openhal.spec import loads
from openhal.spec.models import DeviceFile

FILE = loads(
    """
device: { name: Conformance pads, model: LPD8, manufacturer: Akai }
id: conformance-midi
match: { usb_class: midi }
connect: { midi: "Sim Pads" }
read:
  knob_1: { unit: dimensionless, stream: true, range: [0, 127], map: { cc: 1 } }
  knob_2: { unit: percent, stream: true, map: { cc: 2 } }
  pad_1: { type: bool, stream: true, map: { note: 36 } }
write:
  pad_1_led: { type: bool, map: { note: 36 } }
  filter: { unit: percent, min: 0, max: 100, map: { cc: 74, channel: 2 } }
safe_state: { pad_1_led: false }
hazard: low
confirmed: { by: conformance, at: 2026-10-24 }
"""
)


class _Case:
    def __init__(self) -> None:
        self.controller = SimulatedController()

    def make(self, file: DeviceFile) -> Driver:
        return MidiDriver(file, backend=FakeMidiBackend(self.controller))

    async def break_connection(self, driver: Driver) -> None:
        self.controller.unplug()
        self.controller.plug_in()
        assert isinstance(driver, MidiDriver)
        await driver.close()


def case() -> ConformanceCase:
    state = _Case()
    return ConformanceCase(name="midi", file=FILE, make=state.make, break_connection=state.break_connection)
