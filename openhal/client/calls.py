"""Every API route as a `Call`, shared by the sync and async clients.

A `Call` is the method, path, body and the parser for the answer. The clients only send calls
and map errors, so both stay in step with one list of routes.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

from pydantic import TypeAdapter

from openhal.client import models as m
from openhal.kernel.commands import Action, Write

Value = str | bool | int | float | dict[str, Any]
Command = Write | Action | Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class Call[T]:
    method: str
    path: str
    parse: Callable[[Any], T]
    json: Any = None
    params: dict[str, Any] | None = None


_ADAPTERS: dict[Any, TypeAdapter[Any]] = {}


def _adapter(kind: Any) -> TypeAdapter[Any]:
    adapter = _ADAPTERS.get(kind)
    if adapter is None:
        adapter = _ADAPTERS[kind] = TypeAdapter(kind)
    return adapter


def _as[T](kind: type[T]) -> Callable[[Any], T]:
    def parse(data: Any) -> T:
        result: T = _adapter(kind).validate_python(data)
        return result

    return parse


def _list_of[T](kind: type[T]) -> Callable[[Any], list[T]]:
    def parse(data: Any) -> list[T]:
        result: list[T] = _adapter(list[kind]).validate_python(data)  # type: ignore[valid-type]
        return result

    return parse


def _seg(value: str) -> str:
    """Quote one path segment so an id can never change the route."""
    return quote(value, safe="")


def split_target(target: str) -> tuple[str, str]:
    """Split `device.channel` or `device.action`. Device ids can't contain dots, names can't either."""
    device, dot, name = target.partition(".")
    if not dot or not device or not name:
        raise ValueError(f"Expected device.channel, for example desk-fan.fan_speed. Got {target!r}.")
    return device, name


def flat(value: Value, unit: str | None = None) -> dict[str, Any]:
    """A channel value as REST carries it, the number and its unit apart (ADR 0016).

    A Quantity mapping such as `{"value": 60, "unit": "%"}` is split into the two fields.
    """
    if isinstance(value, Mapping) and "value" in value:
        return {"value": value["value"], "unit": value.get("unit")}
    body: dict[str, Any] = {"value": value}
    if unit is not None:
        body["unit"] = unit
    return body


def command_body(command: Command) -> dict[str, Any]:
    if isinstance(command, Write | Action):
        return command.model_dump(exclude_none=True)
    body = dict(command)
    if "kind" not in body:
        body["kind"] = "action" if "action" in body else "write"
    if body["kind"] == "write" and "value" in body:
        body.update(flat(body["value"], body.get("unit")))
    return body


def status() -> Call[m.HubStatus]:
    return Call("GET", "/v1/status", _as(m.HubStatus))


def whoami() -> Call[m.Principal]:
    return Call("GET", "/v1/whoami", _as(m.Principal))


def devices() -> Call[list[m.DeviceSummary]]:
    return Call("GET", "/v1/devices", _list_of(m.DeviceSummary))


def device(device_id: str) -> Call[m.DeviceView]:
    return Call("GET", f"/v1/devices/{_seg(device_id)}", _as(m.DeviceView))


def read(device_id: str, channel: str) -> Call[m.Reading]:
    return Call("POST", "/v1/read", _as(m.Reading), {"device": device_id, "channel": channel})


def read_many(items: Iterable[tuple[str, str]]) -> Call[list[m.Reading]]:
    body = {"items": [{"device": device_id, "channel": channel} for device_id, channel in items]}
    return Call("POST", "/v1/read_many", _list_of(m.Reading), body)


def write(device_id: str, channel: str, value: Value, unit: str | None = None) -> Call[m.Decision]:
    body = {"kind": "write", "device": device_id, "channel": channel, **flat(value, unit)}
    return Call("POST", "/v1/write", _as(m.Decision), body)


def action(device_id: str, name: str, args: Mapping[str, Any] | None = None) -> Call[m.Decision]:
    body = {"kind": "action", "device": device_id, "action": name, "args": dict(args or {})}
    return Call("POST", "/v1/action", _as(m.Decision), body)


def dry_run(commands: Iterable[Command]) -> Call[list[m.Decision]]:
    body = {"commands": [command_body(command) for command in commands]}
    return Call("POST", "/v1/dry_run", _list_of(m.Decision), body)


def tighten(
    device_id: str,
    channel: str,
    *,
    min: Mapping[str, Any] | None = None,
    max: Mapping[str, Any] | None = None,
    rate: Mapping[str, Any] | None = None,
) -> Call[m.TightenResult]:
    """Session limits as Quantity mappings, for example `max={"value": 50, "unit": "%"}`."""
    body: dict[str, Any] = {"device": device_id, "channel": channel}
    for key, value in (("min", min), ("max", max), ("rate", rate)):
        if value is not None:
            body[key] = dict(value)
    return Call("POST", "/v1/tighten", _as(m.TightenResult), body)


def stop(reason: str = "stop requested") -> Call[m.StopReport]:
    return Call("POST", "/v1/stop", _as(m.StopReport), {"reason": reason[:200]})


def unlock(phrase: str) -> Call[m.UnlockResult]:
    return Call("POST", "/v1/unlock", _as(m.UnlockResult), {"phrase": phrase})


def confirmations(include_done: bool = False) -> Call[list[m.ConfirmationRequest]]:
    params = {"include_done": "true"} if include_done else None
    return Call("GET", "/v1/confirmations", _list_of(m.ConfirmationRequest), params=params)


def confirmation(request_id: str) -> Call[m.ConfirmationRequest]:
    return Call("GET", f"/v1/confirmations/{_seg(request_id)}", _as(m.ConfirmationRequest))


def approve(request_id: str) -> Call[m.Decision]:
    return Call("POST", f"/v1/confirmations/{_seg(request_id)}/approve", _as(m.Decision))


def reject(request_id: str, reason: str = "") -> Call[m.ConfirmationRequest]:
    path = f"/v1/confirmations/{_seg(request_id)}/reject"
    return Call("POST", path, _as(m.ConfirmationRequest), {"reason": reason[:200]})


def audit(
    *,
    device: str | None = None,
    status: str | None = None,
    event: str | None = None,
    since: int = 0,
    limit: int = 200,
) -> Call[list[m.AuditEntry]]:
    params: dict[str, Any] = {"since": since, "limit": limit}
    for key, value in (("device", device), ("status", status), ("event", event)):
        if value is not None:
            params[key] = value
    return Call("GET", "/v1/audit", _list_of(m.AuditEntry), params=params)


def verify_audit() -> Call[m.AuditVerify]:
    return Call("GET", "/v1/audit/verify", _as(m.AuditVerify))


def drivers() -> Call[list[m.DriverInfo]]:
    return Call("GET", "/v1/drivers", _list_of(m.DriverInfo))


def pair(code: str) -> Call[m.OkResult]:
    return Call("POST", "/v1/pair", _as(m.OkResult), {"code": code.strip()})


def discover(drivers: Iterable[str] | None = None) -> Call[m.DiscoveryResult]:
    body = {"drivers": list(drivers)} if drivers is not None else {}
    return Call("POST", "/v1/discover", _as(m.DiscoveryResult), body)


def unknown_devices() -> Call[list[m.Unknown]]:
    return Call("GET", "/v1/discover/unknown", _list_of(m.Unknown))


def routines() -> Call[list[m.RoutineSummary]]:
    return Call("GET", "/v1/routines", _list_of(m.RoutineSummary))


def routine(routine_id: str) -> Call[m.Routine]:
    return Call("GET", f"/v1/routines/{_seg(routine_id)}", _as(m.Routine))


def create_routine(routine_id: str, source: str, kind: str = "yaml") -> Call[m.Routine]:
    body = {"id": routine_id, "kind": kind, "source": source}
    return Call("POST", "/v1/routines", _as(m.Routine), body)


def routine_dry_run(routine_id: str) -> Call[m.RoutineDryRun]:
    return Call("POST", f"/v1/routines/{_seg(routine_id)}/dry_run", _as(m.RoutineDryRun))


def enable_routine(routine_id: str) -> Call[m.Routine]:
    return Call("POST", f"/v1/routines/{_seg(routine_id)}/enable", _as(m.Routine))


def disable_routine(routine_id: str) -> Call[m.Routine]:
    return Call("POST", f"/v1/routines/{_seg(routine_id)}/disable", _as(m.Routine))


def run_routine(routine_id: str) -> Call[m.Run]:
    return Call("POST", f"/v1/routines/{_seg(routine_id)}/run", _as(m.Run))


def delete_routine(routine_id: str) -> Call[m.OkResult]:
    return Call("DELETE", f"/v1/routines/{_seg(routine_id)}", _as(m.OkResult))


def approve_routine(routine_id: str, device_id: str) -> Call[m.Approval]:
    return Call("POST", f"/v1/routines/{_seg(routine_id)}/approve", _as(m.Approval), {"device": device_id})


def start_writer(
    *,
    unknown_id: str | None = None,
    driver: str | None = None,
    params: Mapping[str, Any] | None = None,
    sketch_path: str | None = None,
    manual_text: str | None = None,
) -> Call[m.WriterSession]:
    body: dict[str, Any] = {}
    for key, value in (
        ("unknown_id", unknown_id),
        ("driver", driver),
        ("params", dict(params) if params is not None else None),
        ("sketch_path", sketch_path),
        ("manual_text", manual_text),
    ):
        if value is not None:
            body[key] = value
    return Call("POST", "/v1/writer/sessions", _as(m.WriterSession), body)


def writer_session(session_id: str) -> Call[m.WriterSession]:
    return Call("GET", f"/v1/writer/sessions/{_seg(session_id)}", _as(m.WriterSession))


def propose(session_id: str, draft_yaml: str) -> Call[m.WriterSession]:
    path = f"/v1/writer/sessions/{_seg(session_id)}/propose"
    return Call("POST", path, _as(m.WriterSession), {"draft_yaml": draft_yaml})


def interview(session_id: str) -> Call[m.Interview]:
    return Call("GET", f"/v1/writer/sessions/{_seg(session_id)}/interview", _as(m.Interview))


def answer(session_id: str, answers: Mapping[str, Any]) -> Call[m.WriterSession]:
    path = f"/v1/writer/sessions/{_seg(session_id)}/answers"
    return Call("POST", path, _as(m.WriterSession), {"answers": dict(answers)})


def finish(session_id: str, save_as: str | None = None) -> Call[m.FinishResult]:
    body = {"save_as": save_as} if save_as else {}
    return Call("POST", f"/v1/writer/sessions/{_seg(session_id)}/finish", _as(m.FinishResult), body)


def test_plan(session_id: str) -> Call[m.TestPlan]:
    return Call("GET", f"/v1/writer/sessions/{_seg(session_id)}/test_plan", _as(m.TestPlan))


test_plan.__test__ = False  # type: ignore[attr-defined]


def tokens() -> Call[list[m.TokenInfo]]:
    return Call("GET", "/v1/tokens", _list_of(m.TokenInfo))


def create_token(name: str, kind: str = "agent", scope: str = "read") -> Call[m.NewToken]:
    return Call("POST", "/v1/tokens", _as(m.NewToken), {"name": name, "kind": kind, "scope": scope})


def revoke_token(token_id: str) -> Call[m.OkResult]:
    return Call("DELETE", f"/v1/tokens/{_seg(token_id)}", _as(m.OkResult))


def new_pairing_code() -> Call[m.PairingCode]:
    return Call("POST", "/v1/pair/code", _as(m.PairingCode), {})
