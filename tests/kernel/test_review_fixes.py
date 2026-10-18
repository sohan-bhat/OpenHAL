"""Regression tests for review findings that had no proof-of-concept test (docs/agents/REVIEW-safety.md)."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from openhal.drivers.base import DriverError, Reading
from openhal.drivers.mock import MockDriver
from openhal.kernel import Action, Kernel, Write, agent, human
from openhal.kernel.confirmations import Request
from openhal.kernel.principals import SYSTEM
from openhal.spec import loads
from tests.kernel.conftest import FAN, HEATER, LASER, AddDevice, FakeClock

CLAUDE = agent("claude", "control_medium")


async def test_f13_forged_requests_are_ignored(kernel: Kernel, add: AddDevice) -> None:
    await add(LASER, initial={"door_closed": True})
    await kernel.read("laser", "door_closed", human())
    command = Action(device="laser", action="home")
    forged = Request("forged", command, CLAUDE, 0, 9e9, kernel.evaluate(command, CLAUDE), status="approved")
    decision = await kernel.execute(command, CLAUDE, request=forged)
    assert decision.status == "pending", "a request the queue didn't issue can't confirm anything"


async def test_f13_system_principal_is_refused(kernel: Kernel, add: AddDevice) -> None:
    await add(FAN)
    decision = await kernel.execute(Write(device="desk-fan", channel="fan_speed", value="5 %"), SYSTEM)
    assert decision.code == "not_permitted"
    assert not hasattr(kernel, "sign"), "signing is private"


async def test_f14_timeouts_mark_the_channel_unknown(
    kernel: Kernel, add: AddDevice, clock: FakeClock, monkeypatch: pytest.MonkeyPatch
) -> None:
    from openhal.kernel import kernel as kernel_module

    driver = await add(FAN, latency_s=0.2)
    monkeypatch.setattr(kernel_module, "DRIVER_TIMEOUT_S", 0.05)
    monkeypatch.setattr(kernel_module, "READBACK_TIMEOUT_S", 0.01)
    decision = await kernel.execute(Write(device="desk-fan", channel="fan_speed", value="10 %"), CLAUDE)
    assert decision.status == "failed"
    runtime = kernel.devices["desk-fan"]
    assert runtime.latest("fan_speed", clock.now) is None, "a timed-out write may have landed, so the value is unknown"
    blocked = await kernel.execute(Write(device="desk-fan", channel="fan_speed", value="10 %"), CLAUDE)
    assert blocked.code == "rate_limited"
    assert "unknown" in blocked.message
    driver.settings.latency_s = 0
    await kernel.read("desk-fan", "fan_speed", CLAUDE)
    clock.advance(1)
    assert (await kernel.execute(Write(device="desk-fan", channel="fan_speed", value="10 %"), CLAUDE)).status == "done"


async def test_f16_safe_state_runs_every_step(kernel: Kernel, add: AddDevice) -> None:
    class HalfBroken(MockDriver):
        async def _write(self, channel: str, value: Any) -> Reading | None:
            if channel == "power":
                raise DriverError("relay stuck")
            return await super()._write(channel, value)

    text = """
device: Two outputs
id: two
connect: { mock: two }
write:
  power: { unit: W, min: 0, max: 10 }
  fan: { unit: percent, min: 0, max: 100 }
safe_state:
  - { power: 0 }
  - { fan: 0 }
hazard: low
confirmed: { by: t, at: 2026-10-24 }
"""
    file = loads(text)
    driver = HalfBroken(file)
    kernel.register(file, driver)
    await kernel.connect("two")
    driver.values["fan"] = 80.0
    report = await kernel.stop_all(human(), "test")
    assert report.devices[0].status == "partial"
    assert "relay stuck" in report.devices[0].detail
    assert driver.values["fan"] == 0.0, "a failing step must not skip the ones after it"


async def test_f18_no_approval_window_after_a_stop(kernel: Kernel, add: AddDevice, clock: FakeClock) -> None:
    await add(FAN, settle=0)
    heater = await add(HEATER, latency_s=0.1)
    for speed in ("20 %", "40 %"):
        await kernel.execute(Write(device="desk-fan", channel="fan_speed", value=speed), CLAUDE)
        clock.advance(1)
    await kernel.execute(Write(device="heater", channel="enabled", value=True), human())
    pending = await kernel.execute(Action(device="heater", action="pulse", args={"seconds": "2 s"}), CLAUDE)
    confirming = asyncio.create_task(kernel.confirm(pending.request_id or "", human()))
    await asyncio.sleep(0.02)
    await kernel.stop_all(human(), "test")
    await confirming
    kernel.unlock(human(), "unlock")
    heater.settings.latency_s = 0
    again = await kernel.execute(Action(device="heater", action="pulse", args={"seconds": "2 s"}), CLAUDE)
    assert again.status == "pending", "a stop clears approval windows, even one being created during it"


async def test_f19_unlock_waits_for_the_stop(kernel: Kernel, add: AddDevice) -> None:
    await add(FAN, latency_s=0.2)
    stopping = asyncio.create_task(kernel.stop_all(human(), "test"))
    await asyncio.sleep(0.05)
    with pytest.raises(ValueError, match="still being applied"):
        kernel.unlock(human(), "unlock")
    await stopping
    kernel.unlock(human(), "unlock")


async def test_f20_readings_are_converted(kernel: Kernel, add: AddDevice) -> None:
    await add(FAN)
    kernel.note_reading("desk-fan", Reading("temperature", 86.0, "degF"))
    sample = kernel.devices["desk-fan"].latest("temperature", kernel.clock())
    assert sample is not None
    assert sample.value == pytest.approx(30.0)
    kernel.note_reading("desk-fan", Reading("temperature", 3.0, "V"))
    assert kernel.devices["desk-fan"].latest("temperature", kernel.clock()) is None
    kernel.note_reading("desk-fan", Reading("temperature", None, "degC"))
    assert kernel.devices["desk-fan"].latest("temperature", kernel.clock()) is None


async def test_f09_queue_events_are_logged(kernel: Kernel, add: AddDevice, clock: FakeClock) -> None:
    await add(FAN, settle=0)
    await add(HEATER)
    for speed in ("20 %", "40 %"):
        await kernel.execute(Write(device="desk-fan", channel="fan_speed", value=speed), CLAUDE)
        clock.advance(1)
    first = await kernel.execute(Action(device="heater", action="purge"), CLAUDE)
    clock.advance(301)
    kernel.pending()
    second = await kernel.execute(Action(device="heater", action="purge"), CLAUDE)
    await kernel.stop_all(human(), "test")
    statuses = {entry.body["details"]["request_id"]: entry.status for entry in kernel.audit.entries(event="request")}
    assert statuses == {first.request_id: "expired", second.request_id: "cancelled"}


async def test_orphaned_interlocks_keep_protecting(kernel: Kernel, add: AddDevice, clock: FakeClock) -> None:
    await add(FAN, settle=0)
    await add(HEATER)
    for speed in ("20 %", "40 %"):
        await kernel.execute(Write(device="desk-fan", channel="fan_speed", value=speed), CLAUDE)
        clock.advance(1)
    await kernel.execute(Write(device="heater", channel="power", value="20 W"), CLAUDE)
    kernel.unregister("heater")
    decision = await kernel.execute(Write(device="desk-fan", channel="fan_speed", value="20 %"), CLAUDE)
    assert decision.code == "interlock", "the heater's interlock still guards the fan while the heater is gone"
    assert "not registered right now" in decision.message
    kernel.unregister("nope")


async def test_queue_full_through_execute(kernel: Kernel, add: AddDevice, clock: FakeClock) -> None:
    await add(FAN, settle=0)
    await add(HEATER)
    kernel.queue.per_principal = 1
    for speed in ("20 %", "40 %"):
        await kernel.execute(Write(device="desk-fan", channel="fan_speed", value=speed), CLAUDE)
        clock.advance(1)
    assert (await kernel.execute(Action(device="heater", action="purge"), CLAUDE)).status == "pending"
    refused = await kernel.execute(Action(device="heater", action="purge"), CLAUDE)
    assert refused.code == "queue_full"


async def test_outside_cancellation_is_logged_and_raised(kernel: Kernel, add: AddDevice) -> None:
    await add(FAN, latency_s=1.0)
    task = asyncio.create_task(kernel.execute(Write(device="desk-fan", channel="fan_speed", value="10 %"), CLAUDE))
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    entry = kernel.audit.entries(event="write")[0]
    assert entry.status == "failed"
    assert kernel.devices["desk-fan"].latest("fan_speed", kernel.clock()) is None


async def test_tighten_unknown_device(kernel: Kernel) -> None:
    with pytest.raises(LookupError):
        kernel.tighten(CLAUDE, "ghost", "x", max="1 %")
    assert kernel.audit.entries(event="tighten")[0].code == "unknown_target"


async def test_native_and_action_safe_state_failures(kernel: Kernel) -> None:
    class Grumpy(MockDriver):
        async def _safe_state(self) -> None:
            raise DriverError("feed hold not supported")

        async def _action(self, name: str, args: dict[str, Any]) -> Any:
            raise DriverError("busy")

    text = """
device: Mount
id: mount
connect: { mock: mount }
write:
  speed: { unit: percent, min: 0, max: 100 }
actions:
  park: {}
safe_state:
  - { action: park }
  - { speed: 0 }
hazard: low
confirmed: { by: t, at: 2026-10-24 }
"""
    file = loads(text)
    driver = Grumpy(file)
    kernel.register(file, driver)
    await kernel.connect("mount")
    report = await kernel.stop_all(human(), "test")
    assert report.devices[0].status == "partial"
    assert "feed hold not supported" in report.devices[0].detail
    assert "park" in report.devices[0].detail
    assert driver.values["speed"] == 0.0


async def test_pattern_timeout(kernel: Kernel, add: AddDevice) -> None:
    text = """
device: Sign
id: sign
connect: { mock: sign }
write:
  text: { type: string, max_length: 64, pattern: "^(a|aa)+$" }
safe_state: { text: a }
hazard: low
confirmed: { by: t, at: 2026-10-24 }
"""
    await add(text)
    decision = await kernel.execute(Write(device="sign", channel="text", value="a" * 40 + "!"), CLAUDE)
    assert decision.code == "bad_value"
    assert "too long to check" in decision.message


async def test_non_finite_reading_is_unknown(kernel: Kernel, add: AddDevice) -> None:
    await add(FAN)
    kernel.note_reading("desk-fan", Reading("temperature", float("nan"), "degC"))
    assert kernel.devices["desk-fan"].latest("temperature", kernel.clock()) is None


async def test_dry_run_shadows_owner_channels(kernel: Kernel, add: AddDevice, clock: FakeClock) -> None:
    await add(FAN, settle=0)
    await add(HEATER)
    plan = [
        Write(device="heater", channel="power", value="0 W"),
        Write(device="desk-fan", channel="fan_speed", value="10 %"),
    ]
    assert [decision.status for decision in kernel.dry_run(plan, CLAUDE)] == ["allowed", "allowed"]
