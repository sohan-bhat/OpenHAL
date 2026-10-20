"""F05 (high). Running an action with `effects` throws away the rate reference.

After the action, `runtime.accepted[effect]` is popped and `_rate_reference` falls back to the
snapshot read from connection time, with the elapsed time measured from that old read. A
channel limited to 1 %/s can then jump from 10 % to 100 % in one second.
"""

from __future__ import annotations

from typing import Any

from openhal.drivers.base import Reading
from openhal.drivers.mock import MockDriver
from openhal.kernel import Action, Kernel, Write, agent
from openhal.spec import loads
from tests.kernel.conftest import FakeClock

CLAUDE = agent("claude", "control_medium")

PUMP = """
device: Dosing pump
id: pump
connect: { mock: pump }
write:
  speed: { unit: percent, min: 0, max: 100, max_change_per_s: 1 }
actions:
  prime: { effects: [speed] }
safe_state: { speed: 0 }
hazard: low
confirmed: { by: tester, at: 2026-10-24 }
"""


class QuietDriver(MockDriver):
    """A driver that does not echo a reading after a write. The base contract allows None."""

    async def _write(self, channel: str, value: Any) -> Reading | None:
        await super()._write(channel, value)
        return None


async def test_f05_action_effects_let_channel_skip_rate_limit(kernel: Kernel, clock: FakeClock) -> None:
    file = loads(PUMP)
    driver = QuietDriver(file)
    kernel.register(file, driver)
    await kernel.connect("pump")
    clock.advance(3600)

    assert (await kernel.execute(Write(device="pump", channel="speed", value="10 %"), CLAUDE)).ok
    clock.advance(1)
    assert (await kernel.execute(Action(device="pump", action="prime"), CLAUDE)).ok

    jump = await kernel.execute(Write(device="pump", channel="speed", value="100 %"), CLAUDE)

    assert jump.code == "rate_limited", (
        f"speed went from 10 % to 100 % in about 1 s on a 1 %/s channel: {jump.status} {jump.message}"
    )
