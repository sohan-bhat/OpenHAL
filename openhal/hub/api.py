"""The local HTTP and WebSocket API, version 1. Every client (MCP, CLI, library, dashboard) uses it.

Security, in order of evaluation for every request.
1. Network. Unless LAN access is on, only loopback clients are served, and the Host header must be
   a loopback name, which stops DNS rebinding from a web page.
2. Identity. A bearer token, or the dashboard session cookie. Unknown tokens get 401.
3. Cookie sessions must send the X-OpenHAL-Request header on every state-changing request, which a
   cross-site form can't do.
4. The kernel decides everything else.
"""

from __future__ import annotations

import asyncio
import contextlib
import ipaddress
from dataclasses import asdict
from pathlib import Path
from typing import Annotated, Any, Literal
from urllib.parse import urlparse

from fastapi import Depends, FastAPI, HTTPException, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from starlette.middleware.gzip import GZipMiddleware

from openhal import __version__
from openhal._brand import PRODUCT_NAME, SPEC_VERSION
from openhal.drivers import registry
from openhal.drivers.base import DriverError
from openhal.hub import discovery, views
from openhal.hub.hub import Hub
from openhal.kernel.checks import Block
from openhal.kernel.commands import Action, Write
from openhal.kernel.principals import Principal
from openhal.protocol import websocket as rpc_transport
from openhal.protocol.dispatch import Dispatcher
from openhal.protocol.version import LATEST
from openhal.routines.engine import RoutineError
from openhal.spec.loader import DeviceFileError
from openhal.spec.models import DeviceFile
from openhal.spec.units import wire_unit
from openhal.writer.engine import NotHumanError, WriterError

SESSION_COOKIE = "openhal_session"
CSRF_HEADER = "x-openhal-request"
STATIC_DIR = Path(__file__).parent / "static"


class WriterStartBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    unknown_id: str | None = Field(default=None, max_length=64)
    driver: str | None = Field(default=None, max_length=64)
    params: dict[str, Any] | None = None
    sketch_path: str | None = Field(default=None, max_length=1024)
    manual_text: str | None = Field(default=None, max_length=400_000)


class ProposeBody(BaseModel):
    draft_yaml: str = Field(max_length=256_000)


class AnswersBody(BaseModel):
    answers: dict[str, Any]


class FinishBody(BaseModel):
    save_as: str | None = Field(default=None, max_length=80)


class TokenBody(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    kind: Literal["human", "agent"] = "agent"
    scope: Literal["read", "control_low", "control_medium"] = "read"


class ReadBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    device: str
    channel: str


class ReadManyBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[ReadBody] = Field(max_length=100)


class DryRunBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    commands: list[Annotated[Write | Action, Field(discriminator="kind")]] = Field(max_length=200)


class QuantityBody(BaseModel):
    """A number and its unit (ADR 0016), for example `{"value": 50, "unit": "%"}`."""

    model_config = ConfigDict(extra="forbid")
    value: float = Field(allow_inf_nan=False)
    unit: str = Field(min_length=1, max_length=40)


class TightenBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    device: str
    channel: str
    min: QuantityBody | None = None
    max: QuantityBody | None = None
    rate: QuantityBody | None = Field(default=None, description="A rate such as 5 %/s.")


class StopBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(default="stop requested", max_length=200)


class UnlockBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    phrase: str = Field(max_length=40)


class RejectBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(default="", max_length=200)


class RoutineBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[a-z][a-z0-9-]{0,47}$")
    kind: Literal["yaml", "python"] = "yaml"
    source: str = Field(max_length=128 * 1024)


class ApproveRoutineBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    device: str


class DiscoverBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    drivers: list[str] | None = None


class PairBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str = Field(min_length=6, max_length=6)


_LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "[::1]", "::1"}


def _is_loopback(host: str | None) -> bool:
    if host is None:
        return False
    if host in ("testclient", "localhost"):
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def principal_for(request: Request) -> Principal:
    """Resolve the caller from a bearer token or the dashboard session cookie."""
    hub: Hub = request.app.state.hub
    auth = request.headers.get("authorization", "")
    token = auth.removeprefix("Bearer ").strip() if auth.startswith("Bearer ") else None
    via_cookie = False
    if token is None:
        token = request.cookies.get(SESSION_COOKIE)
        via_cookie = token is not None
    principal = hub.tokens.principal(token)
    if principal is None:
        raise HTTPException(401, "A valid token is required. Create one with openhal token create.")
    if via_cookie and request.method not in ("GET", "HEAD") and request.headers.get(CSRF_HEADER) != "1":
        raise HTTPException(403, "Dashboard requests must send the X-OpenHAL-Request header.")
    return principal


Who = Annotated[Principal, Depends(principal_for)]


def create_app(hub: Hub) -> FastAPI:
    """Build the API for one hub."""
    app = FastAPI(title=f"{PRODUCT_NAME} hub", version=__version__, docs_url=None, redoc_url=None)
    app.state.hub = hub
    app.add_middleware(GZipMiddleware, minimum_size=1024)

    @app.middleware("http")
    async def network_guard(request: Request, call_next: Any) -> Response:
        if not hub.config.api.allow_lan:
            client = request.client.host if request.client else None
            host_header = (request.headers.get("host") or "").rsplit(":", 1)[0]
            if not _is_loopback(client) or (host_header and host_header not in _LOOPBACK_HOSTS | {"testserver"}):
                return JSONResponse({"detail": "This hub only accepts local connections."}, status_code=403)
        response: Response = await call_next(request)
        immutable = request.url.path.startswith("/assets/") and response.status_code == 200
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable" if immutable else "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        return response

    def human_only(principal: Principal) -> None:
        if principal.kind != "human":
            raise HTTPException(403, "Only a human can do this.")

    def device_or_404(device_id: str) -> None:
        if device_id not in hub.kernel.devices:
            raise HTTPException(404, f"There is no device {device_id!r}.")

    @app.get("/v1/status")
    async def status(who: Who) -> dict[str, Any]:
        kernel = hub.kernel
        return {
            "product": PRODUCT_NAME,
            "version": __version__,
            "spec": SPEC_VERSION,
            "protocol_version": LATEST,
            "conformance": rpc.level,
            "allow_lan": hub.config.api.allow_lan,
            "stopped": kernel.stopped,
            "stop_reason": kernel.stop_reason,
            "devices": len(kernel.devices),
            "connected": sum(runtime.connected for runtime in kernel.devices.values()),
            "pending_confirmations": len(kernel.pending()),
            "started_at": hub.started_at,
            "load_problems": [{"path": item.path, "problems": item.problems} for item in hub.load_problems],
            "you": {"kind": who.kind, "name": who.name, "scope": who.scope},
        }

    @app.get("/v1/devices")
    async def devices(who: Who) -> list[dict[str, Any]]:
        return [views.device_summary(hub, device_id) for device_id in hub.kernel.devices]

    @app.get("/v1/devices/{device_id}")
    async def device(device_id: str, who: Who) -> dict[str, Any]:
        device_or_404(device_id)
        return views.device_view(hub, device_id)

    @app.post("/v1/read")
    async def read(body: ReadBody, who: Who) -> dict[str, Any]:
        return await _read(body, who)

    async def _read(body: ReadBody, who: Principal) -> dict[str, Any]:
        device_or_404(body.device)
        try:
            reading = await hub.kernel.read(body.device, body.channel, who)
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc
        except (DriverError, TimeoutError, OSError) as exc:
            error = views.device_text(f"{body.device}.{body.channel} driver error", str(exc)) or "timed out"
            return {"device": body.device, "channel": body.channel, "ok": False, "error": error}
        file = hub.kernel.devices[body.device].file
        value = views.device_value(file, body.device, body.channel, reading.value)
        return {
            "device": body.device,
            "channel": body.channel,
            "ok": True,
            "value": value,
            "unit": wire_unit(reading.unit),
            "at": reading.at,
            "suspect": reading.suspect,
            "bytes": len(reading.value) if isinstance(reading.value, bytes) else None,
        }

    @app.post("/v1/read_many")
    async def read_many(body: ReadManyBody, who: Who) -> list[dict[str, Any]]:
        return [await _read(item, who) for item in body.items]

    def file_of(device: str) -> DeviceFile | None:
        runtime = hub.kernel.devices.get(device)
        return runtime.file if runtime is not None else None

    @app.post("/v1/write")
    async def write(command: Write, who: Who) -> dict[str, Any]:
        return views.decision_view(await hub.kernel.execute(command, who, wire=True))

    @app.post("/v1/action")
    async def action(command: Action, who: Who) -> dict[str, Any]:
        decision = await hub.kernel.execute(command, who, wire=True)
        return views.decision_view(decision, file_of(decision.device))

    @app.post("/v1/dry_run")
    async def dry_run(body: DryRunBody, who: Who) -> list[dict[str, Any]]:
        decisions = hub.kernel.dry_run(body.commands, who, wire=True)
        return [views.decision_view(decision, file_of(decision.device)) for decision in decisions]

    @app.post("/v1/tighten")
    async def tighten(body: TightenBody, who: Who) -> dict[str, Any]:
        device_or_404(body.device)
        try:
            low, high, rate = (
                item.model_dump() if item is not None else None for item in (body.min, body.max, body.rate)
            )
            limits = hub.kernel.tighten(who, body.device, body.channel, min=low, max=high, rate=rate)
        except Block as block:
            return {"ok": False, "code": block.code, "message": block.message}
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc
        return {"ok": True, "limits": limits}

    @app.post("/v1/stop")
    async def stop(body: StopBody, who: Who) -> dict[str, Any]:
        return views.stop_view(await hub.kernel.stop_all(who, body.reason))

    @app.post("/v1/unlock")
    async def unlock(body: UnlockBody, who: Who) -> dict[str, Any]:
        human_only(who)
        try:
            hub.kernel.unlock(who, body.phrase)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        return {"ok": True, "stopped": hub.kernel.stopped}

    @app.get("/v1/confirmations")
    async def confirmations(who: Who, include_done: bool = False) -> list[dict[str, Any]]:
        requests = hub.kernel.queue.recent(100) if include_done else hub.kernel.pending()
        if who.kind != "human":
            requests = [request for request in requests if request.principal.label == who.label]
        return [views.request_view(request, hub.kernel.clock()) for request in requests]

    @app.get("/v1/confirmations/{request_id}")
    async def confirmation(request_id: str, who: Who) -> dict[str, Any]:
        request = hub.kernel.queue.get(request_id)
        if request is None or (who.kind != "human" and request.principal.label != who.label):
            raise HTTPException(404, f"There is no request {request_id}.")
        hub.kernel.queue.expire(hub.kernel.clock())
        return views.request_view(request, hub.kernel.clock())

    @app.post("/v1/confirmations/{request_id}/approve")
    async def approve(request_id: str, who: Who) -> dict[str, Any]:
        human_only(who)
        try:
            return views.decision_view(await hub.kernel.confirm(request_id, who))
        except LookupError as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.post("/v1/confirmations/{request_id}/reject")
    async def reject(request_id: str, body: RejectBody, who: Who) -> dict[str, Any]:
        human_only(who)
        try:
            return views.request_view(hub.kernel.reject(request_id, who, body.reason), hub.kernel.clock())
        except LookupError as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.get("/v1/audit")
    async def audit(
        who: Who,
        device: str | None = None,
        status: str | None = None,
        event: str | None = None,
        since: int = 0,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        entries = hub.audit.entries(device=device, status=status, event=event, since_seq=since, limit=limit)
        return [
            {
                "seq": entry.seq,
                "at": entry.at,
                "event": entry.event,
                "principal": entry.principal,
                "device": entry.device,
                "target": entry.target,
                "status": entry.status,
                "code": entry.code,
                "details": views.audit_details(entry.device, entry.body.get("details", {})),
                "hash": entry.hash,
            }
            for entry in entries
        ]

    @app.get("/v1/audit/verify")
    async def audit_verify(who: Who) -> dict[str, Any]:
        ok, broken = hub.audit.verify()
        return {"ok": ok, "broken_at": broken, "head": hub.audit.head}

    @app.get("/v1/drivers")
    async def drivers(who: Who) -> list[dict[str, Any]]:
        found = []
        for name in registry.names():
            try:
                info = registry.load(name).info
            except registry.UnknownDriver as exc:
                found.append({"name": name, "installed": False, "detail": str(exc)})
                continue
            found.append(
                {
                    "name": info.name,
                    "installed": True,
                    "protocols": list(info.protocols),
                    "hazard_default": info.hazard_default,
                    "summary": info.summary,
                    "safe_state_support": info.safe_state_support,
                }
            )
        return found

    def routine_or_404(routine_id: str) -> Any:
        try:
            return hub.routines.get(routine_id)
        except KeyError as exc:
            raise HTTPException(404, f"There is no routine {routine_id!r}.") from exc

    @app.get("/v1/routines")
    async def routines(who: Who) -> list[dict[str, Any]]:
        return [hub.routines.summary(record) for record in hub.routines.records.values()]

    @app.get("/v1/routines/{routine_id}")
    async def routine_detail(routine_id: str, who: Who) -> dict[str, Any]:
        return hub.routines.detail(routine_or_404(routine_id))

    @app.post("/v1/routines")
    async def routine_create(body: RoutineBody, who: Who) -> dict[str, Any]:
        try:
            record = hub.routines.create(who, body.id, body.kind, body.source)
        except RoutineError as exc:
            raise HTTPException(400, str(exc)) from exc
        return hub.routines.detail(record)

    @app.post("/v1/routines/{routine_id}/dry_run")
    async def routine_dry_run(routine_id: str, who: Who) -> dict[str, Any]:
        routine_or_404(routine_id)
        return hub.routines.dry_run(routine_id)

    @app.post("/v1/routines/{routine_id}/enable")
    async def routine_enable(routine_id: str, who: Who) -> dict[str, Any]:
        routine_or_404(routine_id)
        try:
            return hub.routines.detail(hub.routines.enable(who, routine_id))
        except RoutineError as exc:
            raise HTTPException(403, str(exc)) from exc

    @app.post("/v1/routines/{routine_id}/disable")
    async def routine_disable(routine_id: str, who: Who) -> dict[str, Any]:
        routine_or_404(routine_id)
        if who.kind == "agent" and who.scope == "read":
            raise HTTPException(403, "A read-only token can't disable routines.")
        return hub.routines.detail(hub.routines.disable(who, routine_id, f"disabled by {who.label}"))

    @app.post("/v1/routines/{routine_id}/run")
    async def routine_run(routine_id: str, who: Who) -> dict[str, Any]:
        routine_or_404(routine_id)
        human_only(who)
        try:
            return (await hub.routines.run(routine_id, "manual", by=who)).view()
        except RoutineError as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.delete("/v1/routines/{routine_id}")
    async def routine_delete(routine_id: str, who: Who) -> dict[str, Any]:
        routine_or_404(routine_id)
        human_only(who)
        hub.routines.delete(who, routine_id)
        return {"ok": True}

    @app.post("/v1/routines/{routine_id}/approve")
    async def routine_approve(routine_id: str, body: ApproveRoutineBody, who: Who) -> dict[str, Any]:
        record = routine_or_404(routine_id)
        human_only(who)
        device_or_404(body.device)
        approval = hub.kernel.approve_routine(who, body.device, routine_id, record.sha256)
        hub.add_approval(body.device, approval)
        return approval.model_dump(mode="json")

    @app.post("/v1/discover")
    async def run_discovery(body: DiscoverBody, who: Who) -> dict[str, Any]:
        result = await discovery.discover(body.drivers, registered=set(hub.kernel.devices))
        hub.last_discovery = result
        return result.view()

    @app.get("/v1/discover/unknown")
    async def unknown_devices(who: Who) -> list[dict[str, Any]]:
        if hub.last_discovery is None:
            return []
        unknown: list[dict[str, Any]] = hub.last_discovery.view()["unknown"]
        return unknown

    @app.post("/v1/pair/code")
    async def pair_code(who: Who) -> dict[str, Any]:
        human_only(who)
        return {"code": hub.tokens.new_pairing_code(), "expires_in_s": 300}

    def session_or_404(session_id: str) -> Any:
        try:
            return hub.writer.get(session_id)
        except KeyError as exc:
            raise HTTPException(404, str(exc)) from exc

    def writer_errors(exc: Exception) -> HTTPException:
        if isinstance(exc, NotHumanError):
            return HTTPException(403, str(exc))
        if isinstance(exc, FileExistsError):
            return HTTPException(409, str(exc))
        return HTTPException(400, str(exc))

    @app.post("/v1/writer/sessions")
    async def writer_start(body: WriterStartBody, who: Who) -> dict[str, Any]:
        if who.kind == "agent" and who.scope == "read":
            raise HTTPException(403, "Starting the driver writer needs a control scope.")
        try:
            session = await hub.writer.start(who, **body.model_dump())
        except (WriterError, ValueError, OSError) as exc:
            raise writer_errors(exc) from exc
        return hub.writer.view(session)

    @app.get("/v1/writer/sessions/{session_id}")
    async def writer_get(session_id: str, who: Who) -> dict[str, Any]:
        return hub.writer.view(session_or_404(session_id))

    @app.post("/v1/writer/sessions/{session_id}/propose")
    async def writer_propose(session_id: str, body: ProposeBody, who: Who) -> dict[str, Any]:
        session_or_404(session_id)
        try:
            return hub.writer.view(hub.writer.propose(who, session_id, body.draft_yaml))
        except WriterError as exc:
            raise writer_errors(exc) from exc

    @app.get("/v1/writer/sessions/{session_id}/interview")
    async def writer_interview(session_id: str, who: Who) -> dict[str, Any]:
        session_or_404(session_id)
        return {"questions": [question.view() for question in hub.writer.questions(session_id)]}

    @app.post("/v1/writer/sessions/{session_id}/answers")
    async def writer_answers(session_id: str, body: AnswersBody, who: Who) -> dict[str, Any]:
        session_or_404(session_id)
        try:
            return hub.writer.view(hub.writer.answer(who, session_id, body.answers))
        except (WriterError, NotHumanError) as exc:
            raise writer_errors(exc) from exc

    @app.post("/v1/writer/sessions/{session_id}/finish")
    async def writer_finish(session_id: str, body: FinishBody, who: Who) -> dict[str, Any]:
        session_or_404(session_id)
        try:
            return await hub.writer.finish(who, session_id, body.save_as)
        except (WriterError, NotHumanError, FileExistsError, DeviceFileError) as exc:
            raise writer_errors(exc) from exc

    @app.get("/v1/writer/sessions/{session_id}/test_plan")
    async def writer_test_plan(session_id: str, who: Who) -> dict[str, Any]:
        session_or_404(session_id)
        try:
            return await hub.writer.test_plan(session_id)
        except WriterError as exc:
            raise writer_errors(exc) from exc

    @app.post("/v1/tokens")
    async def create_token(body: TokenBody, who: Who) -> dict[str, Any]:
        human_only(who)
        token, info = hub.tokens.create(body.name, body.kind, body.scope)
        hub.audit.append("token_created", who.label, target=info.token_id, kind=info.kind, scope=info.scope)
        return {"token": token, **asdict(info)}

    @app.get("/v1/tokens")
    async def list_tokens(who: Who) -> list[dict[str, Any]]:
        human_only(who)
        return [asdict(info) for info in hub.tokens.list()]

    @app.delete("/v1/tokens/{token_id}")
    async def revoke_token(token_id: str, who: Who) -> dict[str, Any]:
        human_only(who)
        if not hub.tokens.revoke(token_id):
            raise HTTPException(404, f"There is no active token {token_id!r}.")
        hub.audit.append("token_revoked", who.label, target=token_id)
        return {"ok": True}

    @app.get("/v1/whoami")
    async def whoami(who: Who) -> dict[str, Any]:
        return {"kind": who.kind, "name": who.name, "scope": who.scope}

    @app.post("/v1/pair")
    async def pair(body: PairBody, response: Response) -> dict[str, Any]:
        token = hub.tokens.exchange_pairing_code(body.code)
        if token is None:
            raise HTTPException(403, "That pairing code is wrong or expired. Run openhal pair again.")
        response.set_cookie(SESSION_COOKIE, token, httponly=True, samesite="strict", secure=False, max_age=30 * 86400)
        return {"ok": True}

    @app.websocket("/v1/live")
    async def live(websocket: WebSocket) -> None:
        if not hub.config.api.allow_lan and not _is_loopback(websocket.client.host if websocket.client else None):
            await websocket.close(code=1008)
            return
        token = websocket.query_params.get("token") or websocket.cookies.get(SESSION_COOKIE)
        principal = hub.tokens.principal(token)
        if principal is None:
            await websocket.close(code=1008)
            return
        await websocket.accept()
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=1000)

        def push(event: dict[str, Any]) -> None:
            with contextlib.suppress(asyncio.QueueFull):
                queue.put_nowait(event)

        unsubscribe = hub.subscribe(push)
        try:
            await websocket.send_json({"type": "hello", "you": {"kind": principal.kind, "name": principal.name}})
            while True:
                event = await queue.get()
                await websocket.send_json(event)
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            unsubscribe()

    rpc = Dispatcher.for_hub(hub)

    def socket_allowed(websocket: WebSocket) -> bool:
        """The REST network guard for WebSockets, plus a loopback Origin so a web page can't connect."""
        if hub.config.api.allow_lan:
            return True
        client = websocket.client.host if websocket.client else None
        host_header = (websocket.headers.get("host") or "").rsplit(":", 1)[0]
        if not _is_loopback(client) or (host_header and host_header not in _LOOPBACK_HOSTS | {"testserver"}):
            return False
        origin = websocket.headers.get("origin")
        if origin:
            name = urlparse(origin).hostname or ""
            return _is_loopback(name) or name == "testserver"
        return True

    def socket_principals(websocket: WebSocket) -> tuple[Principal | None, bool, Principal | None]:
        """The header principal, whether a header token was refused, and the session cookie's principal."""
        auth = websocket.headers.get("authorization", "")
        token = auth.removeprefix("Bearer ").strip() if auth.startswith("Bearer ") else None
        principal = hub.tokens.principal(token) if token else None
        cookie = websocket.cookies.get(SESSION_COOKIE)
        fallback = hub.tokens.principal(cookie) if cookie else None
        return principal, token is not None and principal is None, fallback

    @app.websocket("/rpc")
    async def rpc_socket(websocket: WebSocket) -> None:
        if not socket_allowed(websocket):
            await websocket.close(code=1008)
            return
        principal, rejected, fallback = socket_principals(websocket)
        await rpc_transport.serve_rpc(websocket, rpc, principal=principal, token_rejected=rejected, fallback=fallback)

    @app.get("/v1/rpc/log")
    async def rpc_log(who: Who, since: int = 0) -> list[dict[str, Any]]:
        human_only(who)
        return rpc.log.since(since)

    @app.websocket("/v1/rpc/log/live")
    async def rpc_log_live(websocket: WebSocket) -> None:
        if not socket_allowed(websocket):
            await websocket.close(code=1008)
            return
        principal, _, fallback = socket_principals(websocket)
        token = websocket.query_params.get("token")
        who = principal or (hub.tokens.principal(token) if token else None) or fallback
        if who is None or who.kind != "human":
            await websocket.close(code=1008)
            return
        try:
            since = int(websocket.query_params.get("since", "0"))
        except ValueError:
            since = 0
        await rpc_transport.serve_log(websocket, rpc, since)

    if STATIC_DIR.exists():

        @app.get("/", include_in_schema=False)
        async def dashboard_index() -> FileResponse:
            return FileResponse(STATIC_DIR / "index.html")

        @app.get("/assets/{name:path}", include_in_schema=False)
        async def dashboard_asset(name: str) -> FileResponse:
            path = (STATIC_DIR / "assets" / name).resolve()
            if not path.is_relative_to((STATIC_DIR / "assets").resolve()) or not path.is_file():
                raise HTTPException(404)
            return FileResponse(path)

    return app


ScopeName = Literal["read", "control_low", "control_medium"]
