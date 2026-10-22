"""The hub. Owns the kernel, every device, polling, heartbeats and live events (ADR 0003).

`openhald` runs one Hub. Tests, `openhal demo` and scripts can run the same class embedded.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from openhal._brand import DEVICE_FILE_SUFFIX
from openhal.audit.log import AuditLog, Entry
from openhal.drivers import registry
from openhal.drivers.base import Driver, Reading
from openhal.hub import views
from openhal.hub.config import HubConfig
from openhal.hub.locks import DeviceLock, DeviceLocked
from openhal.hub.tokens import TokenStore
from openhal.kernel.kernel import Kernel
from openhal.kernel.principals import SYSTEM
from openhal.kernel.runtime import DeviceRuntime
from openhal.spec.loader import DeviceFileError, load, warnings_for
from openhal.spec.models import Approval, DeviceFile

log = logging.getLogger("openhal.hub")

Listener = Callable[[dict[str, Any]], None]


@dataclass
class LoadProblem:
    path: str
    problems: list[str]


@dataclass
class DeviceInfo:
    path: str | None
    warnings: list[str] = field(default_factory=list)
    last_error: str | None = None


class Hub:
    """One hub process. Embedded use: `async with Hub(config) as hub: ...`."""

    def __init__(
        self, config: HubConfig, *, clock: Callable[[], float] = time.monotonic, in_memory: bool = False
    ) -> None:
        self.config = config
        if not in_memory:
            config.ensure_dirs()
            # The database holds token hashes and the audit log, so only its owner may read it.
            config.db_path.touch(mode=0o600, exist_ok=True)
            config.db_path.chmod(0o600)
        self.audit = AuditLog(":memory:" if in_memory else config.db_path)
        self.tokens = TokenStore(":memory:" if in_memory else config.db_path)
        self.kernel = Kernel(
            self.audit,
            clock=clock,
            confirm_ttl_s=config.confirm.ttl_s,
            approval_key=self._approval_key(in_memory),
        )
        self.in_memory = in_memory
        self.info: dict[str, DeviceInfo] = {}
        from openhal.routines.engine import RoutineEngine

        self.routines = RoutineEngine(self)
        self.load_problems: list[LoadProblem] = []
        self.last_discovery: Any = None
        self.started_at: float | None = None
        self._locks: dict[str, DeviceLock] = {}
        self._tasks: list[asyncio.Task[None]] = []
        self._listeners: list[Listener] = []
        self.audit.subscribe(self._on_audit)

    # ------------------------------------------------------------------ lifecycle

    async def __aenter__(self) -> Hub:
        await self.start()
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()

    async def start(self, *, load_devices: bool = True) -> None:
        """Load device files, connect devices, and start background loops."""
        if load_devices:
            self.load_device_files()
        for device_id in list(self.kernel.devices):
            await self._connect(device_id)
        self.started_at = time.time()
        await self.routines.start()
        self._tasks.append(asyncio.create_task(self._watchdog_loop(), name="openhal-watchdog"))
        for device_id in list(self.kernel.devices):
            self._start_device_tasks(device_id)
        self.audit.append("hub_start", SYSTEM.label, status="done", devices=len(self.kernel.devices))

    async def close(self) -> None:
        await self.routines.close()
        for task in self._tasks:
            task.cancel()
        for task in self._tasks:
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
        self._tasks.clear()
        for runtime in self.kernel.devices.values():
            with contextlib.suppress(Exception):
                await runtime.driver.close()
        for lock in self._locks.values():
            lock.release()
        self._locks.clear()
        self.audit.append("hub_stop", SYSTEM.label, status="done")

    # ------------------------------------------------------------------ devices

    def load_device_files(self) -> None:
        """Register every device file in the devices folder. Problems are kept, not raised."""
        self.load_problems.clear()
        folder = self.config.devices_dir
        if not folder.exists():
            return
        for path in sorted(folder.glob(f"*{DEVICE_FILE_SUFFIX}")):
            try:
                file = load(path)
            except DeviceFileError as exc:
                self.load_problems.append(LoadProblem(str(path), exc.problems))
                continue
            try:
                self.add_device(file, path=path)
            except (registry.UnknownDriver, DeviceLocked, ValueError) as exc:
                self.load_problems.append(LoadProblem(str(path), [str(exc)]))

    def add_device(self, file: DeviceFile, *, driver: Driver | None = None, path: Path | None = None) -> DeviceRuntime:
        """Register one device. The driver is built from the file unless one is given."""
        device_id = file.device_id
        if device_id in self.kernel.devices:
            raise ValueError(f"A device with id {device_id!r} is already registered.")
        if driver is None:
            driver = registry.load(file.connect.driver)(file)
        if not self.in_memory:
            lock = DeviceLock(self.config.locks_dir, device_id)
            lock.acquire()
            self._locks[device_id] = lock
        runtime = self.kernel.register(file, driver)
        self.info[device_id] = DeviceInfo(str(path) if path else None, warnings_for(file))
        return runtime

    async def add_and_start(self, file: DeviceFile, *, driver: Driver | None = None) -> DeviceRuntime:
        """Register, connect and start polling one device while the hub runs."""
        runtime = self.add_device(file, driver=driver)
        await self._connect(file.device_id)
        if self.started_at is not None:
            self._start_device_tasks(file.device_id)
        return runtime

    async def _connect(self, device_id: str) -> bool:
        info = self.info.setdefault(device_id, DeviceInfo(None))
        try:
            await self.kernel.connect(device_id)
        except Exception as exc:  # noqa: BLE001
            info.last_error = f"{type(exc).__name__}: {exc}"
            self.audit.append("connect", SYSTEM.label, device=device_id, status="failed", detail=info.last_error)
            self._emit({"type": "state", "device": device_id})
            return False
        info.last_error = None
        self._emit({"type": "state", "device": device_id})
        return True

    def _start_device_tasks(self, device_id: str) -> None:
        self._tasks.append(asyncio.create_task(self._poll_loop(device_id), name=f"openhal-poll-{device_id}"))
        self._tasks.append(asyncio.create_task(self._heartbeat_loop(device_id), name=f"openhal-heartbeat-{device_id}"))

    # ------------------------------------------------------------------ loops

    async def _poll_loop(self, device_id: str) -> None:
        runtime = self.kernel.devices[device_id]
        intervals: dict[str, float | None] = {name: spec.every for name, spec in runtime.file.read.items()}
        intervals.update({name: spec.every for name, spec in runtime.file.write.items()})
        schedule = {name: max(every, self.config.poll_floor_s) for name, every in intervals.items() if every}
        if not schedule:
            return
        due = dict.fromkeys(schedule, 0.0)
        while True:
            now = time.monotonic()
            for channel, interval in schedule.items():
                if now < due[channel] or not runtime.connected:
                    continue
                due[channel] = now + interval
                try:
                    reading = await asyncio.wait_for(runtime.driver.read(channel), 5.0)
                except Exception as exc:  # noqa: BLE001
                    log.debug("poll %s.%s failed: %s", device_id, channel, exc)
                    continue
                self._record(device_id, reading)
            await asyncio.sleep(min(schedule.values()) / 2)

    def _record(self, device_id: str, reading: Reading) -> None:
        self.kernel.note_reading(device_id, reading)
        self._emit(
            {
                "type": "reading",
                "device": device_id,
                "channel": reading.channel,
                "value": views.device_value(
                    self.kernel.devices[device_id].file, device_id, reading.channel, reading.value
                ),
                "unit": reading.unit,
                "at": reading.at,
                "suspect": reading.suspect,
            }
        )

    async def _heartbeat_loop(self, device_id: str) -> None:
        runtime = self.kernel.devices[device_id]
        interval = runtime.file.watchdog.heartbeat
        backoff = 2.0
        while True:
            await asyncio.sleep(interval if runtime.connected else backoff)
            if runtime.connected:
                try:
                    health = await asyncio.wait_for(runtime.driver.health(), interval)
                    healthy = health.connected
                    detail = health.detail
                except Exception as exc:  # noqa: BLE001
                    healthy, detail = False, f"{type(exc).__name__}: {exc}"
                if not healthy:
                    await self.kernel.connection_lost(device_id, detail or "heartbeat failed")
                    self.info[device_id].last_error = detail or "heartbeat failed"
                    self._emit({"type": "state", "device": device_id})
                continue
            backoff = 2.0 if await self._connect(device_id) else min(backoff * 2, 30.0)

    async def _watchdog_loop(self) -> None:
        while True:
            await asyncio.sleep(self.config.watchdog_tick_s)
            try:
                fired = await self.kernel.tick()
            except Exception as exc:  # noqa: BLE001
                self.audit.append("watchdog", SYSTEM.label, status="failed", detail=repr(exc))
                continue
            for rule in fired:
                self._emit({"type": "watchdog", "rule": rule})
            self.kernel.queue.expire(self.kernel.clock())

    def add_approval(self, device_id: str, approval: Approval) -> None:
        """Store a signed routine approval in a device file, on disk and in the running kernel."""
        runtime = self.kernel.devices[device_id]
        data = runtime.file.model_dump(mode="json", by_alias=True, exclude={"extensions"})
        approvals = [item for item in data.get("approvals", []) if item["routine"] != approval.routine]
        approvals.append(approval.model_dump(mode="json"))
        data["approvals"] = approvals
        updated = DeviceFile.model_validate(data)
        runtime.file = updated
        info = self.info.get(device_id)
        if info is not None and info.path:
            path = Path(info.path)
            block = yaml.safe_dump({"approvals": approvals}, sort_keys=False)
            text = path.read_text(encoding="utf-8")
            if "\napprovals:" in f"\n{text}":
                text = yaml.safe_dump(data, sort_keys=False)
                text = "# Rewritten by openhal when a routine approval was added.\n" + text
            else:
                text = text.rstrip("\n") + "\n" + block
            path.write_text(text, encoding="utf-8")
        self.audit.append(
            "approval_saved", SYSTEM.label, device=device_id, target=f"routine:{approval.routine}", status="done"
        )

    # ------------------------------------------------------------------ live events

    def subscribe(self, listener: Listener) -> Callable[[], None]:
        """Receive live events (readings, state, audit). Returns an unsubscribe function."""
        self._listeners.append(listener)

        def unsubscribe() -> None:
            with contextlib.suppress(ValueError):
                self._listeners.remove(listener)

        return unsubscribe

    def _emit(self, event: dict[str, Any]) -> None:
        for listener in list(self._listeners):
            try:
                listener(event)
            except Exception:  # noqa: S112, BLE001 (one broken view can't stop the hub)
                continue

    def _on_audit(self, entry: Entry) -> None:
        self._emit(
            {
                "type": "audit",
                "seq": entry.seq,
                "event": entry.event,
                "principal": entry.principal,
                "device": entry.device,
                "target": entry.target,
                "status": entry.status,
                "code": entry.code,
                "message": entry.body.get("details", {}).get("message"),
                "at": entry.at,
            }
        )

    # ------------------------------------------------------------------ secrets

    def _approval_key(self, in_memory: bool) -> bytes:
        if in_memory:
            return secrets.token_bytes(32)
        path = self.config.approval_key_path
        if path.exists():
            return bytes.fromhex(path.read_text(encoding="utf-8").strip())
        key = secrets.token_bytes(32)
        path.touch(mode=0o600, exist_ok=True)
        path.chmod(0o600)
        path.write_text(key.hex() + "\n", encoding="utf-8")
        return key
