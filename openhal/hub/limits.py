"""Changing a channel's limits through the hub, so a person never edits a device file by hand.

A change that only narrows what an agent may do, a smaller max, a larger min or a slower rate,
needs no approval. From a person it is written into the device file at once. From an agent it goes
through the kernel's tighten path, so it narrows that agent's own session. A change that widens
anything needs a human principal. A person who typed the phrase confirm gets the change at once,
and any other request becomes a pending limit change that only a person approves, with the phrase
approve. Nothing goes past the range the device itself reports.

Each change is written into the device file with its confirmation bound again to the hash of the
limits, recorded in the audit log and loaded by the running hub at once. A stop cancels every
pending change, the same as the commands the kernel holds.
"""

from __future__ import annotations

import asyncio
import copy
import datetime as dt
import math
import secrets
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar, Final, Literal

import yaml

from openhal.drivers.base import DriverError
from openhal.kernel.checks import Block
from openhal.kernel.principals import Principal
from openhal.spec import risk
from openhal.spec.loader import DeviceFileError, from_data, parse_yaml
from openhal.spec.models import DeviceFile
from openhal.spec.units import Quantity, UnitError, convert, convert_rate, format_quantity, parse_quantity
from openhal.writer import interview
from openhal.writer.engine import force_suggested

if TYPE_CHECKING:
    from openhal.hub.hub import Hub

APPLY_PHRASE: Final = "confirm"
APPROVE_PHRASE: Final = "approve"
DESCRIBE_TIMEOUT_S: Final = 5.0
FIELDS: Final = ("min", "max", "rate")
MAX_PENDING: Final = 100
PER_PRINCIPAL: Final = 20
Status = Literal["pending", "done", "rejected", "expired", "cancelled", "blocked"]


class LimitError(ValueError):
    """A limit change the hub blocks, with the stable code and the reason."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class Change:
    """One channel's limits before and after, in the channel's unit. A rate of None means no rate limit."""

    device: str
    channel: str
    unit: str
    before: dict[str, float | None]
    after: dict[str, float | None]

    @property
    def loosens(self) -> list[str]:
        """The fields that widen what an agent may do."""
        widened = []
        if _num(self.after["min"]) < _num(self.before["min"]):
            widened.append("min")
        if _num(self.after["max"]) > _num(self.before["max"]):
            widened.append("max")
        before_rate, after_rate = self.before["rate"], self.after["rate"]
        if before_rate is not None and (after_rate is None or after_rate > before_rate):
            widened.append("rate")
        return widened

    @property
    def changed(self) -> list[str]:
        return [name for name in FIELDS if self.before[name] != self.after[name]]

    def shown(self, name: str, value: float | None) -> str:
        if value is None:
            return "no limit"
        text = format_quantity(value, self.unit)
        return f"{text}/s" if name == "rate" else text

    def lines(self) -> list[str]:
        """One line per changed field, such as `max 80 % to 100 %`."""
        return [
            f"{name} {self.shown(name, self.before[name])} to {self.shown(name, self.after[name])}"
            for name in self.changed
        ]

    def view(self) -> dict[str, Any]:
        return {
            "device": self.device,
            "channel": self.channel,
            "unit": self.unit,
            "before": dict(self.before),
            "after": dict(self.after),
            "changes": {
                name: {"from": self.shown(name, self.before[name]), "to": self.shown(name, self.after[name])}
                for name in self.changed
            },
            "loosens": self.loosens,
        }


def _num(value: float | None) -> float:
    return math.inf if value is None else value


@dataclass
class HeldRequest:
    """A change held until a person approves it."""

    request_id: str
    change: Any
    principal: Principal
    created_at: float
    expires_at: float
    status: Status = "pending"
    decided_by: str | None = None
    result: str | None = None
    history: list[str] = field(default_factory=list)


@dataclass
class LimitRequest(HeldRequest):
    """A change that widens a limit, held until a person approves the change."""

    change: Change
    limits_sha256: str = ""


def device_file(hub: Hub, device_id: str) -> tuple[Path, dict[str, Any], DeviceFile]:
    """A device's file as data and as loaded, checked to be the same file the hub runs."""
    runtime = hub.kernel.devices.get(device_id)
    info = hub.info.get(device_id)
    if runtime is None:
        raise KeyError(f"There is no device {device_id!r}.")
    if info is None or not info.path:
        raise LimitError("misconfigured", f"Blocked. {device_id} has no device file in the devices folder.")
    path = Path(info.path)
    try:
        data = parse_yaml(path.read_text(encoding="utf-8"))
        on_disk = from_data(data)
    except (OSError, DeviceFileError) as exc:
        raise LimitError("misconfigured", f"Blocked. {path.name} doesn't load. {exc}") from exc
    if on_disk.limits_sha256() != runtime.file.limits_sha256() or _levels(on_disk) != _levels(runtime.file):
        raise LimitError(
            "misconfigured",
            f"Blocked. {path.name} changed on disk after the hub loaded the file. Load the file first.",
        )
    return path, data, on_disk


def _levels(file: DeviceFile) -> dict[str, Any]:
    """Every `risk` entry of a file, which the limits hash leaves out."""
    entries: list[tuple[str, Any]] = [*file.write.items(), *file.actions.items()]
    return {name: spec.risk for name, spec in entries if spec.risk is not None}


class HeldChanges[R: HeldRequest]:
    """Changes held for a person to approve, with the bookkeeping limit and risk changes share.

    A stop cancels every pending change, an unanswered one expires after the confirmation time, and
    each status change is in the audit log under `EVENT`.
    """

    EVENT: ClassVar[str]
    NOUN: ClassVar[str]

    def __init__(self, hub: Hub) -> None:
        self.hub = hub
        self.requests: dict[str, R] = {}
        hub.kernel.on_stop(self._on_stop)

    def _target(self, change: Any) -> str:
        raise NotImplementedError

    def _on_stop(self, reason: str) -> None:
        for request in self.requests.values():
            if request.status == "pending":
                self._close(request, "cancelled", "system", f"cancelled by the stop, {reason}")

    def _make_room(self, who: Principal) -> None:
        self.expire()
        pending = [item for item in self.requests.values() if item.status == "pending"]
        if len([item for item in pending if item.principal == who]) >= PER_PRINCIPAL or len(pending) >= MAX_PENDING:
            raise LimitError("queue_full", f"Blocked. Too many {self.NOUN}s are waiting for a person already.")

    def _filed(self, request: R, **details: Any) -> R:
        self.requests[request.request_id] = request
        self.hub.audit.append(
            self.EVENT,
            request.principal.label,
            device=request.change.device,
            target=self._target(request.change),
            status="pending",
            request=request.request_id,
            **details,
        )
        return request

    def get(self, request_id: str) -> R | None:
        return self.requests.get(request_id)

    def expire(self) -> None:
        now = self.hub.kernel.clock()
        for request in self.requests.values():
            if request.status == "pending" and now > request.expires_at:
                self._close(request, "expired", "system", "expired")

    def _close(self, request: R, status: Status, by: str, note: str) -> None:
        request.status = status
        request.decided_by = by if status in ("done", "rejected") else request.decided_by
        request.result = note
        request.history.append(note)
        self.hub.audit.append(
            self.EVENT,
            by,
            device=request.change.device,
            target=self._target(request.change),
            status=status,
            request=request.request_id,
            message=note,
        )

    def pending(self) -> list[R]:
        self.expire()
        return sorted((item for item in self.requests.values() if item.status == "pending"), key=_created)

    def recent(self, limit: int = 100) -> list[R]:
        self.expire()
        return sorted(self.requests.values(), key=_created, reverse=True)[:limit]

    def reject(self, request_id: str, who: Principal, reason: str = "") -> R:
        request = self.requests[request_id]
        self.expire()
        if request.status != "pending":
            raise LookupError(f"The {self.NOUN} {request_id} is {request.status}, so there is nothing to reject.")
        self._close(request, "rejected", who.label, f"Rejected. {reason}".strip())
        return request


def _value(text: Any, unit: str, name: str) -> float:
    try:
        return convert(parse_quantity(text, default_unit=unit), unit)
    except UnitError as exc:
        raise LimitError("bad_unit", f"Blocked. {name} {exc}") from exc


def _rate(text: Any, unit: str) -> float | None:
    answer = str(text).strip()
    if answer.lower() in ("none", "no limit"):
        return None
    try:
        if "/" in answer or " per " in answer:
            value = convert_rate(parse_quantity(answer.replace("%/s", "percent / second")), unit)
        else:
            amount = parse_quantity(answer, default_unit=unit)
            value = convert_rate(Quantity(amount.magnitude, f"({amount.units}) / second"), unit)
    except UnitError as exc:
        raise LimitError("bad_unit", f"Blocked. rate {exc}") from exc
    if not math.isfinite(value) or value <= 0:
        raise LimitError("bad_request", "Blocked. A rate must be more than zero, or none.")
    return value


def _safe_value(data: dict[str, Any], channel: str, unit: str) -> float | None:
    safe = data.get("safe_state")
    steps = [safe] if isinstance(safe, dict) else safe or []
    for step in steps:
        if not isinstance(step, dict) or "action" in step:
            continue
        values = step.get("values", step)
        if channel in values:
            raw = values[channel]
            if isinstance(raw, bool):
                return None
            return float(raw) if isinstance(raw, int | float) else _value(raw, unit, "safe value")
    return None


class LimitChanges(HeldChanges[LimitRequest]):
    """Limit changes for one hub, with the pending ones a person approves."""

    EVENT = "limit_change"
    NOUN = "limit change"

    def _target(self, change: Change) -> str:
        return f"write:{change.channel}"

    def _read(self, device_id: str, channel: str | None = None) -> tuple[Path, dict[str, Any]]:
        """The device's file as data, checked to be the file the hub runs, with `channel` not read-only."""
        path, data, on_disk = device_file(self.hub, device_id)
        target = f"write:{channel}"
        if channel is not None and (
            on_disk.read_only(target) or self.hub.kernel.devices[device_id].file.read_only(target)
        ):
            raise LimitError(
                "read_only_file",
                f"Blocked. {device_id}.{channel} is high risk and its limits aren't confirmed yet. Answer each "
                f"limit first with openhal file confirm {path}, or Review limits in the Inspector.",
            )
        return path, data

    async def reported(self, device_id: str, data: dict[str, Any]) -> dict[str, tuple[float, float]]:
        """The range the device reports for each channel and action argument, by `channel` or `action.arg`.

        A file keeps the range in `x-device-limits`. A file the device described, saved before OpenHAL
        kept that entry, takes the missing ranges from the connected device's own description, so the
        device's range stays the hard edge. A hand-written or library file keeps only its own entries.
        """
        kept = interview.device_limits(data)
        provenance = data.get("provenance")
        source = provenance.get("source") if isinstance(provenance, dict) else None
        runtime = self.hub.kernel.devices.get(device_id)
        if source not in interview.REPORTING_SOURCES or runtime is None or not runtime.connected:
            return kept
        try:
            described = await asyncio.wait_for(runtime.driver.describe(), DESCRIBE_TIMEOUT_S)
        except (DriverError, TimeoutError, OSError, ValueError, KeyError):
            return kept
        if not described:
            return kept
        live = interview.device_limits({**force_suggested(described), "provenance": {"source": source}})
        return {**live, **kept}

    async def check(
        self, device_id: str, channel: str, *, min: Any = None, max: Any = None, rate: Any = None
    ) -> Change:
        """The change a request asks for, checked against the file and the range the device reports."""
        _, data = self._read(device_id, channel)
        reported = await self.reported(device_id, data)
        return self.plan(device_id, channel, min=min, max=max, rate=rate, reported=reported)

    def plan(
        self,
        device_id: str,
        channel: str,
        *,
        min: Any = None,
        max: Any = None,
        rate: Any = None,
        reported: dict[str, tuple[float, float]] | None = None,
    ) -> Change:
        """The change a request asks for, checked against the file and the device's own range.

        A low risk channel's rate that was only suggested doesn't apply (ADR 0023), so it counts as no rate.
        """
        _, data = self._read(device_id, channel)
        spec = (data.get("write") or {}).get(channel)
        if not isinstance(spec, dict) or spec.get("type", "number") != "number" or not spec.get("unit"):
            raise KeyError(f"{device_id} has no number channel {channel!r} with limits.")
        unit = str(spec["unit"])
        applies = risk.own_rate(self.hub.kernel.devices[device_id].file, channel)
        before: dict[str, float | None] = {
            "min": float(spec["min"]),
            "max": float(spec["max"]),
            "rate": float(spec["max_change_per_s"]) if spec.get("max_change_per_s") is not None and applies else None,
        }
        after = dict(before)
        if min is not None:
            after["min"] = _value(min, unit, "min")
        if max is not None:
            after["max"] = _value(max, unit, "max")
        if rate is not None:
            after["rate"] = _rate(rate, unit)
        change = Change(device_id, channel, unit, before, after)
        if not change.changed:
            raise LimitError("bad_request", "Blocked. The request changes nothing. Give a new min, max or rate.")
        low, high = _num(after["min"]), _num(after["max"])
        if low > high:
            raise LimitError("bad_request", "Blocked. min would be above max.")
        edge = (interview.device_limits(data) if reported is None else reported).get(channel)
        if edge is not None:
            span = f"from {format_quantity(edge[0], unit)} to {format_quantity(edge[1], unit)}"
            if high > edge[1]:
                raise LimitError(
                    "above_max",
                    f"Blocked. {format_quantity(high, unit)} is above {format_quantity(edge[1], unit)}, "
                    f"the most {device_id} reports for {channel}. Keep {channel} {span}.",
                )
            if low < edge[0]:
                raise LimitError(
                    "below_min",
                    f"Blocked. {format_quantity(low, unit)} is below {format_quantity(edge[0], unit)}, "
                    f"the least {device_id} reports for {channel}. Keep {channel} {span}.",
                )
        safe = _safe_value(data, channel, unit)
        if safe is not None and not low <= safe <= high:
            raise LimitError(
                "bad_request",
                f"Blocked. The safe value {format_quantity(safe, unit)} would sit outside "
                f"{format_quantity(low, unit)} to {format_quantity(high, unit)}. Change the safe value first.",
            )
        return change

    async def apply(self, change: Change, who: Principal) -> Path:
        """Write the change into the file, confirmed by `who`, and load the file. `who` is a human principal."""
        async with self.hub.file_lock:
            return await self._apply(change, who)

    async def _apply(self, change: Change, who: Principal) -> Path:
        path, data = self._read(change.device, change.channel)
        bound = data.get("confirmed") if isinstance(data.get("confirmed"), dict) else None
        if bound is not None and bound.get("sha256") and bound["sha256"] != from_data(data).limits_sha256():
            raise LimitError(
                "read_only_file",
                f"Blocked. The confirmation in {path.name} no longer matches its limits, so a change here would "
                f"confirm limits nobody checked. Answer them again with openhal file confirm {path}.",
            )
        updated = copy.deepcopy(data)
        spec = updated["write"][change.channel]
        spec["min"], spec["max"] = _tidy(change.after["min"]), _tidy(change.after["max"])
        if change.after["rate"] is None:
            spec.pop("max_change_per_s", None)
        else:
            spec["max_change_per_s"] = _tidy(change.after["rate"])
        spec.pop("suggested", None)
        today = dt.date.today().isoformat()
        try:
            if updated.pop("confirmed", None) is None:
                spec["confirmed"] = {"by": who.name[:80], "at": today}
            else:
                updated["confirmed"] = {"by": who.name[:80], "at": today, "sha256": from_data(updated).limits_sha256()}
            if from_data(updated).read_only(f"write:{change.channel}"):
                raise LimitError("misconfigured", "Blocked. The changed file would load read-only.")
        except DeviceFileError as exc:
            raise LimitError("bad_request", "Blocked. " + " ".join(exc.problems)) from exc
        text = yaml.safe_dump(updated, sort_keys=False, allow_unicode=True, width=100)
        await asyncio.to_thread(path.write_text, text, "utf-8")
        await self.hub.load_device_file(path, by=who.label)
        self.hub.audit.append(
            "limit_change",
            who.label,
            device=change.device,
            target=f"write:{change.channel}",
            status="done",
            changes=change.view()["changes"],
        )
        return path

    def hold(self, change: Change, who: Principal) -> LimitRequest:
        """File a pending change for a person to approve."""
        self._make_room(who)
        now = self.hub.kernel.clock()
        _, data = self._read(change.device)
        request = LimitRequest(
            request_id=f"limit-{secrets.token_hex(6)}",
            change=change,
            principal=who,
            created_at=now,
            expires_at=now + self.hub.config.confirm.ttl_s,
            limits_sha256=from_data(data).limits_sha256(),
        )
        return self._filed(request, changes=change.view()["changes"])

    async def request(
        self,
        who: Principal,
        device_id: str,
        channel: str,
        *,
        min: Any = None,
        max: Any = None,
        rate: Any = None,
        phrase: str | None = None,
    ) -> dict[str, Any]:
        """Tighten at once, apply a person's confirmed loosening, or hold any other loosening."""
        try:
            change = await self.check(device_id, channel, min=min, max=max, rate=rate)
            if who.kind == "agent" and who.scope == "read" and change.loosens:
                raise LimitError("not_permitted", "Blocked. A read-only token can't ask for wider limits.")
            if not change.loosens:
                if who.kind == "human":
                    await self.apply(change, who)
                    return self._result("done", change, f"Done. {self._said(change)}", scope="file")
                values = {name: _limit_text(change, name) for name in change.changed}
                self.hub.kernel.tighten(who, device_id, channel, **values)
                return self._result(
                    "done", change, f"Done. {self._said(change)} for this agent's session.", scope="session"
                )
            if who.kind == "human" and phrase is not None:
                if phrase.strip().lower() != APPLY_PHRASE:
                    raise LimitError("bad_request", f"Blocked. Type {APPLY_PHRASE} to widen these limits.")
                await self.apply(change, who)
                return self._result("done", change, f"Done. {self._said(change)}", scope="file")
            held = self.hold(change, who)
        except LimitError as error:
            self.hub.audit.append(
                "limit_change",
                who.label,
                device=device_id,
                target=f"write:{channel}",
                status="blocked",
                code=error.code,
                message=error.message,
            )
            return {"status": "blocked", "code": error.code, "message": error.message, "device": device_id}
        except Block as block:
            return {"status": "blocked", "code": block.code, "message": block.message, "device": device_id}
        message = (
            f"Held for a person. {self._said(change)} widens what an agent may do, so a person approves the change "
            f"with openhal confirm approve {held.request_id} or in the Inspector."
        )
        return {**self._result("pending", change, message, scope="file"), "request_id": held.request_id}

    @staticmethod
    def _said(change: Change) -> str:
        return f"{change.device}.{change.channel} " + ", ".join(change.lines())

    @staticmethod
    def _result(status: str, change: Change, message: str, *, scope: str) -> dict[str, Any]:
        return {"status": status, "message": message, "scope": scope, "device": change.device, **change.view()}

    async def approve(self, request_id: str, who: Principal, phrase: str | None) -> LimitRequest:
        """A person approves a pending change. The file must be as it was when the change was asked for."""
        request = self.requests[request_id]
        self.expire()
        if request.status != "pending":
            raise LookupError(f"The limit change {request_id} is {request.status}, so there is nothing to approve.")
        if (phrase or "").strip().lower() != APPROVE_PHRASE:
            raise LimitError("bad_request", f"Blocked. Type {APPROVE_PHRASE} to approve this limit change.")
        try:
            _, data = self._read(request.change.device)
            if from_data(data).limits_sha256() != request.limits_sha256:
                raise LimitError(
                    "misconfigured", "Blocked. The limits changed after the request. Ask for the change again."
                )
            change = await self.check(
                request.change.device,
                request.change.channel,
                **{name: _limit_text(request.change, name) for name in request.change.changed},
            )
            await self.apply(change, who)
        except (LimitError, KeyError) as error:
            self._close(request, "blocked", who.label, str(getattr(error, "message", error)))
            return request
        self._close(request, "done", who.label, f"Done. {self._said(change)}")
        return request

    def view(self, request: LimitRequest) -> dict[str, Any]:
        """A pending change in the shape of a held command, so every list of held requests shows both."""
        now = self.hub.kernel.clock()
        change = request.change
        said = self._said(change)
        held = {
            "status": "needs_confirmation",
            "code": "needs_confirmation",
            "message": f"{said} widens what an agent may do, so a person approves the change.",
            "device": change.device,
            "target": f"limits:{change.channel}",
            "value": None,
            "unit": None,
            "limit": None,
            "request_id": request.request_id,
        }
        result = None
        if request.status in ("done", "blocked"):
            result = {**held, "status": request.status, "code": None, "message": request.result or ""}
        return {
            "id": request.request_id,
            "status": request.status,
            "command": {"kind": "limits", **change.view()},
            "requested_by": request.principal.label,
            "created_at": request.created_at,
            "expires_at": request.expires_at,
            "expires_in_s": round(max(0.0, request.expires_at - now), 1) if request.status == "pending" else 0.0,
            "dry_run": held,
            "decided_by": request.decided_by,
            "result": result,
        }


def _created(request: HeldRequest) -> float:
    return request.created_at


def _tidy(value: float | None) -> float | int | None:
    if value is None:
        return None
    return int(value) if float(value).is_integer() else value


def _limit_text(change: Change, name: str) -> str:
    value = change.after[name]
    if value is None:
        return "none"
    text = f"{value:.12g} {change.unit}"
    return f"{text} / second" if name == "rate" else text
