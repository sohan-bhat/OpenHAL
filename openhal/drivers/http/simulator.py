"""A simulated HTTP smart plug, served through httpx.MockTransport. No sockets, no network.

Routes.

    GET  /api/info          {"model": "SIM-PLUG", "firmware": "1.4.2", "mac": "..."}
    GET  /api/status        {"relay": {"on": false}, "power": {"w": 0.0}, "dimmer": 0, "mode": "auto", "label": "..."}
    POST /api/relay         body {"on": true|false}
    PUT  /api/dimmer        body {"level": 0..255}
    GET  /api/mode?set=...  changes mode (some devices really change state on GET)
    POST /api/reboot        an action
    GET  /snapshot.jpg      a tiny JPEG
    GET  /openapi.json      an OpenAPI 3.1 document describing the routes above

Fault injection for tests and the conformance case: `online`, `delay_s`, `status_override`,
`malformed` and `require_token`.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any

import httpx

# A valid 8x8 grayscale baseline JPEG, small enough to keep inline.
TINY_JPEG = bytes.fromhex(
    "ffd8ffe000104a46494600010100000100010000ffdb004300100b0c0e0c0a100e0d0e1211101318281a181616183123251d"
    "283a333d3c3933383740485c4e404457453738506d51575f626768673e4d71797064785c656763ffc0000b08000800080101"
    "1100ffc4001f0000010501010101010100000000000000000102030405060708090a0bffc400b51000020103030204030505"
    "04040000017d01020300041105122131410613516107227114328191a1082342b1c11552d1f02433627282090a161718191a"
    "25262728292a3435363738393a434445464748494a535455565758595a636465666768696a737475767778797a8384858687"
    "88898a92939495969798999aa2a3a4a5a6a7a8a9aab2b3b4b5b6b7b8b9bac2c3c4c5c6c7c8c9cad2d3d4d5d6d7d8d9dae1e2"
    "e3e4e5e6e7e8e9eaf1f2f3f4f5f6f7f8f9faffda0008010100003f00e4ebffd9"
)

OPENAPI: dict[str, Any] = {
    "openapi": "3.1.0",
    "info": {"title": "Simulated smart plug", "version": "1.4.2"},
    "paths": {
        "/api/status": {
            "get": {
                "responses": {
                    "200": {
                        "description": "Status",
                        "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Status"}}},
                    }
                }
            }
        },
        "/api/relay": {
            "post": {
                "requestBody": {
                    "content": {
                        "application/json": {"schema": {"type": "object", "properties": {"on": {"type": "boolean"}}}}
                    }
                },
                "responses": {"200": {"description": "ok"}},
            }
        },
        "/api/dimmer": {
            "put": {
                "requestBody": {
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "properties": {"level": {"type": "integer", "minimum": 0, "maximum": 255}},
                            }
                        }
                    }
                },
                "responses": {"200": {"description": "ok"}},
            }
        },
        "/api/reboot": {"post": {"summary": "Restart the plug", "responses": {"200": {"description": "ok"}}}},
        "/api/outlets/{index}": {"get": {"responses": {"200": {"description": "one outlet"}}}},
    },
    "components": {
        "schemas": {
            "Status": {
                "type": "object",
                "properties": {
                    "relay": {"type": "object", "properties": {"on": {"type": "boolean"}}},
                    "power": {"type": "object", "properties": {"w": {"type": "number", "x-unit": "W"}}},
                    "dimmer": {"type": "integer"},
                    "mode": {"type": "string", "enum": ["auto", "manual", "eco"]},
                    "label": {"type": "string"},
                },
            }
        }
    },
}


@dataclass
class SimulatedPlug:
    """In-memory device state plus the request log. `transport()` gives an httpx transport."""

    relay: bool = False
    dimmer: int = 0
    mode: str = "auto"
    label: str = "bench plug"
    online: bool = True
    delay_s: float = 0.0
    status_override: int | None = None
    malformed: bool = False
    require_token: str | None = None
    reboots: int = 0
    log: list[tuple[str, str, Any]] = field(default_factory=list)

    @property
    def power_w(self) -> float:
        return round(3.2 + (60.0 * self.dimmer / 255.0 if self.relay else 0.0), 2)

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handle)

    def writes(self) -> list[tuple[str, str, Any]]:
        """Requests that changed state."""
        return [entry for entry in self.log if entry[0] != "GET" or "set" in str(entry[2])]

    async def handle(self, request: httpx.Request) -> httpx.Response:
        if self.delay_s:
            await asyncio.sleep(self.delay_s)
        if not self.online:
            raise httpx.ConnectError("Connection refused (simulated plug is offline)", request=request)
        body: Any = None
        if request.content:
            try:
                body = json.loads(request.content)
            except json.JSONDecodeError:
                return httpx.Response(400, json={"error": "body is not JSON"})
        path = request.url.path
        query = dict(request.url.params)
        raw_path = request.url.raw_path.decode("ascii").split("?", 1)[0]
        self.log.append((request.method, raw_path, body if body is not None else query))
        if self.require_token is not None and request.headers.get("Authorization") != f"Bearer {self.require_token}":
            return httpx.Response(401, json={"error": "unauthorized"})
        if self.status_override is not None:
            return httpx.Response(self.status_override, text="simulated failure")
        if self.malformed:
            return httpx.Response(200, text="<html>not json</html>", headers={"Content-Type": "text/html"})
        return self._route(request.method, path, query, body)

    def _route(self, method: str, path: str, query: dict[str, str], body: Any) -> httpx.Response:
        if method == "GET" and path == "/":
            return httpx.Response(200, text="simulated plug")
        if method == "GET" and path == "/api/info":
            return httpx.Response(200, json={"model": "SIM-PLUG", "firmware": "1.4.2", "mac": "02:00:00:00:00:01"})
        if method == "GET" and path == "/api/status":
            return httpx.Response(
                200,
                json={
                    "relay": {"on": self.relay},
                    "power": {"w": self.power_w},
                    "dimmer": self.dimmer,
                    "mode": self.mode,
                    "label": self.label,
                },
            )
        if method == "GET" and path == "/api/power.txt":
            return httpx.Response(200, text=f"{self.power_w}\n")
        if method == "POST" and path == "/api/relay":
            if not isinstance(body, dict) or not isinstance(body.get("on"), bool):
                return httpx.Response(422, json={"error": "on must be true or false"})
            self.relay = body["on"]
            return httpx.Response(200, json={"ok": True})
        if method == "PUT" and path == "/api/dimmer":
            level = body.get("level") if isinstance(body, dict) else None
            if not isinstance(level, int) or isinstance(level, bool) or not 0 <= level <= 255:
                return httpx.Response(422, json={"error": "level must be an integer 0 to 255"})
            self.dimmer = level
            return httpx.Response(200, json={"ok": True, "level": level})
        if method == "GET" and path == "/api/mode":
            if "set" in query:
                if query["set"] not in ("auto", "manual", "eco"):
                    return httpx.Response(422, json={"error": "unknown mode"})
                self.mode = query["set"]
            return httpx.Response(200, text=self.mode)
        if method == "POST" and path == "/api/reboot":
            delay = body.get("delay_s", 0) if isinstance(body, dict) else 0
            self.reboots += 1
            return httpx.Response(200, json={"rebooting": True, "delay_s": delay})
        if method == "GET" and path == "/snapshot.jpg":
            return httpx.Response(200, content=TINY_JPEG, headers={"Content-Type": "image/jpeg"})
        if method == "GET" and path == "/openapi.json":
            return httpx.Response(200, json=OPENAPI)
        return httpx.Response(404, json={"error": f"no route {method} {path}"})
