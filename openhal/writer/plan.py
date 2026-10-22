"""Staged write tests (driver writer, step 8).

The plan reads every channel first, then tries each write channel once at the smallest change from
its safe value, then returns it to safe, then tests the stop. Every write step needs a person's
approval and nothing here runs it. `validate` replays the write steps through a real kernel with
the mock driver and the confirmed draft, so a plan that the kernel would block is caught now
instead of on the bench.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from openhal.kernel.commands import Write
from openhal.kernel.kernel import Kernel
from openhal.kernel.principals import human
from openhal.spec.models import DeviceFile


@dataclass(frozen=True)
class TestStep:
    __test__ = False  # not a pytest class

    step: int
    command: dict[str, Any] | str
    expected: str
    needs_approval: bool

    def view(self) -> dict[str, Any]:
        return {
            "step": self.step,
            "command": self.command,
            "expected": self.expected,
            "needs_approval": self.needs_approval,
        }


def _safe_values(file: DeviceFile) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for step in file.safe_state:
        values.update(step.values)
    return values


def _first_value(file: DeviceFile, name: str, safe: Any) -> Any:
    """The smallest change away from the safe value that the limits and the rate allow in one second."""
    spec = file.write[name]
    if spec.type == "bool":
        return not bool(safe) if safe is not None else True
    if spec.type == "enum":
        others = [value for value in spec.values if value != safe]
        return others[0] if others else safe
    if spec.type != "number" or spec.min is None or spec.max is None:
        return None
    start = float(safe) if isinstance(safe, int | float) else spec.min
    span = spec.max - spec.min
    step = spec.step or max(span / 100, 1e-9)
    if spec.max_change_per_s:
        step = min(step, spec.max_change_per_s)
    upward = start + step <= spec.max
    value = start + step if upward else start - step
    return round(value, 6)


def _show(value: Any, unit: str | None) -> Any:
    if isinstance(value, bool) or unit is None or unit == "dimensionless":
        return value
    return f"{value:g} {unit}"


def build(file: DeviceFile) -> list[TestStep]:
    steps: list[TestStep] = []
    device = file.device_id

    def add(command: dict[str, Any] | str, expected: str, approval: bool) -> None:
        steps.append(TestStep(len(steps) + 1, command, expected, approval))

    for name, spec in file.read.items():
        add(
            {"kind": "read", "device": device, "channel": name},
            f"A plausible {name} reading{f' in {spec.unit}' if spec.unit else ''}, and nothing changes on the device.",
            False,
        )
    safe = _safe_values(file)
    for name, write_spec in file.write.items():
        add({"kind": "read", "device": device, "channel": name}, f"The current {name}. Nothing changes.", False)
        value = _first_value(file, name, safe.get(name))
        if value is None:
            continue
        add(
            {"kind": "write", "device": device, "channel": name, "value": _show(value, write_spec.unit)},
            f"{name} reads back {_show(value, write_spec.unit)}. Watch the device and stop it if anything else moves.",
            True,
        )
        if name in safe:
            add(
                {"kind": "write", "device": device, "channel": name, "value": _show(safe[name], write_spec.unit)},
                f"{name} is back at its safe value {_show(safe[name], write_spec.unit)}.",
                True,
            )
    if file.write:
        add("openhal stop", "Every channel goes to its safe value and the stop result says safe.", True)
        add("openhal unlock", "Writes are allowed again after you type unlock.", True)
    return steps


async def validate(file: DeviceFile, steps: list[TestStep]) -> list[str]:
    """Problems the kernel finds when it dry-runs the plan's writes. Nothing reaches a device.

    Each write is checked on its own, a minute after the one before, the way a person walks through
    the plan. The stand-in device is the mock driver starting at the safe values.
    """
    from openhal.drivers.base import Reading
    from openhal.drivers.mock.driver import MockDriver
    from openhal.spec.loader import DeviceFileError, from_data

    data = file.model_dump(mode="json", by_alias=True, exclude={"extensions"}, exclude_none=True)
    data["connect"] = {"mock": "test-plan", "initial": _safe_values(file)}
    try:
        stand_in = from_data(data)
        if file.writable and isinstance(data.get("confirmed"), dict):
            # The stand-in only differs in connect. Rebind its confirmation so it is as writable as the file.
            data["confirmed"]["sha256"] = stand_in.limits_sha256()
            stand_in = from_data(data)
    except DeviceFileError as exc:
        return ["The plan could not be checked. " + " ".join(exc.problems)]
    now = [1_000_000.0]
    kernel = Kernel(clock=lambda: now[0])
    kernel.register(stand_in, MockDriver(stand_in))
    device = stand_in.device_id
    await kernel.connect(device)
    problems = []
    for step in steps:
        command = step.command
        if not isinstance(command, dict) or command.get("kind") != "write":
            continue
        now[0] += 60
        decision = kernel.dry_run(
            [Write(device=device, channel=command["channel"], value=command["value"])], human("test plan")
        )[0]
        if decision.status == "blocked":
            problems.append(f"Step {step.step} would be blocked. {decision.message}")
            continue
        unit = stand_in.channel_unit(command["channel"])
        kernel.note_reading(device, Reading(command["channel"], decision.value, unit, at=now[0]))
    return problems
