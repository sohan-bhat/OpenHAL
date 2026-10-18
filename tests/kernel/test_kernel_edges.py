"""Edge cases that close the kernel's branch coverage. Each test names the behavior it pins down."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from openhal.drivers.base import Driver, DriverError, DriverInfo, Health, Reading
from openhal.drivers.mock import MockDriver
from openhal.kernel import Action, Kernel, Write, agent, human, routine
from openhal.kernel import kernel as kernel_module
from openhal.kernel.checks import Block
from openhal.kernel.confirmations import ConfirmationQueue
from openhal.kernel.grants import GrantError
from openhal.spec import loads
from tests.kernel.conftest import FAN, HEATER, AddDevice, FakeClock

CLAUDE = agent("claude", "control_medium")

TRIO_A = """
device: Room
id: room
connect: { mock: room }
read:
  occupied: { type: bool }
  mode: { type: enum, values: [day, night] }
interlocks:
  - if: "lamp.level > 50 %"
    require: "occupied == true and mode == day and siren.armed == false"
    message: "Bright light only when someone is in the room during the day and the siren is off."
"""

LAMP = """
device: Lamp
id: lamp
connect: { mock: lamp }
write:
  level: { unit: percent, min: 0, max: 100 }
safe_state: { level: 0 }
hazard: low
confirmed: { by: t, at: 2026-10-24 }
"""

SIREN = """
device: Siren
id: siren
connect: { mock: siren }
write:
  armed: { type: bool }
safe_state: { armed: false }
hazard: low
confirmed: { by: t, at: 2026-10-24 }
"""

PARKER = """
device: Mount
id: mount
connect: { mock: mount }
write:
  speed: { unit: percent, min: 0, max: 100 }
actions:
  park:
    args:
      rate: { unit: percent, min: 1, max: 100 }
safe_state:
  - { action: park, args: { rate: 10 } }
  - { speed: 0 }
hazard: low
confirmed: { by: t, at: 2026-10-24 }
"""


class QuietDriver(Driver):
    """A driver that returns no reading from writes and has no custom behavior."""

    info = DriverInfo(name="mock", protocols=("test",), hazard_default="low", summary="quiet")

    async def connect(self) -> None:
        return None

    async def read(self, channel: str) -> Reading:
        return Reading(channel, 0.0, "percent")

    async def _write(self, channel: str, value: Any) -> Reading | None:
        return None


async def test_unregister_and_missing_runtime(kernel: Kernel, add: AddDevice) -> None:
    await add(FAN)
    kernel.unregister("desk-fan")
    assert "desk-fan" not in kernel.devices
    with pytest.raises(LookupError):
        await kernel.connect("desk-fan")
    kernel.note_reading("desk-fan", Reading("x", 1.0))


async def test_rate_reference_falls_back_when_nothing_is_known(kernel: Kernel, add: AddDevice) -> None:
    text = FAN.replace("safe_state: { fan_speed: 0 }", "safe_state: { fan_speed: 10 }")
    await add(text, settle=1.0, fail_reads=True)
    assert (await kernel.execute(Write(device="desk-fan", channel="fan_speed", value="35 %"), CLAUDE)).code == (
        "rate_limited"
    )
    assert (await kernel.execute(Write(device="desk-fan", channel="fan_speed", value="30 %"), CLAUDE)).status == "done"


async def test_rate_reference_uses_min_without_safe_state(kernel: Kernel, add: AddDevice) -> None:
    text = FAN.replace("safe_state: { fan_speed: 0 }\n", "safe_state_note: none\n")
    await add(text, settle=1.0, fail_reads=True)
    assert (await kernel.execute(Write(device="desk-fan", channel="fan_speed", value="25 %"), CLAUDE)).code == (
        "rate_limited"
    )


def test_evaluate_rejects_other_objects(kernel: Kernel) -> None:
    decision = kernel.evaluate("not a command", CLAUDE)  # type: ignore[arg-type]
    assert decision.code == "bad_request"


async def test_routine_on_high_hazard_without_key(clock: FakeClock) -> None:
    kernel = Kernel(clock=clock)
    file = loads(FAN.replace("hazard: low", "hazard: high"))
    kernel.register(file, MockDriver(file))
    await kernel.connect("desk-fan")
    clock.advance(60)
    worker = routine("r", "control_medium", "a" * 64)
    assert (await kernel.execute(Write(device="desk-fan", channel="fan_speed", value="5 %"), worker)).code == (
        "needs_confirmation"
    )
    with pytest.raises(PermissionError):
        kernel.sign("desk-fan", "r", "a" * 64, "me", "now")


async def test_interlocks_owned_by_a_third_device(kernel: Kernel, add: AddDevice, clock: FakeClock) -> None:
    room = await add(TRIO_A, settle=0, initial={"occupied": True, "mode": "day"})
    siren = await add(SIREN, settle=0)
    await add(LAMP)
    assert room.values["occupied"] is True
    for channel in ("occupied", "mode"):
        await kernel.read("room", channel, CLAUDE)
    allowed = await kernel.execute(Write(device="lamp", channel="level", value="60 %"), CLAUDE)
    assert allowed.status == "done", allowed.message
    await kernel.execute(Write(device="lamp", channel="level", value="10 %"), CLAUDE)
    await kernel.execute(Write(device="siren", channel="armed", value=True), CLAUDE)
    blocked = await kernel.execute(Write(device="lamp", channel="level", value="60 %"), CLAUDE)
    assert blocked.code == "interlock"
    assert "siren is off" in blocked.message
    assert siren.values["armed"] is True
    room.values["mode"] = "night"
    await kernel.read("room", "mode", CLAUDE)
    await kernel.read("room", "occupied", CLAUDE)
    await kernel.execute(Write(device="siren", channel="armed", value=False), CLAUDE)
    assert (await kernel.execute(Write(device="lamp", channel="level", value="60 %"), CLAUDE)).code == "interlock"


async def test_interlock_reference_to_unknown_device(kernel: Kernel, add: AddDevice) -> None:
    text = LAMP + 'interlocks:\n  - if: "level > 1 %"\n    require: "ghost.flag == true"\n'
    await add(text)
    assert (await kernel.execute(Write(device="lamp", channel="level", value="5 %"), CLAUDE)).code == "interlock"


async def test_interlock_on_image_value_is_unknown(kernel: Kernel, add: AddDevice) -> None:
    text = """
device: Cam
id: cam
connect: { mock: cam }
read:
  frame: { type: image }
write:
  light: { type: bool }
safe_state: { light: false }
interlocks:
  - if: "light == true"
    require: "frame == 'ok'"
hazard: low
confirmed: { by: t, at: 2026-10-24 }
"""
    driver = await add(text)
    driver.values["frame"] = b"\x00\x01"
    await kernel.read("cam", "frame", CLAUDE)
    assert (await kernel.execute(Write(device="cam", channel="light", value=True), CLAUDE)).code == "interlock"


async def test_busy_device(kernel: Kernel, add: AddDevice, monkeypatch: pytest.MonkeyPatch) -> None:
    await add(FAN)
    monkeypatch.setattr(kernel_module, "LOCK_TIMEOUT_S", 0.01)
    await kernel.devices["desk-fan"].lock.acquire()
    try:
        decision = await kernel.execute(Write(device="desk-fan", channel="fan_speed", value="5 %"), CLAUDE)
    finally:
        kernel.devices["desk-fan"].lock.release()
    assert decision.code == "busy"


async def test_concurrent_writes_are_serialized(kernel: Kernel, add: AddDevice) -> None:
    driver = await add(FAN, latency_s=0.01)
    first, second = await asyncio.gather(
        kernel.execute(Write(device="desk-fan", channel="fan_speed", value="20 %"), CLAUDE),
        kernel.execute(Write(device="desk-fan", channel="fan_speed", value="20 %"), agent("other", "control_low")),
    )
    assert {first.status, second.status} == {"done"}
    third = await kernel.execute(Write(device="desk-fan", channel="fan_speed", value="40 %"), CLAUDE)
    assert third.code == "rate_limited", "the second client's write updated the reference value"
    assert len(driver.hardware_writes()) == 2


async def test_write_without_reading(kernel: Kernel, clock: FakeClock) -> None:
    file = loads(FAN)
    kernel.register(file, QuietDriver(file))
    await kernel.connect("desk-fan")
    clock.advance(60)
    decision = await kernel.execute(Write(device="desk-fan", channel="fan_speed", value="5 %"), CLAUDE)
    assert decision.status == "done"
    health = await kernel.devices["desk-fan"].driver.health()
    assert health == Health(connected=True)
    assert await kernel.devices["desk-fan"].driver.describe() is None
    assert await kernel.devices["desk-fan"].driver.identify() == {}
    assert await QuietDriver.discover() == []
    with pytest.raises(DriverError, match="no action"):
        await kernel.devices["desk-fan"].driver._action("x", {})


async def test_action_effects_forget_values(kernel: Kernel, add: AddDevice, clock: FakeClock) -> None:
    await add(FAN, settle=0)
    await add(HEATER)
    for speed in ("20 %", "40 %"):
        await kernel.execute(Write(device="desk-fan", channel="fan_speed", value=speed), CLAUDE)
        clock.advance(1)
    await kernel.execute(Write(device="heater", channel="power", value="10 W"), CLAUDE)
    done = await kernel.execute(Action(device="heater", action="purge"), human())
    assert done.status == "done"
    assert "power" not in kernel.devices["heater"].accepted


async def test_grant_failure_during_run(kernel: Kernel, add: AddDevice, monkeypatch: pytest.MonkeyPatch) -> None:
    await add(FAN)

    def refuse(*args: Any) -> None:
        raise GrantError("refused for the test")

    monkeypatch.setattr(kernel.grants, "consume", refuse)
    decision = await kernel.execute(Write(device="desk-fan", channel="fan_speed", value="5 %"), CLAUDE)
    assert decision.code == "internal_error"
    assert "Grant check failed" in decision.message


async def test_reject_unknown_request(kernel: Kernel) -> None:
    with pytest.raises(LookupError):
        kernel.reject("nope", human())
    with pytest.raises(LookupError):
        await kernel.confirm("nope", human())


async def test_tighten_edges(kernel: Kernel, add: AddDevice) -> None:
    await add(FAN)
    with pytest.raises(LookupError):
        kernel.tighten(CLAUDE, "desk-fan", "nope", max="1 %")
    assert kernel.tighten(CLAUDE, "desk-fan", "fan_speed", min="10 %")["min"] == 10
    with pytest.raises(Block, match="min would be above max"):
        kernel.tighten(CLAUDE, "desk-fan", "fan_speed", max="5 %")


async def test_stop_with_sync_hook_and_failing_device(
    kernel: Kernel, add: AddDevice, monkeypatch: pytest.MonkeyPatch
) -> None:
    await add(FAN, settle=0)
    await add(LAMP)
    calls: list[str] = []
    kernel.on_stop(calls.append)
    original = kernel._stop_device

    async def flaky(runtime: Any, reason: str) -> Any:
        if runtime.device_id == "lamp":
            raise RuntimeError("lamp exploded")
        return await original(runtime, reason)

    monkeypatch.setattr(kernel, "_stop_device", flaky)
    report = await kernel.stop_all(human(), "test")
    assert calls == ["test"]
    statuses = {item.device: item.status for item in report.devices}
    assert statuses == {"desk-fan": "safe", "lamp": "failed"}


async def test_stop_proceeds_when_device_lock_is_held(kernel: Kernel, add: AddDevice) -> None:
    fan = await add(FAN)
    lock = kernel.devices["desk-fan"].lock
    await lock.acquire()
    try:
        report = await kernel.stop_all(human(), "test")
    finally:
        lock.release()
    assert report.devices[0].status == "safe"
    assert fan.values["fan_speed"] == 0.0


async def test_safe_state_runs_actions_with_arguments(kernel: Kernel, add: AddDevice) -> None:
    mount = await add(PARKER)
    report = await kernel.stop_all(human(), "test")
    assert report.devices[0].status == "safe"
    assert ("action", "park", {"rate": 10.0}) in mount.transport_log


async def test_tick_with_unknown_values_and_failed_rule(kernel: Kernel, add: AddDevice, clock: FakeClock) -> None:
    text = """
device: Lamp
id: lamp
connect: { mock: lamp }
read:
  ambient: { unit: lux }
write:
  level: { unit: percent, min: 0, max: 100 }
safe_state: { level: 0 }
watchdog:
  max_duration:
    - when: "ambient > 100 lux"
      for: 1 s
    - when: "level > 10 %"
      for: 1 s
      then: { level: 5 }
hazard: low
confirmed: { by: t, at: 2026-10-24 }
"""
    lamp = await add(text, fail_reads=True)
    await kernel.execute(Write(device="lamp", channel="level", value="20 %"), CLAUDE)
    await kernel.tick()
    clock.advance(2)
    lamp.settings.fail_writes = True
    fired = await kernel.tick()
    assert fired == ["lamp: level > 10 %"]
    assert kernel.audit.entries(event="watchdog", status="failed")


async def test_helpers() -> None:
    assert repr(kernel_module._UNKNOWN) == "unknown"
    assert kernel_module._jsonable(b"abc") == "<3 bytes>"
    assert kernel_module._jsonable([1, (2, float("inf"))]) == [1, [2, "inf"]]
    assert kernel_module._seconds(7200) == "2 h"
    assert kernel_module._seconds(90) == "90 s"
    assert kernel_module._quantity_text("5 V", "V") == "5 V"
    assert kernel_module._display(True, None) == "true"


async def test_pending_list_and_decision_ok(kernel: Kernel, add: AddDevice, clock: FakeClock) -> None:
    await add(FAN, settle=0)
    await add(HEATER)
    for speed in ("20 %", "40 %"):
        await kernel.execute(Write(device="desk-fan", channel="fan_speed", value=speed), CLAUDE)
        clock.advance(1)
    pending = await kernel.execute(Action(device="heater", action="purge"), CLAUDE)
    assert [request.request_id for request in kernel.pending()] == [pending.request_id]
    assert not pending.ok
    assert kernel.queue.recent(1)[0].request_id == pending.request_id


def test_queue_drops_oldest_when_full() -> None:
    queue = ConfirmationQueue(ttl_s=60, max_pending=2)
    decision = kernel_module.Decision(status="needs_confirmation", message="m", device="d", target="t")
    command = Write(device="d", channel="c", value="1 %")
    first = queue.add(command, CLAUDE, decision, 0)
    queue.add(command, CLAUDE, decision, 1)
    queue.add(command, CLAUDE, decision, 2)
    assert first.status == "cancelled"
    assert len(queue.pending(3)) == 2


async def test_runtime_states_block_commands(kernel: Kernel, add: AddDevice, clock: FakeClock) -> None:
    await add(FAN)
    runtime = kernel.devices["desk-fan"]
    runtime.faulted = "overcurrent"
    assert (
        "fault state (overcurrent)"
        in kernel.evaluate(Write(device="desk-fan", channel="fan_speed", value="1 %"), CLAUDE).message
    )
    runtime.faulted = None
    runtime.applying_safe_state = True
    assert (
        "applying its safe state"
        in kernel.evaluate(Write(device="desk-fan", channel="fan_speed", value="1 %"), CLAUDE).message
    )
    runtime.applying_safe_state = False
    clock.advance(1000)
    assert runtime.latest("temperature", clock.now) is None, "sensor readings go stale"
    assert runtime.latest("fan_speed", clock.now) is not None, "setpoints don't"


def test_kernel_package_attribute_error() -> None:
    import openhal.kernel as package

    with pytest.raises(AttributeError):
        package.nothing_here  # noqa: B018
