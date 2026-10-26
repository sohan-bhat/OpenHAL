"""Attack family 4. Concurrency. Races between writes, stops, unlocks and approvals.

A write that lands during a stop must not win, a stop still being applied must refuse an unlock,
two humans must not both make one request run, and a request can't be approved after it expired.
"""

from __future__ import annotations

import asyncio
from typing import Any

from openhal.drivers.base import Reading
from openhal.drivers.mock import MockDriver
from openhal.kernel import Action, Kernel, Write, agent, human
from openhal.spec import loads
from tests.redteam.conftest import AddDevice

CLAUDE = agent("claude", "control_medium")

FAN = """
device: Desk fan
id: desk-fan
connect: { mock: fan, initial: { fan_speed: 0 } }
read:
  temperature: { unit: degC, every: 1 s }
write:
  fan_speed: { unit: "%", min: 0, max: 100, step: 1 }
actions:
  spin_test:
    args:
      seconds: { unit: s, min: 1, max: 30 }
    confirm: confirm
safe_state: { fan_speed: 0 }
hazard: low
confirmed: { by: tester, at: 2026-10-24 }
"""


async def test_a_write_that_lands_during_a_stop_is_undone(kernel: Kernel, clock) -> None:
    class SlowFan(MockDriver):
        async def _write(self, channel: str, value: Any) -> Reading | None:
            if value:
                await asyncio.sleep(0.2)
            return await super()._write(channel, value)

    file = loads(FAN)
    driver = SlowFan(file)
    kernel.register(file, driver)
    await kernel.connect("desk-fan")
    clock.advance(60)

    task = asyncio.create_task(kernel.execute(Write(device="desk-fan", channel="fan_speed", value="90 %"), CLAUDE))
    await asyncio.sleep(0.02)
    report = await kernel.stop_all(human(), "operator stop")
    await task
    assert kernel.stopped
    assert driver.values["fan_speed"] == 0, "a write that landed after the stop must be undone to the safe state"
    assert all(item.status in ("safe", "pending") for item in report.devices)


async def test_unlock_is_refused_while_a_stop_is_still_applying(kernel: Kernel, add: AddDevice) -> None:
    hold = asyncio.Event()

    class SlowSafe(MockDriver):
        async def _safe_state(self) -> None:
            await hold.wait()
            await super()._safe_state()

    file = loads(FAN)
    driver = SlowSafe(file)
    kernel.register(file, driver)
    await kernel.connect("desk-fan")

    stop = asyncio.create_task(kernel.stop_all(human(), "operator stop"))
    await asyncio.sleep(0.02)
    try:
        caught = None
        try:
            kernel.unlock(human(), "unlock")
        except ValueError as exc:
            caught = exc
        assert caught is not None, "unlock must refuse while the stop lock is held"
        assert kernel.stopped
    finally:
        hold.set()
        await stop
    kernel.unlock(human(), "unlock")
    assert not kernel.stopped


async def queue(kernel: Kernel) -> str:
    decision = await kernel.execute(Action(device="desk-fan", action="spin_test", args={"seconds": "2 s"}), CLAUDE)
    assert decision.status == "pending"
    assert decision.request_id is not None
    return decision.request_id


async def test_two_humans_approving_one_request_run_it_once(kernel: Kernel, add: AddDevice) -> None:
    driver = await add(FAN)
    request_id = await queue(kernel)
    first, second = await asyncio.gather(
        kernel.confirm(request_id, human("owner")),
        kernel.confirm(request_id, human("sam")),
        return_exceptions=True,
    )
    outcomes = [item for item in (first, second) if not isinstance(item, BaseException)]
    errors = [item for item in (first, second) if isinstance(item, BaseException)]
    assert len(outcomes) == 1, "exactly one approval should run the command"
    assert len(errors) == 1
    ran = [entry for entry in driver.hardware_writes() if entry[0] == "action"]
    assert len(ran) == 1, f"the action ran {len(ran)} times"


async def test_a_request_cannot_be_approved_after_it_expires(kernel: Kernel, add: AddDevice, clock) -> None:
    driver = await add(FAN)
    request_id = await queue(kernel)
    clock.advance(10_000)
    caught = None
    try:
        await kernel.confirm(request_id, human())
    except LookupError as exc:
        caught = exc
    assert caught is not None, "an expired request must not be approvable"
    assert kernel.queue.get(request_id).status == "expired"
    assert [entry for entry in driver.hardware_writes() if entry[0] == "action"] == []


async def test_a_stop_cancels_a_pending_request_before_approval(kernel: Kernel, add: AddDevice) -> None:
    driver = await add(FAN)
    request_id = await queue(kernel)
    await kernel.stop_all(human(), "operator stop")
    assert kernel.queue.get(request_id).status == "cancelled"
    caught = None
    try:
        await kernel.confirm(request_id, human())
    except LookupError as exc:
        caught = exc
    assert caught is not None
    assert [entry for entry in driver.hardware_writes() if entry[0] == "action"] == []


async def test_a_write_cancelled_by_stop_reapplies_the_safe_state(kernel: Kernel, clock) -> None:
    class SlowFan(MockDriver):
        async def _write(self, channel: str, value: Any) -> Reading | None:
            if value:
                await asyncio.sleep(0.3)
            return await super()._write(channel, value)

    file = loads(FAN)
    driver = SlowFan(file)
    kernel.register(file, driver)
    await kernel.connect("desk-fan")
    clock.advance(60)

    task = asyncio.create_task(kernel.execute(Write(device="desk-fan", channel="fan_speed", value="90 %"), CLAUDE))
    await asyncio.sleep(0.02)
    await kernel.stop_all(human(), "operator stop")
    result = await task
    assert result.status in ("failed", "done")
    assert driver.values["fan_speed"] == 0
    assert kernel.stopped
