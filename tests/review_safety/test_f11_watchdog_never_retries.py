"""F11 (medium). A watchdog rule whose action fails is never applied again while the state persists.

`tick` sets `exhausted = True` before `_apply_rule`, and only fires when not exhausted. If the
safe state fails once (a busy transport, a timeout), the over-budget state stays forever.
"""

from __future__ import annotations

from openhal.kernel import Kernel, Write, agent
from tests.kernel.conftest import FAN, HEATER, AddDevice, FakeClock

CLAUDE = agent("claude", "control_medium")


async def test_f11_failed_watchdog_action_is_retried(kernel: Kernel, add: AddDevice, clock: FakeClock) -> None:
    await add(FAN, settle=0)
    heater = await add(HEATER)
    assert (await kernel.execute(Write(device="desk-fan", channel="fan_speed", value="40 %"), CLAUDE)).ok
    assert (await kernel.execute(Write(device="heater", channel="power", value="50 W"), CLAUDE)).ok
    await kernel.tick()
    clock.advance(61)

    heater.settings.fail_writes = True  # one transient failure while the budget runs out
    assert await kernel.tick()
    heater.settings.fail_writes = False

    for _ in range(5):
        clock.advance(5)
        await kernel.tick()

    assert heater.values["power"] == 0, (
        f"budget ran out 25 s ago and the device is still at {heater.values['power']} W, with no retry"
    )
