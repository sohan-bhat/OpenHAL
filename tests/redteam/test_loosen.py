"""Attack family 6b. Loosening limits. Agents may tighten their own session, never widen.

Session limits only narrow, they are per principal, and no interface widens a confirmed file limit.
A tightened limit is enforced on the next write, and it can't be undone by tightening again.
"""

from __future__ import annotations

from collections.abc import Callable

from openhal.client import AsyncClient
from openhal.hub.hub import Hub
from openhal.kernel import Kernel, Write, agent
from tests.redteam.conftest import AddDevice, Tokens

A = agent("claude", "control_medium")
B = agent("other", "control_medium")

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


def tighten(kernel: Kernel, who, **kw):
    from openhal.kernel.checks import Block

    try:
        kernel.tighten(who, "desk-fan", "fan_speed", **kw)
        return "ok"
    except Block as block:
        return block.code


async def test_session_limits_only_narrow(kernel: Kernel, add: AddDevice) -> None:
    await add(FAN)
    assert tighten(kernel, A, max="50 %") == "ok"
    assert tighten(kernel, A, max="150 %") == "cannot_loosen"
    assert tighten(kernel, A, max="80 %") == "cannot_loosen"
    assert tighten(kernel, A, min="10 %") == "ok"
    assert tighten(kernel, A, min="5 %") == "cannot_loosen"
    assert tighten(kernel, A, rate="5 %/s") == "ok"
    assert tighten(kernel, A, rate="50 %/s") == "cannot_loosen"


async def test_a_tightened_limit_is_enforced_on_the_next_write(kernel: Kernel, add: AddDevice, clock) -> None:
    driver = await add(FAN, settle=0)
    await kernel.read("desk-fan", "fan_speed", A)
    clock.advance(10)
    kernel.tighten(A, "desk-fan", "fan_speed", max="40 %")
    blocked = await kernel.execute(Write(device="desk-fan", channel="fan_speed", value="60 %"), A)
    assert (blocked.status, blocked.code) == ("blocked", "above_max")
    assert blocked.limit == {"max": 40.0, "unit": "%"}
    ok = await kernel.execute(Write(device="desk-fan", channel="fan_speed", value="30 %"), A)
    assert ok.status == "done"
    assert driver.values["fan_speed"] == 30.0


async def test_one_agents_tightening_does_not_loosen_for_another(kernel: Kernel, add: AddDevice, clock) -> None:
    driver = await add(FAN, settle=0)
    kernel.tighten(A, "desk-fan", "fan_speed", max="40 %")
    assert tighten(kernel, B, max="150 %") == "cannot_loosen"
    await kernel.read("desk-fan", "fan_speed", B)
    clock.advance(10)
    over_file = await kernel.execute(Write(device="desk-fan", channel="fan_speed", value="150 %"), B)
    assert (over_file.status, over_file.code) == ("blocked", "above_max")
    assert over_file.limit == {"max": 100.0, "unit": "%"}
    under_file = await kernel.execute(Write(device="desk-fan", channel="fan_speed", value="90 %"), B)
    assert under_file.status == "done", "A's session limit must not bind B, who is still held to the file max"
    assert driver.values["fan_speed"] == 90.0


async def test_tightening_min_above_max_is_refused(kernel: Kernel, add: AddDevice) -> None:
    await add(FAN)
    kernel.tighten(A, "desk-fan", "fan_speed", max="40 %")
    assert tighten(kernel, A, min="60 %") == "cannot_loosen"


async def test_rest_and_client_cannot_widen_a_file_limit(
    hub: Hub, rest, python_client: Callable[[str], AsyncClient], tokens: Tokens
) -> None:
    async with rest(tokens.agent) as client:
        widen = await client.post("/v1/tighten", json={"device": "desk-fan", "channel": "fan_speed", "max": "150 %"})
        assert widen.json()["code"] == "cannot_loosen"
    async with python_client(tokens.agent) as client:
        result = await client.tighten("desk-fan", "fan_speed", max="150 %")
        assert (result.ok, result.code) == (False, "cannot_loosen")
    describe = hub.kernel.devices["desk-fan"].file.write["fan_speed"]
    assert describe.max == 100
