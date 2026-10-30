"""Hub events as protocol notifications, fanned out to every ready session.

Readings come from the hub's live event stream (`Hub.subscribe`, the same stream `/v1/live`
serves). Blocks, confirmation requests, stops and device changes come from the audit log the hub's
stream is built from, because only the full entry carries the requested value. So every client receives
the same notifications whether the command came over the protocol, REST, MCP or a routine.

hal/stopped is sent once every device registered at the time of the stop has reported its result.
hal/confirmationRequested reaches people and the principal that sent the request, never other agents.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from openhal.protocol import convert
from openhal.protocol import messages as m

if TYPE_CHECKING:
    from openhal.audit.log import Entry
    from openhal.protocol.dispatch import Dispatcher
    from openhal.protocol.session import Session

Visible = Callable[["Session"], bool]


def notification(method: str, params: m.Message) -> dict[str, Any]:
    """A JSON-RPC notification from the hub."""
    return {"jsonrpc": "2.0", "method": method, "params": params.wire()}


@dataclass
class _StopWatch:
    reason: str
    by: str
    expected: set[str]
    seen: dict[str, str] = field(default_factory=dict)


class Notifier:
    """Subscribes once to a hub and turns its events into notifications."""

    def __init__(self, dispatcher: Dispatcher) -> None:
        self.dispatcher = dispatcher
        self.hub = dispatcher.hub
        self._allowed = set(m.notifications_for(dispatcher.level))
        self._stop: _StopWatch | None = None
        self.hub.subscribe(self._on_event)
        self.hub.audit.subscribe(self._on_audit)

    def broadcast(self, method: str, params: m.Message, visible: Visible | None = None) -> None:
        """Send one notification to every ready session that may see it."""
        if method not in self._allowed:
            return
        message = notification(method, params)
        for session in list(self.dispatcher.sessions):
            if session.state != "ready" or (visible is not None and not visible(session)):
                continue
            session.notify_threadsafe(message)

    def _on_event(self, event: dict[str, Any]) -> None:
        if event.get("type") != "reading" or not self.dispatcher.sessions:
            return
        self.broadcast(
            "hal/value",
            m.Reading(
                device=event["device"],
                channel=event["channel"],
                value=event.get("value"),
                unit=event.get("unit"),
                at=convert.timestamp(float(event.get("at") or 0.0)),
                suspect=bool(event.get("suspect")),
            ),
        )

    def _on_audit(self, entry: Entry) -> None:
        if not self.dispatcher.sessions and entry.event != "stop" and self._stop is None:
            return
        with contextlib.suppress(Exception):
            self._handle(entry)

    def _handle(self, entry: Entry) -> None:
        details: dict[str, Any] = entry.body.get("details", {})
        if entry.event in ("write", "action") and entry.status == "blocked" and entry.device:
            self._blocked(entry, details)
        elif entry.event in ("write", "action") and entry.status == "pending":
            self._requested(str(details.get("request_id", "")))
        elif entry.event == "stop":
            self._stop = _StopWatch(
                reason=str(details.get("reason") or "stop requested"),
                by=entry.principal,
                expected=set(self.hub.kernel.devices),
            )
            self._finish_stop()
        elif entry.event == "safe_state" and self._stop is not None and entry.device in self._stop.expected:
            if not str(details.get("detail") or "").startswith("reapplied"):
                self._stop.seen[entry.device] = entry.status or "failed"
                self._finish_stop()
        elif entry.event == "register" and entry.device in self.hub.kernel.devices:
            self.broadcast("hal/deviceAdded", m.DeviceAddedParams(device=convert.summary(self.hub, entry.device)))
        elif entry.event == "unregister" and entry.device:
            self.broadcast("hal/deviceRemoved", m.DeviceRemovedParams(device=entry.device))

    def _blocked(self, entry: Entry, details: dict[str, Any]) -> None:
        error = convert.kernel_error(
            self.hub,
            entry.code,
            device=entry.device,
            target=entry.target,
            kernel_message=details.get("message"),
            raw_value=convert.body_value(
                {"kind": entry.event, "value": details.get("requested"), "args": details.get("args")},
                details.get("limit"),
            ),
            limit=details.get("limit"),
            request_id=details.get("request_id"),
            principal=entry.principal,
        )
        params = m.BlockedParams(
            device=entry.device or "",
            target=entry.target or "",
            error=m.ErrorObject.model_validate(error.to_object()),
        )
        self.broadcast("hal/blocked", params)

    def _requested(self, request_id: str) -> None:
        request = self.hub.kernel.queue.get(request_id)
        if request is None:
            return
        requester = request.principal.label

        def visible(session: Session) -> bool:
            who = session.principal
            return who is not None and (who.kind == "human" or who.label == requester)

        params = m.ConfirmationRequestedParams(request=convert.request(self.hub, request))
        self.broadcast("hal/confirmationRequested", params, visible)

    def _finish_stop(self) -> None:
        watch = self._stop
        if watch is None or not watch.expected <= set(watch.seen):
            return
        self._stop = None
        devices = [m.StoppedDevice(device=device, status=watch.seen[device]) for device in sorted(watch.expected)]
        self.broadcast("hal/stopped", m.StoppedParams(reason=watch.reason, by=watch.by, devices=devices))
