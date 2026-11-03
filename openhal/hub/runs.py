"""Runs of steps, waits on a condition and samples over time, for any device (ADR 0019).

Everything here acts as the principal that asked. A write or an action in a run goes to
`Kernel.execute` exactly as a single write does, so units, limits, rates, interlocks, scope,
grants, the stop lock and confirmations apply to every step. Every read goes through
`Kernel.read`, so every read is in the audit log.

Rules the engine adds on top of the kernel.
- A run is checked as a whole plan first, with waits moving the simulated clock. When the plan
  check blocks a step, nothing runs.
- A run stops at the first step that isn't done. A step held for a person ends the run with the
  request id, so a run never holds for an approval.
- Steps only read, write, run an action or wait. No step approves, unlocks, widens a limit or
  enables a routine.
- A stop from any principal or the stop button ends every run, wait and sample at once.
- A run belongs to the principal that started it. Another agent gets no run by that id, and a
  person sees and cancels every run.
- The caps in config.yaml bound the steps in a run, the seconds a run, wait or sample lasts, and
  how many of them one token has going at once. Only a person changes the caps.
"""

from __future__ import annotations

import asyncio
import contextlib
import math
import secrets
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Annotated, Any, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from openhal.drivers.base import Reading
from openhal.hub import views
from openhal.hub.config import RunSettings, save_section
from openhal.kernel.commands import Action, Decision, Write
from openhal.kernel.kernel import Shadow
from openhal.kernel.principals import Principal
from openhal.spec import expressions

if TYPE_CHECKING:
    from openhal.hub.hub import Hub

Sleep = Callable[[float], Awaitable[None]]
Target = Annotated[str, Field(min_length=3, max_length=97, pattern=r"^[^.\s]+\.[^.\s]+$")]

MAX_POINTS: Final = 1000
"""The most readings a sample takes of each target."""
KEPT_RUNS: Final = 200
"""Finished runs the hub keeps for get_run. The audit log keeps every run."""
CAPS_PHRASE: Final = "confirm"
CLOSE_WAIT_S: Final = 15.0
"""How long closing the hub lets a run finish its current command before cancelling the run."""
STOPPED_MESSAGE: Final = "Blocked. The hub is stopped. A human must unlock it before anything can move."
ENDINGS: Final = {
    "stopped": "Ended by a stop. The hub stays stopped until a person unlocks the hub.",
    "token_revoked": "Ended because the token that started the run was revoked.",
    "hub_closed": "Ended because the hub shut down.",
}


class ReadStep(BaseModel):
    """Read one or more channels now."""

    model_config = ConfigDict(extra="forbid")
    kind: Literal["read"]
    targets: list[Target] = Field(min_length=1, max_length=20)


class WriteStep(BaseModel):
    """Set one write channel. `increment` is added to a number value once for each repeat before this one."""

    model_config = ConfigDict(extra="forbid")
    kind: Literal["write"]
    device: str = Field(min_length=1, max_length=48)
    channel: str = Field(min_length=1, max_length=48)
    value: str | bool | dict[str, Any] | int | float
    unit: str | None = Field(default=None, min_length=1, max_length=40)
    increment: float | None = Field(default=None, allow_inf_nan=False)

    @model_validator(mode="after")
    def _number_to_increment(self) -> WriteStep:
        number = isinstance(self.value, int | float) and not isinstance(self.value, bool)
        if self.increment is not None and not (number and self.unit is not None):
            raise ValueError("increment needs a number value with its unit apart")
        return self

    def command(self, iteration: int) -> Write:
        value = self.value
        if self.increment is not None and isinstance(value, int | float):
            value = value + self.increment * iteration
        return Write(device=self.device, channel=self.channel, value=value, unit=self.unit)


class ActionStep(BaseModel):
    """Run one action with its arguments."""

    model_config = ConfigDict(extra="forbid")
    kind: Literal["action"]
    device: str = Field(min_length=1, max_length=48)
    action: str = Field(min_length=1, max_length=48)
    args: dict[str, Any] = {}

    def command(self, iteration: int) -> Action:
        return Action(device=self.device, action=self.action, args=self.args)


class WaitStep(BaseModel):
    """Wait a number of seconds."""

    model_config = ConfigDict(extra="forbid")
    kind: Literal["wait"]
    seconds: float = Field(gt=0, le=86_400, allow_inf_nan=False)


class WaitUntilStep(BaseModel):
    """Wait until a condition over live readings holds, for at most `timeout_s`."""

    model_config = ConfigDict(extra="forbid")
    kind: Literal["wait_until"]
    condition: str = Field(min_length=1, max_length=256)
    timeout_s: float = Field(gt=0, le=86_400, allow_inf_nan=False)
    interval_s: float = Field(default=1.0, gt=0, le=60, allow_inf_nan=False)


Step = Annotated[ReadStep | WriteStep | ActionStep | WaitStep | WaitUntilStep, Field(discriminator="kind")]


class RunBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    steps: list[Step] = Field(min_length=1, max_length=10_000)
    repeat: int = Field(default=1, ge=1, le=10_000)
    wait_s: float = Field(default=5.0, ge=0, le=30, description="Seconds to wait for the run to end before replying.")


class WaitBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    condition: str = Field(min_length=1, max_length=256)
    timeout_s: float = Field(default=30.0, gt=0, le=86_400, allow_inf_nan=False)
    interval_s: float = Field(default=1.0, gt=0, le=60, allow_inf_nan=False)


class SampleBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    targets: list[Target] = Field(min_length=1, max_length=20)
    duration_s: float = Field(gt=0, le=86_400, allow_inf_nan=False)
    interval_s: float = Field(default=1.0, gt=0, le=3600, allow_inf_nan=False)


class CapsBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    max_steps: int | None = Field(default=None, ge=1, le=10_000)
    max_seconds: float | None = Field(default=None, ge=1, le=86_400)
    per_agent: int | None = Field(default=None, ge=1, le=20)
    phrase: str | None = Field(default=None, max_length=40, description="confirm, typed by a person to raise a cap.")


class RunError(Exception):
    """A request the hub can't take. `status` is the HTTP status and the message names the fix."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


@dataclass(eq=False)
class Job:
    """Something the hub does over time for one principal. `ended` is set by a cancel or a stop."""

    principal: Principal
    ended: asyncio.Event = field(default_factory=asyncio.Event)
    reason: str | None = None
    by: str | None = None

    def end(self, reason: str, by: str | None = None) -> None:
        if self.reason is None:
            self.reason, self.by = reason, by
        self.ended.set()

    def ending(self) -> str:
        assert self.reason is not None
        if self.reason == "cancelled":
            return f"Cancelled by {self.by}. The steps after this one did not run."
        return ENDINGS[self.reason]


@dataclass(eq=False)
class Run(Job):
    run_id: str = ""
    steps: list[Any] = field(default_factory=list)
    repeat: int = 1
    status: str = "running"
    message: str = "Running."
    started_at: float = 0.0
    finished_at: float | None = None
    clock_start: float = 0.0
    clock_end: float | None = None
    results: list[dict[str, Any]] = field(default_factory=list)
    stop: dict[str, Any] | None = None
    plan: dict[str, Any] = field(default_factory=dict)
    current: dict[str, Any] | None = None
    task: asyncio.Task[None] | None = None
    done: asyncio.Event = field(default_factory=asyncio.Event)


Flat = list[tuple[int, int, Any]]


def _expression_value(hub: Hub, device: str, channel: str, reading: Reading) -> expressions.Value | None:
    raw = reading.value
    if isinstance(raw, bool | str):
        return expressions.Value(raw)
    if isinstance(raw, int | float):
        return expressions.Value(float(raw), reading.unit or hub.kernel.devices[device].file.channel_unit(channel))
    return None


def _numbers(points: list[dict[str, Any]]) -> list[float]:
    return [
        float(point["value"])
        for point in points
        if point["ok"] and isinstance(point["value"], int | float) and not isinstance(point["value"], bool)
    ]


def series(target: str, points: list[dict[str, Any]]) -> dict[str, Any]:
    """One target's sample, with min, max and mean over its number readings."""
    found = [point for point in points if point["ok"]]
    numbers = _numbers(points)
    summary: dict[str, Any] = {
        "target": target,
        "unit": next((point.get("unit") for point in found), None),
        "count": len(points),
        "failed": len(points) - len(found),
        "first": found[0]["value"] if found else None,
        "last": found[-1]["value"] if found else None,
    }
    if numbers:
        summary |= {"min": min(numbers), "max": max(numbers), "mean": sum(numbers) / len(numbers)}
    return {**summary, "points": [{key: point.get(key) for key in ("at", "ok", "value", "error")} for point in points]}


class RunEngine:
    """Runs, waits and samples for every principal, through the kernel."""

    def __init__(self, hub: Hub, *, sleep: Sleep = asyncio.sleep) -> None:
        self.hub = hub
        self.kernel = hub.kernel
        self.runs: dict[str, Run] = {}
        self._active: set[Job] = set()
        self._sleep = sleep
        self.kernel.on_stop(self._on_stop)

    @property
    def caps(self) -> RunSettings:
        return self.hub.config.runs

    def _admit(self, job: Job) -> None:
        mine = sum(1 for other in self._active if other.principal.label == job.principal.label)
        if mine >= self.caps.per_agent:
            raise RunError(
                429,
                f"{job.principal.label} already has {mine} runs, waits or samples going, the most one token may "
                "have at once. Wait for one to end or cancel a run. A person raises the cap with "
                "openhal runs caps --per-agent.",
            )
        self._active.add(job)

    def _on_stop(self, reason: str) -> None:
        for job in list(self._active):
            job.end("stopped")

    def end_for(self, label: str, reason: str) -> int:
        """End every run, wait and sample of one principal, such as when its token is revoked."""
        mine = [job for job in self._active if job.principal.label == label]
        for job in mine:
            job.end(reason)
        return len(mine)

    async def close(self) -> None:
        for job in list(self._active):
            job.end("hub_closed")
        tasks = [run.task for run in self.runs.values() if run.task is not None and not run.task.done()]
        if tasks:
            _done, pending = await asyncio.wait(tasks, timeout=CLOSE_WAIT_S)
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)

    async def _pause(self, job: Job, seconds: float) -> bool:
        """Sleep for `seconds`, or less when the job ends. True when the whole time passed."""
        if job.ended.is_set():
            return False
        if seconds <= 0:
            return True
        sleeper = asyncio.ensure_future(self._sleep(seconds))
        ender = asyncio.ensure_future(job.ended.wait())
        try:
            await asyncio.wait({sleeper, ender}, return_when=asyncio.FIRST_COMPLETED)
        finally:
            for task in (sleeper, ender):
                task.cancel()
            await asyncio.gather(sleeper, ender, return_exceptions=True)
        return not job.ended.is_set()

    def _target(self, target: str) -> tuple[str, str]:
        device, _, channel = target.partition(".")
        runtime = self.kernel.devices.get(device)
        if runtime is None:
            raise RunError(404, f"There is no device {device!r}. find and list_devices name every device.")
        if channel not in runtime.file.read and channel not in runtime.file.write:
            known = ", ".join([*runtime.file.read, *runtime.file.write]) or "none"
            raise RunError(404, f"{device} has no channel {channel!r}. Its channels are {known}.")
        return device, channel

    def _condition(self, text: str) -> tuple[expressions.Node, list[expressions.Ref]]:
        try:
            tree = expressions.parse(text, frozenset())
        except expressions.ExpressionError as exc:
            raise RunError(400, f"The condition {text!r} doesn't parse. {exc}") from exc
        refs = sorted(expressions.references(tree), key=str)
        if not refs:
            raise RunError(400, "The condition names no channel. Name each channel as device.channel.")
        for ref in refs:
            self._target(str(ref))
        return tree, refs

    async def _read(self, job: Job, device: str, channel: str) -> tuple[Reading | None, dict[str, Any]]:
        try:
            reading = await self.kernel.read(device, channel, job.principal)
        except Exception as exc:  # noqa: BLE001 (a failed read is a result, the channel counts as unknown)
            return None, views.failed_reading(device, channel, exc)
        return reading, views.reading_view(self.hub, device, channel, reading, image_data=False)

    async def _check(
        self, job: Job, tree: expressions.Node, refs: list[expressions.Ref]
    ) -> tuple[bool | None, list[dict[str, Any]]]:
        values: dict[expressions.Ref, expressions.Value | None] = {}
        shown = []
        for ref in refs:
            assert ref.device is not None
            reading, view = await self._read(job, ref.device, ref.name)
            values[ref] = None if reading is None else _expression_value(self.hub, ref.device, ref.name, reading)
            shown.append(view)
        return expressions.evaluate(tree, values.get), shown

    async def _wait(
        self, job: Job, tree: expressions.Node, refs: list[expressions.Ref], timeout_s: float, interval_s: float
    ) -> dict[str, Any]:
        interval = max(interval_s, self.hub.config.poll_floor_s)
        start = self.kernel.clock()
        checks = 0
        while True:
            result, readings = await self._check(job, tree, refs)
            checks += 1
            waited = self.kernel.clock() - start
            if result is True:
                status = "held"
            elif job.ended.is_set():
                status = str(job.reason)
            elif waited >= timeout_s:
                status = "timeout"
            elif await self._pause(job, min(interval, timeout_s - waited)):
                continue
            else:
                status = str(job.reason)
            return {
                "status": status,
                "held": status == "held",
                "result": result,
                "waited_s": round(waited, 3),
                "checks": checks,
                "interval_s": interval,
                "readings": readings,
            }

    async def wait_until(self, who: Principal, body: WaitBody) -> dict[str, Any]:
        """Wait until the condition holds or the timeout passes. Returns the readings of the last check."""
        if body.timeout_s > self.caps.max_seconds:
            raise RunError(400, self._too_long("A wait", body.timeout_s))
        tree, refs = self._condition(body.condition)
        job = Job(who)
        self._admit(job)
        try:
            outcome = await self._wait(job, tree, refs, body.timeout_s, body.interval_s)
        finally:
            self._active.discard(job)
        self.hub.audit.append(
            "wait_until",
            who.label,
            status=outcome["status"],
            condition=body.condition,
            waited_s=outcome["waited_s"],
            checks=outcome["checks"],
        )
        return {"condition": body.condition, **outcome}

    def _too_long(self, what: str, seconds: float) -> str:
        return (
            f"{what} of {seconds:g} s is longer than the {self.caps.max_seconds:g} s the hub allows. "
            "A person raises the cap with openhal runs caps --max-seconds."
        )

    async def sample(self, who: Principal, body: SampleBody) -> dict[str, Any]:
        """Read every target at the interval for the duration, with min, max and mean for numbers."""
        if body.duration_s > self.caps.max_seconds:
            raise RunError(400, self._too_long("A sample", body.duration_s))
        interval = max(body.interval_s, self.hub.config.poll_floor_s)
        ticks = math.floor(body.duration_s / interval + 1e-9) + 1
        if ticks > MAX_POINTS:
            raise RunError(
                400,
                f"That takes {ticks} readings of each target, and a sample takes at most {MAX_POINTS}. "
                "Use a longer interval_s.",
            )
        pairs = [self._target(target) for target in body.targets]
        job = Job(who)
        self._admit(job)
        points: dict[str, list[dict[str, Any]]] = {target: [] for target in body.targets}
        start, started_at, status = self.kernel.clock(), time.time(), "done"
        try:
            for tick in range(ticks):
                for target, (device, channel) in zip(body.targets, pairs, strict=True):
                    points[target].append((await self._read(job, device, channel))[1])
                elapsed = self.kernel.clock() - start
                if tick == ticks - 1 or elapsed > body.duration_s:
                    break
                if not await self._pause(job, max(0.0, (tick + 1) * interval - elapsed)):
                    status = str(job.reason)
                    break
        finally:
            self._active.discard(job)
        taken = len(points[body.targets[0]])
        self.hub.audit.append("sample", who.label, status=status, targets=body.targets, points=taken)
        return {
            "status": status,
            "interval_s": interval,
            "duration_s": round(self.kernel.clock() - start, 3),
            "started_at": started_at,
            "series": [series(target, points[target]) for target in body.targets],
        }

    def _check_body(self, body: RunBody) -> Flat:
        total = len(body.steps) * body.repeat
        if total > self.caps.max_steps:
            raise RunError(
                400,
                f"This run has {total} steps with its repeats, and a run may have {self.caps.max_steps}. "
                "Use fewer steps or repeats. A person raises the cap with openhal runs caps --max-steps.",
            )
        waits = sum(step.seconds for step in body.steps if isinstance(step, WaitStep)) * body.repeat
        if waits > self.caps.max_seconds:
            raise RunError(400, self._too_long("A run that waits", waits))
        for step in body.steps:
            if isinstance(step, ReadStep):
                for target in step.targets:
                    self._target(target)
            elif isinstance(step, WaitUntilStep):
                if step.timeout_s > self.caps.max_seconds:
                    raise RunError(400, self._too_long("A wait_until step", step.timeout_s))
                self._condition(step.condition)
        return [(iteration, index, step) for iteration in range(body.repeat) for index, step in enumerate(body.steps)]

    async def start(self, who: Principal, body: RunBody) -> dict[str, Any]:
        """Check the run as a plan, start it, and reply when it ends or after `wait_s`."""
        flat = self._check_body(body)
        run = Run(
            who,
            run_id=f"run-{secrets.token_hex(8)}",
            steps=list(body.steps),
            repeat=body.repeat,
            started_at=time.time(),
            clock_start=self.kernel.clock(),
        )
        self._admit(run)
        self._keep(run)
        self.hub.audit.append(
            "run",
            who.label,
            target=f"run:{run.run_id}",
            status="running",
            run_id=run.run_id,
            steps=len(body.steps),
            repeat=body.repeat,
            total=len(flat),
        )
        blocked = self._plan(run, flat)
        if blocked is not None:
            self._finish(run, "blocked", blocked)
            return self.view(run)
        run.task = asyncio.create_task(self._execute(run, flat), name=f"openhal-{run.run_id}")
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(run.done.wait(), body.wait_s)
        return self.view(run)

    def _keep(self, run: Run) -> None:
        self.runs[run.run_id] = run
        finished = [item for item in self.runs.values() if item.status != "running"]
        for old in finished[: max(0, len(self.runs) - KEPT_RUNS)]:
            del self.runs[old.run_id]

    def _plan(self, run: Run, flat: Flat) -> dict[str, Any] | None:
        """Evaluate every command in order as if the earlier ones ran, with waits moving the clock."""
        if self.kernel.stopped:
            return {"index": 0, "step": 0, "iteration": 0, "kind": "run", "code": "stopped", "message": STOPPED_MESSAGE}
        shadow = Shadow()
        held: list[int] = []
        commands = 0
        for position, (iteration, index, step) in enumerate(flat):
            if isinstance(step, WaitStep):
                shadow.now += step.seconds
                continue
            if not isinstance(step, WriteStep | ActionStep):
                continue
            command = step.command(iteration)
            decision = self.kernel.evaluate(command, run.principal, shadow=shadow, wire=True)
            commands += 1
            if decision.status == "blocked":
                run.plan = {"commands_checked": commands, "needs_confirmation": held}
                return {
                    "index": position,
                    "step": index,
                    "iteration": iteration,
                    "kind": step.kind,
                    "code": decision.code,
                    "message": f"Nothing ran. {decision.message}",
                    "decision": self._decision(decision),
                }
            if decision.status == "needs_confirmation":
                held.append(position)
            if isinstance(command, Write):
                shadow.record(command.device, command.channel, decision.value)
            else:
                shadow.record_run(command.device, command.action)
        run.plan = {"commands_checked": commands, "needs_confirmation": held}
        return None

    def _decision(self, decision: Decision) -> dict[str, Any]:
        runtime = self.kernel.devices.get(decision.device)
        return views.decision_view(decision, runtime.file if runtime is not None else None)

    async def _execute(self, run: Run, flat: Flat) -> None:
        deadline = run.clock_start + self.caps.max_seconds
        try:
            for position, (iteration, index, step) in enumerate(flat):
                base = {"index": position, "step": index, "iteration": iteration, "kind": step.kind}
                if run.ended.is_set():
                    self._finish(run, "cancelled", {**base, "code": run.reason, "message": run.ending()})
                    return
                if self.kernel.clock() >= deadline:
                    self._finish(run, "cancelled", {**base, **self._time_cap()})
                    return
                run.current = base
                result, stop = await self._step(run, base, step, iteration, deadline)
                run.results.append(result)
                self.hub.audit.append(
                    "run_step",
                    run.principal.label,
                    device=result.get("device"),
                    target=result.get("target") or f"run:{run.run_id}",
                    status=result.get("status"),
                    code=result.get("code"),
                    run_id=run.run_id,
                    **{key: base[key] for key in ("index", "step", "iteration", "kind")},
                )
                if stop is not None:
                    status = stop.pop("status")
                    self._finish(run, status, {**base, **stop})
                    return
            self._finish(run, "done", None)
        except asyncio.CancelledError:
            self._finish(run, "cancelled", {"kind": "run", "code": "hub_closed", "message": ENDINGS["hub_closed"]})
            raise
        except Exception as exc:  # noqa: BLE001 (fail closed, a bug ends the run and nothing else runs)
            message = f"The run hit an unexpected error ({type(exc).__name__}). The steps after this one did not run."
            self._finish(run, "failed", {"kind": "run", "code": "internal_error", "message": message})

    def _time_cap(self) -> dict[str, Any]:
        return {
            "code": "time_cap",
            "message": f"Ended at the run time cap of {self.caps.max_seconds:g} s. The steps after this one did "
            "not run. A person raises the cap with openhal runs caps --max-seconds.",
        }

    def _ended(self, run: Run) -> dict[str, Any]:
        return {"status": "cancelled", "code": run.reason, "message": run.ending()}

    async def _step(
        self, run: Run, base: dict[str, Any], step: Any, iteration: int, deadline: float
    ) -> tuple[dict[str, Any], dict[str, Any] | None]:
        """Run one step. Returns its result and, when the run ends here, why."""
        if isinstance(step, WaitStep):
            seconds = min(step.seconds, deadline - self.kernel.clock())
            whole = await self._pause(run, seconds)
            done = whole and seconds == step.seconds
            result = {**base, "status": "done" if done else "cancelled", "seconds": seconds}
            if not whole:
                return result, self._ended(run)
            if not done:
                return result, {"status": "cancelled", **self._time_cap()}
            return result, None
        if isinstance(step, ReadStep):
            readings = [(await self._read(run, *self._target(target)))[1] for target in step.targets]
            return {**base, "status": "done", "readings": readings}, None
        if isinstance(step, WaitUntilStep):
            tree, refs = self._condition(step.condition)
            limit = min(step.timeout_s, deadline - self.kernel.clock())
            outcome = await self._wait(run, tree, refs, limit, step.interval_s)
            result = {**base, "condition": step.condition, **outcome}
            if outcome["status"] == "held":
                return result, None
            if outcome["status"] != "timeout":
                return result, self._ended(run)
            if limit < step.timeout_s:
                return result, {"status": "cancelled", **self._time_cap()}
            message = (
                f"{step.condition} did not hold within {step.timeout_s:g} s. The steps after this one did not run."
            )
            return result, {"status": "failed", "code": "condition_timeout", "message": message}
        decision = await self.kernel.execute(step.command(iteration), run.principal, wire=True)
        result = {**base, **self._decision(decision)}
        if run.ended.is_set():
            return result, self._ended(run)
        if decision.status == "done":
            return result, None
        if decision.status == "pending":
            message = (
                f"{decision.message} The run ended here, and the steps after this one did not run. A person "
                f"approves the request with openhal confirm approve {decision.request_id}."
            )
            stop = {"status": "pending", "code": "needs_confirmation", "request_id": decision.request_id}
            return result, {**stop, "message": message}
        stop = {"status": "blocked" if decision.status == "blocked" else "failed", "code": decision.code}
        return result, {**stop, "message": f"{decision.message} The steps after this one did not run."}

    def _finish(self, run: Run, status: str, stop: dict[str, Any] | None) -> None:
        run.status, run.stop, run.current = status, stop, None
        run.finished_at, run.clock_end = time.time(), self.kernel.clock()
        run.message = stop["message"] if stop is not None else f"Done. All {len(run.results)} steps ran."
        self._active.discard(run)
        run.done.set()
        self.hub.audit.append(
            "run",
            run.principal.label,
            target=f"run:{run.run_id}",
            status=status,
            code=stop.get("code") if stop is not None else None,
            run_id=run.run_id,
            message=run.message,
            stopped_at=None if stop is None else {key: stop.get(key) for key in ("index", "step", "iteration")},
        )

    def view(self, run: Run, last: int = 50) -> dict[str, Any]:
        """A run as clients receive it, with its `last` step results."""
        end = run.clock_end if run.clock_end is not None else self.kernel.clock()
        return {
            "run_id": run.run_id,
            "owner": run.principal.label,
            "status": run.status,
            "message": run.message,
            "steps": len(run.steps),
            "repeat": run.repeat,
            "total_steps": len(run.steps) * run.repeat,
            "done_steps": len(run.results),
            "current": run.current,
            "started_at": run.started_at,
            "finished_at": run.finished_at,
            "elapsed_s": round(end - run.clock_start, 3),
            "stop": run.stop,
            "request_id": (run.stop or {}).get("request_id"),
            "plan": run.plan,
            "results": run.results[-last:] if last else [],
        }

    def get(self, who: Principal, run_id: str) -> Run:
        """The run, when `who` started it or is a person. Any other caller gets no run by that id."""
        run = self.runs.get(run_id)
        if run is None or (who.kind != "human" and run.principal.label != who.label):
            raise RunError(404, f"There is no run {run_id}.")
        return run

    async def wait_for(self, who: Principal, run_id: str, wait_s: float, last: int) -> dict[str, Any]:
        """The run's view, after waiting up to `wait_s` for the run to end."""
        run = self.get(who, run_id)
        if wait_s > 0:
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(run.done.wait(), wait_s)
        return self.view(run, last)

    def listed(self, who: Principal) -> list[dict[str, Any]]:
        """Every run `who` may see, newest first, without step results."""
        mine = [run for run in self.runs.values() if who.kind == "human" or run.principal.label == who.label]
        return [self.view(run, 0) for run in sorted(mine, key=lambda run: run.started_at, reverse=True)]

    async def cancel(self, who: Principal, run_id: str) -> dict[str, Any]:
        """End a run before its next step. Only the principal that started it, or a person, may."""
        try:
            run = self.get(who, run_id)
        except RunError:
            self.hub.audit.append(
                "run_cancel", who.label, target=f"run:{run_id}", status="blocked", code="unknown_target", run_id=run_id
            )
            raise
        if run.status == "running":
            run.end("cancelled", who.label)
            self.hub.audit.append("run_cancel", who.label, target=f"run:{run_id}", status="done", run_id=run_id)
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(run.done.wait(), 15)
        return self.view(run)

    def caps_view(self) -> dict[str, Any]:
        return {**self.caps.model_dump(), "max_points": MAX_POINTS}

    def set_caps(self, who: Principal, body: CapsBody) -> dict[str, Any]:
        """A person changes the caps. Lowering applies at once, and raising takes the typed phrase confirm."""
        if who.kind != "human":
            self.hub.audit.append("run_caps", who.label, status="blocked", code="not_permitted")
            raise RunError(403, "Changing run caps takes a human principal.")
        current = self.caps
        changes = body.model_dump(exclude={"phrase"}, exclude_none=True)
        raised = sorted(name for name, value in changes.items() if value > getattr(current, name))
        if raised and (body.phrase or "").strip().lower() != CAPS_PHRASE:
            self.hub.audit.append("run_caps", who.label, status="blocked", code="bad_request", raised=raised)
            raise RunError(400, f"Raising {', '.join(raised)} takes the typed phrase {CAPS_PHRASE}.")
        updated = RunSettings.model_validate({**current.model_dump(), **changes})
        if not self.hub.in_memory:
            save_section(self.hub.config.home, "runs", updated.model_dump())
        self.hub.config.runs = updated
        changed = {
            name: {"from": getattr(current, name), "to": value}
            for name, value in changes.items()
            if value != getattr(current, name)
        }
        self.hub.audit.append("run_caps", who.label, status="done", changed=changed)
        return {**self.caps_view(), "changed": changed}
