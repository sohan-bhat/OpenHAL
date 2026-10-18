"""F04 (high). A one second dip resets a max_duration budget, ignoring reset_after.

Spec section 8 says the budget resets only after the expression has been false for at least
`reset_after`. `Kernel.tick` clears `active_since` the first time it sees the expression false,
so a brief dip between ticks restarts the full budget.
"""

from __future__ import annotations

from openhal.kernel import Kernel, Write, agent
from tests.kernel.conftest import FAN, HEATER, AddDevice, FakeClock

CLAUDE = agent("claude", "control_medium")


def power(value: str) -> Write:
    return Write(device="heater", channel="power", value=value)


async def test_f04_short_dip_restarts_budget(kernel: Kernel, add: AddDevice, clock: FakeClock) -> None:
    # HEATER rule: power > 40 W for at most 60 s, reset only after 30 s below.
    await add(FAN, settle=0)
    await add(HEATER)
    assert (await kernel.execute(Write(device="desk-fan", channel="fan_speed", value="40 %"), CLAUDE)).ok

    assert (await kernel.execute(power("50 W"), CLAUDE)).ok
    await kernel.tick()
    clock.advance(55)
    assert (await kernel.execute(power("30 W"), CLAUDE)).ok
    await kernel.tick()
    clock.advance(1)  # far shorter than reset_after (30 s)
    assert (await kernel.execute(power("50 W"), CLAUDE)).ok
    await kernel.tick()
    clock.advance(55)
    fired = await kernel.tick()

    assert fired, "power stayed above 40 W for 110 of the last 111 s and the 60 s budget never fired"
