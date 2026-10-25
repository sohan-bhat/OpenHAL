"""F01 (critical). A same-device channel whose value is unknown is evaluated as a bare word.

docs/SAFETY.md and spec section 7 say an unknown value makes `if` hold and `require` fail, so
unknown always blocks. In `expressions._evaluate_compare` an unresolved bare reference turns
into the string of its own name, so `guard_open != true` is True and `state != jammed` is True
while the hub knows nothing about either channel. These tests fail against the current code.
"""

from __future__ import annotations

from openhal.kernel import Action, Kernel, Write, agent
from tests.kernel.conftest import AddDevice

CLAUDE = agent("claude", "control_medium")

PRESS = """
device: Press
id: press
connect: { mock: press }
read:
  guard_open: { type: bool }
  state: { type: enum, values: [idle, running, jammed] }
write:
  power: { unit: percent, min: 0, max: 100 }
actions:
  cycle:
    require: ["state != jammed"]
safe_state: { power: 0 }
interlocks:
  - if: "power > 0 %"
    require: "guard_open != true"
    message: "The press may only run with the guard shut."
hazard: low
confirmed: { by: tester, at: 2026-10-24 }
"""


async def test_f01_interlock_passes_when_guard_state_is_unknown(kernel: Kernel, add: AddDevice) -> None:
    press = await add(PRESS, initial={"guard_open": True, "state": "jammed"})
    assert kernel.devices["press"].latest("guard_open", kernel.clock()) is None

    decision = await kernel.execute(Write(device="press", channel="power", value="50 %"), CLAUDE)

    assert decision.code == "interlock", f"unknown guard state let the press run: {decision}"
    assert press.hardware_writes() == []


async def test_f01_action_precondition_passes_when_state_is_unknown(kernel: Kernel, add: AddDevice) -> None:
    press = await add(PRESS, initial={"guard_open": False, "state": "jammed"})
    assert kernel.devices["press"].latest("state", kernel.clock()) is None

    decision = await kernel.execute(Action(device="press", action="cycle"), CLAUDE)

    assert decision.code == "interlock", f"unknown machine state satisfied 'state != jammed': {decision}"
    assert press.hardware_writes() == []
