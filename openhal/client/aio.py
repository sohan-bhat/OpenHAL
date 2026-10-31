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

    The client makes no safety decisions. Every write and action is checked by the hub's kernel,
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

    async def __aenter__(self) -> AsyncClient:
        return self

    async def __aexit__(
        self, kind: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None
    ) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        """Close the connection to the hub."""
        await self._http.aclose()

    async def call[T](self, call: Call[T]) -> T:
        """Send one call and parse the response. Raises a subclass of `OpenHALError` on failure."""
        try:
            response = await self._http.request(call.method, call.path, json=call.json, params=call.params)
        except httpx.TransportError as exc:
            raise transport_error(self.url, exc) from exc
        return finish(call, response, self.token_source)

    async def status(self) -> m.HubStatus:
        """The hub's version, protocol version, conformance level and whether a stop is in force."""
        return await self.call(calls.status())

    async def whoami(self) -> m.Principal:
        """The Principal the hub maps this token to, a human or an agent with its scope."""
        return await self.call(calls.whoami())

    async def devices(self) -> list[m.DeviceSummary]:
        """Every device registered with the hub, with its driver, its hazard level and whether the device takes
        commands."""
        return await self.call(calls.devices())

    async def device(self, device_id: str) -> m.DeviceView:
        """One device with its channels, actions, limits, interlocks and safe state."""
        return await self.call(calls.device(device_id))

    async def read(self, device: str, channel: str | None = None) -> m.Reading:
        """Read one channel. `read("printer", "bed_temp")` or `read("printer.bed_temp")`."""
        if channel is None:
            device, channel = split_target(device)
        return await self.call(calls.read(device, channel))

    async def read_many(self, items: Iterable[str | tuple[str, str]]) -> list[m.Reading]:
        """Read several channels in one request, each as `"device.channel"` or a `(device, channel)` pair."""
        pairs = [split_target(item) if isinstance(item, str) else item for item in items]
        return await self.call(calls.read_many(pairs))

    async def write(self, device: str, channel: str, value: Value, unit: str | None = None) -> m.Decision:
        """Send a request to set a channel. A number needs its unit, as `write("printer", "bed_target", 70, "degC")`."""
        return await self.call(calls.write(device, channel, value, unit))

    async def action(
        self, device: str, action: str, args: Mapping[str, Any] | None = None, **kwargs: Any
    ) -> m.Decision:
        """Send a request to run an action, with its arguments in `args` or as keywords.

        `action("printer", "pause")` takes none. A number argument goes with its unit, as
        `duration={"value": 20, "unit": "s"}`.
        """
        return await self.call(calls.action(device, action, {**(args or {}), **kwargs}))

    async def dry_run(self, commands: Iterable[Command]) -> list[m.Decision]:
        """Evaluate commands in order as a dry run. No command reaches a driver."""
        return await self.call(calls.dry_run(commands))

    async def tighten(
        self,
        device: str,
        channel: str,
        *,
        min: Mapping[str, Any] | None = None,
        max: Mapping[str, Any] | None = None,
        rate: Mapping[str, Any] | None = None,
    ) -> m.TightenResult:
        """Narrow limits for this token's session. Widening is blocked with `cannot_loosen`."""
        return await self.call(calls.tighten(device, channel, min=min, max=max, rate=rate))

    async def stop(self, reason: str = "stop requested") -> m.StopReport:
        """Put every device in its safe state and lock writes until a human unlocks."""
        return await self.call(calls.stop(reason))

    async def unlock(self, phrase: str) -> m.UnlockResult:
        """Lift the stop lock. Needs a human token and the phrase `unlock`."""
        return await self.call(calls.unlock(phrase))

    async def confirmations(self, *, include_done: bool = False) -> list[m.ConfirmationRequest]:
        """Requests held for a person. `include_done` adds the requests already decided or expired."""
        return await self.call(calls.confirmations(include_done))

    async def confirmation(self, request_id: str) -> m.ConfirmationRequest:
        """One confirmation request with its command, its dry run and, once decided, its result."""
        return await self.call(calls.confirmation(request_id))

    async def approve(self, request_id: str) -> m.Decision:
        """Approve a queued request with a human token. The kernel runs every check again first."""
        return await self.call(calls.approve(request_id))

    async def reject(self, request_id: str, reason: str = "") -> m.ConfirmationRequest:
        """Turn down a queued request, with an optional reason. Needs a human token."""
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
        """Audit log entries after `since`, newest first, filtered by device, status or event."""
        return await self.call(calls.audit(device=device, status=status, event=event, since=since, limit=limit))

    async def verify_audit(self) -> m.AuditVerify:
        """Check the audit log's hash chain. `broken_at` names the first entry that does not match."""
        return await self.call(calls.verify_audit())

    async def drivers(self) -> list[m.DriverInfo]:
        """The drivers the hub has, with each driver's protocols and whether the driver is installed."""
        return await self.call(calls.drivers())

    async def pair(self, code: str) -> m.OkResult:
        """Trade a pairing code from `openhal pair` for a human session on this client."""
        return await self.call(calls.pair(code))

    async def ramp_to(
        self,
        device: str,
        channel: str,
        target: float | Mapping[str, Any] | str,
        unit: str | None = None,
        *,
        interval_s: float = 1.0,
        margin: float = 0.9,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> list[m.Decision]:
        """Move a channel to `target` in `unit` in steps that each pass its rate limit.

        Waits `interval_s` before each step, so the first step is safe even right after another write.
        Stops at the first step the kernel does not accept and returns every decision so far.
        """
        plan = plan_ramp(await self.device(device), channel, target, unit, interval_s=interval_s, margin=margin)
        decisions: list[m.Decision] = []
        for value in plan.values:
            await sleep(plan.interval_s)
            decision = await self.write(device, channel, value, plan.unit)
            decisions.append(decision)
            if not decision.ok:
                break
        return decisions

    async def discover(self, drivers: Iterable[str] | None = None) -> m.DiscoveryResult:
        """Search for devices with every driver, or only the named ones. Devices no file matches come back unknown."""
        return await self.call(calls.discover(drivers))

    async def unknown_devices(self) -> list[m.Unknown]:
        """Devices discovery found that no device file matches yet."""
        return await self.call(calls.unknown_devices())

    async def routines(self) -> list[m.RoutineSummary]:
        """Every stored routine with its devices, its triggers and whether the routine is enabled."""
        return await self.call(calls.routines())

    async def routine(self, routine_id: str) -> m.Routine:
        """One routine with its source and who drafted and enabled the routine."""
        return await self.call(calls.routine(routine_id))

    async def create_routine(self, routine_id: str, source: str, *, kind: str = "yaml") -> m.Routine:
        """Store a routine. Every new routine starts disabled."""
        return await self.call(calls.create_routine(routine_id, source, kind))

    async def routine_dry_run(self, routine_id: str) -> m.RoutineDryRun:
        """Evaluate every step of a routine against the kernel without running the routine."""
        return await self.call(calls.routine_dry_run(routine_id))

    async def enable_routine(self, routine_id: str) -> m.Routine:
        """Turn a routine on. Needs a human token, or an agent under ADR 0007's opt in."""
        return await self.call(calls.enable_routine(routine_id))

    async def disable_routine(self, routine_id: str) -> m.Routine:
        """Turn a routine off. Every token may turn a routine off except a read scoped agent's token."""
        return await self.call(calls.disable_routine(routine_id))

    async def run_routine(self, routine_id: str) -> m.Run:
        """Run a routine once now. Needs a human token."""
        return await self.call(calls.run_routine(routine_id))

    async def delete_routine(self, routine_id: str) -> m.OkResult:
        """Delete a routine. Needs a human token."""
        return await self.call(calls.delete_routine(routine_id))

    async def approve_routine(self, routine_id: str, device: str) -> m.Approval:
        """Approve a routine's current text to command one device. Needs a human token."""
        return await self.call(calls.approve_routine(routine_id, device))

    async def start_writer(
        self,
        *,
        unknown_id: str | None = None,
        driver: str | None = None,
        params: Mapping[str, Any] | None = None,
        sketch_path: str | None = None,
        manual_text: str | None = None,
    ) -> m.WriterSession:
        """Start a driver writer session from an unknown device, a driver and its params, a sketch or a manual."""
        return await self.call(
            calls.start_writer(
                unknown_id=unknown_id, driver=driver, params=params, sketch_path=sketch_path, manual_text=manual_text
            )
        )

    async def writer_session(self, session_id: str) -> m.WriterSession:
        """One writer session with its status, draft and the limits no person has confirmed yet."""
        return await self.call(calls.writer_session(session_id))

    async def propose(self, session_id: str, draft_yaml: str) -> m.WriterSession:
        """Store a draft device file. The hub marks every limit in the draft as suggested."""
        return await self.call(calls.propose(session_id, draft_yaml))

    async def interview(self, session_id: str) -> m.Interview:
        """The questions a person answers to confirm the draft's limits."""
        return await self.call(calls.interview(session_id))

    async def answer(self, session_id: str, answers: Mapping[str, Any]) -> m.WriterSession:
        """Answer limits interview questions. Needs a human token."""
        return await self.call(calls.answer(session_id, answers))

    async def finish(self, session_id: str, save_as: str | None = None) -> m.FinishResult:
        """Save the confirmed device file, named `save_as` if given. Needs a human token."""
        return await self.call(calls.finish(session_id, save_as))

    async def test_plan(self, session_id: str) -> m.TestPlan:
        """The steps to test the new device file on the real hardware, in order."""
        return await self.call(calls.test_plan(session_id))

    async def tokens(self) -> list[m.TokenInfo]:
        """Every token the hub has issued, without the secrets. Needs a human token."""
        return await self.call(calls.tokens())

    async def create_token(self, name: str, *, kind: str = "agent", scope: str = "read") -> m.NewToken:
        """Issue a token. The response carries the plain token once. Needs a human token."""
        return await self.call(calls.create_token(name, kind, scope))

    async def revoke_token(self, token_id: str) -> m.OkResult:
        """Revoke a token so the hub no longer accepts the token. Revoking needs a human token."""
        return await self.call(calls.revoke_token(token_id))

    async def new_pairing_code(self) -> m.PairingCode:
        """A six digit code that pairs a browser for 300 s. Needs a human token."""
        return await self.call(calls.new_pairing_code())

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
    """Open an async client to the hub.

    With `check`, the client calls `/v1/whoami` first, so a wrong address or token fails here.
    """
    client = AsyncClient(url, token, home=home, timeout=timeout, transport=transport)
    if check:
        try:
            await client.whoami()
        except BaseException:
            await client.aclose()
            raise
    return client
