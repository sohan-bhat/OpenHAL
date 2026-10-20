"""F12 (medium). A max_duration rule stops counting when its sensor goes quiet.

`tick` only fires on True and only resets on False. When the value becomes unknown the rule does
nothing, so a heater that was last seen over temperature runs on unprotected for as long as the
sensor stays silent. Unknown should never lead to a pass (spec section 7).
"""

from __future__ import annotations

from openhal.kernel import Kernel
from tests.kernel.conftest import AddDevice, FakeClock

OVEN = """
device: Oven
id: oven
connect: { mock: oven }
read:
  temp: { unit: degC }
write:
  power: { unit: W, min: 0, max: 500 }
safe_state: { power: 0 }
watchdog:
  max_duration:
    - when: "temp > 80 degC"
      for: 10 s
hazard: low
confirmed: { by: tester, at: 2026-10-24 }
"""


async def test_f12_rule_fires_when_value_goes_unknown(kernel: Kernel, add: AddDevice, clock: FakeClock) -> None:
    oven = await add(OVEN, settle=0, initial={"temp": 95.0, "power": 400.0})
    await kernel.tick()  # temp 95 degC is known, the 10 s budget starts
    oven.settings.fail_reads = True  # the sensor stops answering
    clock.advance(30)  # the reading is now stale, so temp is unknown
    fired = await kernel.tick()

    assert fired, "temp was last seen at 95 degC, 30 s ago, and the 10 s rule never fired"
