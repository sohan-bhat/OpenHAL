"""Bambu Lab printers over the printer's own MQTT broker, in LAN-only mode with Developer Mode on.

Status of local access (checked 2026-10-24, sources in docs/drivers/bambu.md). Since the 2025
Authorization Control firmware, Bambu Lab printers accept control commands over plain LAN MQTT
only in Developer Mode, an opt-in setting under LAN-only mode that Bambu Lab documents and does
not support. Status reports stay readable either way. This driver uses only what Developer Mode
leaves open. It never talks to Bambu Cloud, never uses Bambu Connect or its keys, and never
tries to get around authorization. Without Developer Mode the printer refuses the commands and
the driver reports that.

Protocol. MQTT 3.1.1 over TLS on port 8883 of the printer. User `bblp`, and the LAN access code
from the printer's screen as the password. The printer publishes JSON on `device/<serial>/report`
and takes JSON commands on `device/<serial>/request`.

- Reads come from the newest report. `{"pushing": {"command": "pushall"}}` asks for a full report
  once after connecting. X1 printers send full reports, P1 and A1 printers send only what changed,
  so the driver merges every report into one state.
- `pause`, `resume` and `stop` are `{"print": {"command": ...}}`. The speed level is
  `print_speed` with `param` 1 to 4, and the chamber light is `system.ledctrl`.
- Commands are QoS 1 and wait for the PUBACK. If the printer replies with a result for the same
  `sequence_id`, a failed result raises DriverError with the printer's reason.

TLS. The printer's certificate is signed by Bambu Lab's own authority and names the serial number,
not the address, so ordinary verification fails. The driver needs `cert_sha256`, the certificate's
fingerprint, which it checks before the access code is sent, or `ca_file` with Bambu Lab's
authority certificate, in which case it checks the certificate names the serial number.

Safe state. Native. The driver sends `stop` (or `pause` with `safe_stop: pause`). The printer's
firmware ends the print, turns the heaters off and parks the head.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import itertools
import json
import os
import socket
import ssl
import threading
import time
from collections.abc import Callable
from typing import Any, ClassVar

from pydantic import BaseModel, ValidationError

from openhal.drivers.bambu.protocol import (
    CONTROLS,
    DISCOVERY_PORT,
    DISCOVERY_S,
    FIELDS,
    PRINT_COMMANDS,
    SPEEDS,
    USERNAME,
    ActionMap,
    BambuParams,
    ClientFactory,
    PinMismatchError,
    ReadMap,
    WriteMap,
    default_client,
    merge,
    parse_notify,
    propose,
)
from openhal.drivers.base import Discovered, Driver, DriverError, DriverInfo, Health, Reading
from openhal.drivers.http import values as v
from openhal.spec.models import DeviceFile
from openhal.spec.units import Quantity, UnitError, convert, parse_unit


class BambuDriver(Driver):
    """A Bambu Lab printer over LAN MQTT in Developer Mode. Status reads, pause, resume and stop."""

    info: ClassVar[DriverInfo] = DriverInfo(
        name="bambu",
        protocols=("Bambu Lab LAN MQTT over TLS",),
        hazard_default="medium",
        summary="Bambu Lab printers in LAN Developer Mode. Temperatures and print state, pause, resume and stop.",
        safe_state_support="native",
        conformance="full",
    )
    params_model: ClassVar[type[Any] | None] = BambuParams

    def __init__(
        self,
        device: DeviceFile,
        *,
        client_factory: ClientFactory = default_client,
        environ: Callable[[str], str | None] = os.environ.get,
    ) -> None:
        super().__init__(device)
        self.settings = BambuParams.model_validate(device.connect.params)
        self._factory = client_factory
        self._environ = environ
        self._client: Any = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._connected = threading.Event()
        self._lock = threading.Lock()
        self._state: dict[str, Any] = {}
        self._stamps: dict[str, float] = {}
        self._pending: dict[str, asyncio.Future[dict[str, Any]]] = {}
        self._ids = itertools.count(1)
        self._lost = ""
        self._refused = ""
        self.versions: dict[str, str] = {}
        self.reads: dict[str, ReadMap] = {}
        self.writes: dict[str, str] = {}
        self.actions: dict[str, str] = {}
        for name, spec in device.read.items():
            self.reads[name] = self._read_map(name, spec.map, spec.type)
        for name, wspec in device.write.items():
            control = self._parse(WriteMap, f"write.{name}", wspec.map).control if wspec.map else name
            if control not in CONTROLS:
                raise DriverError(
                    f"write.{name}: the bambu driver can set speed_level and chamber_light only. "
                    "Name the channel after one, or add map: { control: speed_level }."
                )
            if control == "speed_level" and (wspec.type != "enum" or not set(wspec.values) <= set(SPEEDS)):
                raise DriverError(f"write.{name} must be an enum with values from {', '.join(SPEEDS)}.")
            if control == "chamber_light" and wspec.type != "bool":
                raise DriverError(f"write.{name} must be a bool channel.")
            self.writes[name] = control
        for name, action in device.actions.items():
            command = self._parse(ActionMap, f"actions.{name}", action.map).command if action.map else name
            if command not in PRINT_COMMANDS:
                raise DriverError(
                    f"actions.{name}: the bambu driver has pause, resume and stop. Name the action after one, "
                    "or add map: { command: pause }."
                )
            if action.args:
                raise DriverError(f"actions.{name}: {command} takes no arguments.")
            self.actions[name] = command

    @staticmethod
    def _parse[M: BaseModel](model: type[M], where: str, raw: dict[str, Any] | None) -> M:
        try:
            return model.model_validate(raw or {})
        except ValidationError as exc:
            problems = "; ".join(f"{'.'.join(map(str, e['loc'])) or 'map'}: {e['msg']}" for e in exc.errors())
            raise DriverError(f"{where} has an invalid bambu map. {problems}") from None

    def _read_map(self, name: str, raw: dict[str, Any] | None, kind: str) -> ReadMap:
        if raw is not None:
            read_map = self._parse(ReadMap, f"read.{name}", raw)
        elif name in FIELDS:
            path, unit = FIELDS[name]
            read_map = ReadMap(field=path, unit=unit)
        else:
            raise DriverError(
                f"read.{name}: name the channel after a known field ({', '.join(FIELDS)}) "
                "or give map: { field: <path in the print report> }."
            )
        if kind == "image":
            raise DriverError(f"read.{name}: the bambu driver has no image channels. Use an rtsp or ftp tool instead.")
        if read_map.unit:
            try:
                parse_unit(read_map.unit)
            except UnitError as exc:
                raise DriverError(f"read.{name}: {exc}") from None
        return read_map

    @property
    def _where(self) -> str:
        return f"Bambu Lab printer {self.settings.serial} at {self.settings.host}"

    @property
    def report_topic(self) -> str:
        return f"device/{self.settings.serial}/report"

    @property
    def request_topic(self) -> str:
        return f"device/{self.settings.serial}/request"

    @classmethod
    async def discover(cls) -> list[Discovered]:
        """Listen for the printers' own SSDP NOTIFY broadcasts on UDP 2021. Nothing is sent."""
        try:
            listener = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            listener.bind(("", DISCOVERY_PORT))
        except OSError:
            return []
        listener.setblocking(False)
        loop = asyncio.get_running_loop()
        found: dict[str, Discovered] = {}
        deadline = loop.time() + DISCOVERY_S
        try:
            while (left := deadline - loop.time()) > 0:
                try:
                    data, sender = await asyncio.wait_for(loop.sock_recvfrom(listener, 2048), left)
                except (TimeoutError, OSError):
                    break
                printer = parse_notify(data.decode("utf-8", "replace"), sender[0])
                if printer is not None:
                    found[printer.identifiers["serial"]] = printer
        finally:
            listener.close()
        return list(found.values())

    async def identify(self) -> dict[str, str]:
        identity = {"serial": self.settings.serial, "host": self.settings.host}
        identity.update(self.versions)
        return identity

    def _context(self) -> ssl.SSLContext:
        context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
        context.check_hostname = False
        if self.settings.ca_file is not None:
            try:
                context.load_verify_locations(cafile=self.settings.ca_file)
            except (OSError, ssl.SSLError) as exc:
                raise DriverError(f"Could not load ca_file {self.settings.ca_file} ({exc}).") from None
        else:
            context.verify_mode = ssl.CERT_NONE
        return context

    def _check_peer(self, client: Any, userdata: Any, sock: Any) -> None:
        if self.settings.cert_sha256 is not None:
            der = sock.getpeercert(binary_form=True) or b""
            seen = hashlib.sha256(der).hexdigest()
            if seen != self.settings.cert_sha256:
                raise PinMismatchError(f"the printer's certificate has fingerprint {seen}, not the pinned one")
            return
        names = [value for entry in (sock.getpeercert() or {}).get("subject", ()) for _, value in entry]
        if self.settings.serial not in names:
            shown = ", ".join(names) or "nothing"
            raise PinMismatchError(f"the certificate names {shown}, not {self.settings.serial}")

    def _on_connect(self, client: Any, userdata: Any, flags: Any, reason: Any, properties: Any) -> None:
        if getattr(reason, "is_failure", False):
            self._refused = f"the printer refused the connection ({reason})"
            return
        client.subscribe(self.report_topic, 0)
        self._connected.set()

    def _on_disconnect(self, client: Any, userdata: Any, flags: Any, reason: Any, properties: Any) -> None:
        self._connected.clear()
        self._lost = f"disconnected ({reason})"
        loop = self._loop
        if loop is not None and not loop.is_closed():
            loop.call_soon_threadsafe(self._fail_pending, f"{self._where} disconnected ({reason}). Reconnect it.")

    def _on_message(self, client: Any, userdata: Any, message: Any) -> None:
        try:
            document = json.loads(bytes(message.payload))
        except (ValueError, UnicodeDecodeError):
            return
        if not isinstance(document, dict):
            return
        now = time.time()
        replies: list[tuple[str, dict[str, Any]]] = []
        with self._lock:
            for section in ("print", "system", "info"):
                body = document.get(section)
                if not isinstance(body, dict):
                    continue
                command = body.get("command")
                sequence = str(body.get("sequence_id", ""))
                if command not in (None, "push_status") and sequence in self._pending:
                    replies.append((sequence, body))
                if section == "print":
                    merge(self._state, body)
                    for key in body:
                        self._stamps[key] = now
                elif section == "info" and command == "get_version":
                    self._versions(body)
        loop = self._loop
        if replies and loop is not None and not loop.is_closed():
            for sequence, body in replies:
                loop.call_soon_threadsafe(self._resolve, sequence, body)

    def _versions(self, body: dict[str, Any]) -> None:
        for module in body.get("module") or []:
            if isinstance(module, dict) and module.get("name") == "ota" and module.get("sw_ver"):
                self.versions["firmware"] = str(module["sw_ver"])
            if isinstance(module, dict) and module.get("name") == "mc" and module.get("sw_ver"):
                self.versions["motion_controller"] = str(module["sw_ver"])

    def _resolve(self, sequence: str, body: dict[str, Any]) -> None:
        future = self._pending.get(sequence)
        if future is not None and not future.done():
            future.set_result(body)

    def _fail_pending(self, message: str) -> None:
        for future in self._pending.values():
            if not future.done():
                future.set_exception(DriverError(message))
                future.exception()

    async def connect(self) -> None:
        await self.close()
        code = self._environ(self.settings.token_env)
        if not code:
            raise DriverError(
                f"Set the {self.settings.token_env} environment variable to the printer's LAN access code "
                "(Settings, WLAN on the printer's screen)."
            )
        self._loop = asyncio.get_running_loop()
        client = self._factory(f"openhal-{self.device.device_id[:16]}")
        client.on_connect = self._on_connect
        client.on_disconnect = self._on_disconnect
        client.on_message = self._on_message
        client.on_socket_open = self._check_peer
        client.connect_timeout = self.settings.timeout
        client.username_pw_set(USERNAME, code)
        client.tls_set_context(self._context())
        self._connected.clear()
        self._lost = ""
        self._refused = ""
        with self._lock:
            self._state.clear()
            self._stamps.clear()
        try:
            await asyncio.wait_for(
                asyncio.to_thread(client.connect, self.settings.host, self.settings.port, 30),
                self.settings.timeout + 1,
            )
        except TimeoutError:
            raise TimeoutError(f"{self._where} did not answer on port {self.settings.port}.") from None
        except PinMismatchError as exc:
            with contextlib.suppress(Exception):
                client.socket().close()
            raise DriverError(
                f"Refused to log in to {self._where}, because {exc}. The access code was not sent. "
                "Check the address, then read the fingerprint again if the printer was reset."
            ) from None
        except (OSError, ssl.SSLError) as exc:
            raise DriverError(f"Could not reach {self._where} ({exc}). Check LAN-only mode and the address.") from None
        client.loop_start()
        self._client = client
        deadline = time.monotonic() + self.settings.timeout
        while not self._connected.is_set():
            if self._refused or time.monotonic() > deadline:
                reason = self._refused or "no answer to the MQTT login"
                await self.close()
                raise DriverError(f"{self._where} did not accept the login, {reason}. Check the access code.")
            await asyncio.sleep(0.02)
        await self._publish({"info": {"sequence_id": self._next(), "command": "get_version"}})
        await self._publish(
            {"pushing": {"sequence_id": self._next(), "command": "pushall", "version": 1, "push_target": 1}}
        )
        while "gcode_state" not in self._state:
            if time.monotonic() > deadline:
                await self.close()
                raise DriverError(
                    f"{self._where} sent no status report. Check the serial number, which names the MQTT topics."
                )
            await asyncio.sleep(0.02)

    def _next(self) -> str:
        return str(next(self._ids))

    async def close(self) -> None:
        client, self._client = self._client, None
        self._connected.clear()
        if client is None:
            return
        try:
            client.disconnect()
        finally:
            await asyncio.to_thread(client.loop_stop)
            self._fail_pending(f"{self._where} was closed.")

    @property
    def connected(self) -> bool:
        """True while the MQTT session with the printer is up."""
        return self._client is not None and self._connected.is_set()

    async def health(self) -> Health:
        if not self.connected:
            return Health(connected=False, detail=f"{self._where} {self._lost or 'not connected'}")
        return Health(connected=True, detail=f"{self._where}, {self._state.get('gcode_state', 'unknown')}")

    def _check_open(self) -> Any:
        if self._client is None or not self._connected.is_set():
            raise DriverError(f"{self._where} is not connected{f', {self._lost}' if self._lost else ''}. Reconnect it.")
        return self._client

    async def read(self, channel: str) -> Reading:
        self._check_open()
        if channel in self.writes:
            return self._control_value(channel, self.writes[channel])
        read_map = self.reads.get(channel)
        if read_map is None:
            raise DriverError(f"This bambu printer has no channel {channel!r}.")
        spec = self.device.read[channel]
        unit = self.device.channel_unit(channel)
        path = v.parse_path(read_map.field)
        with self._lock:
            if path[0] not in self._state:
                return Reading(channel, None, unit=unit)
            raw = v.extract(self._state, path, f"{self._where} report field {read_map.field}")
            at = self._stamps.get(str(path[0]), time.time())
        where = f"{read_map.field} for {channel}"
        if read_map.field == "lights_report":
            return Reading(channel, self._light(raw, "chamber_light"), at=at)
        if spec.type == "number":
            value = v.to_number(raw, where) * read_map.scale
            if read_map.unit and spec.unit and read_map.unit != spec.unit:
                value = convert(Quantity(value, parse_unit(read_map.unit)), spec.unit)
            suspect = spec.range is not None and not spec.range[0] <= value <= spec.range[1]
            return Reading(channel, value, unit=unit, at=at, suspect=suspect)
        if spec.type == "bool":
            return Reading(channel, v.to_bool(raw, v.DEFAULT_ON, v.DEFAULT_OFF, where), at=at)
        text = v.to_text(raw)
        if read_map.field == "gcode_state":
            text = text.lower()
        if read_map.field == "spd_lvl":
            text = next((word for word, level in SPEEDS.items() if str(level) == text), text)
        if spec.type == "enum" and text not in spec.values:
            raise DriverError(f"{where} reported {text[:60]!r}, which is not one of {', '.join(spec.values)}.")
        return Reading(channel, text, at=at)

    def _light(self, raw: Any, node: str) -> bool | None:
        if not isinstance(raw, list):
            raise DriverError(f"{self._where} sent lights_report that is not a list.")
        for entry in raw:
            if isinstance(entry, dict) and entry.get("node") == node:
                return entry.get("mode") in ("on", "flashing")
        return None

    def _control_value(self, channel: str, control: str) -> Reading:
        with self._lock:
            if control == "chamber_light":
                raw = self._state.get("lights_report")
                at = self._stamps.get("lights_report", time.time())
                value: Any = None if raw is None else self._light(raw, "chamber_light")
            else:
                level = self._state.get("spd_lvl")
                at = self._stamps.get("spd_lvl", time.time())
                value = next((word for word, number in SPEEDS.items() if number == level), None)
                if level is not None and value is None:
                    raise DriverError(f"{self._where} reported speed level {level!r}, which is not 1 to 4.")
        return Reading(channel, value, at=at)

    async def _publish(self, document: dict[str, Any]) -> None:
        client = self._check_open()
        info = client.publish(self.request_topic, json.dumps(document, separators=(",", ":")), qos=1)
        if getattr(info, "rc", 0) != 0:
            raise DriverError(f"{self._where} refused the publish (code {info.rc}).")
        try:
            await asyncio.wait_for(
                asyncio.to_thread(info.wait_for_publish, self.settings.timeout), self.settings.timeout + 1
            )
        except (RuntimeError, ValueError) as exc:
            raise DriverError(f"The command to {self._where} failed ({exc}).") from None
        except TimeoutError:
            pass
        if not info.is_published():
            await self.close()
            raise TimeoutError(
                f"{self._where} didn't acknowledge the command within {self.settings.timeout:g} s. "
                "The connection was closed so the command can't arrive late."
            )

    async def _command(self, section: str, body: dict[str, Any]) -> dict[str, Any] | None:
        sequence = self._next()
        future: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
        self._pending[sequence] = future
        try:
            await self._publish({section: {"sequence_id": sequence, **body}})
            try:
                reply = await asyncio.wait_for(asyncio.shield(future), self.settings.reply_wait)
            except TimeoutError:
                return None
        finally:
            self._pending.pop(sequence, None)
        result = str(reply.get("result", "")).lower()
        if result in ("fail", "failed", "error"):
            reason = str(reply.get("reason") or reply.get("err_code") or "no reason given")[:200]
            hint = ""
            if "verif" in reason.lower() or "auth" in reason.lower():
                hint = " The printer wants authorization, so turn on LAN-only mode and Developer Mode on its screen."
            raise DriverError(f"{self._where} refused {body.get('command')} ({reason}).{hint}")
        return reply

    async def _write(self, channel: str, value: float | bool | str) -> Reading | None:
        control = self.writes.get(channel)
        if control is None:
            raise DriverError(f"This bambu printer has no write channel {channel!r}.")
        if control == "speed_level":
            await self._command("print", {"command": "print_speed", "param": str(SPEEDS[str(value)])})
        else:
            await self._command(
                "system",
                {
                    "command": "ledctrl",
                    "led_node": "chamber_light",
                    "led_mode": "on" if value else "off",
                    "led_on_time": 500,
                    "led_off_time": 500,
                    "loop_times": 0,
                    "interval_time": 0,
                },
            )
        return Reading(channel, value)

    async def _action(self, name: str, args: dict[str, Any]) -> Any:
        command = self.actions.get(name)
        if command is None:
            raise DriverError(f"This bambu printer has no action {name!r}.")
        reply = await self._command("print", {"command": command, "param": ""})
        return {"sent": command, "reply": "none" if reply is None else str(reply.get("result", "ok"))}

    async def _safe_state(self) -> None:
        await self._command("print", {"command": self.settings.safe_stop, "param": ""})

    async def describe(self) -> dict[str, Any] | None:
        if not self.connected:
            return None
        with self._lock:
            state = dict(self._state)
        return propose(state, self.settings.serial)
