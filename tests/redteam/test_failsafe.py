"""Attack family 10. Fail-safe behaviour.

Any unexpected exception inside a check must block the command and be logged, never let it through.
A driver that fails during a write leaves a result, marks the channel unknown, and never reports
done. Nothing fails open.
"""

from __future__ import annotations

from typing import Any

import pytest

from openhal.drivers.base import Reading
from openhal.drivers.mock import MockDriver
from openhal.kernel import Kernel, Write, agent
from openhal.spec import loads
from tests.redteam.conftest import AddDevice

CLAUDE = agent("claude", "control_medium")

HEATER = """
device: Curing heater
id: heater
connect: { mock: heater }
read:
  temp: { unit: degC, every: 1 s }
write:
  setpoint: { unit: degC, min: 0, max: 30 }
safe_state: { setpoint: 0 }
hazard: medium
confirmed: { by: tester, at: 2026-10-24 }
"""


async def test_a_malformed_unit_that_raises_fails_closed(kernel: Kernel, add: AddDevice) -> None:
    await add(HEATER)
    decision = kernel.evaluate(Write(device="heater", channel="setpoint", value="25 percent**0"), CLAUDE)
    assert decision.status == "blocked"
    assert decision.code == "internal_error"


async def test_an_exception_inside_a_check_blocks_and_is_logged(
    kernel: Kernel, add: AddDevice, monkeypatch: pytest.MonkeyPatch
) -> None:
    driver = await add(HEATER)

    def boom(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("check exploded")

    monkeypatch.setattr("openhal.kernel.kernel.normalize", boom)
    decision = await kernel.execute(Write(device="heater", channel="setpoint", value="20 degC"), CLAUDE)
    assert decision.status == "blocked"
    assert decision.code == "internal_error"
    assert "Nothing was sent" in decision.message
    assert driver.hardware_writes() == []
    blocked = [entry for entry in kernel.audit.entries(event="write") if entry.status == "blocked"]
    assert blocked, "the fail-closed block must be in the audit log"
    assert blocked[-1].code == "internal_error"


async def test_a_driver_that_raises_during_a_write_never_reports_done(kernel: Kernel, add: AddDevice) -> None:
    class Exploding(MockDriver):
        async def _write(self, channel: str, value: Any) -> Reading | None:
            raise RuntimeError("transport melted")

    file = loads(HEATER)
    driver = Exploding(file)
    kernel.register(file, driver)
    await kernel.connect("heater")
    decision = await kernel.execute(Write(device="heater", channel="setpoint", value="20 degC"), CLAUDE)
    assert decision.status == "failed"
    assert decision.code == "driver_error"
    assert driver.hardware_writes() == [], "the write raised before the transport, so nothing was sent"
    sample = kernel.devices["heater"].latest("setpoint", kernel.clock())
    assert sample is None or sample.value != 20.0, "a failed write must not be recorded as the new value"
    failed = [entry for entry in kernel.audit.entries(event="write") if entry.status == "failed"]
    assert failed, "a driver failure must be logged"


async def test_a_write_in_flight_is_unknown_and_claims_nothing(kernel: Kernel, add: AddDevice) -> None:
    import asyncio
    import contextlib

    class Hanging(MockDriver):
        async def _write(self, channel: str, value: Any) -> Reading | None:
            await asyncio.Event().wait()

    file = loads(HEATER)
    driver = Hanging(file)
    kernel.register(file, driver)
    await kernel.connect("heater")
    runtime = kernel.devices["heater"]
    task = asyncio.create_task(kernel.execute(Write(device="heater", channel="setpoint", value="20 degC"), CLAUDE))
    await asyncio.sleep(0.05)
    assert "setpoint" in runtime.inflight, "a write in flight must hold the channel"
    assert runtime.latest("setpoint", kernel.clock()) is None, "an in-flight channel is unknown"
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task
