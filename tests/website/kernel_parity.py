"""Run the website's kernel parity cases through the real Python kernel.

Each case registers example device files on the mock driver with a fixed clock, applies its
steps (time passing, readings, executed commands, stops, approvals) and then evaluates or executes
one command. The results are what the TypeScript port in website/src/lib/kernel must reproduce.
Every decision also records its protocol form from openhal.protocol.convert, the Decision object
with its registry error, so the playground answers exactly as the hub does.

Run `uv run python -m tests.website.kernel_parity` to rewrite expected.json after a kernel change.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from openhal.drivers.base import Reading
from openhal.drivers.mock import MockDriver
from openhal.kernel import Kernel
from openhal.kernel.checks import Block
from openhal.kernel.commands import Action, Command, Decision, Write
from openhal.kernel.principals import Principal, human
from openhal.protocol import convert
from openhal.spec import loads
from openhal.spec.models import DeviceFile
from tests.kernel.conftest import FakeClock

ROOT = Path(__file__).resolve().parents[2]
PARITY = ROOT / "website" / "tests" / "kernel-parity"
CASES = PARITY / "cases.json"
EXPECTED = PARITY / "expected.json"
CLOCK_START = 1000.0


def load_cases() -> dict[str, Any]:
    return json.loads(CASES.read_text(encoding="utf-8"))


def device_text(spec: dict[str, Any], name: str) -> str:
    if name in spec["files"]:
        return (ROOT / spec["files"][name]).read_text(encoding="utf-8")
    return spec["inline"][name]


def initial_values(file: DeviceFile, overrides: dict[str, Any]) -> dict[str, Any]:
    """Every channel's starting value, so the mock driver never has to guess one."""
    values: dict[str, Any] = {}
    for name, channel in file.write.items():
        if channel.type == "number":
            values[name] = channel.min
        elif channel.type == "bool":
            values[name] = False
        elif channel.type == "enum":
            values[name] = channel.values[0]
        else:
            values[name] = ""
    for name, read in file.read.items():
        if read.type == "number":
            values[name] = 0.0
        elif read.type == "bool":
            values[name] = False
        elif read.type == "enum":
            values[name] = read.values[0]
        elif read.type == "string":
            values[name] = ""
    values.update(overrides)
    return values


def mock_driver(file: DeviceFile, overrides: dict[str, Any]) -> MockDriver:
    data = file.model_dump(by_alias=True, exclude={"extensions"})
    data["connect"] = {"driver": "mock", "params": {"initial": initial_values(file, overrides)}}
    return MockDriver(DeviceFile.model_validate(data))


def command_of(data: dict[str, Any]) -> Command:
    if "action" in data:
        return Action(device=data["device"], action=data["action"], args=data.get("args", {}))
    return Write(device=data["device"], channel=data["channel"], value=data["value"])


def principal_of(spec: dict[str, Any], key: str) -> Principal:
    item = spec["principals"][key]
    return Principal(item["kind"], item["name"], item["scope"])


def decided(decision: Decision) -> dict[str, Any]:
    return {"status": decision.status, "code": decision.code, "message": decision.message}


def standin_hub(kernel: Kernel) -> Any:
    """Enough of a hub for openhal.protocol.convert, with each file named <id>.hal.yaml."""
    info = {device: SimpleNamespace(path=f"{device}.hal.yaml") for device in kernel.devices}
    return SimpleNamespace(kernel=kernel, info=info)


def on_the_wire(kernel: Kernel, decision: Decision, command: Command, principal: Principal) -> dict[str, Any]:
    wire = convert.decision(standin_hub(kernel), decision, command, principal=principal.label).wire()
    if decision.request_id:
        wire = json.loads(json.dumps(wire).replace(decision.request_id, "REQUEST_ID"))
    return {**decided(decision), "wire": wire}


async def run_case(spec: dict[str, Any], case: dict[str, Any]) -> dict[str, Any]:
    clock = FakeClock(CLOCK_START)
    kernel = Kernel(clock=clock, approval_key=b"website-parity-approval-key-32b!")
    principal = principal_of(spec, case.get("principal", "agent"))
    for entry in case["devices"]:
        name, connect = (entry, True) if isinstance(entry, str) else (entry["name"], entry.get("connect", True))
        file = loads(device_text(spec, name))
        kernel.register(file, mock_driver(file, case.get("initial", {}).get(file.device_id, {})))
        if connect:
            await kernel.connect(file.device_id)
    steps: list[dict[str, Any]] = []
    for step in case.get("steps", []):
        steps.extend(await run_step(spec, kernel, clock, principal, step))
    command = command_of(case["command"])
    if case.get("run") == "execute":
        result = await kernel.execute(command, principal)
    else:
        result = kernel.evaluate(command, principal)
    return {"id": case["id"], "steps": steps, "result": on_the_wire(kernel, result, command, principal)}


async def run_step(
    spec: dict[str, Any], kernel: Kernel, clock: FakeClock, principal: Principal, step: dict[str, Any]
) -> list[dict[str, Any]]:
    if "advance" in step:
        clock.advance(step["advance"])
        return []
    if "execute" in step:
        results = []
        command = command_of(step["execute"])
        for _ in range(step.get("repeat", 1)):
            results.append(on_the_wire(kernel, await kernel.execute(command, principal), command, principal))
        return results
    if "reading" in step:
        item = step["reading"]
        unit = item.get("unit") or kernel.devices[item["device"]].file.channel_unit(item["channel"])
        kernel.note_reading(item["device"], Reading(channel=item["channel"], value=item["value"], unit=unit))
        return []
    if "mark_unknown" in step:
        device, channel = step["mark_unknown"].split(".", 1)
        kernel.devices[device].mark_unknown(channel, clock())
        return []
    if "stop" in step:
        report = await kernel.stop_all(principal_of(spec, step["stop"]), "parity stop")
        return [{"status": "stop", "devices": [[item.device, item.status] for item in report.devices]}]
    if "unlock" in step:
        kernel.unlock(human(), step["unlock"])
        return []
    if "tighten" in step:
        item = dict(step["tighten"])
        device, channel = item.pop("device"), item.pop("channel")
        try:
            limits = kernel.tighten(principal, device, channel, **item)
        except Block as block:
            return [{"status": "blocked", "code": block.code, "message": block.message}]
        except LookupError as exc:
            return [{"status": "error", "code": None, "message": str(exc)}]
        return [{"status": "tightened", "limits": limits}]
    if "approve" in step:
        request = kernel.pending()[-1]
        return [decided(await kernel.confirm(request.request_id, human()))]
    if "unregister" in step:
        kernel.unregister(step["unregister"])
        return []
    if "disconnect" in step:
        await kernel.connection_lost(step["disconnect"], "parity disconnect")
        return []
    if "tick" in step:
        return [{"status": "tick", "fired": await kernel.tick()}]
    raise ValueError(f"Unknown parity step {step!r}.")


def run_all() -> dict[str, Any]:
    spec = load_cases()

    async def every_case() -> list[dict[str, Any]]:
        return [await run_case(spec, case) for case in spec["cases"]]

    hashes = {path: loads((ROOT / path).read_text(encoding="utf-8")).limits_sha256() for path in spec["hashes"]}
    for name, text in spec["inline"].items():
        hashes[f"inline:{name}"] = loads(text).limits_sha256()
    return {"cases": asyncio.run(every_case()), "hashes": hashes}


def render(results: dict[str, Any]) -> str:
    return json.dumps(results, indent=2, ensure_ascii=False) + "\n"


if __name__ == "__main__":
    EXPECTED.write_text(render(run_all()), encoding="utf-8")
    print(f"Wrote {EXPECTED.relative_to(ROOT)}")
