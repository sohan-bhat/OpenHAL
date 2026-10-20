"""Stop, unlock, connection loss and watchdog rules."""

from __future__ import annotations

import pytest

from openhal.kernel import Action, Kernel, Write, agent, human
from tests.kernel.conftest import FAN, HEATER, AddDevice, FakeClock

CLAUDE = agent("claude", "control_medium")

NO_SAFE = """
device: Pump
id: pump
connect: { mock: pump }
write:
  speed: { unit: percent, min: 0, max: 100 }
safe_state_note: The pump has no off state over this protocol.
hazard: low
confirmed: { by: tester, at: 2026-10-24 }
"""

SENSOR = """
device: Sensor
id: sensor
connect: { mock: sensor }
read:
  t: { unit: degC }
"""

THEN_VALUES = """
device: Lamp
id: lamp
connect: { mock: lamp }
write:
  brightness: { unit: percent, min: 0, max: 100 }
safe_state: { brightness: 0 }
watchdog:
  max_duration:
    - when: "brightness > 80 %"
      for: 10 s
      then: { brightness: 50 }
hazard: low
confirmed: { by: tester, at: 2026-10-24 }
"""


async def test_stop_reports_every_device(kernel: Kernel, add: AddDevice, clock: FakeClock) -> None:
    fan = await add(FAN, settle=0)
    await add(NO_SAFE, settle=0)
    await add(SENSOR, settle=0)
    await add(HEATER)
    await kernel.execute(Write(device="desk-fan", channel="fan_speed", value="20 %"), CLAUDE)
    clock.advance(1)
    await kernel.execute(Write(device="desk-fan", channel="fan_speed", value="40 %"), CLAUDE)
    clock.advance(1)
    pending = await kernel.execute(Action(device="heater", action="purge"), CLAUDE)
    assert pending.status == "pending"
    report = await kernel.stop_all(agent("anyone"), "smoke")
    statuses = {item.device: item.status for item in report.devices}
    assert statuses == {"desk-fan": "safe", "pump": "no_safe_state", "sensor": "safe", "heater": "safe"}
    assert report.cancelled_requests == 1
    assert fan.values["fan_speed"] == 0.0
    assert kernel.queue.get(pending.request_id or "").status == "cancelled"  # type: ignore[union-attr]
    assert kernel.stopped


async def test_stop_hooks_run_and_failures_are_logged(kernel: Kernel, add: AddDevice) -> None:
    await add(FAN)
    called: list[str] = []

    async def pause(reason: str) -> None:
        called.append(reason)

    def broken(reason: str) -> None:
        raise RuntimeError("hook failed")

    kernel.on_stop(pause)
    kernel.on_stop(broken)
    report = await kernel.stop_all(human(), "button")
    assert called == ["button"]
    assert report.devices[0].status == "safe"
    assert kernel.audit.entries(event="stop_hook")[0].status == "failed"


async def test_stop_on_disconnected_device(kernel: Kernel, add: AddDevice) -> None:
    await add(FAN, connect=False)
    report = await kernel.stop_all(human(), "test")
    assert report.devices[0].status == "failed"
    assert "not connected" in report.devices[0].detail


async def test_stop_when_driver_fails(kernel: Kernel, add: AddDevice) -> None:
    await add(FAN, fail_writes=True)
    report = await kernel.stop_all(human(), "test")
    assert report.devices[0].status == "partial", "the native step worked, the write failed (F16)"
    assert "DriverError" in report.devices[0].detail


async def test_watchdog_then_values(kernel: Kernel, add: AddDevice, clock: FakeClock) -> None:
    lamp = await add(THEN_VALUES)
    await kernel.execute(Write(device="lamp", channel="brightness", value="90 %"), CLAUDE)
    await kernel.tick()
    clock.advance(11)
    assert await kernel.tick() == ["lamp: brightness > 80 %"]
    assert lamp.values["brightness"] == 50.0
    assert (await kernel.execute(Write(device="lamp", channel="brightness", value="85 %"), CLAUDE)).code == (
        "duration_exceeded"
    )
    assert kernel.audit.entries(event="watchdog")[0].status == "done"


async def test_connection_loss_with_hold(kernel: Kernel, add: AddDevice) -> None:
    text = FAN.replace("hazard: low", "hazard: low\nwatchdog: { on_loss: hold }")
    fan = await add(text)
    await kernel.connection_lost("desk-fan", "gone")
    assert fan.hardware_writes() == []


async def test_unlock_requires_phrase(kernel: Kernel, add: AddDevice) -> None:
    await add(FAN)
    await kernel.stop_all(human(), "test")
    with pytest.raises(PermissionError):
        kernel.unlock(agent("a", "control_medium"), "unlock")
    with pytest.raises(ValueError, match="Type unlock"):
        kernel.unlock(human(), "")
    kernel.unlock(human(), " Unlock ")
    assert not kernel.stopped
    events = [entry.event for entry in kernel.audit.entries()]
    assert "unlock" in events
