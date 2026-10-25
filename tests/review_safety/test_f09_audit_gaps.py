"""F09 (medium). Events the safety documents say are logged leave no audit entry."""

from __future__ import annotations

import pytest

from openhal.drivers.base import DriverError
from openhal.kernel import Action, Kernel, Write, agent
from openhal.kernel.checks import Block
from tests.kernel.conftest import FAN, HEATER, AddDevice, FakeClock

CLAUDE = agent("claude", "control_medium")


async def test_f09_expired_request_is_logged(kernel: Kernel, add: AddDevice, clock: FakeClock) -> None:
    await add(FAN, settle=0)
    await add(HEATER)
    assert (await kernel.execute(Write(device="desk-fan", channel="fan_speed", value="40 %"), CLAUDE)).ok
    pending = await kernel.execute(Action(device="heater", action="purge"), CLAUDE)
    assert pending.status == "pending"
    clock.advance(400)
    kernel.pending()
    request_id = pending.request_id

    entries = kernel.audit.entries(limit=5000)
    logged = [entry for entry in entries if entry.body["details"].get("request_id") == request_id]
    statuses = [entry.status for entry in logged]
    assert any(status in ("expired", "rejected") for status in statuses), (
        f"SAFETY.md says expired requests are rejected and logged. Entries for the request: {statuses}"
    )


async def test_f09_failed_read_is_logged(kernel: Kernel, add: AddDevice) -> None:
    fan = await add(FAN)
    fan.settings.fail_reads = True
    with pytest.raises(DriverError):
        await kernel.read("desk-fan", "temperature", CLAUDE)
    reads = kernel.audit.entries(event="read")
    assert reads, "a read request that failed at the driver left no audit entry"


async def test_f09_refused_tighten_with_bad_unit_is_logged(kernel: Kernel, add: AddDevice) -> None:
    await add(FAN)
    with pytest.raises(Block):
        kernel.tighten(CLAUDE, "desk-fan", "fan_speed", max="50 degC")
    assert kernel.audit.entries(event="tighten"), "a refused tighten_limits call left no audit entry"


async def test_f09_safe_state_write_is_logged_as_a_write(kernel: Kernel, add: AddDevice) -> None:
    await add(FAN)
    assert (await kernel.execute(Write(device="desk-fan", channel="fan_speed", value="40 %"), CLAUDE)).ok
    before = len(kernel.audit.entries(event="safe_state"))
    await kernel.stop_all(CLAUDE, "test")
    safe_entries = kernel.audit.entries(event="safe_state")
    assert len(safe_entries) > before
    writes = [entry for entry in kernel.audit.entries(event="write") if entry.principal == "system:kernel"]
    assert writes, "the safe state wrote fan_speed = 0 to hardware but no write entry records the value change"
