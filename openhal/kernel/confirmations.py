"""The confirmation queue. Commands that need a human wait here until approved, rejected or expired."""

from __future__ import annotations

import secrets
from dataclasses import dataclass, field
from typing import Literal

from openhal.kernel.commands import Command, Decision
from openhal.kernel.principals import Principal

RequestStatus = Literal["pending", "approved", "rejected", "expired", "cancelled", "blocked", "done", "failed"]


@dataclass
class Request:
    """One command waiting for a human."""

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

    def __init__(self, ttl_s: float = 300.0, max_pending: int = 100) -> None:
        self.ttl_s = ttl_s
        self.max_pending = max_pending
        self._requests: dict[str, Request] = {}

    def add(self, command: Command, principal: Principal, dry_run: Decision, now: float) -> Request:
        self.expire(now)
        pending = [request for request in self._requests.values() if request.status == "pending"]
        if len(pending) >= self.max_pending:
            oldest = min(pending, key=lambda request: request.created_at)
            oldest.status = "cancelled"
            oldest.history.append("cancelled because the queue was full")
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
                request.history.append("expired")
                expired.append(request)
        return expired

    def cancel_all(self, reason: str) -> list[Request]:
        cancelled = []
        for request in self._requests.values():
            if request.status == "pending":
                request.status = "cancelled"
                request.history.append(reason)
                cancelled.append(request)
        return cancelled
