"""The blocking client. `openhal.client.connect()` returns one."""

from __future__ import annotations

import time
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path
from types import TracebackType
from typing import Any

import httpx

from openhal.client import calls
from openhal.client import models as m
from openhal.client.calls import Call, Command, Value, split_target
from openhal.client.ramp import plan_ramp
from openhal.client.settings import TokenSource, resolve_token, resolve_url
from openhal.client.transport import finish, headers_for, transport_error


class Client:
    """A blocking client of the hub's local API v1.

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
        transport: httpx.BaseTransport | None = None,
        use_human_token_file: bool = True,
    ) -> None:
        self.url = resolve_url(url, home=home)
        self.token_source: TokenSource = resolve_token(token, home=home, use_human_file=use_human_token_file)
        self._http = httpx.Client(
            base_url=self.url,
            headers=headers_for(self.token_source),
            timeout=timeout,
            transport=transport,
            trust_env=False,
        )

    def __enter__(self) -> Client:
        return self

    def __exit__(self, kind: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None) -> None:
        self.close()

    def close(self) -> None:
        """Close the connection to the hub."""
        self._http.close()

    def call[T](self, call: Call[T]) -> T:
        """Send one call and parse the answer. Raises a subclass of `OpenHALError` on failure."""
        try:
            response = self._http.request(call.method, call.path, json=call.json, params=call.params)
        except httpx.TransportError as exc:
            raise transport_error(self.url, exc) from exc
        return finish(call, response, self.token_source)

    def status(self) -> m.HubStatus:
        """The hub's version, protocol version, conformance level and whether a stop is in force."""
        return self.call(calls.status())

    def whoami(self) -> m.Principal:
        """The Principal the hub takes this token for, a human or an agent with its scope."""
        return self.call(calls.whoami())

    def devices(self) -> list[m.DeviceSummary]:
        """Every device the hub knows, with its driver, hazard level and whether it takes commands."""
        return self.call(calls.devices())

    def device(self, device_id: str) -> m.DeviceView:
        """One device with its channels, actions, limits, interlocks and safe state."""
        return self.call(calls.device(device_id))

    def read(self, device: str, channel: str | None = None) -> m.Reading:
        """Read one channel. `read("plant-waterer", "soil_moisture")` or `read("plant-waterer.soil_moisture")`."""
        if channel is None:
            device, channel = split_target(device)
        return self.call(calls.read(device, channel))

    def read_many(self, items: Iterable[str | tuple[str, str]]) -> list[m.Reading]:
        """Read several channels in one request, each as `"device.channel"` or a `(device, channel)` pair."""
        pairs = [split_target(item) if isinstance(item, str) else item for item in items]
        return self.call(calls.read_many(pairs))

    def write(self, device: str, channel: str, value: Value, unit: str | None = None) -> m.Decision:
        """Ask the kernel to set a channel. A number needs its unit, as `write("led-strip", "brightness", 60, "%")`."""
        return self.call(calls.write(device, channel, value, unit))

    def action(self, device: str, action: str, args: Mapping[str, Any] | None = None, **kwargs: Any) -> m.Decision:
        """Ask the kernel to run an action, with its arguments in `args` or as keywords.

        A number goes with its unit, as `action("plant-waterer", "water", duration={"value": 20, "unit": "s"})`.
        """
        return self.call(calls.action(device, action, {**(args or {}), **kwargs}))

    def dry_run(self, commands: Iterable[Command]) -> list[m.Decision]:
        """Evaluate commands in order without running them. Nothing reaches a driver."""
        return self.call(calls.dry_run(commands))

    def tighten(
        self,
        device: str,
        channel: str,
        *,
        min: Mapping[str, Any] | None = None,
        max: Mapping[str, Any] | None = None,
        rate: Mapping[str, Any] | None = None,
    ) -> m.TightenResult:
        """Narrow limits for this token's session. Widening is refused with `cannot_loosen`."""
        return self.call(calls.tighten(device, channel, min=min, max=max, rate=rate))

    def stop(self, reason: str = "stop requested") -> m.StopReport:
        """Put every device in its safe state and lock writes until a human unlocks."""
        return self.call(calls.stop(reason))

    def unlock(self, phrase: str) -> m.UnlockResult:
        """Lift the stop lock. Needs a human token and the phrase `unlock`."""
        return self.call(calls.unlock(phrase))

    def confirmations(self, *, include_done: bool = False) -> list[m.ConfirmationRequest]:
        """Requests waiting for a person. `include_done` adds the ones already decided or expired."""
        return self.call(calls.confirmations(include_done))

    def confirmation(self, request_id: str) -> m.ConfirmationRequest:
        """One confirmation request with its command, its dry run and, once decided, its result."""
        return self.call(calls.confirmation(request_id))

    def approve(self, request_id: str) -> m.Decision:
        """Approve a queued request. Needs a human token. The kernel checks it again first."""
        return self.call(calls.approve(request_id))

    def reject(self, request_id: str, reason: str = "") -> m.ConfirmationRequest:
        """Turn down a queued request, with an optional reason. Needs a human token."""
        return self.call(calls.reject(request_id, reason))

    def audit(
        self,
        *,
        device: str | None = None,
        status: str | None = None,
        event: str | None = None,
        since: int = 0,
        limit: int = 200,
    ) -> list[m.AuditEntry]:
        """Audit log entries after `since`, newest first, filtered by device, status or event."""
        return self.call(calls.audit(device=device, status=status, event=event, since=since, limit=limit))

    def verify_audit(self) -> m.AuditVerify:
        """Check the audit log's hash chain. `broken_at` names the first entry that does not match."""
        return self.call(calls.verify_audit())

    def drivers(self) -> list[m.DriverInfo]:
        """The drivers the hub knows, whether each is installed and the protocols it speaks."""
        return self.call(calls.drivers())

    def pair(self, code: str) -> m.OkResult:
        """Trade a pairing code from `openhal pair` for a human session on this client."""
        return self.call(calls.pair(code))

    def ramp_to(
        self,
        device: str,
        channel: str,
        target: float | Mapping[str, Any] | str,
        unit: str | None = None,
        *,
        interval_s: float = 1.0,
        margin: float = 0.9,
        sleep: Callable[[float], None] = time.sleep,
    ) -> list[m.Decision]:
        """Move a channel to `target` in `unit` in steps that each pass its rate limit.

        Waits `interval_s` before each step, so the first step is safe even right after another write.
        Stops at the first step the kernel does not accept and returns every decision so far.
        """
        plan = plan_ramp(self.device(device), channel, target, unit, interval_s=interval_s, margin=margin)
        decisions: list[m.Decision] = []
        for value in plan.values:
            sleep(plan.interval_s)
            decision = self.write(device, channel, value, plan.unit)
            decisions.append(decision)
            if not decision.ok:
                break
        return decisions

    def discover(self, drivers: Iterable[str] | None = None) -> m.DiscoveryResult:
        """Look for devices with every driver, or only the named ones. Devices no file matches come back unknown."""
        return self.call(calls.discover(drivers))

    def unknown_devices(self) -> list[m.Unknown]:
        """Devices discovery found that no device file matches yet."""
        return self.call(calls.unknown_devices())

    def routines(self) -> list[m.RoutineSummary]:
        """Every stored routine with its devices, triggers and whether it is enabled."""
        return self.call(calls.routines())

    def routine(self, routine_id: str) -> m.Routine:
        """One routine with its source and who drafted and enabled it."""
        return self.call(calls.routine(routine_id))

    def create_routine(self, routine_id: str, source: str, *, kind: str = "yaml") -> m.Routine:
        """Store a routine. It always starts disabled."""
        return self.call(calls.create_routine(routine_id, source, kind))

    def routine_dry_run(self, routine_id: str) -> m.RoutineDryRun:
        """Evaluate every step of a routine against the kernel without running it."""
        return self.call(calls.routine_dry_run(routine_id))

    def enable_routine(self, routine_id: str) -> m.Routine:
        """Turn a routine on. Needs a human token, or an agent under ADR 0007's opt in."""
        return self.call(calls.enable_routine(routine_id))

    def disable_routine(self, routine_id: str) -> m.Routine:
        """Turn a routine off. Any token but a read scoped agent can."""
        return self.call(calls.disable_routine(routine_id))

    def run_routine(self, routine_id: str) -> m.Run:
        """Run a routine once now. Needs a human token."""
        return self.call(calls.run_routine(routine_id))

    def delete_routine(self, routine_id: str) -> m.OkResult:
        """Delete a routine. Needs a human token."""
        return self.call(calls.delete_routine(routine_id))

    def approve_routine(self, routine_id: str, device: str) -> m.Approval:
        """Approve a routine's current text to command one device. Needs a human token."""
        return self.call(calls.approve_routine(routine_id, device))

    def start_writer(
        self,
        *,
        unknown_id: str | None = None,
        driver: str | None = None,
        params: Mapping[str, Any] | None = None,
        sketch_path: str | None = None,
        manual_text: str | None = None,
    ) -> m.WriterSession:
        """Start a driver writer session from an unknown device, a driver and its params, a sketch or a manual."""
        return self.call(
            calls.start_writer(
                unknown_id=unknown_id, driver=driver, params=params, sketch_path=sketch_path, manual_text=manual_text
            )
        )

    def writer_session(self, session_id: str) -> m.WriterSession:
        """One writer session with its status, draft and the limits no person has confirmed yet."""
        return self.call(calls.writer_session(session_id))

    def propose(self, session_id: str, draft_yaml: str) -> m.WriterSession:
        """Store a draft device file. The hub marks every limit in it as suggested."""
        return self.call(calls.propose(session_id, draft_yaml))

    def interview(self, session_id: str) -> m.Interview:
        """The questions a person answers to confirm the draft's limits."""
        return self.call(calls.interview(session_id))

    def answer(self, session_id: str, answers: Mapping[str, Any]) -> m.WriterSession:
        """Answer limits interview questions. Needs a human token."""
        return self.call(calls.answer(session_id, answers))

    def finish(self, session_id: str, save_as: str | None = None) -> m.FinishResult:
        """Save the confirmed device file, named `save_as` if given. Needs a human token."""
        return self.call(calls.finish(session_id, save_as))

    def test_plan(self, session_id: str) -> m.TestPlan:
        """The steps to try the new device file on the real hardware, in order."""
        return self.call(calls.test_plan(session_id))

    def tokens(self) -> list[m.TokenInfo]:
        """Every token the hub has issued, without the secrets. Needs a human token."""
        return self.call(calls.tokens())

    def create_token(self, name: str, *, kind: str = "agent", scope: str = "read") -> m.NewToken:
        """Issue a token. The answer carries the plain token once. Needs a human token."""
        return self.call(calls.create_token(name, kind, scope))

    def revoke_token(self, token_id: str) -> m.OkResult:
        """Revoke a token so the hub stops accepting it. Needs a human token."""
        return self.call(calls.revoke_token(token_id))

    def new_pairing_code(self) -> m.PairingCode:
        """A six digit code that pairs a browser for 300 s. Needs a human token."""
        return self.call(calls.new_pairing_code())


def connect(
    url: str | None = None,
    token: str | None = None,
    *,
    home: Path | str | None = None,
    timeout: float = 15.0,
    transport: httpx.BaseTransport | None = None,
    check: bool = True,
) -> Client:
    """Open a blocking client to the hub.

    With `check` it calls `/v1/whoami` first, so a wrong address or token fails here.
    """
    client = Client(url, token, home=home, timeout=timeout, transport=transport)
    if check:
        try:
            client.whoami()
        except BaseException:
            client.close()
            raise
    return client
