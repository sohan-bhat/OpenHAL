"""A stand-in for the hub protocol's `/rpc` WebSocket and the `/v1/rpc/log` message log.

The protocol workstream builds the real ones (docs/agents/BRIEF-protocol.md, section 7). Until they
merge, the Inspector's browser tests run against this fixture. It speaks the message shapes of
spec/2026-10-24/basic/messages.md on top of the real kernel, so every decision is the kernel's own.
The harness uses the real routes as soon as the hub app has them.
"""

from __future__ import annotations

import asyncio
import contextlib
import datetime as dt
import itertools
import json
from collections import deque
from collections.abc import Callable
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from openhal.hub.api import SESSION_COOKIE, principal_for
from openhal.hub.hub import Hub
from openhal.kernel.commands import Action, Decision, Write
from openhal.kernel.principals import Principal
from openhal.spec.units import format_quantity

PROTOCOL_VERSION = "2026-10-24"
LOG_SIZE = 2000

REGISTRY: dict[str, tuple[int, str]] = {
    "bad_request": (-32602, "INVALID_PARAMS"),
    "internal_error": (-32603, "INTERNAL_ERROR"),
    "not_permitted": (-32003, "SCOPE_DENIED"),
    "unknown_target": (-32004, "UNKNOWN_TARGET"),
    "device_unavailable": (-32005, "DEVICE_UNAVAILABLE"),
    "above_max": (-32010, "LIMIT_EXCEEDED"),
    "below_min": (-32010, "LIMIT_EXCEEDED"),
    "rate_limited": (-32011, "RATE_LIMITED"),
    "interlock": (-32012, "INTERLOCK_BLOCKED"),
    "needs_confirmation": (-32013, "CONFIRMATION_REQUIRED"),
    "stopped": (-32014, "STOPPED"),
    "read_only_file": (-32015, "UNVERIFIED_LIMITS"),
    "bad_value": (-32016, "INVALID_VALUE"),
    "bad_step": (-32016, "INVALID_VALUE"),
    "duration_exceeded": (-32017, "WATCHDOG_TRIPPED"),
    "busy": (-32018, "BUSY"),
    "queue_full": (-32019, "QUEUE_FULL"),
    "driver_error": (-32020, "DRIVER_ERROR"),
    "misconfigured": (-32021, "MISCONFIGURED"),
    "cannot_loosen": (-32021, "MISCONFIGURED"),
    "expired": (-32022, "REQUEST_CLOSED"),
    "rejected": (-32022, "REQUEST_CLOSED"),
    "bad_unit": (-32023, "UNIT_INVALID"),
}

SYMBOLS = {"percent": "%", "degC": "degC", "W": "W"}


class RpcError(Exception):
    def __init__(self, code: int, name: str, message: str, data: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.name = name
        self.message = message
        self.data = data or {}

    def payload(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "data": {"name": self.name, **self.data}}


def now_iso() -> str:
    return dt.datetime.now(dt.UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class MessageLog:
    def __init__(self) -> None:
        self.entries: deque[dict[str, Any]] = deque(maxlen=LOG_SIZE)
        self._seq = itertools.count(1)
        self._listeners: list[Callable[[dict[str, Any]], None]] = []

    def record(self, direction: str, client: str, principal: str | None, message: Any) -> None:
        entry = {
            "seq": next(self._seq),
            "at": now_iso(),
            "direction": direction,
            "client": client,
            "principal": principal,
            "message": message,
        }
        self.entries.append(entry)
        for listener in list(self._listeners):
            listener(entry)

    def since(self, seq: int) -> list[dict[str, Any]]:
        return [entry for entry in self.entries if entry["seq"] > seq]

    def subscribe(self, listener: Callable[[dict[str, Any]], None]) -> Callable[[], None]:
        self._listeners.append(listener)

        def unsubscribe() -> None:
            with contextlib.suppress(ValueError):
                self._listeners.remove(listener)

        return unsubscribe


def unit_symbol(unit: str | None) -> str | None:
    return SYMBOLS.get(unit, unit) if unit else unit


def blocked_error(hub: Hub, decision: Decision) -> RpcError:
    code, name = REGISTRY.get(decision.code or "internal_error", (-32603, "INTERNAL_ERROR"))
    device = decision.device
    channel = decision.target.split(":", 1)[1] if ":" in decision.target else None
    data: dict[str, Any] = {"kernelCode": decision.code, "device": device}
    if channel:
        data["channel"] = channel
    if decision.request_id:
        data["requestId"] = decision.request_id
    message = decision.message
    if name == "LIMIT_EXCEEDED" and decision.limit:
        unit = str(decision.limit.get("unit") or "")
        bound = decision.limit.get("max", decision.limit.get("min"))
        limit = format_quantity(float(bound), unit) if bound is not None else ""
        requested = message.rsplit("Asked for ", 1)[-1].rstrip(".")
        runtime = hub.kernel.devices.get(device)
        info = hub.info.get(device)
        file_name = Path(info.path).name if info and info.path else f"{device}.hal.yaml"
        confirmed = runtime.file.confirmed if runtime else None
        data.update(limit=limit, requested=requested, file=file_name)
        reason = f"{channel} {requested} exceeds the limit of {limit} ({file_name}"
        if confirmed is not None:
            data.update(confirmedBy=confirmed.by, confirmedAt=str(confirmed.at))
            reason += f", confirmed by {confirmed.by} {confirmed.at}"
        message = reason + ")"
    data["kernelMessage"] = decision.message
    return RpcError(code, name, message, data)


class Connection:
    counter = itertools.count(1)

    def __init__(self, shim: Shim, header_token: str | None, cookie_token: str | None) -> None:
        self.shim = shim
        self.hub = shim.hub
        self.header_token = header_token
        self.cookie_token = cookie_token
        self.client = f"connection {next(self.counter)}"
        self.principal: Principal | None = None
        self.initialized = False
        self.ready = False
        self.outbox: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=1000)

    @property
    def label(self) -> str | None:
        return self.principal.label if self.principal else None

    def send(self, message: dict[str, Any]) -> None:
        with contextlib.suppress(asyncio.QueueFull):
            self.outbox.put_nowait(message)

    def notify(self, method: str, params: dict[str, Any]) -> None:
        if self.ready:
            self.send({"jsonrpc": "2.0", "method": method, "params": params})

    async def receive(self, text: str) -> None:
        try:
            message = json.loads(text)
        except json.JSONDecodeError:
            self.shim.log.record("in", self.client, self.label, text)
            self.send(self.error(None, RpcError(-32700, "PARSE_ERROR", "The message is not valid JSON.")))
            return
        self.shim.log.record("in", self.client, self.label, redact(message))
        if not isinstance(message, dict) or message.get("jsonrpc") != "2.0" or "method" not in message:
            ident = message.get("id") if isinstance(message, dict) else None
            self.send(self.error(ident, RpcError(-32600, "INVALID_REQUEST", "The message is not a JSON-RPC request.")))
            return
        method = message["method"]
        params = message.get("params") or {}
        if "id" not in message:
            self.on_notification(method)
            return
        try:
            result = await self.call(method, params)
        except RpcError as exc:
            self.send(self.error(message["id"], exc))
            return
        self.send({"jsonrpc": "2.0", "id": message["id"], "result": result})

    def error(self, ident: Any, exc: RpcError) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": ident, "error": exc.payload()}

    def on_notification(self, method: str) -> None:
        if method == "hal/initialized" and self.initialized:
            self.ready = True

    async def call(self, method: str, params: dict[str, Any]) -> Any:
        if method == "hal/initialize":
            return self.initialize(params)
        if not self.initialized or self.principal is None:
            raise RpcError(-32001, "NOT_INITIALIZED", "Send hal/initialize first.")
        handler = getattr(self, "m_" + method.removeprefix("hal/").replace("/", "_"), None)
        if handler is None:
            raise RpcError(-32601, "METHOD_NOT_FOUND", f"There is no method {method}.")
        try:
            return await handler(params, self.principal)
        except ValidationError as exc:
            raise RpcError(-32602, "INVALID_PARAMS", str(exc.errors()[0]["msg"])) from exc

    def initialize(self, params: dict[str, Any]) -> dict[str, Any]:
        token = self.header_token or params.get("token") or self.cookie_token
        principal = self.hub.tokens.principal(token)
        if principal is None:
            raise RpcError(-32002, "UNAUTHORIZED", "A valid token is required.")
        self.principal = principal
        self.initialized = True
        info = params.get("clientInfo") or {}
        if isinstance(info, dict) and isinstance(info.get("name"), str):
            self.client = info["name"][:80]
        return {
            "protocolVersion": PROTOCOL_VERSION,
            "hubInfo": {"name": "openhal", "version": "0.1.0"},
            "conformance": "full",
            "principal": {"kind": principal.kind, "name": principal.name, "scope": principal.scope},
            "capabilities": {"notifications": ["hal/value", "hal/blocked", "hal/stopped", "hal/confirmationRequested"]},
        }

    async def m_devices_list(self, params: dict[str, Any], who: Principal) -> dict[str, Any]:
        return {"devices": [self.shim.summary(device_id) for device_id in self.hub.kernel.devices]}

    async def m_read(self, params: dict[str, Any], who: Principal) -> dict[str, Any]:
        device, channel = params.get("device"), params.get("channel")
        if device not in self.hub.kernel.devices:
            raise RpcError(-32004, "UNKNOWN_TARGET", f"There is no device {device}.", {"device": device})
        try:
            reading = await self.hub.kernel.read(str(device), str(channel), who)
        except LookupError as exc:
            raise RpcError(-32004, "UNKNOWN_TARGET", str(exc), {"device": device, "channel": channel}) from exc
        return {
            "device": device,
            "channel": channel,
            "value": reading.value,
            "unit": unit_symbol(reading.unit),
            "at": now_iso(),
            "suspect": reading.suspect,
        }

    async def m_write(self, params: dict[str, Any], who: Principal) -> dict[str, Any]:
        command = Write.model_validate({"kind": "write", **params})
        return self.shim.answer(await self.hub.kernel.execute(command, who), command)

    async def m_action(self, params: dict[str, Any], who: Principal) -> dict[str, Any]:
        command = Action.model_validate({"kind": "action", **params})
        return self.shim.answer(await self.hub.kernel.execute(command, who), command)

    async def m_stop(self, params: dict[str, Any], who: Principal) -> dict[str, Any]:
        reason = str(params.get("reason") or "stop requested")[:200]
        report = await self.hub.kernel.stop_all(who, reason)
        devices = [{"device": item.device, "status": item.status, "detail": item.detail} for item in report.devices]
        self.shim.broadcast(
            "hal/stopped",
            {
                "reason": reason,
                "by": who.label,
                "devices": [{"device": d["device"], "status": d["status"]} for d in devices],
            },
        )
        return {"devices": devices}

    async def m_unlock(self, params: dict[str, Any], who: Principal) -> dict[str, Any]:
        if who.kind != "human":
            raise RpcError(
                -32003, "SCOPE_DENIED", "Only a human can unlock after a stop.", {"kernelCode": "not_permitted"}
            )
        try:
            self.hub.kernel.unlock(who, str(params.get("phrase", "")))
        except ValueError as exc:
            raise RpcError(-32602, "INVALID_PARAMS", str(exc), {"kernelCode": "bad_request"}) from exc
        return {"ok": True}

    async def m_confirmations_list(self, params: dict[str, Any], who: Principal) -> dict[str, Any]:
        requests = self.hub.kernel.pending()
        if who.kind != "human":
            requests = [request for request in requests if request.principal.label == who.label]
        return {"requests": [self.shim.request_view(request) for request in requests]}


def redact(message: Any) -> Any:
    if isinstance(message, dict) and isinstance(message.get("params"), dict) and "token" in message["params"]:
        return {**message, "params": {**message["params"], "token": "[redacted]"}}
    return message


class Shim:
    def __init__(self, hub: Hub) -> None:
        self.hub = hub
        self.log = MessageLog()
        self.connections: set[Connection] = set()
        hub.subscribe(self.on_event)

    def summary(self, device_id: str) -> dict[str, Any]:
        runtime = self.hub.kernel.devices[device_id]
        file = runtime.file
        return {
            "id": device_id,
            "name": file.device.name,
            "model": file.device.model,
            "manufacturer": file.device.manufacturer,
            "driver": file.connect.driver,
            "hazard": file.effective_hazard,
            "writable": file.writable,
            "connected": runtime.connected,
            "conformance": "control",
            "verification": file.provenance.verification.status,
        }

    def request_view(self, request: Any) -> dict[str, Any]:
        return {
            "requestId": request.request_id,
            "status": request.status,
            "command": request.command.model_dump(),
            "requestedBy": request.principal.label,
            "createdAt": now_iso(),
            "expiresAt": now_iso(),
        }

    def answer(self, decision: Decision, command: Write | Action) -> dict[str, Any]:
        if decision.status == "done":
            if isinstance(command, Write):
                return {
                    "status": "done",
                    "device": decision.device,
                    "channel": command.channel,
                    "value": decision.value,
                    "unit": unit_symbol(decision.unit),
                }
            return {"status": "done", "result": decision.value}
        if decision.status == "pending":
            request = self.hub.kernel.queue.get(decision.request_id or "")
            if request is not None:
                self.broadcast("hal/confirmationRequested", {"request": self.request_view(request)})
            expires = round(request.expires_at - self.hub.kernel.clock()) if request else 300
            return {"status": "pending", "requestId": decision.request_id, "expiresInS": expires}
        error = blocked_error(self.hub, decision)
        if decision.status == "failed":
            error = RpcError(-32020, "DRIVER_ERROR", decision.message, {"kernelCode": decision.code or "driver_error"})
        self.broadcast(
            "hal/blocked",
            {
                "device": decision.device,
                "target": decision.target,
                "error": {
                    "code": error.code,
                    "name": error.name,
                    "message": error.message,
                    "data": error.payload()["data"],
                },
            },
        )
        raise error

    def broadcast(self, method: str, params: dict[str, Any]) -> None:
        for connection in list(self.connections):
            connection.notify(method, params)

    def on_event(self, event: dict[str, Any]) -> None:
        if event.get("type") != "reading":
            return
        self.broadcast(
            "hal/value",
            {
                "device": event["device"],
                "channel": event["channel"],
                "value": event["value"],
                "unit": unit_symbol(event.get("unit")),
                "at": now_iso(),
                "suspect": event.get("suspect", False),
            },
        )


def mount(app: FastAPI, hub: Hub) -> Shim:
    shim = Shim(hub)
    app.state.rpc_shim = shim

    @app.get("/v1/rpc/log")
    async def rpc_log(request: Request, since: int = 0) -> dict[str, Any]:
        who = principal_for(request)
        if who.kind != "human":
            raise HTTPException(403, "Only a human can read the message log.")
        return {"entries": shim.log.since(since)}

    @app.websocket("/v1/rpc/log/live")
    async def rpc_log_live(websocket: WebSocket) -> None:
        token = websocket.query_params.get("token") or websocket.cookies.get(SESSION_COOKIE)
        principal = hub.tokens.principal(token)
        if principal is None or principal.kind != "human":
            await websocket.close(code=1008)
            return
        await websocket.accept()
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=LOG_SIZE)

        def push(entry: dict[str, Any]) -> None:
            with contextlib.suppress(asyncio.QueueFull):
                queue.put_nowait(entry)

        unsubscribe = shim.log.subscribe(push)
        try:
            while True:
                await websocket.send_json(await queue.get())
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            unsubscribe()

    @app.websocket("/rpc")
    async def rpc(websocket: WebSocket) -> None:
        auth = websocket.headers.get("authorization", "")
        header_token = auth.removeprefix("Bearer ").strip() if auth.startswith("Bearer ") else None
        connection = Connection(shim, header_token, websocket.cookies.get(SESSION_COOKIE))
        await websocket.accept()
        shim.connections.add(connection)

        async def writer() -> None:
            while True:
                message = await connection.outbox.get()
                shim.log.record("out", connection.client, connection.label, message)
                await websocket.send_text(json.dumps(message))

        sender = asyncio.create_task(writer())
        try:
            while True:
                await connection.receive(await websocket.receive_text())
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            shim.connections.discard(connection)
            sender.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await sender

    return shim
