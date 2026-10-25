"""A Home Assistant simulator for the REST and WebSocket APIs, written from the developer docs.

`HomeAssistantSim` keeps a set of entities (a dimmable light, a switch, a fan, a number, a
select, sensors and a binary sensor) and runs the services the driver calls.

- `sim.http_transport()` is an `httpx.MockTransport` for `GET /api/`, `GET /api/config`,
  `GET /api/states/<entity_id>` and `POST /api/services/<domain>/<service>`. Every request needs
  `Authorization: Bearer <token>`.
- `await sim.start_websocket()` serves `/api/websocket` on 127.0.0.1 with the auth handshake,
  `get_states`, `call_service` and `subscribe_entities` with its compressed event format.

Faults. `latency_s`, `fail_http`, `fail_next`, `malformed`, `set_unavailable(entity_id)`,
`drop_websockets()`.
"""

from __future__ import annotations

import asyncio
import contextlib
import copy
import json
from typing import Any

import httpx


class ServiceError(Exception):
    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def default_entities() -> dict[str, dict[str, Any]]:
    return {
        "light.desk_lamp": {
            "state": "off",
            "attributes": {
                "friendly_name": "Desk lamp",
                "brightness": None,
                "color_temp_kelvin": None,
                "min_color_temp_kelvin": 2200,
                "max_color_temp_kelvin": 6500,
                "supported_color_modes": ["color_temp"],
            },
        },
        "switch.heater_plug": {"state": "off", "attributes": {"friendly_name": "Heater plug"}},
        "fan.ceiling": {
            "state": "off",
            "attributes": {
                "friendly_name": "Ceiling fan",
                "percentage": 0,
                "percentage_step": 25.0,
                "preset_modes": ["breeze", "sleep"],
                "preset_mode": None,
            },
        },
        "number.pump_speed": {
            "state": "20.0",
            "attributes": {"friendly_name": "Pump speed", "min": 0, "max": 100, "step": 5, "unit_of_measurement": "%"},
        },
        "select.mode": {
            "state": "eco",
            "attributes": {"friendly_name": "Mode", "options": ["eco", "comfort", "away"]},
        },
        "sensor.room_temperature": {
            "state": "71.6",
            "attributes": {
                "friendly_name": "Room temperature",
                "unit_of_measurement": "°F",
                "device_class": "temperature",
            },
        },
        "sensor.firmware": {"state": "1.4.2", "attributes": {"friendly_name": "Firmware"}},
        "binary_sensor.window": {"state": "off", "attributes": {"friendly_name": "Window", "device_class": "window"}},
        "lock.front_door": {"state": "locked", "attributes": {"friendly_name": "Front door"}},
    }


class HomeAssistantSim:
    def __init__(self, token: str = "ha-token") -> None:  # noqa: S107 (a fake token for the simulator)
        self.token = token
        self.entities = default_entities()
        self.calls: list[tuple[str, str, dict[str, Any]]] = []
        self.latency_s = 0.0
        self.fail_http = False
        self.fail_next = 0
        self.malformed = False
        self.port: int | None = None
        self._server: Any = None
        self._connections: set[Any] = set()
        self._subscribers: list[tuple[Any, int, set[str]]] = []
        self._tasks: set[asyncio.Task[None]] = set()

    def set_unavailable(self, entity_id: str) -> None:
        self.entities[entity_id]["state"] = "unavailable"

    def call_service(self, domain: str, service: str, data: dict[str, Any]) -> list[dict[str, Any]]:
        entity_id = data.get("entity_id")
        self.calls.append((domain, service, dict(data)))
        if not isinstance(entity_id, str) or entity_id not in self.entities:
            raise ServiceError(400, f"Referenced entities {entity_id} are missing or not currently available")
        if not entity_id.startswith(f"{domain}."):
            raise ServiceError(400, f"Entity {entity_id} does not support {domain}.{service}")
        entity = self.entities[entity_id]
        if entity["state"] == "unavailable":
            raise ServiceError(500, f"Entity {entity_id} is unavailable")
        attrs = entity["attributes"]
        if service == "turn_on":
            entity["state"] = "on"
            if domain == "light":
                if "brightness_pct" in data:
                    attrs["brightness"] = round(float(data["brightness_pct"]) * 255 / 100)
                    if attrs["brightness"] == 0:
                        entity["state"] = "off"
                elif attrs.get("brightness") is None:
                    attrs["brightness"] = 255
                if "color_temp_kelvin" in data:
                    attrs["color_temp_kelvin"] = int(data["color_temp_kelvin"])
            if domain == "fan" and not attrs.get("percentage"):
                attrs["percentage"] = 100
        elif service == "turn_off":
            entity["state"] = "off"
            if domain == "light":
                attrs["brightness"] = None
            if domain == "fan":
                attrs["percentage"] = 0
        elif (domain, service) == ("fan", "set_percentage"):
            attrs["percentage"] = int(data["percentage"])
            entity["state"] = "on" if attrs["percentage"] else "off"
        elif (domain, service) == ("fan", "set_preset_mode"):
            if data.get("preset_mode") not in attrs["preset_modes"]:
                raise ServiceError(400, f"The preset_mode {data.get('preset_mode')} is not a valid preset_mode")
            attrs["preset_mode"] = data["preset_mode"]
        elif service == "set_value":
            value = float(data["value"])
            if not attrs["min"] <= value <= attrs["max"]:
                raise ServiceError(400, f"Value {value} for {entity_id} is outside valid range")
            entity["state"] = str(value)
        elif service == "select_option":
            if data.get("option") not in attrs["options"]:
                raise ServiceError(400, f"Option {data.get('option')} is not valid for {entity_id}")
            entity["state"] = data["option"]
        else:
            raise ServiceError(400, f"Service {domain}.{service} not found")
        task = asyncio.get_running_loop().create_task(self.notify(entity_id))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return [self.state(entity_id)]

    def state(self, entity_id: str) -> dict[str, Any]:
        entity = self.entities[entity_id]
        return {
            "entity_id": entity_id,
            "state": entity["state"],
            "attributes": copy.deepcopy(entity["attributes"]),
            "last_changed": "2026-10-24T12:00:00+00:00",
        }

    def http_transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self._http)

    async def _http(self, request: httpx.Request) -> httpx.Response:
        if self.latency_s:
            await asyncio.sleep(self.latency_s)
        if self.fail_next > 0:
            self.fail_next -= 1
            raise httpx.ConnectError("connection reset", request=request)
        if self.fail_http:
            raise httpx.ConnectError("connection refused", request=request)
        if request.headers.get("authorization") != f"Bearer {self.token}":
            return httpx.Response(401, text="401: Unauthorized")
        if self.malformed:
            return httpx.Response(200, content=b"<!doctype html>")
        path = request.url.path
        if (request.method, path) == ("GET", "/api/"):
            return httpx.Response(200, json={"message": "API running."})
        if (request.method, path) == ("GET", "/api/config"):
            return httpx.Response(200, json={"version": "2026.10.2", "location_name": "Sim Home"})
        if request.method == "GET" and path.startswith("/api/states/"):
            entity_id = path.removeprefix("/api/states/")
            if entity_id not in self.entities:
                return httpx.Response(404, json={"message": "Entity not found."})
            return httpx.Response(200, json=self.state(entity_id))
        if request.method == "POST" and path.startswith("/api/services/"):
            domain, _, service = path.removeprefix("/api/services/").partition("/")
            try:
                changed = self.call_service(domain, service, json.loads(request.content or b"{}"))
            except ServiceError as exc:
                return httpx.Response(exc.code, json={"message": exc.message})
            return httpx.Response(200, json=changed)
        return httpx.Response(404, json={"message": "Not found"})

    async def start_websocket(self) -> int:
        from websockets.asyncio.server import serve

        self._server = await serve(self._ws, "127.0.0.1", 0)
        self.port = int(next(iter(self._server.sockets)).getsockname()[1])
        return self.port

    async def _ws(self, connection: Any) -> None:
        self._connections.add(connection)
        try:
            await connection.send(json.dumps({"type": "auth_required", "ha_version": "2026.10.2"}))
            auth = json.loads(await connection.recv())
            if auth.get("type") != "auth" or auth.get("access_token") != self.token:
                await connection.send(json.dumps({"type": "auth_invalid", "message": "Invalid access token"}))
                return
            await connection.send(json.dumps({"type": "auth_ok", "ha_version": "2026.10.2"}))
            async for raw in connection:
                task = asyncio.create_task(self._ws_command(connection, raw))
                self._tasks.add(task)
                task.add_done_callback(self._tasks.discard)
        except Exception:  # noqa: BLE001, S110 (a dropped client ends its session)
            pass
        finally:
            self._connections.discard(connection)
            self._subscribers = [item for item in self._subscribers if item[0] is not connection]

    async def _ws_command(self, connection: Any, raw: str | bytes) -> None:
        if self.latency_s:
            await asyncio.sleep(self.latency_s)
        try:
            message = json.loads(raw)
            ident, kind = message["id"], message["type"]
        except (ValueError, KeyError, TypeError):
            return
        if self.malformed:
            await self._send(connection, {"id": ident, "type": "result"})
            return
        if kind == "get_states":
            await self._result(connection, ident, [self.state(entity_id) for entity_id in self.entities])
        elif kind == "call_service":
            data = {**(message.get("service_data") or {}), **(message.get("target") or {})}
            try:
                self.call_service(message.get("domain", ""), message.get("service", ""), data)
            except ServiceError as exc:
                await self._send(
                    connection,
                    {
                        "id": ident,
                        "type": "result",
                        "success": False,
                        "error": {"code": "home_assistant_error", "message": exc.message},
                    },
                )
                return
            await self._result(connection, ident, {"context": {"id": "sim"}})
        elif kind == "subscribe_entities":
            wanted = set(message.get("entity_ids") or self.entities)
            self._subscribers.append((connection, ident, wanted))
            await self._result(connection, ident, None)
            added = {
                entity_id: {"s": self.entities[entity_id]["state"], "a": self.entities[entity_id]["attributes"]}
                for entity_id in wanted
                if entity_id in self.entities
            }
            await self._send(connection, {"id": ident, "type": "event", "event": {"a": added}})
        elif kind == "ping":
            await self._send(connection, {"id": ident, "type": "pong"})
        else:
            await self._send(
                connection,
                {
                    "id": ident,
                    "type": "result",
                    "success": False,
                    "error": {"code": "unknown_command", "message": "Unknown command."},
                },
            )

    async def notify(self, entity_id: str) -> None:
        entity = self.entities[entity_id]
        change = {entity_id: {"+": {"s": entity["state"], "a": copy.deepcopy(entity["attributes"])}}}
        for connection, ident, wanted in list(self._subscribers):
            if entity_id in wanted:
                await self._send(connection, {"id": ident, "type": "event", "event": {"c": change}})

    async def _result(self, connection: Any, ident: int, result: Any) -> None:
        await self._send(connection, {"id": ident, "type": "result", "success": True, "result": result})

    async def _send(self, connection: Any, message: dict[str, Any]) -> None:
        with contextlib.suppress(Exception):
            await connection.send(json.dumps(message))

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
