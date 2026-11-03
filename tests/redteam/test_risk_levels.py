"""Red team. Every way an agent could try to slip past the risk levels (ADR 0023).

The hub runs a simulated OpenHAL board whose device file maps a heater to pin 5, the same pin the
board lists as free, plus a kiln with odd units. Each test is one way in. Every attempt must end
with nothing reaching the heater's pin and no level going down.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any

import pytest

from openhal.drivers.base import DriverError
from openhal.drivers.openhal_firmware.driver import OpenHalFirmwareDriver
from openhal.drivers.openhal_firmware.simulator import SIMULATORS, FirmwareSimulator, SimChannel
from openhal.hub.config import HubConfig
from openhal.hub.hub import Hub
from openhal.mcp import TOOL_NAMES, Tools
from openhal.mcp.tools import RunStep
from openhal.spec import loads, risk
from openhal.writer.engine import force_suggested
from tests.kernel.conftest import FakeClock
from tests.redteam.conftest import Rest, Tokens

BENCH = """\
openhal: "0.1"
device: Bench board
id: bench
connect: { openhal-firmware: "sim:rt-bench", timeout_s: 0.5 }
write:
  brightness: { unit: percent, min: 0, max: 100, suggested: true, map: { pin: 2 } }
  heater: { unit: percent, min: 0, max: 100, suggested: true, map: { pin: 5 } }
  pin5: { type: bool, suggested: true, map: { pin: 5, mode: out } }
  pin5_pwm: { unit: percent, min: 0, max: 100, suggested: true, map: { pin: 5, mode: pwm } }
  pin5_mode:
    type: enum
    values: [input, input_pullup, output, pwm]
    suggested: true
    map: { pin: 5, mode: mode }
  pin6_pwm: { unit: percent, min: 0, max: 100, suggested: true, map: { pin: 6, mode: pwm } }
safe_state: { brightness: 0, heater: 0 }
provenance: { source: self-described }
"""

KILN = """\
openhal: "0.1"
device: Kiln controller
id: kiln
connect: { mock: kiln }
write:
  heat_level: { unit: dimensionless, min: 0, max: 255 }
  boiler: { unit: mol, min: 0, max: 1 }
  brightness: { unit: dimensionless, min: 0, max: 255 }
  glow: { unit: percent, min: 0, max: 100 }
safe_state: { heat_level: 0, boiler: 0, brightness: 0, glow: 0 }
"""


def bench_board() -> FirmwareSimulator:
    return FirmwareSimulator(
        product="rt-bench",
        heartbeat_ms=0,
        channels={
            "brightness": SimChannel("brightness", "percent", 0.0, writable=True, maximum=100, pin=2),
            "heater": SimChannel("heater", "percent", 0.0, writable=True, maximum=100),
        },
        pins={5: "iuop", 6: "iuop"},
    )


@pytest.fixture
async def hub(tmp_path: Path, clock: FakeClock) -> AsyncIterator[Hub]:
    devices = tmp_path / "devices"
    devices.mkdir()
    (devices / "bench.hal.yaml").write_text(BENCH)
    (devices / "kiln.hal.yaml").write_text(KILN)
    SIMULATORS["rt-bench"] = bench_board()
    hub = Hub(HubConfig(home=tmp_path), clock=clock, in_memory=True)
    await hub.start()
    clock.advance(60)
    yield hub
    await hub.close()
    SIMULATORS.pop("rt-bench", None)


def board() -> FirmwareSimulator:
    return SIMULATORS["rt-bench"]


async def write(tools: Tools, device: str, channel: str, value: Any, unit: str | None = None) -> Any:
    return await tools.write(device, channel, value, unit)


def error_name(result: Any) -> str | None:
    return result.error.name if result.error is not None else None


async def test_an_agent_never_lowers_a_level(hub: Hub, tokens: Tokens, rest: Rest) -> None:
    for token in (tokens.agent, tokens.low, tokens.reader):
        async with rest(token) as agent:
            for level in ("low", "medium"):
                result = (
                    await agent.post("/v1/risk", json={"device": "bench", "name": "heater", "level": level})
                ).json()
                assert (result["status"], result["code"]) == ("blocked", "not_permitted")
            assert (
                await agent.post(
                    "/v1/risk", json={"device": "bench", "name": "heater", "level": "low", "phrase": "confirm"}
                )
            ).json()["code"] == "not_permitted"
    async with rest(tokens.human) as person:
        held = (await person.post("/v1/risk", json={"device": "bench", "name": "heater", "level": "low"})).json()
    assert held["status"] == "pending"
    async with rest(tokens.agent) as agent:
        approve = await agent.post(f"/v1/confirmations/{held['request_id']}/approve", json={"phrase": "approve"})
        assert approve.status_code == 403
        assert (await agent.post("/v1/runs", json={"steps": [{"kind": "risk", "device": "bench"}]})).status_code == 422
    assert risk.level(hub.kernel.devices["bench"].file, "write:heater") == "high"
    assert not [name for name in TOOL_NAMES if "risk" in name and name != "describe_device"]
    drafted = force_suggested(loads(BENCH).model_dump(mode="json", by_alias=True, exclude={"extensions"}))
    drafted["write"]["heater"]["risk"] = {"level": "low", "by": "owner", "at": "2026-11-03"}
    assert force_suggested(drafted)["write"]["heater"]["risk"] == "low"
    assert (
        risk.level(loads(BENCH.replace("map: { pin: 5 } }", "map: { pin: 5 }, risk: low }")), "write:heater") == "high"
    )


async def test_a_pin_on_a_heater_s_pin_is_as_high_as_the_heater(
    hub: Hub, tokens: Tokens, mcp_tools: Callable[[str], Tools]
) -> None:
    agent = mcp_tools(tokens.agent)
    for channel, value, unit in (("pin5", True, None), ("pin5_pwm", 50, "%"), ("pin5_mode", "output", None)):
        result = await write(agent, "bench", channel, value, unit)
        assert error_name(result) == "UNVERIFIED_LIMITS", channel
    planned = await agent.dry_run("bench", channel="pin5_pwm", value=50, unit="%")
    assert (planned.status, planned.code) == ("blocked", "read_only_file")
    run = await agent.run_steps([RunStep(kind="write", device="bench", channel="pin5", value=True)])
    assert (run.status, run.error.name if run.error else None) == ("blocked", "UNVERIFIED_LIMITS")
    assert (await write(agent, "bench", "pin6_pwm", 30, "%")).error is None
    assert 5 not in board().pin_state
    assert board().pin_state == {6: "pwm"}
    shared = risk.assess(hub.kernel.devices["bench"].file)["write:pin5_pwm"]
    assert "write:heater" in shared.shared_with


async def test_an_odd_or_missing_unit_only_raises(hub: Hub, tokens: Tokens, mcp_tools: Callable[[str], Tools]) -> None:
    levels = risk.assess(hub.kernel.devices["kiln"].file)
    assert [levels[f"write:{name}"].level for name in ("heat_level", "boiler", "brightness", "glow")] == [
        "high",
        "high",
        "medium",
        "low",
    ]
    agent = mcp_tools(tokens.agent)
    for channel in ("heat_level", "boiler"):
        result = await write(agent, "kiln", channel, 1, "dimensionless" if channel == "heat_level" else "mol")
        assert error_name(result) == "UNVERIFIED_LIMITS", channel
    helper = mcp_tools(tokens.low)
    missing = await write(helper, "kiln", "brightness", 10, "dimensionless")
    assert error_name(missing) == "SCOPE_DENIED", "a missing unit lifted it to medium"
    assert (await write(helper, "kiln", "glow", 10, "%")).error is None


async def test_a_mode_change_never_reaches_a_high_pin(
    hub: Hub, tokens: Tokens, mcp_tools: Callable[[str], Tools]
) -> None:
    agent = mcp_tools(tokens.agent)
    for mode in ("output", "pwm", "input_pullup", "input"):
        result = await write(agent, "bench", "pin5_mode", mode)
        assert error_name(result) == "UNVERIFIED_LIMITS", mode
    assert 5 not in board().pin_state
    SIMULATORS["rt-claimed"] = FirmwareSimulator(
        product="rt-claimed",
        heartbeat_ms=0,
        channels={"heater": SimChannel("heater", "percent", 0.0, writable=True, maximum=100, pin=5)},
        pins={5: "iuop", 6: "iuop"},
    )
    try:
        driver = OpenHalFirmwareDriver(loads('device: Claimed\nconnect: { openhal-firmware: "sim:rt-claimed" }\n'))
        await driver.connect()
        described = await driver.describe()
        assert described is not None
        assert "pin5_mode" not in described["write"], "the board keeps the heater's pin to itself"
        assert described["write"]["heater"]["map"] == {"pin": 5}
        for words in (("5", "out", "1"), ("5", "pwm", "10"), ("5", "pullup")):
            with pytest.raises(DriverError, match="unknown pin"):
                await driver._require_link().request("PIN", *words)
        await driver.close()
    finally:
        SIMULATORS.pop("rt-claimed", None)


async def test_a_level_raised_during_a_run_stops_the_run(
    hub: Hub, clock: FakeClock, tokens: Tokens, rest: Rest, mcp_tools: Callable[[str], Tools]
) -> None:
    step = asyncio.Event()

    async def sleep(seconds: float) -> None:
        step.set()
        clock.advance(seconds)
        await asyncio.sleep(0.05)

    hub.runs._sleep = sleep
    fade = RunStep(kind="write", device="bench", channel="brightness", value=0, unit="%", increment=10)
    run = await mcp_tools(tokens.agent).run_steps([fade, RunStep(kind="wait", seconds=0.2)], repeat=10, wait_s=0)
    await asyncio.wait_for(step.wait(), 5)
    async with rest(tokens.human) as person:
        raised = (await person.post("/v1/risk", json={"device": "bench", "name": "brightness", "level": "high"})).json()
    assert raised["status"] == "done"
    async with rest(tokens.agent) as agent:
        ended = (await agent.get(f"/v1/runs/{run.run_id}", params={"wait_s": 10})).json()
    assert ended["status"] == "blocked"
    assert ended["stop"]["code"] == "read_only_file"
    sent = board().channels["brightness"].value
    assert sent < 100, "the fade stopped at the step after the level went up"
    entries = [entry for entry in hub.audit.entries(event="write", device="bench") if entry.status == "done"]
    assert len(entries) < 10
