"""The safety kernel. Every write, action and safe state goes through `Kernel`.

The kernel is deterministic code with no model involved. It evaluates a command against the
current state in the fixed order documented in docs/SAFETY.md, stops at the first failure, and
only then issues a single-use grant to the driver. Any unexpected exception blocks the command.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import math
import time
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass, field
from typing import Any, Final

from openhal.audit.log import AuditLog
from openhal.drivers.base import Driver, DriverError, Reading
from openhal.kernel.checks import Block, check_rate, effective_limits, normalize
from openhal.kernel.commands import Action, Command, Decision, Write
from openhal.kernel.confirmations import ConfirmationQueue, Request
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
APPROVAL_WINDOW_S: Final = 600.0
UNLOCK_PHRASE: Final = "unlock"

Clock = Callable[[], float]
StopHook = Callable[[str], Awaitable[None] | None]


@dataclass
class DeviceStopResult:
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

    def record(self, device: str, channel: str, value: Any) -> None:
        self.values[(device, channel)] = value
        self.stamps[(device, channel)] = self.now

    def copy(self) -> Shadow:
        return Shadow(dict(self.values), dict(self.stamps), self.now)


_Shadow = Shadow


def approval_message(device_id: str, routine: str, sha256: str, by: str, at: str) -> bytes:
    """The exact bytes a routine approval signature covers."""
    return f"openhal-approval-v1|{device_id}|{routine}|{sha256}|{by}|{at}".encode()


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
        self.queue = ConfirmationQueue(ttl_s=confirm_ttl_s)
        self.devices: dict[str, DeviceRuntime] = {}
        self.stopped = False
        self.stop_reason: str | None = None
        self._approval_key = approval_key
        self._session_limits: dict[tuple[str, str, str], dict[str, float]] = {}
        self._approval_windows: dict[tuple[str, str, str, str], float] = {}
        self._stop_hooks: list[StopHook] = []
        self._stop_lock = asyncio.Lock()

    # ------------------------------------------------------------------ registration

    def register(self, file: DeviceFile, driver: Driver) -> DeviceRuntime:
        """Add a device and attach its driver to this kernel's grant book."""
        device_id = file.device_id
        if device_id in self.devices:
            raise ValueError(f"A device with id {device_id!r} is already registered.")
        driver.attach(self._verify_grant)
        rules = [
            RuleState(rule, expressions.parse_cached(rule.when, file.channel_names()))
            for rule in file.watchdog.max_duration
        ]
        runtime = DeviceRuntime(file=file, driver=driver, rules=rules)
        self.devices[device_id] = runtime
        self.audit.append(
            "register",
            SYSTEM.label,
            device=device_id,
            hazard=file.effective_hazard,
            writable=file.writable,
            driver=file.connect.driver,
        )
        return runtime

    def unregister(self, device_id: str) -> None:
        self.grants.revoke_all(device_id)
        self.devices.pop(device_id, None)

    def on_stop(self, hook: StopHook) -> None:
        """Run `hook(reason)` during every stop, after the lock is set (the routine engine pauses here)."""
        self._stop_hooks.append(hook)

    def _verify_grant(self, grant: object, device_id: str, target: str, value: object) -> None:
        self.grants.consume(grant, device_id, target, value)

    # ------------------------------------------------------------------ connection state

    async def connect(self, device_id: str) -> None:
        runtime = self._runtime(device_id)
        await asyncio.wait_for(runtime.driver.connect(), DRIVER_TIMEOUT_S)
        runtime.connected = True
        runtime.connected_at = self.clock()
        runtime.faulted = None
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
        """Record a value the hub read from a device (polling, streams, explicit reads)."""
        runtime = self.devices.get(device_id)
        if runtime is not None:
            runtime.reads[reading.channel] = Sample(reading.value, self.clock())

    async def read(self, device_id: str, channel: str, principal: Principal) -> Reading:
        """Read one channel. Every client read request is logged."""
        runtime = self._runtime(device_id)
        file = runtime.file
        if channel not in file.read and channel not in file.write:
            self.audit.append(
                "read",
                principal.label,
                device=device_id,
                target=f"read:{channel}",
                status="blocked",
                code="unknown_target",
            )
            raise LookupError(f"{device_id} has no channel {channel!r}.")
        if runtime.available:
            self.audit.append(
                "read",
                principal.label,
                device=device_id,
                target=f"read:{channel}",
                status="blocked",
                code="device_unavailable",
            )
            raise DriverError(f"{device_id} is {runtime.available}.")
        reading = await asyncio.wait_for(runtime.driver.read(channel), DRIVER_TIMEOUT_S)
        self.note_reading(device_id, reading)
        self.audit.append(
            "read",
            principal.label,
            device=device_id,
            target=f"read:{channel}",
            status="done",
            value=_jsonable(reading.value),
            unit=reading.unit,
        )
        return reading

    # ------------------------------------------------------------------ evaluation

    def evaluate(
        self, command: Command, principal: Principal, *, confirmed: bool = False, shadow: _Shadow | None = None
    ) -> Decision:
        """Decide a command without side effects. Never raises. Fails closed."""
        target = getattr(command, "target", "unknown")
        device = getattr(command, "device", "unknown")
        try:
            return self._evaluate(command, principal, confirmed=confirmed, shadow=shadow)
        except Block as block:
            return Decision(
                status="blocked",
                code=block.code,
                message=block.message,
                device=device,
                target=target,
                limit=block.limit,
            )
        except Exception as exc:  # noqa: BLE001
            return Decision(
                status="blocked",
                code="internal_error",
                device=device,
                target=target,
                message=f"Blocked. The safety kernel hit an unexpected error ({type(exc).__name__}). "
                "Nothing was sent to the device.",
            )

    def _evaluate(self, command: Command, principal: Principal, *, confirmed: bool, shadow: _Shadow | None) -> Decision:
        now = self.clock()
        # 1. Command shape.
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
        # 2. Stop lock.
        if self.stopped:
            raise Block("stopped", "Blocked. The hub is stopped. A human must unlock it before anything can move.")
        # 3. File state.
        if not file.writable:
            raise Block(
                "read_only_file",
                f"Blocked. {command.device} is read-only until a human confirms limits for "
                f"{', '.join(file.unconfirmed())}. Run the limits interview.",
            )
        # 4. Device state.
        if runtime.available:
            raise Block("device_unavailable", f"Blocked. {command.device} is {runtime.available}.")
        # 5. Principal scope.
        hazard = file.effective_hazard
        if principal.kind == "agent" and principal.scope == "read":
            raise Block(
                "not_permitted", "Blocked. This client has a read-only token. Ask the owner for a control token."
            )
        if not principal.covers(hazard):
            raise Block(
                "not_permitted",
                f"Blocked. {command.device} is {hazard} hazard and this client's "
                f"{principal.scope} scope doesn't cover it.",
            )
        # 6 to 9. Units, type, range, step.
        if isinstance(command, Write):
            assert spec is not None
            tightened = self._session_limits.get((principal.label, command.device, command.channel))
            value: Any = normalize(command.channel, spec, command.value, tightened=tightened)
            digest_value: Any = value
            changes = {command.channel: value}
        else:
            assert action_spec is not None
            args = {name: normalize(name, action_spec.args[name], raw) for name, raw in command.args.items()}
            value = args
            digest_value = args
            changes = {effect: _UNKNOWN for effect in action_spec.effects}
        # 10. Rate of change.
        if isinstance(command, Write) and spec is not None and spec.type == "number":
            assert spec.unit is not None
            limits = effective_limits(
                spec, self._session_limits.get((principal.label, command.device, command.channel))
            )
            reference, elapsed = self._rate_reference(runtime, command.channel, spec, now, shadow)
            check_rate(command.channel, spec.unit, limits.rate, float(value), reference, elapsed)
        # 11. Interlocks and action preconditions.
        resolver = self._resolver(runtime, changes, now, shadow)
        if isinstance(command, Action) and action_spec is not None:
            for condition in action_spec.require:
                result = expressions.evaluate(expressions.parse_cached(condition, file.channel_names()), resolver)
                if result is not True:
                    held = "is unknown" if result is None else "doesn't hold"
                    raise Block("interlock", f"Blocked. {command.action} needs {condition}, which {held} right now.")
        self._check_interlocks(command.device, set(changes), resolver)
        # 12. Watchdog budgets.
        for state in runtime.rules:
            if not state.exhausted:
                continue
            mentioned = {ref.name for ref in expressions.references(state.tree) if ref.device is None}
            if mentioned & set(changes) and expressions.evaluate(state.tree, resolver) is not False:
                raise Block(
                    "duration_exceeded",
                    f"Blocked. {state.rule.when} already ran for its "
                    f"{_seconds(state.rule.for_)} limit. Wait for the budget to reset.",
                )
        # 14. Confirmation.
        unit = spec.unit if spec is not None else None
        decision_kwargs: dict[str, Any] = {
            "device": command.device,
            "target": command.target,
            "value": _jsonable(value),
            "unit": unit,
        }
        if spec is not None:
            tier = spec.confirm
        else:
            assert action_spec is not None
            tier = action_spec.confirm
        if hazard == "high":
            tier = "confirm-each-time"
        if self._confirmation_satisfied(command, principal, runtime, tier, digest_value, confirmed, now):
            return Decision(status="allowed", message="Allowed.", **decision_kwargs)
        if principal.kind == "routine":
            raise Block(
                "needs_confirmation",
                f"Blocked. {command.target} on {command.device} needs a human to "
                "confirm, and routines can't wait for one.",
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
        confirmed: bool,
        now: float,
    ) -> bool:
        if principal.kind in ("human", "system") or confirmed:
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
                expected = self.sign(
                    runtime.device_id, approval.routine, approval.sha256, approval.by, approval.at.isoformat()
                )
                if hmac.compare_digest(expected, approval.signature):
                    return True
        return False

    def sign(self, device_id: str, routine: str, sha256: str, by: str, at: str) -> str:
        """HMAC signature for a routine approval. Only the human approval flow calls this."""
        if self._approval_key is None:
            raise PermissionError("This hub has no approval key, so it can't sign approvals.")
        message = approval_message(device_id, routine, sha256, by, at)
        return hmac.new(self._approval_key, message, hashlib.sha256).hexdigest()

    def approve_routine(self, principal: Principal, device_id: str, routine: str, sha256: str) -> Approval:
        """Create a signed approval for a routine on a high hazard device. Humans only."""
        if principal.kind != "human":
            raise PermissionError("Only a human can approve a routine for a high hazard device.")
        import datetime as dt

        at = dt.datetime.now(dt.UTC).replace(microsecond=0)
        signature = self.sign(device_id, routine, sha256, principal.name, at.isoformat())
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
        self, runtime: DeviceRuntime, channel: str, spec: WriteChannel, now: float, shadow: _Shadow | None
    ) -> tuple[float | None, float]:
        if shadow is not None and (runtime.device_id, channel) in shadow.values:
            key = (runtime.device_id, channel)
            return float(shadow.values[key]), shadow.now - shadow.stamps.get(key, shadow.now)
        candidates = [
            sample
            for sample in (runtime.accepted.get(channel), runtime.reads.get(channel))
            if sample is not None and isinstance(sample.value, int | float) and not isinstance(sample.value, bool)
        ]
        if candidates:
            newest = max(candidates, key=lambda sample: sample.at)
            return float(newest.value), now - newest.at
        fallback = _safe_value(runtime.file, channel)
        if fallback is None:
            fallback = spec.min
        return fallback, now - runtime.connected_at

    def _resolver(
        self, runtime: DeviceRuntime, changes: dict[str, Any], now: float, shadow: _Shadow | None
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
            if raw is None or raw is _UNKNOWN:
                return None
            if isinstance(raw, bool | str):
                return expressions.Value(raw)
            if isinstance(raw, int | float):
                return expressions.Value(float(raw), target.file.channel_unit(ref.name))
            return None

        return resolve

    def _check_interlocks(self, device_id: str, changed: set[str], resolver: expressions.Resolver) -> None:
        for runtime in self.devices.values():
            for interlock in runtime.file.interlocks:
                channels = runtime.file.channel_names()
                if_tree = expressions.parse_cached(interlock.if_, channels)
                require_tree = expressions.parse_cached(interlock.require, channels)
                refs = expressions.references(if_tree) | expressions.references(require_tree)
                touches = any(
                    (ref.device is None and runtime.device_id == device_id and ref.name in changed)
                    or (ref.device == device_id and ref.name in changed)
                    for ref in refs
                )
                if not touches:
                    continue
                local = (
                    resolver if runtime.device_id == device_id else self._foreign_resolver(runtime, device_id, resolver)
                )
                applies = expressions.evaluate(if_tree, local)
                satisfied = expressions.evaluate(require_tree, local)
                if applies is not False and satisfied is not True:
                    detail = interlock.message or f"When {interlock.if_}, {interlock.require} must hold."
                    state = "is unknown" if satisfied is None else "doesn't hold"
                    raise Block(
                        "interlock",
                        f"Blocked by an interlock on {runtime.device_id}. {detail} "
                        f"Right now {interlock.require} {state}.",
                    )

    def _foreign_resolver(
        self, owner: DeviceRuntime, changed_device: str, resolver: expressions.Resolver
    ) -> expressions.Resolver:
        """Resolve another device's interlock. Its bare names are its own channels."""

        def resolve(ref: expressions.Ref) -> expressions.Value | None:
            if ref.device is None:
                sample = owner.latest(ref.name, self.clock())
                if sample is None:
                    return None
                raw = sample.value
                if isinstance(raw, bool | str):
                    return expressions.Value(raw)
                if isinstance(raw, int | float):
                    return expressions.Value(float(raw), owner.file.channel_unit(ref.name))
                return None
            if ref.device == changed_device:
                return resolver(expressions.Ref(None, ref.name))
            return resolver(ref)

        return resolve

    # ------------------------------------------------------------------ execution

    async def execute(
        self, command: Command, principal: Principal, *, confirmed: bool = False, request: Request | None = None
    ) -> Decision:
        """Evaluate and, if allowed, run a command. Queues it if it needs a human."""
        runtime = self.devices.get(getattr(command, "device", ""))
        if runtime is None:
            decision = self.evaluate(command, principal)
            self._log(command, principal, decision)
            return decision
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
            decision = self.evaluate(command, principal, confirmed=confirmed)
            if decision.status == "needs_confirmation":
                queued = self.queue.add(command, principal, decision, self.clock())
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
        before = self._before(runtime, command)
        try:
            if isinstance(command, Write):
                value = self._normalized_write(runtime, command, principal)
                grant = self.grants.issue(runtime.device_id, command.target, value)
                reading = await asyncio.wait_for(runtime.driver.write(command.channel, value, grant), DRIVER_TIMEOUT_S)
                runtime.accepted[command.channel] = Sample(value, self.clock(), commanded=True)
                if reading is not None:
                    self.note_reading(runtime.device_id, reading)
                result = decision.model_copy(
                    update={
                        "status": "done",
                        "message": f"Done. {command.channel} is now {_display(value, decision.unit)}.",
                    }
                )
            else:
                spec = runtime.file.actions[command.action]
                args = {name: normalize(name, spec.args[name], raw) for name, raw in command.args.items()}
                grant = self.grants.issue(runtime.device_id, command.target, args)
                await asyncio.wait_for(runtime.driver.action(command.action, args, grant), DRIVER_TIMEOUT_S)
                for effect in spec.effects:
                    runtime.accepted.pop(effect, None)
                result = decision.model_copy(update={"status": "done", "message": f"Done. {command.action} ran."})
        except GrantError as exc:
            result = decision.model_copy(
                update={
                    "status": "blocked",
                    "code": "internal_error",
                    "message": f"Blocked. Grant check failed ({exc}).",
                }
            )
        except (DriverError, OSError, TimeoutError) as exc:
            result = decision.model_copy(
                update={
                    "status": "failed",
                    "code": "driver_error",
                    "message": f"The device didn't complete {command.target}. {exc}",
                }
            )
        self._log(command, principal, result, before=before, request=request)
        return result

    def _normalized_write(self, runtime: DeviceRuntime, command: Write, principal: Principal) -> float | bool | str:
        spec = runtime.file.write[command.channel]
        tightened = self._session_limits.get((principal.label, command.device, command.channel))
        return normalize(command.channel, spec, command.value, tightened=tightened)

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
            details["requested"] = _jsonable(command.value)
        else:
            details["args"] = _jsonable(command.args)
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

    # ------------------------------------------------------------------ dry runs

    def dry_run(self, commands: Iterable[Command], principal: Principal) -> list[Decision]:
        """Evaluate commands in order as if each allowed one had run. Nothing is sent anywhere."""
        shadow = Shadow()
        decisions = []
        for command in commands:
            decision = self.evaluate(command, principal, shadow=shadow)
            decisions.append(decision)
            if decision.status in ("allowed", "needs_confirmation") and isinstance(command, Write):
                shadow.record(command.device, command.channel, decision.value)
        return decisions

    # ------------------------------------------------------------------ confirmations

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
        decision = await self.execute(request.command, request.principal, confirmed=True, request=request)
        request.result = decision
        request.status = (
            "done" if decision.status == "done" else ("failed" if decision.status == "failed" else "blocked")
        )
        if decision.status == "done":
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

    # ------------------------------------------------------------------ session limits

    def tighten(
        self, principal: Principal, device_id: str, channel: str, *, min: Any = None, max: Any = None, rate: Any = None
    ) -> dict[str, float]:
        """Narrow a channel's limits for this principal's session. Widening is refused."""
        runtime = self._runtime(device_id)
        spec = runtime.file.write.get(channel)
        if spec is None or spec.type != "number" or spec.unit is None:
            raise LookupError(f"{device_id} has no numeric write channel {channel!r}.")
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
        except Block as block:
            self.audit.append(
                "tighten",
                principal.label,
                device=device_id,
                target=f"write:{channel}",
                status="blocked",
                code=block.code,
                message=block.message,
            )
            raise
        if updated.get("min", -math.inf) > updated.get("max", math.inf):
            raise Block("cannot_loosen", "Refused. min would be above max.")
        self._session_limits[key] = updated
        self.audit.append(
            "tighten", principal.label, device=device_id, target=f"write:{channel}", status="done", limits=updated
        )
        return updated

    # ------------------------------------------------------------------ stop and unlock

    async def stop_all(self, principal: Principal, reason: str = "stop requested") -> StopReport:
        """Lock writes, cancel pending requests, pause routines, then put every device in its safe state."""
        async with self._stop_lock:
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
                except Exception as exc:  # noqa: BLE001
                    self.audit.append("stop_hook", SYSTEM.label, status="failed", detail=repr(exc))
            report = StopReport(reason=reason, by=principal.label, cancelled_requests=len(cancelled))
            results = await asyncio.gather(
                *(self._stop_device(runtime, reason) for runtime in self.devices.values()),
                return_exceptions=True,
            )
            for runtime, result in zip(self.devices.values(), results, strict=True):
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
        acquired = False
        try:
            await asyncio.wait_for(runtime.lock.acquire(), 2.0)
            acquired = True
        except TimeoutError:
            pass
        try:
            return await self._apply_safe_state(runtime, reason=reason)
        finally:
            if acquired:
                runtime.lock.release()

    async def _apply_safe_state(
        self, runtime: DeviceRuntime, *, reason: str, allow_disconnected: bool = False
    ) -> DeviceStopResult:
        file = runtime.file
        if not (file.write or file.actions):
            return DeviceStopResult(runtime.device_id, "safe", "read-only device")
        if not file.safe_state and runtime.driver.info.safe_state_support != "native":
            return DeviceStopResult(runtime.device_id, "no_safe_state", file.safe_state_note or "no safe state defined")
        if not runtime.connected and not allow_disconnected:
            return DeviceStopResult(runtime.device_id, "failed", "not connected")
        runtime.applying_safe_state = True
        try:

            async def apply() -> None:
                grant = self.grants.issue(runtime.device_id, "safe_state", None)
                await runtime.driver.safe_state(grant)
                for step in file.safe_state:
                    if step.action is not None:
                        spec = file.actions[step.action]
                        args = {
                            name: normalize(name, spec.args[name], _quantity_text(raw, spec.args[name].unit))
                            for name, raw in step.args.items()
                        }
                        action_grant = self.grants.issue(runtime.device_id, f"action:{step.action}", args)
                        await runtime.driver.action(step.action, args, action_grant)
                    for channel, raw in step.values.items():
                        value = _safe_value_for(file, channel, raw)
                        write_grant = self.grants.issue(runtime.device_id, f"write:{channel}", value)
                        await runtime.driver.write(channel, value, write_grant)
                        runtime.accepted[channel] = Sample(value, self.clock(), commanded=True)

            await asyncio.wait_for(apply(), STOP_DEVICE_TIMEOUT_S)
            return DeviceStopResult(runtime.device_id, "safe", reason)
        except Exception as exc:  # noqa: BLE001
            return DeviceStopResult(runtime.device_id, "failed", f"{type(exc).__name__}: {exc}")
        finally:
            runtime.applying_safe_state = False

    def unlock(self, principal: Principal, phrase: str) -> None:
        """A human lifts the stop lock by typing the unlock phrase."""
        if principal.kind != "human":
            self.audit.append("unlock", principal.label, status="blocked", code="not_permitted")
            raise PermissionError("Only a human can unlock after a stop.")
        if phrase.strip().lower() != UNLOCK_PHRASE:
            self.audit.append("unlock", principal.label, status="blocked", code="bad_request")
            raise ValueError(f"Type {UNLOCK_PHRASE} to confirm.")
        self.stopped = False
        self.stop_reason = None
        self.audit.append("unlock", principal.label, status="done")

    # ------------------------------------------------------------------ watchdog

    async def tick(self) -> list[str]:
        """Advance max-duration budgets and apply rules whose budget ran out. Returns what fired."""
        fired: list[str] = []
        now = self.clock()
        for runtime in list(self.devices.values()):
            resolver = self._resolver(runtime, {}, now, None)
            for state in runtime.rules:
                active = expressions.evaluate(state.tree, resolver)
                if active is True:
                    state.false_since = None
                    if state.active_since is None:
                        state.active_since = now
                    if not state.exhausted and now - state.active_since >= state.rule.for_:
                        state.exhausted = True
                        fired.append(f"{runtime.device_id}: {state.rule.when}")
                        await self._apply_rule(runtime, state)
                elif active is False:
                    state.active_since = None
                    if state.false_since is None:
                        state.false_since = now
                    reset_after = state.rule.reset_after if state.rule.reset_after is not None else state.rule.for_
                    if state.exhausted and now - state.false_since >= reset_after:
                        state.exhausted = False
                        self.audit.append(
                            "watchdog_reset", SYSTEM.label, device=runtime.device_id, rule=state.rule.when
                        )
        return fired

    async def _apply_rule(self, runtime: DeviceRuntime, state: RuleState) -> None:
        self.audit.append(
            "watchdog",
            SYSTEM.label,
            device=runtime.device_id,
            status="done",
            rule=state.rule.when,
            then=state.rule.then if isinstance(state.rule.then, str) else _jsonable(state.rule.then),
        )
        if state.rule.then == "safe_state":
            async with runtime.lock:
                result = await self._apply_safe_state(runtime, reason=f"watchdog: {state.rule.when}")
            self.audit.append(
                "safe_state", SYSTEM.label, device=runtime.device_id, status=result.status, detail=result.detail
            )
            return
        assert isinstance(state.rule.then, dict)
        async with runtime.lock:
            for channel, raw in state.rule.then.items():
                value = _safe_value_for(runtime.file, channel, raw)
                grant = self.grants.issue(runtime.device_id, f"write:{channel}", value)
                try:
                    await asyncio.wait_for(runtime.driver.write(channel, value, grant), DRIVER_TIMEOUT_S)
                    runtime.accepted[channel] = Sample(value, self.clock(), commanded=True)
                except Exception as exc:  # noqa: BLE001
                    self.audit.append(
                        "watchdog", SYSTEM.label, device=runtime.device_id, status="failed", detail=repr(exc)
                    )

    # ------------------------------------------------------------------ expressions for routines

    def evaluate_expression(self, text: str) -> bool | None:
        """Evaluate an expression against current state. References must name their device."""
        tree = expressions.parse(text, frozenset())
        now = self.clock()

        def resolve(ref: expressions.Ref) -> expressions.Value | None:
            if ref.device is None:
                return None
            target = self.devices.get(ref.device)
            if target is None:
                return None
            sample = target.latest(ref.name, now)
            if sample is None:
                return None
            raw = sample.value
            if isinstance(raw, bool | str):
                return expressions.Value(raw)
            if isinstance(raw, int | float):
                return expressions.Value(float(raw), target.file.channel_unit(ref.name))
            return None

        return expressions.evaluate(tree, resolve)

    # ------------------------------------------------------------------ helpers

    def _runtime(self, device_id: str) -> DeviceRuntime:
        runtime = self.devices.get(device_id)
        if runtime is None:
            raise LookupError(f"There is no device {device_id!r}.")
        return runtime

    def pending(self) -> list[Request]:
        return self.queue.pending(self.clock())


class _Unknown:
    def __repr__(self) -> str:
        return "unknown"


_UNKNOWN: Final = _Unknown()


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
