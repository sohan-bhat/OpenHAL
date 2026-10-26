"""Run the whole system on mocks, end to end, and record what happened (`openhal demo --full`).

`run()` makes a temporary home, plugs in the simulated plant waterer as `sim:plant-waterer` and
starts a real hub on a loopback port with an empty devices folder (openhal/demo/rig.py). Nothing
touches hardware.

1. Discovery. The person asks the hub to discover boards. The driver probes the ports listed in
   OPENHAL_FIRMWARE_PORTS and finds the plant waterer as an openhal-firmware device.
2. Driver writer. The person starts the writer on that board and on
   examples/plant-waterer/plant-waterer.ino, whether or not the device library knows the board.
3. Limits interview. A script answers every question as the person, through the same calls
   `openhal writer interview` and `openhal writer finish` make. The hub then restarts, so it loads
   the saved file from its devices folder.
4. Agent. `openhal mcp` runs with an agent token and a real MCP client session talks to it over
   stdio. The agent reads soil moisture and drafts a routine that waters below 40 %. The person
   enables it with the human token, the routine waters and soil moisture rises.
5. Limit. The agent asks for a 120 s watering and gets LIMIT_EXCEEDED. Nothing reaches the board.

The record keeps what the hub, the board and the MCP server answered. The only time in it is the
date the person confirmed the limits. `stable()` masks that date, so two runs compare equal.
"""

from __future__ import annotations

import asyncio
import json
import re
import tempfile
import time
from pathlib import Path
from typing import Any, Final

import yaml

from openhal.client import AsyncClient, models
from openhal.demo import plant
from openhal.demo.rig import (
    MCP_COMMAND,
    Agent,
    Board,
    DemoError,
    mcp_session,
    plugged_in,
    running_hub,
    set_up_home,
)
from openhal.drivers.openhal_firmware.simulator import PlantWatererSimulator
from openhal.hub.views import quantity
from openhal.protocol.version import LATEST

DEVICE: Final = plant.DEVICE
FILE_NAME: Final = plant.FILE_NAME
DRIVER: Final = "openhal-firmware"
SKETCH: Final = "plant-waterer.ino"
PERSON: Final = "owner"
AGENT: Final = "claude"
AGENT_SCOPE: Final = "control_low"
SPEED: Final = plant.SPEED
WAIT_S: Final = 30.0
E2E_PATH: Final = Path("docs") / "demo" / "e2e.yaml"
RECORDED_WITH: Final = "uv run openhal demo --full --record docs/demo/e2e.yaml"
DATE_MASK: Final = "<confirmed on>"

ROUTINE_ID: Final = "water-when-dry"
ROUTINE: Final = """\
id: water-when-dry
description: Water for 20 s when the soil is drier than 40 %.
triggers:
  - when: "plant-waterer.soil_moisture < 40 %"
steps:
  - action: { device: plant-waterer, action: water, args: { duration: { value: 20, unit: s } } }
"""

ANSWERS: Final = {
    "device.hazard": "low",
    "water.duration.min": "1 s",
    "water.duration.max": "30 s",
    "water.require": "tank == ok because pump can't run while tank is empty",
    "water.max_runs": "3 per 1 h",
    "water.confirm": "none",
    "stop.require": "none",
    "stop.max_runs": "none",
    "stop.confirm": "none",
    "device.safe_action": "stop",
    "device.interlocks": "none",
}
"""What the person answers, by question id. A question missing here stops the demo."""


async def run(*, speed: float = SPEED) -> dict[str, Any]:
    """Run the whole demo once and return the record."""
    simulator = PlantWatererSimulator(speed=speed)
    board = Board(simulator)
    longest = 30.0 / speed + WAIT_S
    with tempfile.TemporaryDirectory(prefix="openhal-e2e-") as folder, plugged_in(DEVICE, simulator) as port:
        home = Path(folder) / "home"
        person_token = set_up_home(home, PERSON)
        async with running_hub(home) as url, AsyncClient(url, person_token, use_human_token_file=False) as person:
            agent = await person.create_token(AGENT, kind="agent", scope=AGENT_SCOPE)
            steps = await _set_up(person, board, port)
        async with (
            running_hub(home) as url,
            AsyncClient(url, person_token, use_human_token_file=False) as person,
            mcp_session(url, agent.token, home) as mcp,
        ):
            steps.append(await _restarted(person))
            steps += await _agent(mcp, person, board, longest)
    return _record(steps)


def _sources(views: list[str]) -> list[str]:
    """The labels of the data blocks a writer session read, `sketch plant-waterer.ino` and so on."""
    return [match.group(1) for view in views if (match := re.search(r'source="([^"]+)"', view))]


async def _set_up(person: AsyncClient, board: Board, port: str) -> list[dict[str, Any]]:
    """Discovery, the driver writer and the limits interview, all done by the person."""
    who = f"human:{PERSON}"
    board.mark()
    discovered = await person.discover([DRIVER])
    candidates: list[models.Match | models.Unknown] = [*discovered.matched, *discovered.unknown]
    found = next((item for item in candidates if item.address == port), None)
    if found is None:
        raise DemoError(f"Discovery didn't find the board at {port}. {discovered.model_dump(mode='json')}")
    discovery = {
        "id": "discovery",
        "actor": who,
        "call": "discover",
        "args": {"drivers": [DRIVER]},
        "found": {
            "driver": found.driver,
            "address": found.address,
            "identifiers": dict(found.identifiers),
            "label": found.label,
        },
        "board_received": board.received(),
    }

    board.mark()
    params = {"port": found.address}
    session = await person.start_writer(driver=DRIVER, params=params, sketch_path=str(plant.sketch(SKETCH)))
    if session.status != "interview" or session.draft_yaml is None:
        raise DemoError(f"The driver writer couldn't draft a file ({session.status}). {session.problems}")
    writer = {
        "id": "writer",
        "actor": who,
        "call": "start_writer",
        "args": {"driver": DRIVER, "params": params, "sketch_path": f"examples/plant-waterer/{SKETCH}"},
        "status": session.status,
        "sources": _sources(session.sources),
        "problems": session.problems,
        "draft": yaml.safe_load(session.draft_yaml),
        "board_received": board.received(),
    }

    questions = (await person.interview(session.id)).questions
    missing = [question.id for question in questions if question.id not in ANSWERS]
    if missing:
        raise DemoError(f"The interview asked {', '.join(missing)}, which the script has no answer for.")
    answers = {question.id: ANSWERS[question.id] for question in questions}
    answered = await person.answer(session.id, answers)
    if answered.status != "ready":
        raise DemoError(f"The interview didn't confirm the limits ({answered.status}). {answered.problems}")
    interview = {
        "id": "interview",
        "actor": who,
        "call": "answer",
        "answers": [
            {
                "question": question.id,
                "prompt": question.prompt,
                "suggested": question.suggested,
                "answer": answers[question.id],
            }
            for question in questions
        ],
        "status": answered.status,
        "unconfirmed": answered.unconfirmed,
    }

    saved = await person.finish(session.id, DEVICE)
    confirmed = yaml.safe_load(await asyncio.to_thread(Path(saved.path).read_text, encoding="utf-8"))
    finish = {
        "id": "save",
        "actor": who,
        "call": "finish",
        "args": {"save_as": DEVICE},
        "saved": Path(saved.path).name,
        "device": saved.device_id,
        "writable": saved.writable,
        "confirmed": {"by": confirmed["confirmed"]["by"], "at": str(confirmed["confirmed"]["at"])},
        "water": confirmed["actions"]["water"],
    }
    return [discovery, writer, interview, finish]


async def _restarted(person: AsyncClient) -> dict[str, Any]:
    devices = await person.devices()
    return {
        "id": "restart",
        "note": f"The hub restarts and loads {FILE_NAME} from its devices folder.",
        "devices": [
            {"id": item.id, "writable": item.writable, "connected": item.connected, "hazard": item.hazard}
            for item in devices
        ],
    }


def _value(reading: dict[str, Any]) -> dict[str, Any]:
    if not reading.get("ok", True):
        raise DemoError(f"The agent couldn't read soil moisture. {reading.get('error')}")
    return quantity(float(reading["value"]), str(reading["unit"]))


async def _wait_for_run(person: AsyncClient, deadline: float) -> dict[str, Any]:
    while time.monotonic() < deadline:
        routine = await person.routine(ROUTINE_ID)
        finished = [run for run in routine.history if run.status != "running"]
        if finished:
            return finished[-1].model_dump(mode="json")
        await asyncio.sleep(0.05)
    raise DemoError(f"The routine {ROUTINE_ID} didn't run after it was enabled.")


async def _agent(mcp: Agent, person: AsyncClient, board: Board, longest: float) -> list[dict[str, Any]]:
    """The agent's MCP session, the person enabling the routine, the routine's run and the refusal."""
    agent = f"agent:{AGENT}"
    via = " ".join(MCP_COMMAND)
    soil = {"device": DEVICE, "channel": "soil_moisture"}
    before = _value(await mcp.call("read", soil))
    read = {"id": "agent-reads", "actor": agent, "via": via, "tool": "read", "arguments": soil, "result": before}

    drafting = {"routine_id": ROUTINE_ID, "source": ROUTINE}
    drafted = await mcp.call("draft_routine", drafting)
    draft = {
        "id": "agent-drafts",
        "actor": agent,
        "via": via,
        "tool": "draft_routine",
        "arguments": drafting,
        "result": {
            key: drafted[key] for key in ("id", "enabled", "disabled_reason", "drafted_by", "devices", "triggers")
        },
    }
    checked = await mcp.call("run_routine_dry", {"routine_id": ROUTINE_ID})
    dry_run = {
        "id": "agent-dry-runs",
        "actor": agent,
        "via": via,
        "tool": "run_routine_dry",
        "arguments": {"routine_id": ROUTINE_ID},
        "result": {
            "ok": checked["ok"],
            "decisions": [
                {key: decision.get(key) for key in ("step", "status", "target")} for decision in checked["decisions"]
            ],
            "problems": checked["problems"],
        },
    }

    board.mark()
    enabled = await person.enable_routine(ROUTINE_ID)
    enable = {
        "id": "person-enables",
        "actor": f"human:{PERSON}",
        "call": "enable_routine",
        "args": {"routine_id": ROUTINE_ID},
        "result": {"enabled": enabled.enabled, "enabled_by": enabled.enabled_by},
    }
    deadline = time.monotonic() + longest
    ran = await _wait_for_run(person, deadline)
    await board.settle(deadline)
    routine = {
        "id": "routine-runs",
        "actor": f"routine:{ROUTINE_ID}",
        "trigger": ran["trigger"],
        "status": ran["status"],
        "commands": [
            {"target": item["target"], "status": item["status"]} for item in ran["steps"] if item.get("target")
        ],
        "board_received": board.received(),
    }
    after = _value(await mcp.call("read", soil))
    reread = {
        "id": "agent-reads-again",
        "actor": agent,
        "via": via,
        "tool": "read",
        "arguments": soil,
        "result": after,
        "soil_moisture": {"before": before, "after": after},
    }

    asking = {"device": DEVICE, "action": "water", "args": {"duration": {"value": 120, "unit": "s"}}}
    board.mark()
    decision = await mcp.call("action", asking)
    refused = {
        "id": "too-long",
        "actor": agent,
        "via": via,
        "tool": "action",
        "arguments": asking,
        "result": {key: decision.get(key) for key in ("status", "code", "error")},
        "board_received": board.received(),
    }
    return [read, draft, dry_run, enable, routine, reread, refused]


def _record(steps: list[dict[str, Any]]) -> dict[str, Any]:
    saved = step({"steps": steps}, "save")
    duration = saved["water"]["args"]["duration"]
    record = {
        "scenario": "plant-waterer-e2e",
        "recorded_with": RECORDED_WITH,
        "protocol_version": LATEST,
        "device": DEVICE,
        "file": saved["saved"],
        "person": f"human:{PERSON}",
        "agent": f"agent:{AGENT}",
        "confirmed": saved["confirmed"],
        "limits": {
            "water_duration": {
                "min": quantity(float(duration["min"]), str(duration["unit"])),
                "max": quantity(float(duration["max"]), str(duration["unit"])),
            }
        },
        "steps": steps,
    }
    plain: dict[str, Any] = json.loads(json.dumps(record))
    return plain


def stable(record: dict[str, Any]) -> Any:
    """The record with the confirmation date masked, the one field that depends on when it ran."""
    date = str(record["confirmed"]["at"])

    def mask(value: Any) -> Any:
        if isinstance(value, str):
            return value.replace(date, DATE_MASK)
        if isinstance(value, dict):
            return {key: mask(item) for key, item in value.items()}
        if isinstance(value, list):
            return [mask(item) for item in value]
        return value

    return mask(record)


def step(record: dict[str, Any], step_id: str) -> dict[str, Any]:
    """One step of a record by its id, such as `too-long`."""
    found: dict[str, Any] = next(item for item in record["steps"] if item["id"] == step_id)
    return found


class _Dumper(yaml.SafeDumper):
    """Block style for text with line breaks, such as the routine source."""


def _text(dumper: yaml.SafeDumper, value: str) -> yaml.ScalarNode:
    return dumper.represent_scalar("tag:yaml.org,2002:str", value, style="|" if "\n" in value else None)


_Dumper.add_representer(str, _text)


def dump(record: dict[str, Any]) -> str:
    """The record as YAML, in a stable order."""
    return yaml.dump(record, Dumper=_Dumper, sort_keys=False, allow_unicode=True, width=200)


def read(path: Path | None = None) -> dict[str, Any]:
    """The recorded run, from docs/demo/e2e.yaml by default."""
    target = path or Path(__file__).resolve().parents[2] / E2E_PATH
    data: dict[str, Any] = yaml.safe_load(target.read_text(encoding="utf-8"))
    return data
