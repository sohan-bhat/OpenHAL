"""F17 (medium). A cross-device reference to a device that is not registered silently disables an interlock.

The fan file says "while the fan is below 30 %, the heater must be off", but misspells the
heater's id. Nothing rejects the reference, and because the interlock never "touches" writes to
the real heater, the heater can be switched on with the fan stopped.
"""

from __future__ import annotations

from openhal.kernel import Kernel, Write, agent
from tests.kernel.conftest import AddDevice

FAN = """
device: Desk fan
id: desk-fan
connect: { mock: fan }
write:
  fan_speed: { unit: percent, min: 0, max: 100 }
safe_state: { fan_speed: 0 }
interlocks:
  - if: "fan_speed < 30 %"
    require: "heatr.power == 0 W"
hazard: low
confirmed: { by: tester, at: 2026-10-24 }
"""

HEATER = """
device: Heater
id: heater
connect: { mock: heater }
write:
  power: { unit: W, min: 0, max: 60 }
safe_state: { power: 0 }
hazard: low
confirmed: { by: tester, at: 2026-10-24 }
"""


async def test_f17_reference_to_missing_device_is_rejected(kernel: Kernel, add: AddDevice) -> None:
    fan = await add(FAN, settle=0)
    try:
        heater = await add(HEATER)
    except (ValueError, LookupError):
        return  # rejecting the dangling reference at registration is an acceptable fix
    decision = await kernel.execute(Write(device="heater", channel="power", value="50 W"), agent("a", "control_low"))
    assert not (heater.values["power"] > 0 and fan.values["fan_speed"] < 30), (
        f"heater on at {heater.values['power']} W with the fan at {fan.values['fan_speed']} %: {decision.status}"
    )
