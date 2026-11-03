"""An agent uses the general MCP tools on mock devices it has never seen (docs/demo/general-tools.yaml).

`run()` starts a hub with a mock lamp and a mock warming plate on a free loopback port, then starts
`openhal mcp` with an agent token and talks to the server over stdio as an MCP client. The agent
finds its targets with find, blinks the lamp five times with run_steps, warms the plate and waits
until the plate passes a temperature, samples the plate, has a run that breaks a limit stopped at
that step, and ends a long run with stop_all. Nothing touches hardware.

`uv run python -m openhal.demo.general --record docs/demo/general-tools.yaml` saves the transcript.
The transcript keeps the calls, the statuses, codes and counts, and drops ids and times.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import tempfile
from pathlib import Path
from typing import Any, Final

import yaml

from openhal.client import AsyncClient
from openhal.demo import rig
from openhal.drivers.mock import MockDriver
from openhal.hub.hub import Hub

RECORDED_WITH: Final = "uv run python -m openhal.demo.general --record docs/demo/general-tools.yaml"
RECORD_PATH: Final = Path(__file__).resolve().parents[2] / "docs" / "demo" / "general-tools.yaml"
DEVICES: Final = {
    "lamp": """\
device: Signal lamp
id: lamp
connect: { mock: lamp }
write:
  on: { type: bool }
  brightness: { unit: "%", min: 0, max: 100, max_change_per_s: 50 }
safe_state: { on: false, brightness: 0 }
hazard: low
confirmed: { by: owner, at: 2026-11-02 }
""",
    "warmer": """\
device: Warming plate
id: warmer
connect: { mock: warmer, simulate: heater, ambient_c: 22 }
read:
  temp: { unit: degC }
write:
  power: { unit: W, min: 0, max: 20, max_change_per_s: 10 }
safe_state: { power: 0 }
hazard: low
confirmed: { by: owner, at: 2026-11-02 }
""",
}
BLINK: Final = [
    {"kind": "write", "device": "lamp", "channel": "on", "value": True},
    {"kind": "wait", "seconds": 0.2},
    {"kind": "write", "device": "lamp", "channel": "on", "value": False},
    {"kind": "wait", "seconds": 0.2},
]


def _expect(condition: bool, message: str) -> None:
    if not condition:
        raise rig.DemoError(message)


def _round(value: Any) -> Any:
    return round(value, 2) if isinstance(value, float) else value


def _readings(readings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {"target": f"{item['device']}.{item['channel']}", "value": _round(item.get("value")), "unit": item.get("unit")}
        for item in readings
    ]


def _run(run: dict[str, Any]) -> dict[str, Any]:
    shown = {key: run[key] for key in ("status", "message", "total_steps", "done_steps")}
    if run.get("stop"):
        shown["stop"] = {key: run["stop"].get(key) for key in ("index", "step", "iteration", "kind", "code")}
    if run.get("error"):
        shown["error"] = {key: run["error"][key] for key in ("code", "name", "message")}
    return shown


def _lamp_writes(hub: Hub) -> list[Any]:
    driver = hub.kernel.devices["lamp"].driver
    assert isinstance(driver, MockDriver)
    return [value for kind, channel, value in driver.hardware_writes() if kind == "write" and channel == "on"]


async def _session(agent: rig.Agent, hub: Hub) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = []

    async def call(step_id: str, tool: str, arguments: dict[str, Any]) -> Any:
        result = await agent.call(tool, arguments)
        steps.append({"id": step_id, "tool": tool, "arguments": json.loads(json.dumps(arguments))})
        return result

    found = await call("find-temperature", "find", {"text": "temperature"})
    steps[-1]["targets"] = [match["target"] for match in found["matches"]]
    _expect(steps[-1]["targets"] == ["warmer.temp"], f"find matched {steps[-1]['targets']}")
    found = await call("find-writable-percent", "find", {"kind": "writable", "unit": "%"})
    steps[-1]["targets"] = [match["target"] for match in found["matches"]]
    _expect(steps[-1]["targets"] == ["lamp.brightness"], f"find matched {steps[-1]['targets']}")

    blink = await call("blink-five-times", "run_steps", {"steps": BLINK, "repeat": 5, "wait_s": 10})
    steps[-1]["run"] = _run(blink)
    steps[-1]["lamp_received"] = _lamp_writes(hub)
    _expect(blink["status"] == "done" and blink["done_steps"] == 20, f"the blink run ended {blink['message']}")
    _expect(steps[-1]["lamp_received"] == [True, False] * 5, "the lamp did not blink five times")

    warm_steps: list[dict[str, Any]] = [
        {"kind": "wait", "seconds": 1},
        {"kind": "write", "device": "warmer", "channel": "power", "value": 10, "unit": "W"},
    ]
    warm = await call("warm-the-plate", "run_steps", {"steps": warm_steps})
    steps[-1]["run"] = _run(warm)
    _expect(warm["status"] == "done", f"the warming run ended {warm['message']}")

    waited = await call(
        "wait-until-warm", "wait_until", {"condition": "warmer.temp > 28 degC", "timeout_s": 20, "interval_s": 0.2}
    )
    steps[-1] |= {"held": waited["held"], "checks": waited["checks"], "readings": _readings(waited["readings"])}
    _expect(waited["held"], "the plate never passed 28 degC")

    sampled = await call("sample-the-plate", "sample", {"targets": ["warmer.temp"], "duration_s": 1, "interval_s": 0.2})
    series = sampled["series"][0]
    steps[-1]["series"] = {key: _round(series[key]) for key in ("target", "unit", "count", "min", "max", "mean")}
    _expect(series["count"] == 6 and series["max"] > series["min"], "the sample did not show the plate warming")

    too_bright = [
        {"kind": "write", "device": "lamp", "channel": "brightness", "value": 40, "unit": "%"},
        {"kind": "wait", "seconds": 1},
        {"kind": "write", "device": "lamp", "channel": "brightness", "value": 150, "unit": "%"},
    ]
    blocked = await call("run-past-a-limit", "run_steps", {"steps": too_bright})
    steps[-1]["run"] = _run(blocked)
    _expect(blocked["status"] == "blocked" and blocked["stop"]["step"] == 2, f"the run ended {blocked['message']}")

    long_run = await call("start-a-long-run", "run_steps", {"steps": BLINK, "repeat": 50, "wait_s": 0})
    steps[-1]["run"] = {key: long_run[key] for key in ("status", "total_steps")}
    _expect(long_run["status"] == "running", "the long run did not keep running")
    await asyncio.sleep(0.5)
    report = await call("stop-everything", "stop_all", {"reason": "end of the demo"})
    steps[-1]["devices"] = {item["device"]: item["status"] for item in report["devices"]}
    ended = await call("the-long-run-ended", "get_run", {"run_id": long_run["run_id"], "wait_s": 10, "last": 0})
    steps[-1]["arguments"] = {"run_id": "RUN_ID", "wait_s": 10, "last": 0}
    steps[-1]["run"] = {"status": ended["status"], "code": ended["stop"]["code"], "message": ended["message"]}
    steps[-1]["ran_before_the_stop"] = "fewer than all 200 steps" if ended["done_steps"] < 200 else "every step"
    _expect((ended["status"], ended["stop"]["code"]) == ("cancelled", "stopped"), "the stop did not end the run")
    return steps


async def run() -> dict[str, Any]:
    """Run the whole session once and return the transcript."""
    with tempfile.TemporaryDirectory(prefix="openhal-general-") as folder:
        home = Path(folder)
        person = rig.set_up_home(home, "owner")
        for name, text in DEVICES.items():
            (home / "devices" / f"{name}.hal.yaml").write_text(text, encoding="utf-8")
        async with rig.serving(home) as (hub, url):
            async with AsyncClient(url, person, use_human_token_file=False) as owner:
                token = (await owner.create_token("ai-client", kind="agent", scope="control_low")).token
            async with rig.mcp_session(url, token, home) as agent:
                steps = await _session(agent, hub)
    return {"recorded_with": RECORDED_WITH, "agent": "agent:ai-client, scope control_low", "steps": steps}


def dump(record: dict[str, Any]) -> str:
    return yaml.safe_dump(record, sort_keys=False, allow_unicode=True, width=200)


def read(path: Path = RECORD_PATH) -> dict[str, Any]:
    data: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run the general MCP tools against mock devices.")
    parser.add_argument("--record", type=Path, help="Save the transcript as YAML.")
    options = parser.parse_args(argv)
    text = dump(asyncio.run(run()))
    if options.record is not None:
        options.record.write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
