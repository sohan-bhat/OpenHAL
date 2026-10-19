"""The asyncio client. `await openhal.client.aconnect()` returns one."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Awaitable, Callable, Iterable, Mapping
from pathlib import Path
from types import TracebackType
from typing import Any
from urllib.parse import urlencode

import httpx

from openhal.client import calls
from openhal.client import models as m
from openhal.client.calls import Call, Command, Value, split_target
from openhal.client.errors import HubError, HubNotRunning, Unauthorized
from openhal.client.ramp import plan_ramp
from openhal.client.settings import TokenSource, resolve_token, resolve_url
from openhal.client.transport import START_HINT, finish, headers_for, transport_error


class AsyncClient:
    """An asyncio client of the hub's local API v1.

    The client makes no safety decisions. Every write and action is decided by the hub's kernel,
    and a blocked command comes back as a `Decision` with status `blocked`, not an exception.
    """

    def __init__(
        self,
        url: str | None = None,
        token: str | None = None,
        *,
        home: Path | str | None = None,
        timeout: float = 15.0,
        transport: httpx.AsyncBaseTransport | None = None,
        use_human_token_file: bool = True,
    ) -> None:
        self.url = resolve_url(url, home=home)
        self.token_source: TokenSource = resolve_token(token, home=home, use_human_file=use_human_token_file)
        self._http = httpx.AsyncClient(
            base_url=self.url,
            headers=headers_for(self.token_source),
            timeout=timeout,
            transport=transport,
            trust_env=False,
        )

    # ------------------------------------------------------------------ plumbing

    async def __aenter__(self) -> AsyncClient:
        return self

    async def __aexit__(
        self, kind: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None
    ) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._http.aclose()

    async def call[T](self, call: Call[T]) -> T:
        """Send one call and parse the answer. Raises a subclass of `OpenHALError` on failure."""
        try:
            response = await self._http.request(call.method, call.path, json=call.json, params=call.params)
        except httpx.TransportError as exc:
            raise transport_error(self.url, exc) from exc
        return finish(call, response, self.token_source)

    # ------------------------------------------------------------------ hub

    async def status(self) -> m.HubStatus:
        return await self.call(calls.status())

    async def whoami(self) -> m.Principal:
        return await self.call(calls.whoami())

    async def devices(self) -> list[m.DeviceSummary]:
        return await self.call(calls.devices())

    async def device(self, device_id: str) -> m.DeviceView:
        return await self.call(calls.device(device_id))

    async def read(self, device: str, channel: str | None = None) -> m.Reading:
        """Read one channel. `read("desk-fan", "temperature")` or `read("desk-fan.temperature")`."""
        if channel is None:
            device, channel = split_target(device)
        return await self.call(calls.read(device, channel))

    async def read_many(self, items: Iterable[str | tuple[str, str]]) -> list[m.Reading]:
        pairs = [split_target(item) if isinstance(item, str) else item for item in items]
        return await self.call(calls.read_many(pairs))

    async def write(self, device: str, channel: str, value: Value) -> m.Decision:
        """Ask the kernel to set a channel. Numbers need a unit, for example `"60 %"`."""
        return await self.call(calls.write(device, channel, value))

    async def action(
        self, device: str, action: str, args: Mapping[str, Any] | None = None, **kwargs: Any
    ) -> m.Decision:
        return await self.call(calls.action(device, action, {**(args or {}), **kwargs}))

    async def dry_run(self, commands: Iterable[Command]) -> list[m.Decision]:
        """Evaluate commands in order without running them. Nothing reaches a driver."""
        return await self.call(calls.dry_run(commands))

    async def tighten(
        self, device: str, channel: str, *, min: str | None = None, max: str | None = None, rate: str | None = None
    ) -> m.TightenResult:
        """Narrow limits for this token's session. Widening is refused with `cannot_loosen`."""
        return await self.call(calls.tighten(device, channel, min=min, max=max, rate=rate))

    async def stop(self, reason: str = "stop requested") -> m.StopReport:
        """Put every device in its safe state and lock writes until a human unlocks."""
        return await self.call(calls.stop(reason))

    async def unlock(self, phrase: str) -> m.UnlockResult:
        """Lift the stop lock. Needs a human token and the phrase `unlock`."""
        return await self.call(calls.unlock(phrase))

    async def confirmations(self, *, include_done: bool = False) -> list[m.ConfirmationRequest]:
        return await self.call(calls.confirmations(include_done))

    async def confirmation(self, request_id: str) -> m.ConfirmationRequest:
        return await self.call(calls.confirmation(request_id))

    async def approve(self, request_id: str) -> m.Decision:
        """Approve a queued request. Needs a human token. The kernel checks it again first."""
        return await self.call(calls.approve(request_id))

    async def reject(self, request_id: str, reason: str = "") -> m.ConfirmationRequest:
        return await self.call(calls.reject(request_id, reason))

    async def audit(
        self,
        *,
        device: str | None = None,
        status: str | None = None,
        event: str | None = None,
        since: int = 0,
        limit: int = 200,
    ) -> list[m.AuditEntry]:
        return await self.call(calls.audit(device=device, status=status, event=event, since=since, limit=limit))

    async def verify_audit(self) -> m.AuditVerify:
        return await self.call(calls.verify_audit())

    async def drivers(self) -> list[m.DriverInfo]:
        return await self.call(calls.drivers())

    async def pair(self, code: str) -> m.OkResult:
        return await self.call(calls.pair(code))

    async def ramp_to(
        self,
        device: str,
        channel: str,
        target: str,
        *,
        interval_s: float = 1.0,
        margin: float = 0.9,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> list[m.Decision]:
        """Move a channel to `target` in steps that each pass its rate limit.

        Waits `interval_s` before each step, so the first step is safe even right after another write.
        Stops at the first step the kernel does not accept and returns every decision so far.
        """
        plan = plan_ramp(await self.device(device), channel, target, interval_s=interval_s, margin=margin)
        decisions: list[m.Decision] = []
        for value in plan.values:
            await sleep(plan.interval_s)
            decision = await self.write(device, channel, value)
            decisions.append(decision)
            if not decision.ok:
                break
        return decisions

    # ------------------------------------------------------------------ discovery

    async def discover(self, drivers: Iterable[str] | None = None) -> m.DiscoveryResult:
        return await self.call(calls.discover(drivers))

    async def unknown_devices(self) -> list[m.Unknown]:
        return await self.call(calls.unknown_devices())

    # ------------------------------------------------------------------ routines

    async def routines(self) -> list[m.RoutineSummary]:
        return await self.call(calls.routines())

    async def routine(self, routine_id: str) -> m.Routine:
        return await self.call(calls.routine(routine_id))

    async def create_routine(self, routine_id: str, source: str, *, kind: str = "yaml") -> m.Routine:
        """Store a routine. It always starts disabled."""
        return await self.call(calls.create_routine(routine_id, source, kind))

    async def routine_dry_run(self, routine_id: str) -> m.RoutineDryRun:
        return await self.call(calls.routine_dry_run(routine_id))

    async def enable_routine(self, routine_id: str) -> m.Routine:
        return await self.call(calls.enable_routine(routine_id))

    async def disable_routine(self, routine_id: str) -> m.Routine:
        return await self.call(calls.disable_routine(routine_id))

    async def run_routine(self, routine_id: str) -> m.Run:
        return await self.call(calls.run_routine(routine_id))

    async def delete_routine(self, routine_id: str) -> m.OkResult:
        return await self.call(calls.delete_routine(routine_id))

    async def approve_routine(self, routine_id: str, device: str) -> m.Approval:
        return await self.call(calls.approve_routine(routine_id, device))

    # ------------------------------------------------------------------ driver writer

    async def start_writer(
        self,
        *,
        unknown_id: str | None = None,
        driver: str | None = None,
        params: Mapping[str, Any] | None = None,
        sketch_path: str | None = None,
        manual_text: str | None = None,
    ) -> m.WriterSession:
        return await self.call(
            calls.start_writer(
                unknown_id=unknown_id, driver=driver, params=params, sketch_path=sketch_path, manual_text=manual_text
            )
        )

    async def writer_session(self, session_id: str) -> m.WriterSession:
        return await self.call(calls.writer_session(session_id))

    async def propose(self, session_id: str, draft_yaml: str) -> m.WriterSession:
        """Store a draft device file. The hub marks every limit in it as suggested."""
        return await self.call(calls.propose(session_id, draft_yaml))

    async def interview(self, session_id: str) -> m.Interview:
        return await self.call(calls.interview(session_id))

    async def answer(self, session_id: str, answers: Mapping[str, Any]) -> m.WriterSession:
        """Answer limits interview questions. Needs a human token."""
        return await self.call(calls.answer(session_id, answers))

    async def finish(self, session_id: str, save_as: str | None = None) -> m.FinishResult:
        return await self.call(calls.finish(session_id, save_as))

    async def test_plan(self, session_id: str) -> m.TestPlan:
        return await self.call(calls.test_plan(session_id))

    # ------------------------------------------------------------------ tokens and pairing

    async def tokens(self) -> list[m.TokenInfo]:
        return await self.call(calls.tokens())

    async def create_token(self, name: str, *, kind: str = "agent", scope: str = "read") -> m.NewToken:
        return await self.call(calls.create_token(name, kind, scope))

    async def revoke_token(self, token_id: str) -> m.OkResult:
        return await self.call(calls.revoke_token(token_id))

    async def new_pairing_code(self) -> m.PairingCode:
        return await self.call(calls.new_pairing_code())

    # ------------------------------------------------------------------ live events

    async def events(self) -> AsyncIterator[dict[str, Any]]:
        """Yield live events (`hello`, `reading`, `state`, `audit`, `watchdog`) from `/v1/live`.

        Needs the `websockets` package, which the `hub` extra installs.
        """
        try:
            from websockets.asyncio.client import connect as ws_connect
            from websockets.exceptions import WebSocketException
        except ImportError as exc:  # pragma: no cover (installed with the hub extra)
            raise HubError("Live events need the websockets package. Install openhal-hub[hub].") from exc
        if not self.token_source.token:
            raise Unauthorized(f"Live events need a token ({self.token_source.describe()}).")
        base = "ws" + self.url.removeprefix("http")
        address = f"{base}/v1/live?{urlencode({'token': self.token_source.token})}"
        try:
            async with ws_connect(address, proxy=None, open_timeout=10) as socket:
                async for message in socket:
                    event = json.loads(message)
                    if isinstance(event, dict):
                        yield event
        except OSError as exc:
            raise HubNotRunning(f"The hub is not running at {self.url}. {START_HINT}") from exc
        except WebSocketException as exc:
            raise Unauthorized(f"The hub closed the live connection ({exc}). Check the token.") from exc


async def aconnect(
    url: str | None = None,
    token: str | None = None,
    *,
    home: Path | str | None = None,
    timeout: float = 15.0,  # noqa: ASYNC109 (the HTTP timeout handed to httpx)
    transport: httpx.AsyncBaseTransport | None = None,
    check: bool = True,
) -> AsyncClient:
    """Connect to the hub. With `check`, asks the hub who we are so a bad address or token fails now."""
    client = AsyncClient(url, token, home=home, timeout=timeout, transport=transport)
    if check:
        try:
            await client.whoami()
        except BaseException:
            await client.aclose()
            raise
    return client
