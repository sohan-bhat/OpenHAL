"""The routine engine. Runs YAML and Python routines with no model involved (ADR 0007).

Every write and action a routine makes goes through the safety kernel as principal
`routine:<id>`, with the scope of whoever enabled it (capped at control_medium) and the routine's
content hash, which approvals for high hazard devices are bound to.

Rules the engine adds on top of the kernel.
- New routines start disabled. Python routines can only be enabled by a human.
- Changing a routine's content disables it.
- A stop disables every enabled routine and cancels running ones. A human re-enables them.
- A routine runs at most once at a time, no more often than `routines.min_interval_s`, and is
  cancelled after its max runtime.
"""

from __future__ import annotations

import asyncio
import contextlib
import datetime as dt
import json
import secrets
import sqlite3
import threading
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from pydantic import TypeAdapter, ValidationError

from openhal._brand import ROUTINE_FILE_SUFFIX
from openhal.kernel.commands import Action, Decision, Write
from openhal.kernel.kernel import Shadow
from openhal.kernel.principals import SCOPE_RANK, Principal, Scope, routine
from openhal.routines.models import (
    PYTHON_RUN,
    ActionStep,
    AtTrigger,
    EveryTrigger,
    IfStep,
    LogStep,
    ManualTrigger,
    Routine,
    Step,
    Trigger,
    WaitStep,
    WhenTrigger,
    WriteStep,
    content_sha256,
)
from openhal.spec.loader import DeviceFileError, parse_yaml
from openhal.spec.units import UnitError, parse_duration

if TYPE_CHECKING:
    from openhal.hub.hub import Hub

Kind = Literal["yaml", "python"]
RunStatus = Literal["running", "ok", "blocked", "failed", "cancelled"]

_SCHEMA = """
CREATE TABLE IF NOT EXISTS routines (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    source TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 0,
    enabled_by TEXT,
    enabled_scope TEXT,
    drafted_by TEXT NOT NULL,
    disabled_reason TEXT,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS routine_runs (
    run_id TEXT PRIMARY KEY,
    routine_id TEXT NOT NULL,
    trigger TEXT NOT NULL,
    started_at REAL NOT NULL,
    finished_at REAL,
    status TEXT NOT NULL,
    message TEXT,
    steps TEXT NOT NULL
);
"""

_TRIGGERS = TypeAdapter(list[Trigger])


class RoutineError(ValueError):
    """A routine is invalid or the request isn't allowed. The message says why."""


class RoutineBlockedError(RuntimeError):
    """A Python routine's command was blocked and the routine stops."""

    def __init__(self, decision: Decision) -> None:
        self.decision = decision
        super().__init__(decision.message)


@dataclass
class Run:
    run_id: str
    routine_id: str
    trigger: str
    started_at: float
    finished_at: float | None = None
    status: RunStatus = "running"
    message: str = ""
    steps: list[dict[str, Any]] = field(default_factory=list)

    def view(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "routine_id": self.routine_id,
            "trigger": self.trigger,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "status": self.status,
            "message": self.message,
            "steps": self.steps,
        }


@dataclass
class Record:
    """One stored routine."""

    id: str
    kind: Kind
    source: str
    sha256: str
    enabled: bool
    enabled_by: str | None
    enabled_scope: str | None
    drafted_by: str
    disabled_reason: str | None
    created_at: float
    parsed: Routine | None = None
    triggers: list[Trigger] = field(default_factory=list)
    last_run: Run | None = None
    last_dry_run: dict[str, Any] | None = None
    last_fired: dict[int, Any] = field(default_factory=dict)


def parse(routine_id: str, kind: Kind, source: str) -> tuple[Routine | None, list[Trigger]]:
    """Validate routine source. Returns the YAML model (None for Python) and its triggers."""
    if len(source.encode("utf-8")) > 128 * 1024:
        raise RoutineError("Routines may be at most 128 KiB.")
    if kind == "yaml":
        try:
            data = parse_yaml(source)
        except DeviceFileError as exc:
            raise RoutineError("; ".join(exc.problems)) from exc
        if not isinstance(data, dict):
            raise RoutineError("A YAML routine must be a mapping.")
        if data.get("id") not in (None, routine_id):
            raise RoutineError(f"The routine's id is {data.get('id')!r}, but it is being saved as {routine_id!r}.")
        data["id"] = routine_id
        try:
            model = Routine.model_validate(data)
        except ValidationError as exc:
            problems = [f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}" for error in exc.errors()]
            raise RoutineError("; ".join(problems)) from exc
        return model, list(model.triggers)
    if kind == "python":
        if not PYTHON_RUN.search(source):
            raise RoutineError("A Python routine must define async def run(ctx).")
        try:
            compile(source, f"<routine {routine_id}>", "exec")
        except SyntaxError as exc:
            raise RoutineError(f"Python syntax error on line {exc.lineno}: {exc.msg}") from exc
        triggers = _python_triggers(source)
        return None, triggers
    raise RoutineError("kind must be yaml or python.")


def _python_triggers(source: str) -> list[Trigger]:
    """Read a literal TRIGGERS list from a Python routine without running it."""
    import ast

    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "TRIGGERS" for t in node.targets):
            try:
                value = ast.literal_eval(node.value)
            except ValueError as exc:
                raise RoutineError("TRIGGERS must be a literal list of mappings.") from exc
            try:
                return _TRIGGERS.validate_python(value)
            except ValidationError as exc:
                raise RoutineError(f"TRIGGERS: {exc.errors()[0]['msg']}") from exc
    return [ManualTrigger(manual=True)]


class RoutineContext:
    """What a Python routine can use. Every hardware call goes through the kernel."""

    def __init__(self, engine: RoutineEngine, principal: Principal, run: Run) -> None:
        self._engine = engine
        self._principal = principal
        self._run = run

    async def read(self, device: str, channel: str) -> Any:
        reading = await self._engine.kernel.read(device, channel, self._principal)
        return reading.value

    async def write(self, device: str, channel: str, value: Any) -> Decision:
        return await self._engine.command(
            Write(device=device, channel=channel, value=value), self._principal, self._run, raise_on_block=True
        )

    async def action(self, device: str, action: str, **args: Any) -> Decision:
        return await self._engine.command(
            Action(device=device, action=action, args=args), self._principal, self._run, raise_on_block=True
        )

    async def wait(self, duration: str | float) -> None:
        seconds = parse_duration(duration) if isinstance(duration, str) else float(duration)
        if not 0 <= seconds <= 3600:
            raise RoutineError("wait must be between 0 s and 1 h.")
        await asyncio.sleep(seconds)

    def value(self, expression: str) -> bool | None:
        return self._engine.kernel.evaluate_expression(expression)

    def log(self, message: str) -> None:
        self._run.steps.append({"log": str(message)[:300]})


class RoutineEngine:
    """Stores routines, schedules them, and runs them through the kernel."""

    def __init__(self, hub: Hub, *, sleep: Callable[[float], Awaitable[None]] = asyncio.sleep) -> None:
        self.hub = hub
        self.kernel = hub.kernel
        self.settings = hub.config.routines
        path = ":memory:" if hub.in_memory else str(hub.config.db_path)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self._conn.executescript(_SCHEMA)
        self.records: dict[str, Record] = {}
        self._running: dict[str, asyncio.Task[Run]] = {}
        self._last_start: dict[str, float] = {}
        self._sleep = sleep
        self._task: asyncio.Task[None] | None = None
        self.kernel.on_stop(self._on_stop)
        self._load()

    # ------------------------------------------------------------------ storage

    def _load(self) -> None:
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, kind, source, sha256, enabled, enabled_by, enabled_scope, drafted_by, disabled_reason,"
                " created_at FROM routines"
            ).fetchall()
        for row in rows:
            record = Record(row[0], row[1], row[2], row[3], bool(row[4]), row[5], row[6], row[7], row[8], row[9])
            try:
                record.parsed, record.triggers = parse(record.id, record.kind, record.source)
            except RoutineError as exc:
                record.enabled = False
                record.disabled_reason = f"invalid: {exc}"
            self.records[record.id] = record
        if not self.hub.in_memory:
            self._sync_files()

    def _sync_files(self) -> None:
        """Pick up routine files people edited by hand. Changed content disables the routine."""
        folder = self.hub.config.routines_dir
        for path in sorted(folder.glob(f"*{ROUTINE_FILE_SUFFIX}")) + sorted(folder.glob("*.routine.py")):
            kind: Kind = "python" if path.suffix == ".py" else "yaml"
            routine_id = path.name.split(".routine.")[0]
            source = path.read_text(encoding="utf-8")
            existing = self.records.get(routine_id)
            if existing is not None and existing.source == source:
                continue
            try:
                self.create(Principal("human", "file"), routine_id, kind, source, write_file=False, replace=True)
            except RoutineError as exc:
                self.hub.audit.append(
                    "routine_load", "system:kernel", target=f"routine:{routine_id}", status="failed", detail=str(exc)
                )

    def _save(self, record: Record) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO routines (id, kind, source, sha256, enabled, enabled_by, enabled_scope,"
                " drafted_by, disabled_reason, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    record.id,
                    record.kind,
                    record.source,
                    record.sha256,
                    int(record.enabled),
                    record.enabled_by,
                    record.enabled_scope,
                    record.drafted_by,
                    record.disabled_reason,
                    record.created_at,
                ),
            )

    def _file_path(self, record: Record) -> Path:
        suffix = ".routine.py" if record.kind == "python" else ROUTINE_FILE_SUFFIX
        return self.hub.config.routines_dir / f"{record.id}{suffix}"

    # ------------------------------------------------------------------ management

    def create(
        self,
        principal: Principal,
        routine_id: str,
        kind: Kind,
        source: str,
        *,
        write_file: bool = True,
        replace: bool = False,
    ) -> Record:
        """Store a new routine, always disabled."""
        if principal.kind == "agent" and principal.scope == "read":
            raise RoutineError("A read-only token can't draft routines.")
        if principal.kind == "routine":
            raise RoutineError("Routines can't create routines.")
        if routine_id in self.records and not replace:
            raise RoutineError(f"A routine called {routine_id!r} already exists.")
        parsed, triggers = parse(routine_id, kind, source)
        record = Record(
            id=routine_id,
            kind=kind,
            source=source,
            sha256=content_sha256(kind, source),
            enabled=False,
            enabled_by=None,
            enabled_scope=None,
            drafted_by=principal.label,
            disabled_reason="new routine",
            created_at=time.time(),
            parsed=parsed,
            triggers=triggers,
        )
        previous = self.records.get(routine_id)
        if previous is not None:
            self._cancel(routine_id)
            record.disabled_reason = "content changed"
        self.records[routine_id] = record
        self._save(record)
        if write_file and not self.hub.in_memory:
            self._file_path(record).write_text(source, encoding="utf-8")
        self.hub.audit.append(
            "routine_create",
            principal.label,
            target=f"routine:{routine_id}",
            status="done",
            kind=kind,
            sha256=record.sha256,
        )
        return record

    def get(self, routine_id: str) -> Record:
        record = self.records.get(routine_id)
        if record is None:
            raise KeyError(f"There is no routine {routine_id!r}.")
        return record

    def max_hazard(self, record: Record) -> str:
        rank = {"low": 0, "medium": 1, "high": 2}
        hazards = [
            self.kernel.devices[device].file.effective_hazard
            for device in self._devices(record)
            if device in self.kernel.devices
        ]
        return max(hazards, key=lambda hazard: rank[hazard]) if hazards else "low"

    def _devices(self, record: Record) -> set[str]:
        if record.parsed is not None:
            return record.parsed.devices()
        return set()

    def enable(self, principal: Principal, routine_id: str) -> Record:
        record = self.get(routine_id)
        if self.kernel.stopped:
            raise RoutineError("The hub is stopped. Unlock it before enabling routines.")
        if record.disabled_reason and record.disabled_reason.startswith("invalid"):
            raise RoutineError(f"This routine is invalid and can't be enabled ({record.disabled_reason}).")
        missing = sorted(device for device in self._devices(record) if device not in self.kernel.devices)
        if missing:
            raise RoutineError(f"This routine uses devices that aren't registered: {', '.join(missing)}.")
        if principal.kind == "human":
            scope: Scope = "control_medium"
        elif principal.kind == "agent":
            if not self.settings.agent_enable_low_hazard:
                raise RoutineError("Only a human can enable routines on this hub.")
            if record.kind != "yaml":
                raise RoutineError("Only a human can enable a Python routine.")
            if self.max_hazard(record) != "low" or SCOPE_RANK[principal.scope] < SCOPE_RANK["control_low"]:
                raise RoutineError("Agents may only enable routines that touch low hazard devices.")
            scope = "control_low"
        else:
            raise RoutineError("Only a human can enable this routine.")
        record.enabled = True
        record.enabled_by = principal.label
        record.enabled_scope = scope
        record.disabled_reason = None
        self._save(record)
        self.hub.audit.append(
            "routine_enable", principal.label, target=f"routine:{routine_id}", status="done", sha256=record.sha256
        )
        return record

    def disable(self, principal: Principal, routine_id: str, reason: str = "disabled") -> Record:
        record = self.get(routine_id)
        record.enabled = False
        record.disabled_reason = reason
        self._cancel(routine_id)
        self._save(record)
        self.hub.audit.append(
            "routine_disable", principal.label, target=f"routine:{routine_id}", status="done", reason=reason
        )
        return record

    def delete(self, principal: Principal, routine_id: str) -> None:
        if principal.kind != "human":
            raise RoutineError("Only a human can delete a routine.")
        record = self.get(routine_id)
        self._cancel(routine_id)
        del self.records[routine_id]
        with self._lock:
            self._conn.execute("DELETE FROM routines WHERE id = ?", (routine_id,))
        if not self.hub.in_memory:
            with contextlib.suppress(FileNotFoundError):
                self._file_path(record).unlink()
        self.hub.audit.append("routine_delete", principal.label, target=f"routine:{routine_id}", status="done")

    def principal_for(self, record: Record) -> Principal:
        scope: Scope = "control_low" if record.enabled_scope == "control_low" else "control_medium"
        return routine(record.id, scope, record.sha256)

    # ------------------------------------------------------------------ dry run

    def dry_run(self, routine_id: str) -> dict[str, Any]:
        """Evaluate every command in every branch as the routine would run it, without running anything."""
        record = self.get(routine_id)
        who = self.principal_for(record) if record.enabled else routine(record.id, "control_medium", record.sha256)
        problems: list[str] = []
        decisions: list[dict[str, Any]] = []
        if record.parsed is None:
            problems.append("Python routines can't be dry-run step by step. Read the source before enabling it.")
        else:
            self._simulate(record.parsed.steps, "steps", who, Shadow(), decisions, problems)
            missing = sorted(device for device in record.parsed.devices() if device not in self.kernel.devices)
            if missing:
                problems.append(f"Unknown devices: {', '.join(missing)}.")
        ok = not problems and all(item["status"] == "allowed" for item in decisions)
        result = {"ok": ok, "decisions": decisions, "problems": problems}
        record.last_dry_run = result
        return result

    def _simulate(
        self,
        steps: list[Step],
        prefix: str,
        who: Principal,
        shadow: Shadow,
        decisions: list[dict[str, Any]],
        problems: list[str],
    ) -> None:
        """Walk the steps in order. Each branch of an if starts from a copy of the state before it."""
        for index, step in enumerate(steps):
            path = f"{prefix}[{index}]"
            if isinstance(step, WaitStep):
                shadow.now += step.wait
                continue
            if isinstance(step, IfStep):
                self._simulate(step.then, f"{path}.then", who, shadow.copy(), decisions, problems)
                self._simulate(step.else_, f"{path}.else", who, shadow.copy(), decisions, problems)
                continue
            found = _commands([step], path, problems)
            if not found:
                continue
            command = found[0][1]
            decision = self.kernel.evaluate(command, who, shadow=shadow)
            decisions.append({"step": path, **decision.model_dump()})
            if decision.status in ("allowed", "needs_confirmation") and isinstance(command, Write):
                shadow.record(command.device, command.channel, decision.value)

    # ------------------------------------------------------------------ running

    async def run(self, routine_id: str, trigger: str = "manual", *, by: Principal | None = None) -> Run:
        """Run a routine now and wait for it to finish."""
        record = self.get(routine_id)
        if by is not None and by.kind != "human":
            raise RoutineError("Only a human can run a routine by hand.")
        if self.kernel.stopped:
            raise RoutineError("The hub is stopped.")
        if routine_id in self._running:
            raise RoutineError(f"{routine_id} is already running.")
        principal = (
            self.principal_for(record) if record.enabled else routine(record.id, "control_medium", record.sha256)
        )
        task = asyncio.create_task(self._execute(record, trigger, principal), name=f"openhal-routine-{routine_id}")
        self._running[routine_id] = task
        try:
            return await task
        finally:
            self._running.pop(routine_id, None)

    async def _execute(self, record: Record, trigger: str, principal: Principal) -> Run:
        run = Run(secrets.token_hex(6), record.id, trigger, time.time())
        record.last_run = run
        self._last_start[record.id] = time.monotonic()
        self.hub.audit.append(
            "routine_run",
            principal.label,
            target=f"routine:{record.id}",
            status="running",
            run_id=run.run_id,
            trigger=trigger,
        )
        limit = record.parsed.max_runtime if record.parsed is not None else self.settings.max_runtime_s
        limit = min(limit, self.settings.max_runtime_s)
        try:
            await asyncio.wait_for(self._body(record, principal, run), limit)
            if run.status == "running":
                run.status = "ok"
        except RoutineBlockedError as exc:
            run.status = "blocked"
            run.message = exc.decision.message
        except TimeoutError:
            run.status = "failed"
            run.message = f"Stopped after the {limit:g} s max runtime."
        except asyncio.CancelledError:
            run.status = "cancelled"
            run.message = "Cancelled."
        except Exception as exc:  # noqa: BLE001 (a routine bug fails the run, never the hub)
            run.status = "failed"
            run.message = f"{type(exc).__name__}: {exc}"
        run.finished_at = time.time()
        self._store_run(run)
        self.hub.audit.append(
            "routine_run",
            principal.label,
            target=f"routine:{record.id}",
            status=run.status,
            run_id=run.run_id,
            message=run.message,
        )
        return run

    async def _body(self, record: Record, principal: Principal, run: Run) -> None:
        if record.parsed is not None:
            await self._steps(record.parsed.steps, record.parsed.on_block, principal, run)
            return
        namespace: dict[str, Any] = {"__name__": f"openhal_routine_{record.id}"}
        exec(compile(record.source, f"<routine {record.id}>", "exec"), namespace)  # noqa: S102 (human-enabled code)
        entry = namespace.get("run")
        if entry is None or not asyncio.iscoroutinefunction(entry):
            raise RoutineError("The routine has no async def run(ctx).")
        await entry(RoutineContext(self, principal, run))

    async def _steps(self, steps: list[Step], on_block: str, principal: Principal, run: Run) -> None:
        for step in steps:
            if isinstance(step, WriteStep):
                command: Write | Action = Write(
                    device=step.write["device"], channel=step.write["channel"], value=_value(step.write["value"])
                )
                await self.command(command, principal, run, raise_on_block=on_block == "stop")
            elif isinstance(step, ActionStep):
                args = {key: _value(value) for key, value in (step.action.get("args") or {}).items()}
                command = Action(device=step.action["device"], action=step.action["action"], args=args)
                await self.command(command, principal, run, raise_on_block=on_block == "stop")
            elif isinstance(step, WaitStep):
                await self._sleep(step.wait)
            elif isinstance(step, LogStep):
                run.steps.append({"log": step.log})
            elif isinstance(step, IfStep):
                outcome = self.kernel.evaluate_expression(step.if_)
                run.steps.append({"if": step.if_, "result": outcome})
                branch = step.then if outcome is True else step.else_
                await self._steps(branch, on_block, principal, run)

    async def command(
        self, command: Write | Action, principal: Principal, run: Run, *, raise_on_block: bool
    ) -> Decision:
        decision = await self.kernel.execute(command, principal)
        run.steps.append(decision.model_dump())
        if decision.status not in ("done",) and raise_on_block:
            raise RoutineBlockedError(decision)
        return decision

    def _store_run(self, run: Run) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO routine_runs (run_id, routine_id, trigger, started_at, finished_at, status,"
                " message, steps) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    run.run_id,
                    run.routine_id,
                    run.trigger,
                    run.started_at,
                    run.finished_at,
                    run.status,
                    run.message,
                    json.dumps(run.steps, default=str),
                ),
            )

    def history(self, routine_id: str, limit: int = 20) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT run_id, routine_id, trigger, started_at, finished_at, status, message, steps FROM routine_runs"
                " WHERE routine_id = ? ORDER BY started_at DESC LIMIT ?",
                (routine_id, limit),
            ).fetchall()
        return [
            {
                "run_id": row[0],
                "routine_id": row[1],
                "trigger": row[2],
                "started_at": row[3],
                "finished_at": row[4],
                "status": row[5],
                "message": row[6],
                "steps": json.loads(row[7]),
            }
            for row in rows
        ]

    # ------------------------------------------------------------------ scheduling

    async def start(self) -> None:
        self._task = asyncio.create_task(self._scheduler(), name="openhal-routines")

    async def close(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        for routine_id in list(self._running):
            self._cancel(routine_id)

    async def _scheduler(self) -> None:
        while True:
            await asyncio.sleep(0.5)
            if self.kernel.stopped:
                continue
            for record in list(self.records.values()):
                if record.enabled and record.id not in self._running:
                    trigger = self.due(record)
                    if trigger is not None:
                        self._spawn(record, trigger)

    def due(self, record: Record, now: float | None = None, wall: dt.datetime | None = None) -> str | None:
        """Which trigger, if any, should start this routine now."""
        monotonic = time.monotonic() if now is None else now
        last = self._last_start.get(record.id)
        if last is not None and monotonic - last < self.settings.min_interval_s:
            return None
        local = wall or dt.datetime.now()
        for index, trigger in enumerate(record.triggers):
            if isinstance(trigger, EveryTrigger):
                if last is None or monotonic - last >= trigger.every:
                    return f"every {trigger.every:g} s"
            elif isinstance(trigger, AtTrigger):
                stamp = local.strftime("%H:%M")
                today = local.date().isoformat()
                if stamp == trigger.at and record.last_fired.get(index) != today:
                    record.last_fired[index] = today
                    return f"at {trigger.at}"
            elif isinstance(trigger, WhenTrigger):
                current = self.kernel.evaluate_expression(trigger.when)
                previous = record.last_fired.get(index)
                record.last_fired[index] = current
                if current is True and previous is not True:
                    return f"when {trigger.when}"
        return None

    def _spawn(self, record: Record, trigger: str) -> None:
        principal = self.principal_for(record)
        task = asyncio.create_task(self._execute(record, trigger, principal), name=f"openhal-routine-{record.id}")
        self._running[record.id] = task
        task.add_done_callback(lambda _: self._running.pop(record.id, None))

    def _cancel(self, routine_id: str) -> None:
        task = self._running.pop(routine_id, None)
        if task is not None:
            task.cancel()

    async def _on_stop(self, reason: str) -> None:
        for routine_id in list(self._running):
            self._cancel(routine_id)
        for record in self.records.values():
            if record.enabled:
                record.enabled = False
                record.disabled_reason = f"disabled by stop ({reason})"
                self._save(record)

    def summary(self, record: Record) -> dict[str, Any]:
        return {
            "id": record.id,
            "kind": record.kind,
            "enabled": record.enabled,
            "sha256": record.sha256,
            "devices": sorted(self._devices(record)),
            "max_hazard": self.max_hazard(record),
            "triggers": [_describe(trigger) for trigger in record.triggers],
            "drafted_by": record.drafted_by,
            "enabled_by": record.enabled_by,
            "disabled_reason": record.disabled_reason,
            "last_run": record.last_run.view() if record.last_run else None,
        }

    def detail(self, record: Record) -> dict[str, Any]:
        from openhal.hub.views import data_block

        return {
            **self.summary(record),
            "source": data_block(f"routine {record.id} source", record.source),
            "source_raw": record.source,
            "history": self.history(record.id),
            "last_dry_run": record.last_dry_run,
        }


def _describe(trigger: Trigger) -> str:
    if isinstance(trigger, EveryTrigger):
        return f"every {trigger.every:g} s"
    if isinstance(trigger, AtTrigger):
        return f"at {trigger.at}"
    if isinstance(trigger, WhenTrigger):
        return f"when {trigger.when}"
    return "manual"


def _value(value: Any) -> Any:
    """YAML may write quantities as `60 %`. Pass strings, bools and mappings through unchanged."""
    if isinstance(value, int | float) and not isinstance(value, bool):
        raise RoutineError(f"{value} needs a unit, for example {value} %.")
    return value


def _commands(steps: list[Step], prefix: str, problems: list[str]) -> list[tuple[str, Write | Action]]:
    found: list[tuple[str, Write | Action]] = []
    for index, step in enumerate(steps):
        path = f"{prefix}[{index}]" if len(steps) > 1 or not prefix.endswith("]") else prefix
        try:
            if isinstance(step, WriteStep):
                found.append(
                    (
                        path,
                        Write(
                            device=step.write["device"],
                            channel=step.write["channel"],
                            value=_value(step.write["value"]),
                        ),
                    )
                )
            elif isinstance(step, ActionStep):
                args = {key: _value(value) for key, value in (step.action.get("args") or {}).items()}
                found.append((path, Action(device=step.action["device"], action=step.action["action"], args=args)))
            elif isinstance(step, IfStep):
                found.extend(_commands(step.then, f"{path}.then", problems))
                found.extend(_commands(step.else_, f"{path}.else", problems))
        except (RoutineError, UnitError, ValidationError) as exc:
            problems.append(f"{path}: {exc}")
    return found
