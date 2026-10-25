"""Registry errors in MCP tool results (ADR 0015, MCP mapping).

A blocked or failed decision gains `error`, the same `{ code, name, message, data }` a protocol
client gets from the hub. Its reason needs the device file and who confirmed the limit, which come
from `hal/devices/describe` over the hub's `/rpc` socket. When that socket can't be reached, the
REST device view gives the file name and limits, and the reason leaves the confirmation out.

Tool errors for refused calls start with the registry name and number, for example
`SCOPE_DENIED (-32003). Only a human can do this.`
"""

from __future__ import annotations

import contextlib
from pathlib import Path
from typing import Any, Final

import httpx
from pydantic import BaseModel, Field
from websockets.exceptions import WebSocketException

from openhal.client import AsyncClient, OpenHALError
from openhal.client import models as m
from openhal.client.errors import HubNotRunning
from openhal.protocol.client import ProtocolClient, ProtocolError
from openhal.protocol.convert import Facts, build_error, target_parts
from openhal.protocol.errors import BY_NAME

HTTP_NAMES: Final = {
    400: "INVALID_PARAMS",
    401: "UNAUTHORIZED",
    403: "SCOPE_DENIED",
    404: "UNKNOWN_TARGET",
    409: "REQUEST_CLOSED",
    422: "INVALID_PARAMS",
}


class ErrorInfo(BaseModel):
    """The registry error behind a blocked or failed decision, as a protocol client sees it."""

    code: int = Field(description="The registry number, for example -32010.")
    name: str = Field(description="The registry name to branch on, for example LIMIT_EXCEEDED.")
    message: str = Field(description="The reason, naming the limit, the device file and who confirmed it.")
    data: dict[str, Any] = Field(description="The fields the reason was formed from.")


class Decision(m.Decision):
    """The kernel's answer, with the registry error when it was blocked or failed."""

    error: ErrorInfo | None = Field(default=None, description="Set when status is blocked or failed.")


def tool_error_text(exc: OpenHALError) -> str:
    """A refused call's message, led by its registry name and number when it has one."""
    if isinstance(exc, HubNotRunning) or exc.status_code is None:
        return str(exc)
    name = HTTP_NAMES.get(exc.status_code) or ("INTERNAL_ERROR" if exc.status_code >= 500 else None)
    if name is None:
        return str(exc)
    spec = BY_NAME[name]
    return f"{spec.name} ({spec.code}). {exc}"


def _confirmed(item: Any) -> tuple[str | None, str | None]:
    if isinstance(item, dict) and item.get("by"):
        return str(item["by"]), str(item.get("at") or "") or None
    return None, None


def _limits(channel: dict[str, Any]) -> dict[str, float]:
    found = {"max": channel.get("max"), "min": channel.get("min"), "rate_per_s": channel.get("maxChangePerS")}
    return {key: float(value) for key, value in found.items() if isinstance(value, int | float)}


def facts_from_description(device: dict[str, Any], target: str | None) -> Facts:
    """Facts from a protocol DeviceDescription."""
    channel, action = target_parts(target)
    entry: dict[str, Any] = {}
    if channel is not None:
        entry = device.get("write", {}).get(channel) or {}
    elif action is not None:
        entry = device.get("actions", {}).get(action) or {}
    by, at = _confirmed(entry.get("confirmed"))
    if by is None:
        by, at = _confirmed(device.get("confirmed"))
    return Facts(
        file=device.get("file"),
        confirmed_by=by,
        confirmed_at=at,
        unit=entry.get("unit") if channel is not None else None,
        number=channel is not None and entry.get("type") == "number",
        limits=_limits(entry) if channel is not None else {},
    )


def facts_from_view(view: m.DeviceView, target: str | None) -> Facts:
    """Facts from the REST device view, which has no confirmation."""
    channel, _ = target_parts(target)
    spec = view.write.get(channel) if channel is not None else None
    limits: dict[str, float] = {}
    if spec is not None:
        found = {"max": spec.max, "min": spec.min, "rate_per_s": spec.max_change_per_s}
        limits = {key: value for key, value in found.items() if value is not None}
    return Facts(
        file=Path(view.path).name if view.path else None,
        unit=spec.unit if spec is not None else None,
        number=spec is not None and spec.type == "number",
        limits=limits,
    )


def reaches_network(client: AsyncClient) -> bool:
    """False when the client talks to an in-process app, as tests do, so no socket is opened."""
    transport = client._http._transport  # noqa: SLF001
    return isinstance(transport, httpx.AsyncHTTPTransport)


class ErrorMapper:
    """Adds registry errors to decisions for one hub client.

    `use_socket` says whether to ask the hub's `/rpc` socket for the device's limits provenance.
    It defaults to whether the client reaches the network at all.
    """

    def __init__(self, client: AsyncClient, *, use_socket: bool | None = None) -> None:
        self.client = client
        self.use_socket = reaches_network(client) if use_socket is None else use_socket

    async def _described(self, device: str) -> dict[str, Any] | None:
        token = self.client.token_source.token
        try:
            async with ProtocolClient(self.client.url, token, client_name="openhal-mcp") as hub:
                described = await hub.call("hal/devices/describe", {"device": device})
        except (OSError, TimeoutError, ProtocolError, WebSocketException):
            return None
        found: dict[str, Any] = described["device"]
        return found

    async def facts(self, device: str, target: str | None) -> Facts | None:
        described = await self._described(device) if self.use_socket else None
        if described is not None:
            return facts_from_description(described, target)
        with contextlib.suppress(OpenHALError):
            return facts_from_view(await self.client.device(device), target)
        return None

    async def decision(self, decision: m.Decision, raw_value: Any = None, principal: str | None = None) -> Decision:
        """The decision with `error` set when it was blocked or failed."""
        result = Decision.model_validate(decision.model_dump())
        if decision.status not in ("blocked", "failed"):
            return result
        error = build_error(
            decision.code,
            device=decision.device,
            target=decision.target,
            facts=await self.facts(decision.device, decision.target),
            kernel_message=decision.message,
            raw_value=raw_value,
            limit=decision.limit,
            request_id=decision.request_id,
            principal=principal,
        )
        body = error.to_object()
        result.error = ErrorInfo(code=error.code, name=error.name, message=error.reason, data=body["data"])
        return result
