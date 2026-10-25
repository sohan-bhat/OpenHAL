"""Action run limits (max_runs), requirement messages and argument names on limit blocks."""

from __future__ import annotations

import pytest

from openhal.audit.log import AuditLog
from openhal.drivers.mock import MockDriver
from openhal.kernel import Action, Kernel, human
from openhal.spec import loads
from tests.kernel.conftest import AddDevice, FakeClock

WATERER = """
device: Plant waterer
id: waterer
connect: { mock: waterer, initial: { tank: ok, soil_moisture: 31 } }
read:
  soil_moisture: { unit: percent }
  tank: { type: enum, values: [empty, ok] }
actions:
  water:
    args:
      duration: { unit: s, min: 1, max: 30 }
    require:
      - condition: "tank == ok"
        message: "pump can't run while tank is empty"
    max_runs: { count: 3, per: 1 h }
  stop: {}
safe_state:
  - action: stop
hazard: low
confirmed: { by: sohan, at: 2026-10-24 }
"""

PERSON = human("sohan")


def water(seconds: float) -> Action:
    return Action(device="waterer", action="water", args={"duration": {"value": seconds, "unit": "s"}})


async def fresh(kernel: Kernel, driver: MockDriver) -> None:
    """Read the tank again, as the hub's polling would, so the requirement sees a current value."""
    kernel.note_reading("waterer", await driver.read("tank"))


async def test_three_runs_per_hour_then_rate_limited(add: AddDevice, kernel: Kernel, clock: FakeClock) -> None:
    driver = await add(WATERER)
    for _ in range(3):
        await fresh(kernel, driver)
        decision = await kernel.execute(water(20), PERSON)
        assert decision.status == "done", decision.message
        clock.advance(60)
    await fresh(kernel, driver)
    blocked = await kernel.execute(water(20), PERSON)
    assert blocked.status == "blocked"
    assert blocked.code == "rate_limited"
    assert "at most 3 times per 1 h" in blocked.message
    assert blocked.limit == {"runs": 3, "per_s": 3600.0}
    clock.advance(3600)
    await fresh(kernel, driver)
    assert (await kernel.execute(water(20), PERSON)).status == "done"


async def test_requirement_message_names_the_reason(add: AddDevice, kernel: Kernel) -> None:
    driver = await add(WATERER)
    driver.values["tank"] = "empty"
    kernel.note_reading("waterer", await driver.read("tank"))
    blocked = await kernel.execute(water(20), PERSON)
    assert blocked.code == "interlock"
    assert blocked.limit == {"interlock": "pump can't run while tank is empty"}
    assert "Pump can't run while tank is empty." in blocked.message


async def test_argument_limit_names_the_argument(add: AddDevice, kernel: Kernel) -> None:
    await fresh(kernel, await add(WATERER))
    blocked = await kernel.execute(water(120), PERSON)
    assert blocked.code == "above_max"
    assert blocked.limit == {"max": 30.0, "unit": "s", "argument": "duration"}


async def test_dry_run_counts_planned_runs(add: AddDevice, kernel: Kernel) -> None:
    await fresh(kernel, await add(WATERER))
    decisions = kernel.dry_run([water(10)] * 4, PERSON)
    assert [decision.status for decision in decisions] == ["allowed", "allowed", "allowed", "blocked"]
    assert decisions[3].code == "rate_limited"


async def test_a_restart_does_not_reset_the_window(clock: FakeClock) -> None:
    audit = AuditLog(":memory:")
    first = Kernel(audit, clock=clock, approval_key=b"test-approval-key-32-bytes-long!")
    file = loads(WATERER)
    driver = MockDriver(file)
    first.register(file, driver)
    await first.connect("waterer")
    for _ in range(3):
        clock.advance(2)
        first.note_reading("waterer", await driver.read("tank"))
        assert (await first.execute(water(5), PERSON)).status == "done"
    second = Kernel(audit, clock=clock, approval_key=b"test-approval-key-32-bytes-long!")
    second.register(file, MockDriver(file))
    await second.connect("waterer")
    clock.advance(2)
    blocked = await second.execute(water(5), PERSON)
    assert blocked.code == "rate_limited"


def test_max_runs_window_is_bounded() -> None:
    with pytest.raises(ValueError, match="between 1 s and 7 days"):
        loads(WATERER.replace("per: 1 h", "per: 30 days"))


async def test_an_unknown_requirement_never_claims_the_tank_is_empty(
    add: AddDevice, kernel: Kernel, clock: FakeClock
) -> None:
    await add(WATERER)
    clock.advance(3600)
    blocked = await kernel.execute(water(20), PERSON)
    assert blocked.code == "interlock"
    assert blocked.limit == {"interlock": "water needs tank == ok, which is unknown"}
