"""Attack family 2b. The structured value format (ADR 0016) and the action run limit.

Over the wire a number travels as a value with its unit beside it. A number sent as one string, a
unit on a non-number channel, or a Quantity holding a bool, a non-finite number or an incompatible
unit must be refused with UNIT_INVALID and never reach hardware. An action's `max_runs` limit holds
across a restart, because the window is seeded from the audit log.
"""

from __future__ import annotations

from collections.abc import Callable

from openhal.audit.log import AuditLog
from openhal.client import AsyncClient
from openhal.drivers.mock import MockDriver
from openhal.hub.hub import Hub
from openhal.kernel import Action, Kernel, human
from openhal.mcp import Tools
from openhal.spec import loads
from tests.kernel.conftest import FakeClock
from tests.redteam.conftest import AddDevice, Tokens, writes

RUNS = """
device: Pulser
id: pulser
connect: { mock: pulser, initial: { enabled: true } }
write:
  enabled: { type: bool }
actions:
  pulse:
    args:
      seconds: { unit: s, min: 1, max: 10 }
    max_runs: { count: 2, per: 1 h }
hazard: low
confirmed: { by: tester, at: 2026-10-24 }
"""


async def test_a_number_sent_as_one_string_is_refused_over_the_wire(hub: Hub, rest, tokens: Tokens) -> None:
    async with rest(tokens.agent) as client:
        for body in (
            {"device": "desk-fan", "channel": "fan_speed", "value": "30 %"},
            {"device": "desk-fan", "channel": "fan_speed", "value": "30"},
        ):
            decision = (await client.post("/v1/write", json=body)).json()
            assert (decision["status"], decision["code"]) == ("blocked", "bad_unit")
    assert writes(hub, "desk-fan") == []


async def test_a_unit_on_a_non_number_channel_is_refused(
    hub: Hub, python_client: Callable[[str], AsyncClient], tokens: Tokens
) -> None:
    async with python_client(tokens.agent) as client:
        on_bool = await client.write("heater", "enabled", True, "%")
        assert (on_bool.status, on_bool.code) == ("blocked", "bad_unit")
        on_enum = await client.write("heater", "mode", "eco", "degC")
        assert (on_enum.status, on_enum.code) == ("blocked", "bad_unit")
    assert writes(hub, "heater") == []


async def test_a_quantity_with_a_bool_or_bad_unit_is_refused(hub: Hub, rest, tokens: Tokens) -> None:
    async with rest(tokens.agent) as client:
        bool_body = {"device": "heater", "channel": "power", "value": True, "unit": "W"}
        a_bool = await client.post("/v1/write", json=bool_body)
        assert a_bool.json()["code"] == "bad_unit"
        odd_body = {"device": "heater", "action": "pulse", "args": {"seconds": {"value": 2, "unit": "parsec"}}}
        odd = await client.post("/v1/action", json=odd_body)
        assert odd.json()["code"] == "bad_unit"
    assert writes(hub, "heater") == []


async def test_a_non_finite_value_is_refused(hub: Hub, rest, tokens: Tokens) -> None:
    headers = {"content-type": "application/json"}
    async with rest(tokens.agent) as client:
        for literal in ("Infinity", "NaN", "1e999", "-Infinity"):
            body = f'{{"device": "heater", "channel": "setpoint", "value": {literal}, "unit": "degC"}}'
            response = await client.post("/v1/write", content=body, headers=headers)
            assert response.status_code == 200, literal
            assert response.json()["code"] == "bad_unit", literal
    assert writes(hub, "heater") == []


async def test_a_non_finite_quantity_argument_is_refused(transport, hub: Hub, tokens: Tokens) -> None:
    async with transport(tokens.agent) as rpc:
        await rpc.initialize()
        error = await rpc.error(
            "hal/action", {"device": "heater", "action": "pulse", "args": {"seconds": {"value": 1e999, "unit": "s"}}}
        )
        assert error["data"]["name"] in ("INVALID_PARAMS", "UNIT_INVALID")
    assert writes(hub, "heater") == []


async def test_mcp_write_needs_the_unit_beside_the_number(
    hub: Hub, mcp_tools: Callable[[str], Tools], tokens: Tokens
) -> None:
    tools = mcp_tools(tokens.agent)
    missing = await tools.write("heater", "setpoint", 20.0)
    assert (missing.status, missing.code) == ("blocked", "bad_unit")
    ok = await tools.write("heater", "setpoint", 20.0, "degC")
    assert ok.status == "done"
    assert ("write", "setpoint", 20.0) in writes(hub, "heater")


async def test_action_run_limit_blocks_the_third_call(kernel: Kernel, add: AddDevice) -> None:
    driver = await add(RUNS)
    for _ in range(2):
        decision = await kernel.execute(Action(device="pulser", action="pulse", args={"seconds": "2 s"}), human())
        assert decision.status == "done"
    third = await kernel.execute(Action(device="pulser", action="pulse", args={"seconds": "2 s"}), human())
    assert (third.status, third.code) == ("blocked", "rate_limited")
    ran = [entry for entry in driver.hardware_writes() if entry[0] == "action"]
    assert len(ran) == 2


async def test_the_run_limit_survives_a_restart() -> None:
    audit = AuditLog()
    clock = FakeClock()
    file = loads(RUNS)

    first = Kernel(audit, clock=clock)
    first.register(file, MockDriver(file))
    await first.connect("pulser")
    for _ in range(2):
        decision = await first.execute(Action(device="pulser", action="pulse", args={"seconds": "2 s"}), human())
        assert decision.status == "done"

    second = Kernel(audit, clock=clock)
    driver = MockDriver(file)
    second.register(file, driver)
    await second.connect("pulser")
    after_restart = await second.execute(Action(device="pulser", action="pulse", args={"seconds": "2 s"}), human())
    assert (after_restart.status, after_restart.code) == ("blocked", "rate_limited"), (
        "restarting the hub reset the run window, so an agent could loop the hub to keep running the action"
    )
    assert [entry for entry in driver.hardware_writes() if entry[0] == "action"] == []
