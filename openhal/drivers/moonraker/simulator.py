"""A Moonraker and Klipper simulator, written from the Moonraker web API documentation.

`KlipperState` holds the printer objects (extruder, heater_bed, fan, print_stats, toolhead,
webhooks, configfile, virtual_sdcard and a chamber sensor) and runs the G-code the driver sends.
`MoonrakerSim` puts the JSON-RPC methods in front of it, reachable two ways.

- `sim.http_transport()` is an `httpx.MockTransport` for the HTTP endpoints
  (`GET /printer/objects/query?extruder=temperature`, `POST /printer/gcode/script`, ...).
- `await sim.start_websocket()` serves `/websocket` on 127.0.0.1 with real JSON-RPC 2.0, including
  `printer.objects.subscribe` and `notify_status_update` notifications.

Heaters. A heater below its target warms to the target within a few seconds. A heater above its
target, or with its target at 0, cools toward `ambient` by Newton's law of cooling, at the rate
COOLING_S gives each heater. Klipper reports temperatures rounded to two decimals, and so does the
simulator. The heaters follow `clock`, which is `time.monotonic` unless the caller passes a clock of
its own, such as the demo's story clock (openhal/demo/scenario.py).

Print controls. A pause keeps the heaters as they are. A cancel first runs the G-code of the
CANCEL_PRINT macro that Mainsail and Fluidd ship, TURN_OFF_HEATERS and M106 S0, so every heater
target and the part fan go to 0 and the heaters cool.

Faults. `latency_s`, `klippy_state` ("ready", "shutdown", "startup", "disconnected"), `fail_http` (every HTTP
request raises a connection error), `fail_next` (only the next N do), `malformed` (reply with
invalid JSON) and `drop_websockets()`.
"""

from __future__ import annotations

import asyncio
import contextlib
import copy
import json
import math
import time
from collections.abc import Callable
from typing import Any, Final
from urllib.parse import parse_qsl

import httpx

AMBIENT_C: Final = 22.0
"""The temperature of the room the simulated printer stands in, in degC."""
HEATING_PER_S: Final = 0.8
"""The share of the gap to its target that a warming heater closes each second."""
COOLING_S: Final = {"extruder": 80.0, "heater_bed": 600.0, "heater_generic enclosure": 900.0}
"""Each heater's time constant for Newton's law of cooling, in seconds.

With its heater off, a hotend whose heatsink fan runs falls from 215 degC to about 113 degC in a
minute, and a heated bed at 70 degC falls to about 40 degC in ten minutes.
"""
CANCEL_PRINT: Final = ("TURN_OFF_HEATERS", "M106 S0")
"""The G-code the CANCEL_PRINT macro that Mainsail and Fluidd ship runs before Klipper's own cancel."""


class RpcError(Exception):
    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class KlipperState:
    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self.objects: dict[str, dict[str, Any]] = {
            "webhooks": {"state": "ready", "state_message": "Printer is ready"},
            "extruder": {"temperature": 22.0, "target": 0.0, "power": 0.0},
            "heater_bed": {"temperature": 21.5, "target": 0.0, "power": 0.0},
            "fan": {"speed": 0.0, "rpm": None},
            "temperature_sensor chamber": {"temperature": 24.0},
            "heater_generic enclosure": {"temperature": 23.0, "target": 0.0, "power": 0.0},
            "fan_generic exhaust": {"speed": 0.0},
            "print_stats": {"state": "standby", "filename": "", "print_duration": 0.0},
            "virtual_sdcard": {"progress": 0.0, "is_active": False},
            "toolhead": {"homed_axes": "", "position": [10.0, 20.0, 5.0, 0.0], "print_time": 0.0},
            "configfile": {
                "settings": {
                    "extruder": {"min_temp": 0, "max_temp": 280},
                    "heater_bed": {"min_temp": 0, "max_temp": 120},
                    "heater_generic enclosure": {"min_temp": 0, "max_temp": 70},
                }
            },
        }
        self.gcode: list[str] = []
        self.home_time_s = 0.0
        self.ambient = AMBIENT_C
        self.clock = clock
        self._last = clock()

    def step(self) -> None:
        """Move every heater on to the clock's time. A clock that hasn't moved changes nothing."""
        now = self.clock()
        elapsed = now - self._last
        if elapsed <= 0:
            return
        self._last = now
        for name, cooling_s in COOLING_S.items():
            heater = self.objects[name]
            heater["temperature"] = self._heated(heater["temperature"], heater["target"], elapsed, cooling_s)

    def _heated(self, temperature: float, target: float, elapsed: float, cooling_s: float) -> float:
        if target > temperature:
            return temperature + (target - temperature) * min(1.0, HEATING_PER_S * elapsed)
        cooled = self.ambient + (temperature - self.ambient) * math.exp(-elapsed / cooling_s)
        return max(cooled, target) if target > 0 else cooled

    def reported(self, name: str) -> dict[str, Any] | None:
        """One printer object as Klipper reports it, with its temperature rounded to two decimals."""
        obj = self.objects.get(name)
        if obj is None:
            return None
        shown = copy.deepcopy(obj)
        if isinstance(shown.get("temperature"), float):
            shown["temperature"] = round(shown["temperature"], 2)
        return shown

    def heater(self, name: str) -> dict[str, Any]:
        for key in (name, f"heater_generic {name}"):
            if key in self.objects and "target" in self.objects[key]:
                return self.objects[key]
        raise RpcError(400, f"Unknown heater '{name}'")

    async def run_gcode(self, script: str) -> str:
        if self.objects["webhooks"]["state"] != "ready":
            raise RpcError(503, "Klippy is not ready")
        for line in script.splitlines():
            await self._line(line.strip())
        return "ok"

    async def _line(self, line: str) -> None:
        if not line:
            return
        self.gcode.append(line)
        await self._command(line)

    async def _command(self, line: str) -> None:
        words = line.split()
        code = words[0].upper()
        params = {key.upper(): value for key, _, value in (word.partition("=") for word in words[1:]) if value}
        letters = {word[0].upper(): word[1:] for word in words[1:] if "=" not in word and word}
        if code == "SET_HEATER_TEMPERATURE":
            heater = self.heater(params.get("HEATER", ""))
            target = float(params.get("TARGET", "0"))
            name = params.get("HEATER", "")
            limits = self.objects["configfile"]["settings"].get(name) or self.objects["configfile"]["settings"].get(
                f"heater_generic {name}", {"max_temp": 300}
            )
            if target > limits["max_temp"]:
                raise RpcError(400, f"Requested temperature ({target:.1f}) out of range (0.0:{limits['max_temp']:.1f})")
            heater["target"] = target
        elif code in ("M104", "M140"):
            self.heater("extruder" if code == "M104" else "heater_bed")["target"] = float(letters.get("S", "0"))
        elif code == "M106":
            self.objects["fan"]["speed"] = max(0.0, min(1.0, float(letters.get("S", "255")) / 255))
        elif code == "M107":
            self.objects["fan"]["speed"] = 0.0
        elif code == "SET_FAN_SPEED":
            key = f"fan_generic {params.get('FAN', '')}"
            if key not in self.objects:
                raise RpcError(400, f"Unknown fan '{params.get('FAN')}'")
            self.objects[key]["speed"] = float(params.get("SPEED", "0"))
        elif code == "TURN_OFF_HEATERS":
            for obj in self.objects.values():
                if "target" in obj:
                    obj["target"] = 0.0
        elif code == "G28":
            if self.home_time_s:
                await asyncio.sleep(self.home_time_s)
            axes = "".join(sorted({w.lower() for w in letters if w in "XYZ"})) or "xyz"
            homed = set(self.objects["toolhead"]["homed_axes"]) | set(axes)
            self.objects["toolhead"]["homed_axes"] = "".join(a for a in "xyz" if a in homed)
            position = self.objects["toolhead"]["position"]
            for index, axis in enumerate("xyz"):
                if axis in axes:
                    position[index] = 0.0
        else:
            raise RpcError(400, f'Unknown command:"{code}"')

    async def print_control(self, action: str) -> str:
        """Pause, resume or cancel the print. A cancel runs CANCEL_PRINT first, the way Klipper runs the macro.

        `gcode` keeps only what the driver sent, so the macro's lines are left out of it.
        """
        stats = self.objects["print_stats"]
        if action == "pause":
            if stats["state"] != "printing":
                raise RpcError(400, "Print is not in progress")
            stats["state"] = "paused"
        elif action == "resume":
            if stats["state"] != "paused":
                raise RpcError(400, "Print is not paused, resume aborted")
            stats["state"] = "printing"
        elif action == "cancel":
            if stats["state"] not in ("printing", "paused"):
                raise RpcError(400, "Print is not in progress")
            for line in CANCEL_PRINT:
                await self._command(line)
            stats["state"] = "cancelled"
        return "ok"


class MoonrakerSim:
    def __init__(self, state: KlipperState | None = None) -> None:
        self.state = state or KlipperState()
        self.latency_s = 0.0
        self.fail_http = False
        self.fail_next = 0
        self.malformed = False
        self.api_key: str | None = None
        self.calls: list[str] = []
        self.port: int | None = None
        self._server: Any = None
        self._connections: set[Any] = set()
        self._subscriptions: dict[Any, dict[str, list[str] | None]] = {}

    @property
    def klippy_state(self) -> str:
        return str(self.state.objects["webhooks"]["state"])

    @klippy_state.setter
    def klippy_state(self, value: str) -> None:
        self.state.objects["webhooks"]["state"] = value
        self.state.objects["webhooks"]["state_message"] = {
            "shutdown": "MCU 'mcu' shutdown: Timer too close",
            "startup": "Printer is not ready",
        }.get(value, "Printer is ready")

    def _query(self, objects: dict[str, list[str] | None]) -> dict[str, Any]:
        self.state.step()
        status: dict[str, Any] = {}
        for name, fields in objects.items():
            obj = self.state.reported(name)
            if obj is None:
                continue
            status[name] = obj if not fields else {k: v for k, v in obj.items() if k in fields}
        return {"eventtime": self.state.clock(), "status": status}

    async def call(self, method: str, params: dict[str, Any] | None = None) -> Any:
        params = params or {}
        self.calls.append(method)
        if self.latency_s:
            await asyncio.sleep(self.latency_s)
        connected = self.klippy_state != "disconnected"
        if method == "server.info":
            return {"klippy_connected": True, "klippy_state": self.klippy_state, "moonraker_version": "v0.9.3-sim"}
        if method == "printer.info":
            return {
                "state": self.klippy_state,
                "state_message": self.state.objects["webhooks"]["state_message"],
                "hostname": "voron-sim",
                "software_version": "v0.12.0-sim",
            }
        if not connected:
            raise RpcError(503, "Klippy Disconnected")
        if method == "printer.objects.list":
            return {"objects": list(self.state.objects)}
        if method == "printer.objects.query":
            return self._query(params.get("objects", {}))
        if method == "printer.gcode.script":
            return await self.state.run_gcode(str(params.get("script", "")))
        if method in ("printer.print.pause", "printer.print.resume", "printer.print.cancel"):
            if self.klippy_state != "ready":
                raise RpcError(503, "Klippy is not ready")
            return await self.state.print_control(method.rsplit(".", 1)[1])
        if method == "printer.emergency_stop":
            self.klippy_state = "shutdown"
            return "ok"
        raise RpcError(404, f"Method not found: {method}")

    def http_transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self._http)

    async def _http(self, request: httpx.Request) -> httpx.Response:
        if self.fail_next > 0:
            self.fail_next -= 1
            raise httpx.ConnectError("connection reset", request=request)
        if self.fail_http:
            raise httpx.ConnectError("connection refused", request=request)
        if self.api_key is not None and request.headers.get("x-api-key") != self.api_key:
            return httpx.Response(401, json={"error": {"code": 401, "message": "Unauthorized"}})
        path = request.url.path
        try:
            method, params = self._route(request.method, path, request)
            result = await self.call(method, params)
        except RpcError as exc:
            return httpx.Response(exc.code, json={"error": {"code": exc.code, "message": exc.message}})
        if self.malformed:
            return httpx.Response(200, content=b"{not json")
        return httpx.Response(200, json={"result": result})

    def _route(self, verb: str, path: str, request: httpx.Request) -> tuple[str, dict[str, Any]]:
        if path == "/printer/objects/query" and verb == "GET":
            objects: dict[str, list[str] | None] = {}
            for key, value in parse_qsl(request.url.query.decode(), keep_blank_values=True):
                objects[key] = value.split(",") if value else None
            return "printer.objects.query", {"objects": objects}
        if path == "/printer/gcode/script" and verb == "POST":
            body = json.loads(request.content or b"{}")
            return "printer.gcode.script", {"script": body.get("script", "")}
        simple = {
            ("GET", "/server/info"): "server.info",
            ("GET", "/printer/info"): "printer.info",
            ("GET", "/printer/objects/list"): "printer.objects.list",
            ("POST", "/printer/print/pause"): "printer.print.pause",
            ("POST", "/printer/print/resume"): "printer.print.resume",
            ("POST", "/printer/print/cancel"): "printer.print.cancel",
            ("POST", "/printer/emergency_stop"): "printer.emergency_stop",
        }
        if (verb, path) in simple:
            return simple[(verb, path)], {}
        raise RpcError(404, f"Not found: {verb} {path}")

    async def start_websocket(self) -> int:
        from websockets.asyncio.server import serve

        self._server = await serve(self._ws, "127.0.0.1", 0)
        sockets = list(self._server.sockets)
        self.port = int(sockets[0].getsockname()[1])
        return self.port

    async def _ws(self, connection: Any) -> None:
        self._connections.add(connection)
        try:
            async for raw in connection:
                asyncio.create_task(self._ws_message(connection, raw))  # noqa: RUF006 (each request replies on its own)
        except Exception:  # noqa: BLE001, S110 (a dropped client just ends the session)
            pass
        finally:
            self._connections.discard(connection)
            self._subscriptions.pop(connection, None)

    async def _ws_message(self, connection: Any, raw: str | bytes) -> None:
        try:
            request = json.loads(raw)
            method, params, ident = request["method"], request.get("params") or {}, request.get("id")
        except (ValueError, KeyError, TypeError):
            await self._send(connection, {"jsonrpc": "2.0", "error": {"code": -32700, "message": "Parse error"}})
            return
        try:
            if method == "printer.objects.subscribe":
                self._subscriptions[connection] = params.get("objects", {})
                result: Any = self._query(params.get("objects", {}))
            else:
                result = await self.call(method, params)
        except RpcError as exc:
            await self._send(
                connection, {"jsonrpc": "2.0", "id": ident, "error": {"code": exc.code, "message": exc.message}}
            )
            return
        if self.malformed:
            with contextlib.suppress(Exception):
                await connection.send("{not json")
            return
        await self._send(connection, {"jsonrpc": "2.0", "id": ident, "result": result})

    async def _send(self, connection: Any, message: dict[str, Any]) -> None:
        with contextlib.suppress(Exception):
            await connection.send(json.dumps(message))

    async def notify(self) -> None:
        """Send `notify_status_update` with the subscribed objects to every subscriber."""
        for connection, objects in list(self._subscriptions.items()):
            status = self._query(objects)["status"]
            await self._send(
                connection, {"jsonrpc": "2.0", "method": "notify_status_update", "params": [status, self.state.clock()]}
            )

    async def drop_websockets(self) -> None:
        for connection in list(self._connections):
            with contextlib.suppress(Exception):
                await connection.close()

    async def close(self) -> None:
        await self.drop_websockets()
        if self._server is not None:
            self._server.close()
            with contextlib.suppress(Exception):
                await self._server.wait_closed()
            self._server = None
