"""F03 (high). Stop reports a device safe while a write that started earlier is still landing.

`_stop_device` waits only 2 s for the device lock, then applies the safe state alongside the
in-flight command. The older write finishes afterwards and leaves the device in the commanded
state, with `runtime.accepted` updated to match, after stop said "safe".
"""

from __future__ import annotations

import asyncio
from typing import Any

from openhal.drivers.base import Reading
from openhal.drivers.mock import MockDriver
from openhal.kernel import Kernel, Write, agent, human
from openhal.spec import loads
from tests.kernel.conftest import FAN, FakeClock


class SlowMoveDriver(MockDriver):
    """Moving to a nonzero setpoint takes 3 s (a ramp, a G-code move with M400). Going to zero is quick."""

    async def _write(self, channel: str, value: Any) -> Reading | None:
        if value:
            await asyncio.sleep(3.0)
        return await super()._write(channel, value)


async def test_f03_write_lands_after_stop_reported_safe(kernel: Kernel, clock: FakeClock) -> None:
    file = loads(FAN)
    driver = SlowMoveDriver(file)
    kernel.register(file, driver)
    await kernel.connect("desk-fan")
    clock.advance(60)

    task = asyncio.create_task(
        kernel.execute(Write(device="desk-fan", channel="fan_speed", value="40 %"), agent("a", "control_low"))
    )
    await asyncio.sleep(0.05)
    report = await kernel.stop_all(human(), "operator pressed stop")
    assert report.devices[0].status == "safe"
    await task

    assert kernel.stopped
    assert driver.values["fan_speed"] == 0, (
        f"stop reported safe, but the fan ended at {driver.values['fan_speed']} % after the in-flight write landed"
    )
