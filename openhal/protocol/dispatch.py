"""The one dispatcher. It answers JSON-RPC messages for one hub, whatever transport carried them.

A transport opens a `Session` per connection (openhal/protocol/session.py), passes every received
text to `Session.receive`, and sends whatever `Session.next` yields. `Dispatcher.handle` answers one
parsed message and is what both front ends use. The `/rpc` WebSocket calls it directly, and
`openhal rpc` bridges stdio to that WebSocket.

Lifecycle (ADR 0015). Every method but `hal/initialize` answers NOT_INITIALIZED until initialize
succeeds. Notifications flow only after the client sends `hal/initialized`, and stop after
`hal/shutdown`. Batches are not supported in this version and get INVALID_REQUEST.

Every message in and out is kept in the dispatcher's `MessageLog` with tokens redacted.
"""

from __future__ import annotations

import json
import logging
import weakref
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any, Final

from pydantic import ValidationError

from openhal import __version__
from openhal._brand import PACKAGE_NAME
from openhal.drivers.base import DriverError
from openhal.hub import views
from openhal.kernel.commands import Action, Decision, Write
from openhal.kernel.kernel import Shadow
from openhal.kernel.principals import Principal
from openhal.protocol import convert
from openhal.protocol import messages as m
from openhal.protocol.errors import RpcError, from_kernel
from openhal.protocol.log import MessageLog
from openhal.protocol.notify import Notifier
from openhal.protocol.session import Session
from openhal.protocol.version import is_version, negotiate
from openhal.spec.units import UnitError, parse_quantity
from openhal.spec.units import convert as convert_units

if TYPE_CHECKING:
    from openhal.hub.hub import Hub

log = logging.getLogger("openhal.protocol")

MAX_WAIT_S: Final = 3600.0
UNLOCK_PROBLEM: Final = "phrase must be unlock"

Handler = Callable[["Session", Any], Awaitable[m.Message]]


def _problems(exc: ValidationError) -> list[str]:
    found = []
    for item in exc.errors(include_url=False):
        where = ".".join(str(part) for part in item.get("loc", ())) or "params"
        found.append(f"{where} {str(item.get('msg', 'is invalid')).lower()}")
    return found


def success(request_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def failure(request_id: Any, error: RpcError) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": error.to_object()}


_DISPATCHERS: weakref.WeakKeyDictionary[Hub, Dispatcher] = weakref.WeakKeyDictionary()


class Dispatcher:
    """Answers protocol messages for one hub and fans the hub's events out as notifications."""

    def __init__(self, hub: Hub, *, level: m.Conformance = "full", message_log: MessageLog | None = None) -> None:
        self.hub = hub
        self.level: m.Conformance = level
        self.log = message_log or MessageLog()
        self.sessions: set[Session] = set()
        self._methods = set(m.methods_for(level))
        self._handlers: dict[str, Handler] = {
            "hal/devices/list": self._devices_list,
            "hal/devices/describe": self._devices_describe,
            "hal/read": self._read,
            "hal/readMany": self._read_many,
            "hal/write": self._write,
            "hal/dryRun": self._dry_run,
            "hal/planCheck": self._plan_check,
            "hal/stop": self._stop_all,
            "hal/action": self._action,
            "hal/confirmations/list": self._confirmations_list,
            "hal/confirmations/approve": self._approve,
            "hal/confirmations/reject": self._reject,
            "hal/unlock": self._unlock,
            "hal/routines/list": self._routines_list,
            "hal/routines/dryRun": self._routines_dry_run,
            "hal/audit/query": self._audit_query,
        }
        self.notifier = Notifier(self)

    @classmethod
    def for_hub(cls, hub: Hub) -> Dispatcher:
        """The hub's dispatcher, created on first use, so every transport shares one log and one fan-out."""
        found = _DISPATCHERS.get(hub)
        if found is None:
            found = cls(hub)
            _DISPATCHERS[hub] = found
        return found

    def open(
        self,
        *,
        principal: Principal | None = None,
        token_rejected: bool = False,
        fallback: Principal | None = None,
    ) -> Session:
        """A new session. `principal` comes from an Authorization header, `fallback` from a session cookie."""
        session = Session(self, principal=principal, token_rejected=token_rejected, fallback=fallback)
        self.sessions.add(session)
        return session

    def parse(self, session: Session, text: str | bytes) -> Any:
        """Decode one frame. Invalid JSON is answered with PARSE_ERROR here and returns None."""
        try:
            message = json.loads(text)
        except (ValueError, UnicodeDecodeError):
            raw = text.decode("utf-8", "replace") if isinstance(text, bytes) else text
            self.log.record("in", session.client, session.label, raw)
            session.send(failure(None, RpcError("PARSE_ERROR")))
            return None
        self.log.record("in", session.client, session.label, message)
        return message

    async def handle(self, session: Session, message: Any) -> dict[str, Any] | None:
        """Answer one parsed JSON-RPC message. Returns the response, or None for a notification."""
        if isinstance(message, list):
            return failure(None, RpcError("INVALID_REQUEST", message="Batches are not supported in this version"))
        if not isinstance(message, dict):
            return failure(None, RpcError("INVALID_REQUEST"))
        has_id = "id" in message
        request_id = message.get("id")
        if has_id and (isinstance(request_id, bool) or not isinstance(request_id, str | int)):
            return failure(None, RpcError("INVALID_REQUEST", message="The id must be a string or an integer"))
        method = message.get("method")
        if message.get("jsonrpc") != "2.0" or not isinstance(method, str):
            return failure(request_id, RpcError("INVALID_REQUEST"))
        params = message.get("params")
        if not has_id:
            self._client_notification(session, method)
            return None
        if params is None:
            params = {}
        if not isinstance(params, dict):
            return failure(request_id, RpcError("INVALID_PARAMS", {"problems": ["params must be an object"]}))
        try:
            result = await self._call(session, method, params)
        except RpcError as error:
            return failure(request_id, error)
        except ValidationError as exc:
            return failure(request_id, RpcError("INVALID_PARAMS", {"problems": _problems(exc)}))
        except Exception:
            log.exception("protocol method %s failed", method)
            return failure(request_id, from_kernel("internal_error"))
        return success(request_id, result)

    def _client_notification(self, session: Session, method: str) -> None:
        if method == "hal/initialized" and session.state == "initialized":
            session.state = "ready"
        elif method == "hal/shutdown":
            session.close()

    async def _call(self, session: Session, method: str, params: dict[str, Any]) -> dict[str, Any]:
        if method == "hal/initialize":
            return self._initialize(session, m.InitializeParams.model_validate(params)).wire()
        if session.principal is None:
            raise RpcError("NOT_INITIALIZED")
        spec = m.METHODS.get(method)
        if spec is None or method not in self._methods:
            raise RpcError("METHOD_NOT_FOUND", {"method": method})
        if spec.human_only and session.principal.kind != "human":
            raise from_kernel("not_permitted", {"kernelMessage": f"Only a person can call {method}."})
        parsed = spec.params.model_validate(params)
        result = await self._handlers[method](session, parsed)
        return result.wire()

    def _who(self, session: Session) -> Principal:
        assert session.principal is not None
        return session.principal

    def _initialize(self, session: Session, params: m.InitializeParams) -> m.InitializeResult:
        if session.principal is not None:
            raise RpcError("INVALID_REQUEST", message="hal/initialize already ran on this connection")
        if not is_version(params.protocol_version):
            raise RpcError("INVALID_PARAMS", {"problems": ["protocolVersion must be a date such as 2026-10-24"]})
        principal = session.header_principal
        if principal is None and not session.token_rejected:
            principal = self.hub.tokens.principal(params.token) if params.token else session.fallback
        if principal is None:
            raise RpcError("UNAUTHORIZED")
        session.principal = principal
        session.client = params.client_info.name
        session.client_version = params.client_info.version
        session.protocol_version = negotiate(params.protocol_version)
        session.state = "initialized"
        return m.InitializeResult(
            protocol_version=session.protocol_version,
            hub_info=m.Info(name=PACKAGE_NAME, version=__version__),
            conformance=self.level,
            principal=m.PrincipalInfo(kind=principal.kind, name=principal.name, scope=principal.scope),
            capabilities=m.Capabilities(notifications=m.notifications_for(self.level)),
        )

    def _device(self, device: str) -> None:
        if device not in self.hub.kernel.devices:
            raise from_kernel("unknown_target", {"device": device})

    async def _devices_list(self, session: Session, params: m.Empty) -> m.DevicesListResult:
        return m.DevicesListResult(devices=[convert.summary(self.hub, item) for item in self.hub.kernel.devices])

    async def _devices_describe(self, session: Session, params: m.DescribeParams) -> m.DescribeResult:
        self._device(params.device)
        return m.DescribeResult(device=convert.description(self.hub, params.device))

    async def _read(self, session: Session, params: m.ReadParams) -> m.Reading:
        self._device(params.device)
        kernel = self.hub.kernel
        try:
            reading = await kernel.read(params.device, params.channel, self._who(session))
        except LookupError:
            raise from_kernel("unknown_target", {"device": params.device, "channel": params.channel}) from None
        except (DriverError, TimeoutError, OSError) as exc:
            unavailable = kernel.devices[params.device].available
            text = views.device_text(f"{params.device}.{params.channel} driver error", str(exc)) or "timed out"
            raise convert.kernel_error(
                self.hub,
                "device_unavailable" if unavailable else "driver_error",
                device=params.device,
                target=f"read:{params.channel}",
                kernel_message=text,
            ) from None
        return convert.reading(self.hub, params.device, reading)

    async def _read_many(self, session: Session, params: m.ReadManyParams) -> m.ReadManyResult:
        readings: list[m.Reading | m.ReadFailure] = []
        for item in params.items:
            try:
                readings.append(await self._read(session, item))
            except RpcError as error:
                failed = m.ErrorObject.model_validate(error.to_object())
                readings.append(m.ReadFailure(device=item.device, channel=item.channel, error=failed))
        return m.ReadManyResult(readings=readings)

    def _expires_in(self, request_id: str | None) -> float:
        request = self.hub.kernel.queue.get(request_id or "")
        if request is None:
            return 0.0
        return round(max(0.0, request.expires_at - self.hub.kernel.clock()), 1)

    async def _write(self, session: Session, params: m.WriteParams) -> m.WriteDone | m.Pending:
        command = Write(device=params.device, channel=params.channel, value=params.value, unit=params.unit)
        decision = await self.hub.kernel.execute(command, self._who(session), wire=True)
        if decision.status == "done":
            return m.WriteDone(device=decision.device, channel=params.channel, value=decision.value, unit=decision.unit)
        if decision.status == "pending" and decision.request_id:
            return m.Pending(request_id=decision.request_id, expires_in_s=self._expires_in(decision.request_id))
        raise convert.decision_error(self.hub, decision, command, self._who(session).label)

    async def _action(self, session: Session, params: m.ActionParams) -> m.ActionDone | m.Pending:
        command = Action(device=params.device, action=params.action, args=convert.kernel_args(params.args))
        decision = await self.hub.kernel.execute(command, self._who(session), wire=True)
        if decision.status == "done":
            args = convert.action_args(self.hub, decision.device, params.action, decision.value)
            return m.ActionDone(result=m.ActionOutcome(device=decision.device, action=params.action, args=args))
        if decision.status == "pending" and decision.request_id:
            return m.Pending(request_id=decision.request_id, expires_in_s=self._expires_in(decision.request_id))
        raise convert.decision_error(self.hub, decision, command, self._who(session).label)

    async def _dry_run(self, session: Session, params: m.DryRunParams) -> m.DryRunResult:
        commands = [convert.kernel_command(item) for item in params.commands]
        who = self._who(session)
        decisions = self.hub.kernel.dry_run(commands, who, wire=True)
        return m.DryRunResult(
            decisions=[
                convert.decision(self.hub, decision, command, principal=who.label)
                for decision, command in zip(decisions, commands, strict=True)
            ]
        )

    async def _plan_check(self, session: Session, params: m.PlanCheckParams) -> m.PlanResult:
        """Evaluate a plan in order. Waits advance simulated time, so rate limits are judged as in a real run.

        A plan can't hold a pending request, so a step that needs a person carries CONFIRMATION_REQUIRED.
        """
        shadow = Shadow()
        decisions: list[m.Decision] = []
        problems: list[str] = []
        who = self._who(session)
        for index, step in enumerate(params.steps):
            path = f"steps[{index}]"
            if isinstance(step, m.Wait):
                try:
                    seconds = convert_units(parse_quantity(step.duration.model_dump()), "s")
                except UnitError as exc:
                    problems.append(f"{path} wait {exc}")
                    continue
                if seconds > MAX_WAIT_S:
                    problems.append(f"{path} wait may be at most 1 h")
                    continue
                shadow.now += seconds
                continue
            command = convert.kernel_command(step)
            decision = self.hub.kernel.evaluate(command, who, shadow=shadow, wire=True)
            decisions.append(convert.decision(self.hub, decision, command, principal=who.label, cannot_wait=True))
            if decision.status in ("allowed", "needs_confirmation"):
                if isinstance(command, Write):
                    shadow.record(command.device, command.channel, decision.value)
                else:
                    shadow.record_run(command.device, command.action)
        ok = not problems and all(item.status == "allowed" for item in decisions)
        return m.PlanResult(ok=ok, decisions=decisions, problems=problems)

    async def _stop_all(self, session: Session, params: m.StopParams) -> m.StopResult:
        report = await self.hub.kernel.stop_all(self._who(session), params.reason or "stop requested")
        return m.StopResult(
            devices=[
                m.StopDevice(device=item.device, status=item.status, detail=item.detail) for item in report.devices
            ]
        )

    async def _unlock(self, session: Session, params: m.UnlockParams) -> m.UnlockResult:
        try:
            self.hub.kernel.unlock(self._who(session), params.phrase)
        except PermissionError as exc:
            raise from_kernel("not_permitted", {"kernelMessage": str(exc)}) from None
        except ValueError as exc:
            if params.phrase.strip().lower() != "unlock":
                raise from_kernel(
                    "bad_request", {"kernelMessage": str(exc), "problems": ["phrase must be unlock"]}
                ) from None
            raise from_kernel("busy", {"kernelMessage": str(exc)}) from None
        return m.UnlockResult(ok=True)

    def _visible(self, session: Session, requester: Principal) -> bool:
        who = self._who(session)
        return who.kind == "human" or requester.label == who.label

    async def _confirmations_list(
        self, session: Session, params: m.ConfirmationsListParams
    ) -> m.ConfirmationsListResult:
        kernel = self.hub.kernel
        kernel.queue.expire(kernel.clock())
        wanted = params.status or "pending"
        requests = [
            item
            for item in kernel.queue.recent(100)
            if item.status == wanted and self._visible(session, item.principal)
        ]
        return m.ConfirmationsListResult(requests=[convert.request(self.hub, item) for item in requests])

    def _closed(self, request_id: str, exc: Exception) -> RpcError:
        """REQUEST_CLOSED for a request that is unknown or no longer pending."""
        request = self.hub.kernel.queue.get(request_id)
        code = "rejected" if request is not None and request.status == "rejected" else "expired"
        return from_kernel(code, {"requestId": request_id, "kernelMessage": str(exc)})

    async def _approve(self, session: Session, params: m.ApproveParams) -> m.Decision:
        request = self.hub.kernel.queue.get(params.request_id)
        try:
            decision = await self.hub.kernel.confirm(params.request_id, self._who(session))
        except PermissionError as exc:
            raise from_kernel("not_permitted", {"kernelMessage": str(exc)}) from None
        except LookupError as exc:
            raise self._closed(params.request_id, exc) from None
        command = request.command if request is not None else None
        requester = request.principal.label if request is not None else None
        return convert.decision(self.hub, decision, command, principal=requester)

    async def _reject(self, session: Session, params: m.RejectParams) -> m.ConfirmationRequest:
        try:
            request = self.hub.kernel.reject(params.request_id, self._who(session), params.reason or "")
        except PermissionError as exc:
            raise from_kernel("not_permitted", {"kernelMessage": str(exc)}) from None
        except LookupError as exc:
            raise self._closed(params.request_id, exc) from None
        return convert.request(self.hub, request)

    async def _routines_list(self, session: Session, params: m.Empty) -> m.RoutinesListResult:
        routines = self.hub.routines
        return m.RoutinesListResult(
            routines=[convert.routine_summary(routines.summary(item)) for item in routines.records.values()]
        )

    async def _routines_dry_run(self, session: Session, params: m.RoutineDryRunParams) -> m.PlanResult:
        try:
            self.hub.routines.get(params.routine_id)
        except KeyError:
            raise from_kernel("unknown_target", {"routine": params.routine_id}) from None
        result = self.hub.routines.dry_run(params.routine_id)
        decisions = []
        for item in result["decisions"]:
            kernel = Decision.model_validate({key: value for key, value in item.items() if key != "step"})
            decisions.append(convert.decision(self.hub, kernel, cannot_wait=True))
        return m.PlanResult(ok=result["ok"], decisions=decisions, problems=list(result["problems"]))

    async def _audit_query(self, session: Session, params: m.AuditQueryParams) -> m.AuditQueryResult:
        entries = self.hub.audit.entries(
            device=params.device,
            status=params.status,
            event=params.event,
            since_seq=params.since,
            limit=params.limit,
        )
        return m.AuditQueryResult(entries=[convert.audit_entry(entry) for entry in entries])
