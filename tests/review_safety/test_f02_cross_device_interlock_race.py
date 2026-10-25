"""F02 (high). Interlocks across two devices are checked against stale state during in-flight writes.

Locks are per device, and `runtime.accepted` is only updated after the driver returns. While a
heater write is in flight, a fan write is evaluated as if the heater were still off, so both are
accepted and the interlock "heater power > 0 W needs fan >= 30 %" ends up violated.
"""

from __future__ import annotations

import asyncio

from openhal.kernel import Kernel, Write, agent
from tests.kernel.conftest import FAN, HEATER, AddDevice, FakeClock

CLAUDE = agent("claude", "control_medium")


async def test_f02_parallel_writes_break_cross_device_interlock(
    kernel: Kernel, add: AddDevice, clock: FakeClock
) -> None:
    fan = await add(FAN, settle=0)
    heater = await add(HEATER)
    assert (await kernel.execute(Write(device="desk-fan", channel="fan_speed", value="40 %"), CLAUDE)).ok
    clock.advance(5)
    heater.settings.latency_s = 0.2

    await asyncio.gather(
        kernel.execute(Write(device="heater", channel="power", value="50 W"), CLAUDE),
        kernel.execute(Write(device="desk-fan", channel="fan_speed", value="0 %"), CLAUDE),
    )

    heater_on = heater.values["power"] > 0
    fan_low = fan.values["fan_speed"] < 30
    assert not (heater_on and fan_low), (
        f"interlock violated on hardware: heater power {heater.values['power']} W, fan {fan.values['fan_speed']} %"
    )
