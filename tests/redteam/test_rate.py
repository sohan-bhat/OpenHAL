"""Attack family 3. Rate limits. An agent tries to move a channel faster than max_change_per_s.

The fan allows 20 %/s. The reference is the newest known value on a monotonic clock, so neither a
rapid sequence, nor many small steps, nor alternating values, nor two clients racing may move it
further than time allows.
"""

from __future__ import annotations

import asyncio

from openhal.kernel import Kernel, Write, agent
from tests.redteam.conftest import AddDevice

A = agent("a", "control_low")
B = agent("b", "control_low")

FAN = """
device: Desk fan
id: desk-fan
connect: { mock: fan, initial: { fan_speed: 0 } }
read:
  temperature: { unit: degC, every: 1 s }
write:
  fan_speed: { unit: "%", min: 0, max: 100, step: 1, max_change_per_s: 20 }
safe_state: { fan_speed: 0 }
hazard: low
confirmed: { by: tester, at: 2026-10-24 }
"""


async def test_a_single_jump_beyond_the_rate_is_blocked(kernel: Kernel, add: AddDevice, clock) -> None:
    driver = await add(FAN, settle=0)
    await kernel.read("desk-fan", "fan_speed", A)
    clock.advance(1.0)
    decision = await kernel.execute(Write(device="desk-fan", channel="fan_speed", value="80 %"), A)
    assert (decision.status, decision.code) == ("blocked", "rate_limited")
    assert driver.values["fan_speed"] == 0


async def test_a_rapid_burst_cannot_outrun_the_clock(kernel: Kernel, add: AddDevice, clock) -> None:
    driver = await add(FAN, settle=0)
    await kernel.read("desk-fan", "fan_speed", A)
    accepted = 0
    for _ in range(50):
        decision = await kernel.execute(Write(device="desk-fan", channel="fan_speed", value="100 %"), A)
        if decision.status == "done":
            accepted += 1
    assert accepted == 0, "no time passed, so no change should have been allowed"
    assert driver.values["fan_speed"] == 0


async def test_many_small_steps_still_obey_the_clock(kernel: Kernel, add: AddDevice, clock) -> None:
    await add(FAN, settle=0)
    await kernel.read("desk-fan", "fan_speed", A)
    last = 0.0
    for value in range(1, 101):
        decision = await kernel.execute(Write(device="desk-fan", channel="fan_speed", value=f"{value} %"), A)
        if decision.status == "done":
            assert value - last <= 20.0 + 1e-6, f"stepped to {value} % from {last} % with no time elapsed"
            last = float(value)
    assert last == 0.0


async def test_alternating_values_measure_from_the_newest(kernel: Kernel, add: AddDevice, clock) -> None:
    driver = await add(FAN, settle=0)
    await kernel.read("desk-fan", "fan_speed", A)
    clock.advance(1.0)
    first = await kernel.execute(Write(device="desk-fan", channel="fan_speed", value="20 %"), A)
    assert first.status == "done"
    second = await kernel.execute(Write(device="desk-fan", channel="fan_speed", value="100 %"), A)
    assert (second.status, second.code) == ("blocked", "rate_limited")
    back = await kernel.execute(Write(device="desk-fan", channel="fan_speed", value="0 %"), A)
    assert (back.status, back.code) == ("blocked", "rate_limited")
    assert driver.values["fan_speed"] == 20.0


async def test_two_clients_racing_one_channel_cannot_add_up(kernel: Kernel, add: AddDevice, clock) -> None:
    driver = await add(FAN, settle=0)
    await kernel.read("desk-fan", "fan_speed", A)
    clock.advance(1.0)
    results = await asyncio.gather(
        kernel.execute(Write(device="desk-fan", channel="fan_speed", value="20 %"), A),
        kernel.execute(Write(device="desk-fan", channel="fan_speed", value="20 %"), B),
    )
    assert driver.values["fan_speed"] in (0.0, 20.0)
    done = [item for item in results if item.status == "done"]
    assert len(done) <= 2
    assert all(entry[2] <= 20.0 for entry in driver.hardware_writes() if entry[1] == "fan_speed")


async def test_two_clients_racing_a_big_move_cannot_double_it(kernel: Kernel, add: AddDevice, clock) -> None:
    driver = await add(FAN, settle=0)
    await kernel.read("desk-fan", "fan_speed", A)
    clock.advance(1.0)
    results = await asyncio.gather(
        kernel.execute(Write(device="desk-fan", channel="fan_speed", value="20 %"), A),
        kernel.execute(Write(device="desk-fan", channel="fan_speed", value="40 %"), B),
    )
    statuses = sorted(item.status for item in results)
    assert statuses in (["blocked", "done"], ["blocked", "blocked"])
    assert driver.values["fan_speed"] in (0.0, 20.0), "40 % needs 2 s from 0, so it must never land in one tick"
