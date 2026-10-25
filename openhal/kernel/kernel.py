"""The safety kernel. Every write, action and safe state goes through `Kernel`.

The kernel is deterministic code with no model involved. It evaluates a command against the
current state in the fixed order documented in docs/SAFETY.md, stops at the first failure, and
only then issues a single-use grant to the driver. Any unexpected exception blocks the command or,
once hardware may have changed, marks the affected channels unknown and is logged.

The Python API of this class is trusted. The hub builds principals from authenticated tokens and
agents only ever reach the kernel through the hub's HTTP and MCP interfaces, never through this
object (docs/THREAT_MODEL.md, review finding F13).
"""

from __future__ import annotations

import asyncio
import datetime as dt
import hashlib
import hmac
import math
import time
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass, field
from typing import Any, Final

from openhal.audit.log import AuditLog
from openhal.drivers.base import Driver, Reading
from openhal.kernel.checks import Block, check_rate, effective_limits, normalize
from openhal.kernel.commands import Action, Command, Decision, Write
from openhal.kernel.confirmations import ConfirmationQueue, QueueFull, Request
from openhal.kernel.grants import GrantBook, GrantError, value_digest
from openhal.kernel.principals import SYSTEM, Principal
from openhal.kernel.runtime import DeviceRuntime, RuleState, Sample
from openhal.spec import expressions
from openhal.spec.models import Action as ActionSpec
from openhal.spec.models import Approval, DeviceFile, WriteChannel
from openhal.spec.units import UnitError, convert, format_quantity, parse_quantity, parse_rate

LOCK_TIMEOUT_S: Final = 5.0
DRIVER_TIMEOUT_S: Final = 10.0
STOP_DEVICE_TIMEOUT_S: Final = 10.0
STOP_LOCK_WAIT_S: Final = 5.0
READBACK_TIMEOUT_S: Final = 2.0
APPROVAL_WINDOW_S: Final = 600.0
UNLOCK_PHRASE: Final = "unlock"
WATCHDOG_MAX_FAILURES: Final = 3

Clock = Callable[[], float]
StopHook = Callable[[str], Awaitable[None] | None]


@dataclass
class DeviceStopResult:
    """How one device came out of a stop. Status is safe, partial, failed, pending or no_safe_state."""

    device: str
    status: str
    detail: str = ""


@dataclass
class StopReport:
    reason: str
    by: str
    devices: list[DeviceStopResult] = field(default_factory=list)
    cancelled_requests: int = 0


@dataclass
class Shadow:
    """Values a dry run has already 'written', so a plan's later steps see earlier ones.

    `now` is simulated seconds since the dry run started. A routine's wait steps advance it, so
    rate limits are judged as they would be in a real run.
    """

    values: dict[tuple[str, str], Any] = field(default_factory=dict)
    stamps: dict[tuple[str, str], float] = field(default_factory=dict)
    now: float = 0.0
    runs: dict[tuple[str, str], list[float]] = field(default_factory=dict)

    def record(self, device: str, channel: str, value: Any) -> None:
        self.values[(device, channel)] = value
        self.stamps[(device, channel)] = self.now

    def record_run(self, device: str, action: str) -> None:
        self.runs.setdefault((device, action), []).append(self.now)

    def copy(self) -> Shadow:
        runs = {key: list(times) for key, times in self.runs.items()}
        return Shadow(dict(self.values), dict(self.stamps), self.now, runs)


_Shadow = Shadow


def approval_message(device_id: str, routine: str, sha256: str, by: str, at: str) -> bytes:
    """The exact bytes a routine approval signature covers."""
    return f"openhal-approval-v1|{device_id}|{routine}|{sha256}|{by}|{at}".encode()


class _Unknown:
    def __repr__(self) -> str:
        return "unknown"


_UNKNOWN: Final = _Unknown()


class Kernel:
    """The one place that decides whether a command may reach hardware."""

    def __init__(
        self,
        audit: AuditLog | None = None,
        *,
        clock: Clock = time.monotonic,
        confirm_ttl_s: float = 300.0,
        approval_key: bytes | None = None,
    ) -> None:
        self.audit = audit or AuditLog()
        self.clock = clock
        self.grants = GrantBook()
        self.queue = ConfirmationQueue(ttl_s=confirm_ttl_s, on_change=self._request_changed)
        self.devices: dict[str, DeviceRuntime] = {}
        self.stopped = False
        self.stop_reason: str | None = None
        self._approval_key = approval_key
        self._session_limits: dict[tuple[str, str, str], dict[str, float]] = {}
        self._approval_windows: dict[tuple[str, str, str, str], float] = {}
        self._stop_hooks: list[StopHook] = []
        self._stop_lock = asyncio.Lock()
        self._stop_generation = 0
        self._orphans: dict[str, DeviceFile] = {}

    def register(self, file: DeviceFile, driver: Driver) -> DeviceRuntime:
        """Add a device and attach its driver to a grant verifier for that device only."""
        device_id = file.device_id
        if device_id in self.devices:
            raise ValueError(f"A device with id {device_id!r} is already registered.")
        driver.attach(self.grants.verifier_for(device_id))
        rules = [
            RuleState(rule, expressions.parse_cached(rule.when, file.channel_names()))
            for rule in file.watchdog.max_duration
        ]
        runtime = DeviceRuntime(file=file, driver=driver, rules=rules)
        self._seed_runs(runtime)
        self.devices[device_id] = runtime
        self._orphans.pop(device_id, None)
        self.audit.append(
            "register",
            SYSTEM.label,
            device=device_id,
            hazard=file.effective_hazard,
            writable=file.writable,
            driver=file.connect.driver,
        )
        self.check_references()
        return runtime

    def _seed_runs(self, runtime: DeviceRuntime) -> None:
        """Restore recent action runs from the audit log, so a restart doesn't reset a max_runs window."""
        limited = {name: spec.max_runs for name, spec in runtime.file.actions.items() if spec.max_runs is not None}
        if not limited:
            return
        wall, now = time.time(), self.clock()
        for entry in self.audit.entries(device=runtime.device_id, event="action", limit=5000):
            name = (entry.target or "").removeprefix("action:")
            rule = limited.get(name)
            if rule is None or entry.status not in ("done", "failed"):
                continue
            age = wall - entry.at
            if 0 <= age < rule.per:
                runtime.runs.setdefault(name, []).append(now - age)

    def _check_runs(
        self, runtime: DeviceRuntime, action: str, spec: ActionSpec, now: float, shadow: Shadow | None
    ) -> None:
        rule = spec.max_runs
        if rule is None:
            return
        at = now + (shadow.now if shadow is not None else 0.0)
        times = list(runtime.runs.get(action, []))
        if shadow is not None:
            times += [now + offset for offset in shadow.runs.get((runtime.device_id, action), [])]
        recent = [moment for moment in times if 0 <= at - moment < rule.per]
        if len(recent) >= rule.count:
            wait = max(0.0, min(recent) + rule.per - at)
            raise Block(
                "rate_limited",
                f"Blocked. {action} may run at most {rule.count} times per {_seconds(rule.per)}. "
                f"It ran {len(recent)} times in that window. Try again in {_seconds(wait)}.",
                {"runs": rule.count, "per_s": rule.per},
            )

    def unregister(self, device_id: str) -> None:
        """Remove a device. Its interlocks that name other devices keep protecting them."""
        runtime = self.devices.pop(device_id, None)
        self.grants.revoke_all(device_id)
        if runtime is None:
            return
        if any(ref.device for ref in _file_refs(runtime.file)):
            self._orphans[device_id] = runtime.file
        self.audit.append("unregister", SYSTEM.label, device=device_id, status="done")
        self.check_references()

    def check_references(self) -> dict[str, str]:
        """Mark devices whose expressions name a device that isn't registered (review finding F17).

        Such a device can't be written until the reference is fixed or the other device registers,
        because its interlocks can't protect anything while they point at nothing.
        """
        problems: dict[str, str] = {}
        for runtime in self.devices.values():
            missing = sorted({ref.device for ref in _file_refs(runtime.file) if ref.device} - set(self.devices))
            runtime_problem = None
            if missing:
                runtime_problem = f"its expressions name {', '.join(missing)}, which isn't registered"
                problems[runtime.device_id] = runtime_problem
            if runtime.reference_problem != runtime_problem:
                runtime.reference_problem = runtime_problem
                if runtime_problem:
                    self.audit.append(
                        "reference_problem",
                        SYSTEM.label,
                        device=runtime.device_id,
                        status="blocked",
                        detail=runtime_problem,
                    )
        return problems

    def on_stop(self, hook: StopHook) -> None:
        """Run `hook(reason)` during every stop, after the lock is set (the routine engine pauses here)."""
        self._stop_hooks.append(hook)

    async def connect(self, device_id: str) -> None:
        runtime = self._runtime(device_id)
        await asyncio.wait_for(runtime.driver.connect(), DRIVER_TIMEOUT_S)
        runtime.connected = True
        runtime.connected_at = self.clock()
        runtime.faulted = None
        for channel in list(runtime.file.read) + list(runtime.file.write):
            runtime.mark_unknown(channel, runtime.connected_at)
        self.audit.append("connect", SYSTEM.label, device=device_id, status="done")
        await self.snapshot(device_id)

    async def snapshot(self, device_id: str) -> None:
        """Read every readable channel once, so interlocks and rate limits start from known values."""
        runtime = self._runtime(device_id)
        channels = [name for name, spec in runtime.file.read.items() if spec.type != "image"]
        channels += list(runtime.file.write)
        for channel in channels:
            try:
                reading = await asyncio.wait_for(runtime.driver.read(channel), DRIVER_TIMEOUT_S)
            except Exception:  # noqa: S112, BLE001 (a channel that can't be read stays unknown)
                continue
            self.note_reading(device_id, reading)

    async def connection_lost(self, device_id: str, detail: str) -> None:
        """Called by the hub's heartbeat when a device stops answering."""
        runtime = self._runtime(device_id)
        runtime.connected = False
        self.grants.revoke_all(device_id)
        self.audit.append("connection_lost", SYSTEM.label, device=device_id, status="failed", detail=detail)
        on_loss = runtime.file.watchdog.on_loss or ("safe_state" if runtime.file.safe_state else "hold")
        if on_loss == "safe_state":
            result = await self._apply_safe_state(runtime, reason="connection lost", allow_disconnected=True)
            self.audit.append("safe_state", SYSTEM.label, device=device_id, status=result.status, detail=result.detail)

    def note_reading(self, device_id: str, reading: Reading) -> None:
        """Record a value read from a device, converted into the channel's unit (review finding F20).

        A reading of None means the device can't report this channel, such as a CAN or KNX output
        with no read-back. It adds nothing, so what the kernel already knows stands. A failed
        command still marks its channels unknown.
        """
        runtime = self.devices.get(device_id)
        if runtime is None:
            return
        now = self.clock()
        value = reading.value
        unit = runtime.file.channel_unit(reading.channel)
        if value is None:
            return
        if (
            unit
            and reading.unit
            and reading.unit != unit
            and isinstance(value, int | float)
            and not isinstance(value, bool)
        ):
            try:
                value = convert(parse_quantity(f"{value} {reading.unit}"), unit)
            except UnitError:
                runtime.mark_unknown(reading.channel, now)
                self.audit.append(
                    "read",
                    SYSTEM.label,
                    device=device_id,
                    target=f"read:{reading.channel}",
                    status="failed",
                    code="bad_unit",
                    detail=f"reported {reading.unit}, the file says {unit}",
                )
                return
        if isinstance(value, float) and not math.isfinite(value):
            runtime.mark_unknown(reading.channel, now)
            return
        runtime.reads[reading.channel] = Sample(value, now)

    async def read(self, device_id: str, channel: str, principal: Principal) -> Reading:
        """Read one channel. Every client read request is logged, including failures."""
        runtime = self._runtime(device_id)
        file = runtime.file
        target = f"read:{channel}"
        if channel not in file.read and channel not in file.write:
            self.audit.append(
                "read", principal.label, device=device_id, target=target, status="blocked", code="unknown_target"
            )
            raise LookupError(f"{device_id} has no channel {channel!r}.")
        if runtime.available:
            self.audit.append(
                "read", principal.label, device=device_id, target=target, status="blocked", code="device_unavailable"
            )
            raise _driver_error(f"{device_id} is {runtime.available}.")
        try:
            reading = await asyncio.wait_for(runtime.driver.read(channel), DRIVER_TIMEOUT_S)
        except BaseException as exc:
            self.audit.append(
                "read",
                principal.label,
                device=device_id,
                target=target,
                status="failed",
                code="driver_error",
                detail=f"{type(exc).__name__}: {exc}",
            )
            raise
        self.note_reading(device_id, reading)
        self.audit.append(
            "read",
            principal.label,
            device=device_id,
            target=target,
            status="done",
            value=_jsonable(reading.value),
            unit=reading.unit,
        )
        return reading

    def evaluate(
        self, command: Command, principal: Principal, *, shadow: Shadow | None = None, wire: bool = False
    ) -> Decision:
        """Decide a command without side effects, as a dry run. Never raises. Fails closed.

        `wire` marks a command from a protocol message, REST body or MCP tool. Its numbers must travel
        with a separate unit, never as one string (ADR 0016).
        """
        return self._decide(command, principal, approved=False, shadow=shadow, wire=wire)

    def _decide(
        self, command: Command, principal: Principal, *, approved: bool, shadow: Shadow | None, wire: bool = False
    ) -> Decision:
        target = getattr(command, "target", "unknown")
        device = getattr(command, "device", "unknown")
        try:
            return self._evaluate(command, principal, approved=approved, shadow=shadow, wire=wire)
        except Block as block:
            return Decision(
                status="blocked",
                code=block.code,
                message=block.message,
                device=device,
                target=target,
                limit=block.limit,
            )
        except Exception as exc:  # noqa: BLE001 (fail closed on anything unexpected)
            return Decision(
                status="blocked",
                code="internal_error",
                device=device,
                target=target,
                message=f"Blocked. The safety kernel hit an unexpected error ({type(exc).__name__}). "
                "Nothing was sent to the device.",
            )

    def _evaluate(
        self, command: Command, principal: Principal, *, approved: bool, shadow: Shadow | None, wire: bool
    ) -> Decision:
        now = self.clock()
        if not isinstance(command, Write | Action):
            raise Block("bad_request", "Blocked. The command must be a write or an action.")
        runtime = self.devices.get(command.device)
        if runtime is None:
            raise Block("unknown_target", f"Blocked. There is no device {command.device!r}. Run openhal devices.")
        file = runtime.file
        spec: WriteChannel | None = None
        action_spec: ActionSpec | None = None
        if isinstance(command, Write):
            spec = file.write.get(command.channel)
            if spec is None:
                known = ", ".join(sorted(file.write)) or "none"
                raise Block(
                    "unknown_target",
                    f"Blocked. {command.device} has no write channel {command.channel!r}. Write channels are {known}.",
                )
        else:
            action_spec = file.actions.get(command.action)
            if action_spec is None:
                known = ", ".join(sorted(file.actions)) or "none"
                raise Block(
                    "unknown_target",
                    f"Blocked. {command.device} has no action {command.action!r}. Actions are {known}.",
                )
            unknown = set(command.args) - set(action_spec.args)
            missing = set(action_spec.args) - set(command.args)
            if unknown or missing:
                parts = []
                if unknown:
                    parts.append(f"unknown arguments {', '.join(sorted(unknown))}")
                if missing:
                    parts.append(f"missing arguments {', '.join(sorted(missing))}")
                raise Block("bad_request", f"Blocked. {command.action} has {' and '.join(parts)}.")
        if self.stopped:
            raise Block("stopped", "Blocked. The hub is stopped. A human must unlock it before anything can move.")
        if not file.writable:
            raise Block(
                "read_only_file",
                f"Blocked. {command.device} is read-only until a human confirms limits for "
                f"{', '.join(file.unconfirmed())}. Run the limits interview.",
            )
        dangling = [
            f"{item.device_id} ({item.reference_problem})" for item in self.devices.values() if item.reference_problem
        ]
        if dangling:
            raise Block(
                "misconfigured",
                "Blocked. An interlock or condition names a device that isn't registered, so no device can be "
                f"written until it is fixed. {'; '.join(dangling)}.",
            )
        if runtime.available:
            raise Block("device_unavailable", f"Blocked. {command.device} is {runtime.available}.")
        hazard = file.effective_hazard
        if principal.kind == "system":
            raise Block("not_permitted", "Blocked. The system principal is internal to the kernel.")
        if principal.kind == "agent" and principal.scope == "read":
            raise Block(
                "not_permitted", "Blocked. This client has a read-only token. Ask the owner for a control token."
            )
        if not principal.covers(hazard):
            raise Block(
                "not_permitted",
                f"Blocked. {command.device} is {hazard} hazard and this client's {principal.scope} scope "
                "doesn't cover it.",
            )
        if isinstance(command, Write):
            assert spec is not None
            tightened = self._session_limits.get((principal.label, command.device, command.channel))
            value: Any = normalize(
                command.channel, spec, command.value, unit=command.unit, text=not wire, tightened=tightened
            )
            digest_value: Any = value
            changes: dict[str, Any] = {command.channel: value}
        else:
            assert action_spec is not None
            args = {
                name: normalize(name, action_spec.args[name], raw, text=not wire, argument=True)
                for name, raw in command.args.items()
            }
            value = args
            digest_value = args
            changes = dict.fromkeys(action_spec.effects, _UNKNOWN)
            self._check_runs(runtime, command.action, action_spec, now, shadow)
        if isinstance(command, Write) and spec is not None and spec.type == "number":
            assert spec.unit is not None
            limits = effective_limits(
                spec, self._session_limits.get((principal.label, command.device, command.channel))
            )
            if limits.rate is not None:
                reference, elapsed = self._rate_reference(runtime, command.channel, spec, now, shadow)
                if reference is None:
                    raise Block(
                        "rate_limited",
                        f"Blocked. {command.channel} is rate limited and its current value is unknown. "
                        "Read it first so the change can be measured.",
                    )
                check_rate(command.channel, spec.unit, limits.rate, float(value), reference, elapsed)
        resolver = self._resolver(runtime, changes, now, shadow)
        if isinstance(command, Action) and action_spec is not None:
            for condition, message in action_spec.conditions:
                result = expressions.evaluate(expressions.parse_cached(condition, file.channel_names()), resolver)
                if result is not True:
                    held = "is unknown" if result is None else "doesn't hold"
                    detail = f"{message[:1].upper()}{message[1:]}. " if message else ""
                    reason = message if result is False else f"{command.action} needs {condition}, which is unknown"
                    raise Block(
                        "interlock",
                        f"Blocked. {detail}{command.action} needs {condition}, which {held} right now.",
                        {"interlock": reason} if reason else None,
                    )
        self._check_interlocks(command.device, set(changes), resolver, shadow)
        for state in runtime.rules:
            if not state.exhausted:
                continue
            mentioned = {ref.name for ref in expressions.references(state.tree) if ref.device is None}
            if mentioned & set(changes) and expressions.evaluate(state.tree, resolver) is not False:
                raise Block(
                    "duration_exceeded",
                    f"Blocked. {state.rule.when} already ran for its {_seconds(state.rule.for_)} limit. "
                    "Wait for the budget to reset.",
                )
        decision_kwargs: dict[str, Any] = {
            "device": command.device,
            "target": command.target,
            "value": _jsonable(value),
            "unit": spec.unit if spec is not None else None,
        }
        if spec is not None:
            tier = spec.confirm
        else:
            assert action_spec is not None
            tier = action_spec.confirm
        if hazard == "high":
            tier = "confirm-each-time"
        if self._confirmation_satisfied(command, principal, runtime, tier, digest_value, approved, now):
            return Decision(status="allowed", message="Allowed.", **decision_kwargs)
        if principal.kind == "routine":
            raise Block(
                "needs_confirmation",
                f"Blocked. {command.target} on {command.device} needs a human to confirm, "
                "and routines can't wait for one.",
            )
        return Decision(
            status="needs_confirmation",
            code="needs_confirmation",
            message=f"Waiting for a human to approve {command.target} on {command.device}.",
            **decision_kwargs,
        )

    def _confirmation_satisfied(
        self,
        command: Command,
        principal: Principal,
        runtime: DeviceRuntime,
        tier: str,
        digest_value: Any,
        approved: bool,
        now: float,
    ) -> bool:
        if principal.kind == "human" or approved:
            return True
        if principal.kind == "routine":
            if runtime.file.effective_hazard == "high":
                return self._routine_approved(runtime, principal)
            return tier == "none"
        if tier == "none":
            return True
        if tier == "confirm":
            key = (principal.label, command.device, command.target, value_digest(digest_value))
            expires = self._approval_windows.get(key)
            return expires is not None and now <= expires
        return False

    def _routine_approved(self, runtime: DeviceRuntime, principal: Principal) -> bool:
        if self._approval_key is None or principal.ref is None:
            return False
        for approval in runtime.file.approvals:
            if approval.routine == principal.name and approval.sha256 == principal.ref:
                expected = self._sign(
                    runtime.device_id, approval.routine, approval.sha256, approval.by, approval.at.isoformat()
                )
                if hmac.compare_digest(expected, approval.signature):
                    return True
        return False

    def _sign(self, device_id: str, routine: str, sha256: str, by: str, at: str) -> str:
        """HMAC signature for a routine approval. Only approve_routine and the check above use it."""
        if self._approval_key is None:
            raise PermissionError("This hub has no approval key, so it can't sign approvals.")
        message = approval_message(device_id, routine, sha256, by, at)
        return hmac.new(self._approval_key, message, hashlib.sha256).hexdigest()

    def approve_routine(self, principal: Principal, device_id: str, routine: str, sha256: str) -> Approval:
        """Create a signed approval for a routine on a high hazard device. Humans only."""
        if principal.kind != "human":
            raise PermissionError("Only a human can approve a routine for a high hazard device.")
        at = dt.datetime.now(dt.UTC).replace(microsecond=0)
        signature = self._sign(device_id, routine, sha256, principal.name, at.isoformat())
        self.audit.append(
            "approve_routine",
            principal.label,
            device=device_id,
            target=f"routine:{routine}",
            status="done",
            sha256=sha256,
        )
        return Approval(routine=routine, sha256=sha256, by=principal.name, at=at, signature=signature)

    def _rate_reference(
        self, runtime: DeviceRuntime, channel: str, spec: WriteChannel, now: float, shadow: Shadow | None
    ) -> tuple[float | None, float]:
        """The value a change is measured from, and the seconds since it was observed.

        Returns (None, 0) when the channel's value is unknown (after a failed command, or after an
        action that may have changed it), which blocks the write (review findings F05 and F14).
        """
        if shadow is not None and (runtime.device_id, channel) in shadow.values:
            key = (runtime.device_id, channel)
            return float(shadow.values[key]), shadow.now - shadow.stamps.get(key, shadow.now)
        candidates = [
            sample
            for sample in runtime.known_samples(channel)
            if isinstance(sample.value, int | float) and not isinstance(sample.value, bool)
        ]
        if candidates:
            newest = max(candidates, key=lambda sample: sample.at)
            return float(newest.value), now - newest.at
        if channel in runtime.unknown_since and runtime.unknown_since[channel] > runtime.connected_at:
            return None, 0.0
        fallback = _safe_value(runtime.file, channel)
        if fallback is None:
            fallback = spec.min
        return fallback, now - runtime.connected_at

    def _resolver(
        self, runtime: DeviceRuntime, changes: dict[str, Any], now: float, shadow: Shadow | None
    ) -> expressions.Resolver:
        def resolve(ref: expressions.Ref) -> expressions.Value | None:
            target = runtime if ref.device is None else self.devices.get(ref.device)
            if target is None:
                return None
            if target is runtime and ref.name in changes:
                raw = changes[ref.name]
            elif shadow is not None and (target.device_id, ref.name) in shadow.values:
                raw = shadow.values[(target.device_id, ref.name)]
            else:
                sample = target.latest(ref.name, now)
                raw = None if sample is None else sample.value
            return _as_value(target, ref.name, raw)

        return resolve

    def _check_interlocks(
        self, device_id: str, changed: set[str], resolver: expressions.Resolver, shadow: Shadow | None
    ) -> None:
        owners: list[tuple[str, DeviceFile, DeviceRuntime | None]] = [
            (runtime.device_id, runtime.file, runtime) for runtime in self.devices.values()
        ]
        owners += [(owner_id, file, None) for owner_id, file in self._orphans.items()]
        for owner_id, file, owner in owners:
            channels = file.channel_names()
            for interlock in file.interlocks:
                if_tree = expressions.parse_cached(interlock.if_, channels)
                require_tree = expressions.parse_cached(interlock.require, channels)
                refs = expressions.references(if_tree) | expressions.references(require_tree)
                touches = any(
                    (ref.device is None and owner_id == device_id and ref.name in changed)
                    or (ref.device == device_id and ref.name in changed)
                    for ref in refs
                )
                if not touches:
                    continue
                if owner_id == device_id:
                    local = resolver
                else:
                    local = self._foreign_resolver(owner, device_id, resolver, shadow)
                applies = expressions.evaluate(if_tree, local)
                satisfied = expressions.evaluate(require_tree, local)
                if applies is not False and satisfied is not True:
                    detail = interlock.message or f"When {interlock.if_}, {interlock.require} must hold."
                    state = "is unknown" if satisfied is None else "doesn't hold"
                    where = owner_id if owner is not None else f"{owner_id} (not registered right now)"
                    reason = interlock.message if satisfied is False else f"{interlock.require} is unknown right now"
                    raise Block(
                        "interlock",
                        f"Blocked by an interlock on {where}. {detail} Right now {interlock.require} {state}.",
                        {"interlock": reason} if reason else None,
                    )

    def _foreign_resolver(
        self, owner: DeviceRuntime | None, changed_device: str, resolver: expressions.Resolver, shadow: Shadow | None
    ) -> expressions.Resolver:
        """Resolve another device's interlock. Its bare names are its own channels."""

        def resolve(ref: expressions.Ref) -> expressions.Value | None:
            if ref.device is None:
                if owner is None:
                    return None
                if shadow is not None and (owner.device_id, ref.name) in shadow.values:
                    return _as_value(owner, ref.name, shadow.values[(owner.device_id, ref.name)])
                sample = owner.latest(ref.name, self.clock())
                return _as_value(owner, ref.name, None if sample is None else sample.value)
            if ref.device == changed_device:
                return resolver(expressions.Ref(None, ref.name))
            return resolver(ref)

        return resolve

    async def execute(
        self, command: Command, principal: Principal, *, request: Request | None = None, wire: bool = False
    ) -> Decision:
        """Evaluate and, if allowed, run a command. Queues it if it needs a human.

        `request` is only honored when it is the queue's own approved request for this exact
        command, which only `confirm` produces (review finding F13). `wire` is as for `evaluate`.
        """
        runtime = self.devices.get(getattr(command, "device", ""))
        if runtime is None:
            decision = self.evaluate(command, principal, wire=wire)
            self._log(command, principal, decision)
            return decision
        approved = (
            request is not None
            and self.queue.get(request.request_id) is request
            and request.status == "approved"
            and request.command == command
            and request.principal == principal
        )
        try:
            await asyncio.wait_for(runtime.lock.acquire(), LOCK_TIMEOUT_S)
        except TimeoutError:
            decision = Decision(
                status="blocked",
                code="busy",
                device=command.device,
                target=command.target,
                message=f"Blocked. {command.device} is busy with another command. Try again.",
            )
            self._log(command, principal, decision)
            return decision
        try:
            decision = self._decide(command, principal, approved=approved, shadow=None, wire=wire)
            if decision.status == "needs_confirmation":
                try:
                    queued = self.queue.add(command, principal, decision, self.clock())
                except QueueFull as full:
                    blocked = decision.model_copy(
                        update={"status": "blocked", "code": "queue_full", "message": str(full)}
                    )
                    self._log(command, principal, blocked)
                    return blocked
                pending = decision.model_copy(update={"status": "pending", "request_id": queued.request_id})
                self._log(command, principal, pending)
                return pending
            if decision.status != "allowed":
                self._log(command, principal, decision, request=request)
                return decision
            return await self._run(runtime, command, principal, decision, request)
        finally:
            runtime.lock.release()

    async def _run(
        self,
        runtime: DeviceRuntime,
        command: Command,
        principal: Principal,
        decision: Decision,
        request: Request | None,
    ) -> Decision:
        """Send one allowed command to the driver. Runs with the device lock held."""
        before = self._before(runtime, command)
        generation = self._stop_generation
        if isinstance(command, Write):
            channels = [command.channel]
            value: Any = normalize(
                command.channel,
                runtime.file.write[command.channel],
                command.value,
                unit=command.unit,
                tightened=self._session_limits.get((principal.label, command.device, command.channel)),
            )
        else:
            spec = runtime.file.actions[command.action]
            channels = list(spec.effects)
            value = {name: normalize(name, spec.args[name], raw, argument=True) for name, raw in command.args.items()}
        grant = self.grants.issue(runtime.device_id, command.target, value)
        if isinstance(command, Action):
            runtime.runs.setdefault(command.action, []).append(self.clock())
        runtime.inflight.update(channels)
        runtime.inflight_task = asyncio.current_task()
        sent = False
        try:
            if isinstance(command, Write):
                reading = await asyncio.wait_for(runtime.driver.write(command.channel, value, grant), DRIVER_TIMEOUT_S)
                runtime.accepted[command.channel] = Sample(value, self.clock(), commanded=True)
                runtime.unknown_since.pop(command.channel, None)
                if reading is not None:
                    self.note_reading(runtime.device_id, reading)
                result = decision.model_copy(
                    update={
                        "status": "done",
                        "message": f"Done. {command.channel} is now {_display(value, decision.unit)}.",
                    }
                )
            else:
                await asyncio.wait_for(runtime.driver.action(command.action, value, grant), DRIVER_TIMEOUT_S)
                result = decision.model_copy(update={"status": "done", "message": f"Done. {command.action} ran."})
            sent = True
        except GrantError as exc:
            result = decision.model_copy(
                update={
                    "status": "blocked",
                    "code": "internal_error",
                    "message": f"Blocked. Grant check failed ({exc}).",
                }
            )
        except asyncio.CancelledError:
            if generation == self._stop_generation:
                self._mark_unknown(runtime, channels)
                self._log(
                    command,
                    principal,
                    decision.model_copy(
                        update={
                            "status": "failed",
                            "code": "driver_error",
                            "message": "Cancelled before the device answered.",
                        }
                    ),
                    before=before,
                    request=request,
                )
                raise
            task = asyncio.current_task()
            if task is not None:
                task.uncancel()
            result = decision.model_copy(
                update={
                    "status": "failed",
                    "code": "stopped",
                    "message": "Cancelled by a stop. The device may have received the command, so its safe state is "
                    "applied again.",
                }
            )
        except Exception as exc:  # noqa: BLE001 (any driver failure is a result, review finding F06)
            result = decision.model_copy(
                update={
                    "status": "failed",
                    "code": "driver_error",
                    "message": f"The device didn't complete {command.target}. {type(exc).__name__}: {exc}".rstrip(),
                }
            )
        finally:
            runtime.inflight.difference_update(channels)
            runtime.inflight_task = None
        if not sent or isinstance(command, Action):
            self._mark_unknown(runtime, channels)
            await self._read_back(runtime, channels)
        self._log(command, principal, result, before=before, request=request)
        if generation != self._stop_generation:
            await self._reapply_after_stop(runtime)
        return result

    def _mark_unknown(self, runtime: DeviceRuntime, channels: list[str]) -> None:
        now = self.clock()
        for channel in channels:
            runtime.mark_unknown(channel, now)

    async def _read_back(self, runtime: DeviceRuntime, channels: list[str]) -> None:
        for channel in channels:
            try:
                reading = await asyncio.wait_for(runtime.driver.read(channel), READBACK_TIMEOUT_S)
            except Exception:  # noqa: BLE001, S112 (the channel stays unknown)
                continue
            self.note_reading(runtime.device_id, reading)

    async def _reapply_after_stop(self, runtime: DeviceRuntime) -> None:
        """A stop happened while a command was in flight. Undo whatever may have landed (review F03)."""
        result = await self._apply_safe_state(runtime, reason="stop happened while a command was in flight")
        self.audit.append(
            "safe_state",
            SYSTEM.label,
            device=runtime.device_id,
            status=result.status,
            detail=f"reapplied after an in-flight command. {result.detail}",
        )

    def _before(self, runtime: DeviceRuntime, command: Command) -> Any:
        if isinstance(command, Write):
            sample = runtime.latest(command.channel, self.clock())
            return None if sample is None else _jsonable(sample.value)
        return None

    def _log(
        self,
        command: Command,
        principal: Principal,
        decision: Decision,
        *,
        before: Any = None,
        request: Request | None = None,
    ) -> None:
        details: dict[str, Any] = {"message": decision.message}
        if isinstance(command, Write):
            asked = command.value if command.unit is None else {"value": command.value, "unit": command.unit}
            details["requested"] = _jsonable(asked)
        else:
            details["args"] = _jsonable(getattr(command, "args", {}))
        if decision.limit and decision.status in ("blocked", "failed"):
            details["limit"] = _jsonable(decision.limit)
        if decision.status == "done":
            details["before"] = before
            details["after"] = decision.value
        if decision.request_id:
            details["request_id"] = decision.request_id
        if request is not None:
            details["request_id"] = request.request_id
            details["approved_by"] = request.decided_by
        event = "action" if isinstance(command, Action) else "write"
        self.audit.append(
            event,
            principal.label,
            device=getattr(command, "device", None),
            target=getattr(command, "target", None),
            status=decision.status,
            code=decision.code,
            **details,
        )

    def dry_run(self, commands: Iterable[Command], principal: Principal, *, wire: bool = False) -> list[Decision]:
        """Evaluate commands in order as if each allowed one had run. Nothing is sent anywhere."""
        shadow = Shadow()
        decisions = []
        for command in commands:
            decision = self.evaluate(command, principal, shadow=shadow, wire=wire)
            decisions.append(decision)
            if decision.status in ("allowed", "needs_confirmation"):
                if isinstance(command, Write):
                    shadow.record(command.device, command.channel, decision.value)
                else:
                    shadow.record_run(command.device, command.action)
        return decisions

    def _request_changed(self, request: Request, reason: str) -> None:
        self.audit.append(
            "request",
            SYSTEM.label,
            device=request.command.device,
            target=request.command.target,
            status=request.status,
            request_id=request.request_id,
            requested_by=request.principal.label,
            reason=reason,
        )

    async def confirm(self, request_id: str, principal: Principal) -> Decision:
        """A human approves a queued request. All checks run again against the current state."""
        request = self.queue.get(request_id)
        if principal.kind != "human":
            self.audit.append("confirm", principal.label, status="blocked", code="not_permitted", request_id=request_id)
            raise PermissionError("Only a human can approve a request.")
        self.queue.expire(self.clock())
        if request is None or request.status != "pending":
            status = "missing" if request is None else request.status
            self.audit.append(
                "confirm", principal.label, status="blocked", code="expired", request_id=request_id, state=status
            )
            raise LookupError(f"Request {request_id} is {status}, so it can't be approved.")
        request.status = "approved"
        request.decided_by = principal.label
        self.audit.append(
            "confirm",
            principal.label,
            device=request.command.device,
            target=request.command.target,
            status="done",
            request_id=request_id,
            requested_by=request.principal.label,
        )
        generation = self._stop_generation
        decision = await self.execute(request.command, request.principal, request=request)
        request.result = decision
        request.status = (
            "done" if decision.status == "done" else ("failed" if decision.status == "failed" else "blocked")
        )
        if decision.status == "done" and generation == self._stop_generation and not self.stopped:
            runtime = self.devices[request.command.device]
            tier = (
                runtime.file.write[request.command.channel].confirm
                if isinstance(request.command, Write)
                else runtime.file.actions[request.command.action].confirm
            )
            if tier == "confirm" and runtime.file.effective_hazard != "high":
                digest_value = (
                    decision.value
                    if isinstance(request.command, Write)
                    else self._action_args(runtime, request.command)
                )
                key = (
                    request.principal.label,
                    request.command.device,
                    request.command.target,
                    value_digest(digest_value),
                )
                self._approval_windows[key] = self.clock() + APPROVAL_WINDOW_S
        return decision

    def _action_args(self, runtime: DeviceRuntime, command: Action) -> dict[str, Any]:
        spec = runtime.file.actions[command.action]
        return {name: normalize(name, spec.args[name], raw) for name, raw in command.args.items()}

    def reject(self, request_id: str, principal: Principal, reason: str = "") -> Request:
        """A human rejects a queued request."""
        if principal.kind != "human":
            raise PermissionError("Only a human can reject a request.")
        request = self.queue.get(request_id)
        if request is None or request.status != "pending":
            raise LookupError(f"Request {request_id} is not pending.")
        request.status = "rejected"
        request.decided_by = principal.label
        self.audit.append(
            "reject",
            principal.label,
            device=request.command.device,
            target=request.command.target,
            status="rejected",
            code="rejected",
            request_id=request_id,
            reason=reason,
        )
        return request

    def tighten(
        self, principal: Principal, device_id: str, channel: str, *, min: Any = None, max: Any = None, rate: Any = None
    ) -> dict[str, float]:
        """Narrow a channel's limits for this principal's session. Widening is refused. Refusals are logged."""
        target = f"write:{channel}"
        try:
            runtime = self._runtime(device_id)
            spec = runtime.file.write.get(channel)
            if spec is None or spec.type != "number" or spec.unit is None:
                raise Block("unknown_target", f"Refused. {device_id} has no numeric write channel {channel!r}.")
            key = (principal.label, device_id, channel)
            current = effective_limits(spec, self._session_limits.get(key))
            updated = dict(self._session_limits.get(key, {}))
            try:
                if min is not None:
                    low = convert(parse_quantity(min), spec.unit)
                    if low < current.min:
                        raise Block(
                            "cannot_loosen",
                            f"Refused. {channel} min is already {format_quantity(current.min, spec.unit)}. "
                            "Session limits can only be tightened.",
                        )
                    updated["min"] = low
                if max is not None:
                    high = convert(parse_quantity(max), spec.unit)
                    if high > current.max:
                        raise Block(
                            "cannot_loosen",
                            f"Refused. {channel} max is already {format_quantity(current.max, spec.unit)}. "
                            "Session limits can only be tightened.",
                        )
                    updated["max"] = high
                if rate is not None:
                    value = parse_rate(rate, spec.unit)
                    if current.rate is not None and value > current.rate:
                        raise Block(
                            "cannot_loosen",
                            f"Refused. {channel} may already change by at most "
                            f"{format_quantity(current.rate, spec.unit)} per second. "
                            "Session limits can only be tightened.",
                        )
                    updated["rate"] = value
            except UnitError as exc:
                raise Block("bad_unit", f"Refused. {exc}") from exc
            if updated.get("min", -math.inf) > updated.get("max", math.inf):
                raise Block("cannot_loosen", "Refused. min would be above max.")
        except Block as block:
            self.audit.append(
                "tighten",
                principal.label,
                device=device_id,
                target=target,
                status="blocked",
                code=block.code,
                message=block.message,
            )
            if block.code == "unknown_target":
                raise LookupError(block.message) from None
            raise
        except LookupError:
            self.audit.append(
                "tighten", principal.label, device=device_id, target=target, status="blocked", code="unknown_target"
            )
            raise
        self._session_limits[key] = updated
        self.audit.append("tighten", principal.label, device=device_id, target=target, status="done", limits=updated)
        return updated

    async def stop_all(self, principal: Principal, reason: str = "stop requested") -> StopReport:
        """Lock writes, cancel pending requests, pause routines, then put every device in its safe state."""
        async with self._stop_lock:
            self._stop_generation += 1
            self.stopped = True
            self.stop_reason = reason
            self.audit.append("stop", principal.label, status="done", reason=reason)
            cancelled = self.queue.cancel_all("cancelled by stop")
            self._approval_windows.clear()
            for hook in list(self._stop_hooks):
                try:
                    outcome = hook(reason)
                    if asyncio.iscoroutine(outcome):
                        await outcome
                except Exception as exc:  # noqa: BLE001 (a hook failure must not stop the stop)
                    self.audit.append("stop_hook", SYSTEM.label, status="failed", detail=repr(exc))
            report = StopReport(reason=reason, by=principal.label, cancelled_requests=len(cancelled))
            runtimes = list(self.devices.values())
            results = await asyncio.gather(
                *(self._stop_device(runtime, reason) for runtime in runtimes), return_exceptions=True
            )
            for runtime, result in zip(runtimes, results, strict=True):
                if isinstance(result, BaseException):
                    report.devices.append(DeviceStopResult(runtime.device_id, "failed", repr(result)))
                else:
                    report.devices.append(result)
            for item in report.devices:
                self.audit.append(
                    "safe_state", SYSTEM.label, device=item.device, status=item.status, detail=item.detail
                )
            return report

    async def _stop_device(self, runtime: DeviceRuntime, reason: str) -> DeviceStopResult:
        self.grants.revoke_all(runtime.device_id)
        task = runtime.inflight_task
        if task is not None and task is not asyncio.current_task() and not task.done():
            task.cancel()
        acquired = False
        try:
            await asyncio.wait_for(runtime.lock.acquire(), STOP_LOCK_WAIT_S)
            acquired = True
        except TimeoutError:
            pass
        try:
            result = await self._apply_safe_state(runtime, reason=reason)
            if not acquired and result.status == "safe":
                result = DeviceStopResult(
                    runtime.device_id,
                    "pending",
                    "A command was still running. The safe state was applied and is applied again when it returns.",
                )
            return result
        finally:
            if acquired:
                runtime.lock.release()

    async def _apply_safe_state(
        self, runtime: DeviceRuntime, *, reason: str, allow_disconnected: bool = False
    ) -> DeviceStopResult:
        """Run every safe-state step even if one fails, and log each change (review findings F09 and F16)."""
        file = runtime.file
        if not (file.write or file.actions):
            return DeviceStopResult(runtime.device_id, "safe", "read-only device")
        if not file.safe_state and runtime.driver.info.safe_state_support != "native":
            return DeviceStopResult(runtime.device_id, "no_safe_state", file.safe_state_note or "no safe state defined")
        if not runtime.connected and not allow_disconnected:
            return DeviceStopResult(runtime.device_id, "failed", "not connected")
        runtime.applying_safe_state = True
        errors: list[str] = []
        steps = 0
        try:
            deadline = time.monotonic() + STOP_DEVICE_TIMEOUT_S

            async def bounded(coro: Awaitable[Any]) -> Any:
                return await asyncio.wait_for(coro, max(0.1, deadline - time.monotonic()))

            steps += 1
            try:
                await bounded(runtime.driver.safe_state(self.grants.issue(runtime.device_id, "safe_state", None)))
            except Exception as exc:  # noqa: BLE001 (keep going with the file's steps)
                errors.append(f"native safe state: {type(exc).__name__}: {exc}")
            for step in file.safe_state:
                if step.action is not None:
                    steps += 1
                    spec = file.actions[step.action]
                    try:
                        args = {
                            name: normalize(name, spec.args[name], _quantity_text(raw, spec.args[name].unit))
                            for name, raw in step.args.items()
                        }
                        grant = self.grants.issue(runtime.device_id, f"action:{step.action}", args)
                        await bounded(runtime.driver.action(step.action, args, grant))
                        self.audit.append(
                            "action",
                            SYSTEM.label,
                            device=runtime.device_id,
                            target=f"action:{step.action}",
                            status="done",
                            args=_jsonable(args),
                            reason=reason,
                        )
                    except Exception as exc:  # noqa: BLE001
                        errors.append(f"{step.action}: {type(exc).__name__}: {exc}")
                        self.audit.append(
                            "action",
                            SYSTEM.label,
                            device=runtime.device_id,
                            target=f"action:{step.action}",
                            status="failed",
                            code="driver_error",
                            detail=str(exc),
                            reason=reason,
                        )
                for channel, raw in step.values.items():
                    steps += 1
                    before = runtime.latest(channel, self.clock())
                    try:
                        value = _safe_value_for(file, channel, raw)
                        grant = self.grants.issue(runtime.device_id, f"write:{channel}", value)
                        await bounded(runtime.driver.write(channel, value, grant))
                        runtime.accepted[channel] = Sample(value, self.clock(), commanded=True)
                        runtime.unknown_since.pop(channel, None)
                        self.audit.append(
                            "write",
                            SYSTEM.label,
                            device=runtime.device_id,
                            target=f"write:{channel}",
                            status="done",
                            before=None if before is None else _jsonable(before.value),
                            after=_jsonable(value),
                            reason=reason,
                        )
                    except Exception as exc:  # noqa: BLE001
                        errors.append(f"{channel}: {type(exc).__name__}: {exc}")
                        runtime.mark_unknown(channel, self.clock())
                        self.audit.append(
                            "write",
                            SYSTEM.label,
                            device=runtime.device_id,
                            target=f"write:{channel}",
                            status="failed",
                            code="driver_error",
                            detail=str(exc),
                            reason=reason,
                        )
        finally:
            runtime.applying_safe_state = False
        if not errors:
            return DeviceStopResult(runtime.device_id, "safe", reason)
        failed_all = len(errors) >= steps
        return DeviceStopResult(runtime.device_id, "failed" if failed_all else "partial", "; ".join(errors))

    def unlock(self, principal: Principal, phrase: str) -> None:
        """A human lifts the stop lock by typing the unlock phrase."""
        if principal.kind != "human":
            self.audit.append("unlock", principal.label, status="blocked", code="not_permitted")
            raise PermissionError("Only a human can unlock after a stop.")
        if phrase.strip().lower() != UNLOCK_PHRASE:
            self.audit.append("unlock", principal.label, status="blocked", code="bad_request")
            raise ValueError(f"Type {UNLOCK_PHRASE} to confirm.")
        if self._stop_lock.locked():
            self.audit.append("unlock", principal.label, status="blocked", code="busy")
            raise ValueError("A stop is still being applied. Try again in a moment.")
        self.stopped = False
        self.stop_reason = None
        self._approval_windows.clear()
        self.audit.append("unlock", principal.label, status="done")

    async def tick(self) -> list[str]:
        """Advance max-duration budgets and apply rules whose budget ran out. Returns what fired."""
        fired: list[str] = []
        now = self.clock()
        for runtime in list(self.devices.values()):
            resolver = self._resolver(runtime, {}, now, None)
            for state in runtime.rules:
                active = expressions.evaluate(state.tree, resolver)
                counting = active is True or (active is None and state.active_since is not None)
                if counting:
                    state.false_since = None
                    if state.active_since is None:
                        state.active_since = now
                    if not state.exhausted and now - state.active_since >= state.rule.for_:
                        state.exhausted = True
                        state.applied = False
                        state.failures = 0
                        state.retry_at = now
                        fired.append(f"{runtime.device_id}: {state.rule.when}")
                    if state.exhausted and not state.applied and now >= state.retry_at:
                        await self._fire(runtime, state, now)
                elif active is False:
                    if state.false_since is None:
                        state.false_since = now
                    reset_after = state.rule.reset_after if state.rule.reset_after is not None else state.rule.for_
                    if now - state.false_since >= reset_after:
                        if state.exhausted:
                            self.audit.append(
                                "watchdog_reset", SYSTEM.label, device=runtime.device_id, rule=state.rule.when
                            )
                        state.active_since = None
                        state.exhausted = False
                        state.applied = False
        return fired

    async def _fire(self, runtime: DeviceRuntime, state: RuleState, now: float) -> None:
        """Apply a rule's action, retrying with backoff and escalating to the safe state (review F11)."""
        escalate = isinstance(state.rule.then, dict) and state.failures >= WATCHDOG_MAX_FAILURES
        ok = await self._apply_rule(runtime, state, safe_state=escalate or state.rule.then == "safe_state")
        if ok:
            state.applied = True
        else:
            state.failures += 1
            state.retry_at = now + min(2.0**state.failures, 30.0)

    async def _apply_rule(self, runtime: DeviceRuntime, state: RuleState, *, safe_state: bool) -> bool:
        then = "safe_state" if safe_state else state.rule.then
        if safe_state:
            async with runtime.lock:
                result = await self._apply_safe_state(runtime, reason=f"watchdog: {state.rule.when}")
            ok = result.status == "safe"
            self.audit.append(
                "watchdog",
                SYSTEM.label,
                device=runtime.device_id,
                status="done" if ok else "failed",
                rule=state.rule.when,
                then="safe_state",
                detail=result.detail,
            )
            return ok
        assert isinstance(then, dict)
        ok = True
        async with runtime.lock:
            for channel, raw in then.items():
                before = runtime.latest(channel, self.clock())
                try:
                    value = _safe_value_for(runtime.file, channel, raw)
                    grant = self.grants.issue(runtime.device_id, f"write:{channel}", value)
                    await asyncio.wait_for(runtime.driver.write(channel, value, grant), DRIVER_TIMEOUT_S)
                    runtime.accepted[channel] = Sample(value, self.clock(), commanded=True)
                    runtime.unknown_since.pop(channel, None)
                    self.audit.append(
                        "write",
                        SYSTEM.label,
                        device=runtime.device_id,
                        target=f"write:{channel}",
                        status="done",
                        before=None if before is None else _jsonable(before.value),
                        after=_jsonable(value),
                        reason=f"watchdog: {state.rule.when}",
                    )
                except Exception as exc:  # noqa: BLE001
                    ok = False
                    runtime.mark_unknown(channel, self.clock())
                    self.audit.append(
                        "write",
                        SYSTEM.label,
                        device=runtime.device_id,
                        target=f"write:{channel}",
                        status="failed",
                        code="driver_error",
                        detail=repr(exc),
                        reason=f"watchdog: {state.rule.when}",
                    )
        self.audit.append(
            "watchdog",
            SYSTEM.label,
            device=runtime.device_id,
            status="done" if ok else "failed",
            rule=state.rule.when,
            then=_jsonable(then),
        )
        return ok

    def evaluate_expression(self, text: str) -> bool | None:
        """Evaluate an expression against current state. References must name their device.

        Bare names are words (enum values), never channels, so `a != b` compares two words.
        """
        tree = expressions.parse(text, frozenset())
        now = self.clock()

        def resolve(ref: expressions.Ref) -> expressions.Value | None:
            if ref.device is None:
                return None
            target = self.devices.get(ref.device)
            if target is None:
                return None
            sample = target.latest(ref.name, now)
            return _as_value(target, ref.name, None if sample is None else sample.value)

        return expressions.evaluate(tree, resolve)

    def _runtime(self, device_id: str) -> DeviceRuntime:
        runtime = self.devices.get(device_id)
        if runtime is None:
            raise LookupError(f"There is no device {device_id!r}.")
        return runtime

    def pending(self) -> list[Request]:
        return self.queue.pending(self.clock())


def _driver_error(message: str) -> Exception:
    from openhal.drivers.base import DriverError

    return DriverError(message)


def _file_refs(file: DeviceFile) -> set[expressions.Ref]:
    channels = file.channel_names()
    texts = [item.if_ for item in file.interlocks] + [item.require for item in file.interlocks]
    texts += [condition for action in file.actions.values() for condition, _message in action.conditions]
    texts += [rule.when for rule in file.watchdog.max_duration]
    found: set[expressions.Ref] = set()
    for text in texts:
        found |= expressions.references(expressions.parse_cached(text, channels))
    return found


def _as_value(target: DeviceRuntime, channel: str, raw: Any) -> expressions.Value | None:
    if raw is None or raw is _UNKNOWN:
        return None
    if isinstance(raw, bool | str):
        return expressions.Value(raw)
    if isinstance(raw, int | float):
        return expressions.Value(float(raw), target.file.channel_unit(channel))
    return None


def _jsonable(value: Any) -> Any:
    if isinstance(value, bytes):
        return f"<{len(value)} bytes>"
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, float) and not math.isfinite(value):
        return repr(value)
    return value


def _display(value: Any, unit: str | None) -> str:
    if isinstance(value, float) and unit:
        return format_quantity(value, unit)
    return str(value).lower() if isinstance(value, bool) else str(value)


def _seconds(seconds: float) -> str:
    if seconds >= 3600 and seconds % 3600 == 0:
        return f"{seconds / 3600:g} h"
    if seconds >= 60 and seconds % 60 == 0:
        return f"{seconds / 60:g} min"
    return f"{seconds:g} s"


def _quantity_text(raw: Any, unit: str | None) -> Any:
    """Safe states and watchdog rules in files may use bare numbers in the channel unit."""
    if unit is not None and isinstance(raw, int | float) and not isinstance(raw, bool):
        return f"{raw} {unit}"
    return raw


def _safe_value_for(file: DeviceFile, channel: str, raw: Any) -> float | bool | str:
    spec = file.write[channel]
    return normalize(channel, spec, _quantity_text(raw, spec.unit))


def _safe_value(file: DeviceFile, channel: str) -> float | None:
    for step in file.safe_state:
        if channel in step.values:
            value = _safe_value_for(file, channel, step.values[channel])
            if isinstance(value, float):
                return value
    return None
