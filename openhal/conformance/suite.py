"""The conformance suite. A standard battery every driver must pass against its mock or simulator.

The suite runs the driver inside a real kernel and spies on the driver's `_write` and `_action`,
so it can prove that blocked commands and grant-less calls never reach the protocol layer.
Drivers supply a `ConformanceCase`: a device file and a factory that builds the driver against
its simulator. Fault injection hooks are optional and make the timeout and disconnect checks
meaningful for that driver.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from openhal.drivers.base import Conformance, Driver, DriverError, Reading
from openhal.kernel.commands import Action, Write
from openhal.kernel.grants import GrantError
from openhal.kernel.kernel import Kernel
from openhal.kernel.principals import human
from openhal.spec.models import DeviceFile


@dataclass
class ConformanceCase:
    """How to test one driver. `make` builds a fresh driver connected to its simulator.

    `level` is the conformance level under test. It defaults to the driver's own
    `DriverInfo.conformance`, and checks above it are reported as skipped, never run (ADR 0015).
    """

    name: str
    file: DeviceFile
    make: Callable[[DeviceFile], Driver]
    break_connection: Callable[[Driver], Awaitable[None]] | None = None
    make_slow: Callable[[Driver], Awaitable[None]] | None = None
    cleanup: Callable[[], Awaitable[None]] | None = None
    level: Conformance | None = None


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str = ""
    skipped: bool = False


@dataclass
class Report:
    driver: str
    results: list[CheckResult] = field(default_factory=list)
    level: Conformance = "control"

    @property
    def ok(self) -> bool:
        return all(result.ok or result.skipped for result in self.results)

    def summary(self) -> str:
        passed = sum(result.ok for result in self.results)
        skipped = sum(result.skipped for result in self.results)
        failed = len(self.results) - passed - skipped
        return f"{self.driver} ({self.level}): {passed} passed, {failed} failed, {skipped} skipped"


LEVELS: dict[Conformance, int] = {"core": 0, "control": 1, "full": 2}


class _Spy:
    """Counts calls that reached the driver's protocol layer."""

    def __init__(self, driver: Driver) -> None:
        self.calls: list[tuple[str, Any]] = []
        original_write = driver._write  # noqa: SLF001
        original_action = driver._action  # noqa: SLF001

        async def spy_write(channel: str, value: Any) -> Reading | None:
            self.calls.append((f"write:{channel}", value))
            return await original_write(channel, value)

        async def spy_action(name: str, args: dict[str, Any]) -> Any:
            self.calls.append((f"action:{name}", args))
            return await original_action(name, args)

        driver._write = spy_write  # type: ignore[method-assign]  # noqa: SLF001
        driver._action = spy_action  # type: ignore[method-assign]  # noqa: SLF001


def _outside_value(file: DeviceFile) -> tuple[str, str] | None:
    for name, spec in file.write.items():
        if spec.type == "number" and spec.max is not None and spec.unit:
            return name, f"{spec.max + max(1.0, abs(spec.max))} {spec.unit}"
    return None


def _inside_value(file: DeviceFile) -> tuple[str, Any] | None:
    for name, spec in file.write.items():
        if spec.type == "number" and spec.min is not None and spec.unit:
            return name, f"{spec.min} {spec.unit}"
        if spec.type == "bool":
            return name, False
        if spec.type == "enum":
            return name, spec.values[0]
    return None


def _argument_value(spec: Any) -> Any:
    """A value inside an argument's limits, or None when the suite can't make one."""
    if spec.type == "number" and spec.min is not None and spec.unit:
        return f"{spec.min} {spec.unit}"
    if spec.type == "bool":
        return False
    if spec.type == "enum" and spec.values:
        return spec.values[0]
    return None


def _inside_actions(file: DeviceFile) -> list[tuple[str, dict[str, Any]]]:
    """Every action with arguments the suite can fill in, fewest arguments first."""
    found = []
    for name, spec in file.actions.items():
        args = {arg: _argument_value(arg_spec) for arg, arg_spec in spec.args.items()}
        if all(value is not None for value in args.values()):
            found.append((name, args))
    return sorted(found, key=lambda item: len(item[1]))


def _outside_action(file: DeviceFile) -> tuple[str, dict[str, Any]] | None:
    """An action call with one numeric argument above its max and the rest inside their limits."""
    for name, spec in file.actions.items():
        for arg, arg_spec in spec.args.items():
            if arg_spec.type != "number" or arg_spec.max is None or not arg_spec.unit:
                continue
            others = {other: _argument_value(other_spec) for other, other_spec in spec.args.items() if other != arg}
            if any(value is None for value in others.values()):
                continue
            outside = f"{arg_spec.max + max(1.0, abs(arg_spec.max))} {arg_spec.unit}"
            return name, {**others, arg: outside}
    return None


async def run(case: ConformanceCase) -> Report:
    """Run every check and return a report. Never raises for a failing driver."""
    driver = case.make(case.file)
    level: Conformance = case.level or driver.info.conformance
    report = Report(case.name, level=level)

    async def check(name: str, needed: Conformance, body: Callable[[], Awaitable[str | None]]) -> None:
        if LEVELS[needed] > LEVELS[level]:
            report.results.append(CheckResult(name, False, f"above the declared {level} level", skipped=True))
            return
        started = time.monotonic()
        try:
            detail = await asyncio.wait_for(body(), 30)
        except _Skip as skip:
            report.results.append(CheckResult(name, False, str(skip), skipped=True))
            return
        except Exception as exc:  # noqa: BLE001
            report.results.append(CheckResult(name, False, f"{type(exc).__name__}: {exc}"))
            return
        elapsed = time.monotonic() - started
        report.results.append(CheckResult(name, True, detail or f"{elapsed * 1000:.0f} ms"))

    clock_now = [10_000.0]
    kernel = Kernel(clock=lambda: clock_now[0])
    spy = _Spy(driver)
    kernel.register(case.file, driver)
    device_id = case.file.device_id
    who = human("conformance")

    async def identify() -> str:
        identity = await driver.identify()
        if not isinstance(identity, dict):
            raise AssertionError("identify() must return a mapping of strings.")
        return ", ".join(f"{key}={value}" for key, value in identity.items()) or "no identity fields"

    async def connect() -> str:
        await kernel.connect(device_id)
        clock_now[0] += 3600
        return "connected"

    async def describe() -> str:
        described = await driver.describe()
        if described is None:
            return "driver does not self-describe"
        if not isinstance(described, dict):
            raise AssertionError("describe() must return a mapping or None.")
        unknown = set(described) - {"read", "write", "actions", "match", "device", "notes", "safe_state", "watchdog"}
        if unknown:
            raise AssertionError(f"describe() returned unknown sections {sorted(unknown)}.")
        return f"sections {sorted(described)}"

    async def read_every_channel() -> str:
        channels = [name for name, spec in case.file.read.items() if spec.type != "image"] + list(case.file.write)
        for channel in channels:
            reading = await kernel.read(device_id, channel, who)
            if reading.channel != channel:
                raise AssertionError(f"read({channel}) returned a reading for {reading.channel}.")
            expected = case.file.channel_unit(channel)
            if expected and reading.unit not in (expected, None):
                raise AssertionError(f"{channel} reported unit {reading.unit}, the file sets {expected}.")
        return f"{len(channels)} channels"

    async def write_inside_limits() -> str:
        if not case.file.writable:
            raise _Skip("the case's device file is read-only")
        target = _inside_value(case.file)
        if target is None:
            raise _Skip("no write channel")
        before = len(spy.calls)
        decision = await kernel.execute(Write(device=device_id, channel=target[0], value=target[1]), who)
        if decision.status != "done":
            raise AssertionError(f"expected done, got {decision.status} {decision.code}: {decision.message}")
        if len(spy.calls) != before + 1:
            raise AssertionError("an allowed write must reach the driver exactly once")
        return f"{target[0]} = {target[1]}"

    async def write_outside_limits_is_blocked() -> str:
        target = _outside_value(case.file)
        if target is None or not case.file.writable:
            raise _Skip("no numeric write channel")
        before = len(spy.calls)
        decision = await kernel.execute(Write(device=device_id, channel=target[0], value=target[1]), who)
        if decision.status != "blocked":
            raise AssertionError(f"expected blocked, got {decision.status}")
        if len(spy.calls) != before:
            raise AssertionError("a blocked write reached the driver")
        return decision.message

    async def no_bypass_without_grant() -> str:
        target = _inside_value(case.file)
        if target is None:
            raise _Skip("no write channel")
        before = len(spy.calls)
        try:
            await driver.write(target[0], 0.0, None)
        except GrantError:
            pass
        else:
            raise AssertionError("driver.write accepted a call without a grant")
        if len(spy.calls) != before:
            raise AssertionError("a grant-less call reached the protocol layer")
        return "refused"

    async def action_inside_limits() -> str:
        if not case.file.writable:
            raise _Skip("the case's device file is read-only")
        candidates = _inside_actions(case.file)
        if not candidates:
            raise _Skip("no action the suite can fill in")
        held: list[str] = []
        for name, args in candidates:
            before = len(spy.calls)
            decision = await kernel.execute(Action(device=device_id, action=name, args=args), who)
            if decision.status == "done":
                if len(spy.calls) != before + 1:
                    raise AssertionError(f"an allowed action {name} must reach the driver exactly once")
                return name
            if len(spy.calls) != before:
                raise AssertionError(f"action {name} was {decision.status} but still reached the driver")
            if decision.status == "failed":
                raise AssertionError(f"action {name} failed in the driver: {decision.message}")
            held.append(f"{name} {decision.code}")
        raise _Skip(f"no action could run in the simulator's state ({', '.join(held)})")

    async def action_outside_limits_is_blocked() -> str:
        target = _outside_action(case.file)
        if target is None or not case.file.writable:
            raise _Skip("no action with a numeric argument")
        before = len(spy.calls)
        decision = await kernel.execute(Action(device=device_id, action=target[0], args=target[1]), who)
        if decision.status != "blocked":
            raise AssertionError(f"expected blocked, got {decision.status}")
        if len(spy.calls) != before:
            raise AssertionError("a blocked action reached the driver")
        return decision.message

    async def no_action_without_grant() -> str:
        candidates = _inside_actions(case.file) or [(name, {}) for name in case.file.actions]
        if not candidates:
            raise _Skip("no action")
        name, _args = candidates[0]
        before = len(spy.calls)
        try:
            await driver.action(name, {}, None)
        except GrantError:
            pass
        else:
            raise AssertionError("driver.action accepted a call without a grant")
        if len(spy.calls) != before:
            raise AssertionError("a grant-less action reached the protocol layer")
        return "refused"

    async def concurrent_access() -> str:
        target = _inside_value(case.file)
        if target is None or not case.file.writable:
            raise _Skip("no write channel")
        decisions = await asyncio.gather(
            *(kernel.execute(Write(device=device_id, channel=target[0], value=target[1]), who) for _ in range(4))
        )
        statuses = {decision.status for decision in decisions}
        if not statuses <= {"done", "blocked", "failed"}:
            raise AssertionError(f"unexpected statuses {statuses}")
        return ", ".join(sorted(statuses))

    async def safe_state() -> str:
        result = await kernel.stop_all(who, "conformance")
        status = result.devices[0].status
        kernel.unlock(who, "unlock")
        if status == "failed":
            raise AssertionError(result.devices[0].detail)
        return status

    async def disconnect_and_reconnect() -> str:
        if case.break_connection is None:
            raise _Skip("no break_connection hook for this driver")
        await case.break_connection(driver)
        health = await driver.health()
        if health.connected:
            raise AssertionError("health() still reports connected after the connection broke")
        await kernel.connection_lost(device_id, "conformance")
        await kernel.connect(device_id)
        await read_every_channel()
        return "reconnected"

    async def timeout_handling() -> str:
        if case.make_slow is None:
            raise _Skip("no make_slow hook for this driver")
        await case.make_slow(driver)
        channel = next(iter(case.file.read or case.file.write))
        try:
            await asyncio.wait_for(driver.read(channel), 2.0)
        except (TimeoutError, DriverError):
            return "slow reads time out or raise DriverError"
        return "driver answered within the deadline"

    async def close() -> str:
        await driver.close()
        return "closed"

    checks: tuple[tuple[str, Conformance, Callable[[], Awaitable[str | None]]], ...] = (
        ("identify", "core", identify),
        ("connect", "core", connect),
        ("describe", "core", describe),
        ("read every channel", "core", read_every_channel),
        ("write inside limits", "control", write_inside_limits),
        ("write outside limits is blocked before the driver", "control", write_outside_limits_is_blocked),
        ("no write without a kernel grant", "control", no_bypass_without_grant),
        ("action inside limits", "full", action_inside_limits),
        ("action outside limits is blocked before the driver", "full", action_outside_limits_is_blocked),
        ("no action without a kernel grant", "full", no_action_without_grant),
        ("concurrent access", "control", concurrent_access),
        ("safe state", "control", safe_state),
        ("disconnect and reconnect", "core", disconnect_and_reconnect),
        ("timeout handling", "core", timeout_handling),
        ("close", "core", close),
    )
    for name, needed, body in checks:
        await check(name, needed, body)
    if case.cleanup is not None:
        await case.cleanup()
    return report


class _Skip(Exception):  # noqa: N818
    """A check that doesn't apply to this driver."""
