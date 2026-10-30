"""The confirmation queue holds each command that needs a human until a person decides or it expires.

Every status change is reported through `on_change` so the kernel can log it (review finding F09).
Each principal may have at most `per_principal` pending requests. A full queue blocks new
requests instead of evicting someone else's (review finding F22).
"""

from __future__ import annotations

import secrets
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal

from openhal.kernel.commands import Command, Decision
from openhal.kernel.principals import Principal

RequestStatus = Literal["pending", "approved", "rejected", "expired", "cancelled", "blocked", "done", "failed"]


class QueueFull(Exception):  # noqa: N818 (a blocked request, not an error)
    """The principal, or the whole queue, already has the maximum number of pending requests."""


@dataclass
class Request:
    """One command held for a human."""

    request_id: str
    command: Command
    principal: Principal
    created_at: float
    expires_at: float
    dry_run: Decision
    status: RequestStatus = "pending"
    decided_by: str | None = None
    result: Decision | None = None
    history: list[str] = field(default_factory=list)


class ConfirmationQueue:
    """Pending requests, keyed by id. The kernel owns the only instance."""

    def __init__(
        self,
        ttl_s: float = 300.0,
        max_pending: int = 100,
        per_principal: int = 20,
        on_change: Callable[[Request, str], None] | None = None,
    ) -> None:
        self.ttl_s = ttl_s
        self.max_pending = max_pending
        self.per_principal = per_principal
        self.on_change = on_change
        self._requests: dict[str, Request] = {}

    def _changed(self, request: Request, reason: str) -> None:
        request.history.append(reason)
        if self.on_change is not None:
            self.on_change(request, reason)

    def add(self, command: Command, principal: Principal, dry_run: Decision, now: float) -> Request:
        self.expire(now)
        pending = [request for request in self._requests.values() if request.status == "pending"]
        mine = [request for request in pending if request.principal.label == principal.label]
        if len(mine) >= self.per_principal:
            raise QueueFull(
                f"This client already has {len(mine)} requests waiting for a human. Wait for them to be decided."
            )
        if len(pending) >= self.max_pending:
            raise QueueFull("The confirmation queue is full. Wait for pending requests to be decided.")
        request = Request(
            request_id=secrets.token_hex(8),
            command=command,
            principal=principal,
            created_at=now,
            expires_at=now + self.ttl_s,
            dry_run=dry_run,
        )
        self._requests[request.request_id] = request
        return request

    def get(self, request_id: str) -> Request | None:
        return self._requests.get(request_id)

    def pending(self, now: float) -> list[Request]:
        self.expire(now)
        return sorted(
            (request for request in self._requests.values() if request.status == "pending"),
            key=lambda request: request.created_at,
        )

    def recent(self, limit: int = 50) -> list[Request]:
        return sorted(self._requests.values(), key=lambda request: request.created_at, reverse=True)[:limit]

    def expire(self, now: float) -> list[Request]:
        expired = []
        for request in self._requests.values():
            if request.status == "pending" and now > request.expires_at:
                request.status = "expired"
                self._changed(request, "expired")
                expired.append(request)
        return expired

    def cancel_all(self, reason: str) -> list[Request]:
        cancelled = []
        for request in self._requests.values():
            if request.status == "pending":
                request.status = "cancelled"
                self._changed(request, reason)
                cancelled.append(request)
        return cancelled
