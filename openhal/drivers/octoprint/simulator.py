"""An OctoPrint REST API simulator, written from the OctoPrint API documentation.

`OctoPrintSim.http_transport()` returns an `httpx.MockTransport` that answers the endpoints the
driver uses (`/api/version`, `/api/printer`, `/api/printer/tool`, `/bed`, `/chamber`,
`/printhead`, `/command`, `/api/job`, `/api/printerprofiles`) with OctoPrint's status codes.
Every request needs the `X-Api-Key` header. The printer can be operational, printing, paused or
offline, and heaters drift toward their targets.

Faults. `latency_s`, `fail_http`, `fail_next`, `malformed`, `offline()`.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any

import httpx

ERROR = {"operational": False, "printing": False, "paused": False, "pausing": False, "cancelling": False}


class OctoPrintSim:
    def __init__(self, api_key: str = "octo-key") -> None:
        self.api_key = api_key
        self.temps: dict[str, dict[str, float]] = {
            "tool0": {"actual": 22.0, "target": 0.0, "offset": 0.0},
            "tool1": {"actual": 22.5, "target": 0.0, "offset": 0.0},
            "bed": {"actual": 21.0, "target": 0.0, "offset": 0.0},
            "chamber": {"actual": 24.0, "target": 0.0, "offset": 0.0},
        }
        self.connected = True
        self.error = False
        self.job_state = "idle"
        self.completion: float | None = None
        self.filename: str | None = None
        self.commands: list[str] = []
        self.homed: list[list[str]] = []
        self.requests: list[str] = []
        self.latency_s = 0.0
        self.fail_http = False
        self.fail_next = 0
        self.malformed = False
        self._last = time.monotonic()

    def offline(self) -> None:
        self.connected = False
        self.job_state = "idle"

    def _step(self) -> None:
        now = time.monotonic()
        dt = min(now - self._last, 5.0)
        self._last = now
        for heater in self.temps.values():
            goal = heater["target"] if heater["target"] > 0 else 22.0
            heater["actual"] += (goal - heater["actual"]) * min(1.0, 0.8 * dt)

    def flags(self) -> dict[str, bool]:
        if not self.connected:
            return {**ERROR, "closedOrError": True, "error": self.error, "ready": False}
        return {
            "operational": True,
            "printing": self.job_state == "printing",
            "paused": self.job_state == "paused",
            "pausing": False,
            "cancelling": False,
            "closedOrError": False,
            "error": False,
            "ready": self.job_state == "idle",
            "sdReady": False,
        }

    def state_text(self) -> str:
        if not self.connected:
            return "Offline after error" if self.error else "Offline"
        return {"printing": "Printing", "paused": "Paused"}.get(self.job_state, "Operational")

    def http_transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self._handle)

    async def _handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(f"{request.method} {request.url.path}")
        if self.latency_s:
            await asyncio.sleep(self.latency_s)
        if self.fail_next > 0:
            self.fail_next -= 1
            raise httpx.ConnectError("connection reset", request=request)
        if self.fail_http:
            raise httpx.ConnectError("connection refused", request=request)
        if request.headers.get("x-api-key") != self.api_key:
            return httpx.Response(
                403, json={"error": "You don't have the permission to access the requested resource."}
            )
        body = json.loads(request.content) if request.content else {}
        response = self._route(request.method, request.url.path, body)
        if self.malformed and response.status_code == 200:
            return httpx.Response(200, content=b"<html>not json")
        return response

    def _conflict(self, text: str) -> httpx.Response:
        return httpx.Response(409, json={"error": text})

    def _route(self, verb: str, path: str, body: dict[str, Any]) -> httpx.Response:
        self._step()
        if (verb, path) == ("GET", "/api/version"):
            return httpx.Response(200, json={"api": "0.1", "server": "1.10.2", "text": "OctoPrint 1.10.2"})
        if (verb, path) == ("GET", "/api/printerprofiles"):
            profile = {
                "id": "_default",
                "name": "Prusa i3 MK3S",
                "model": "Original Prusa i3 MK3S",
                "default": True,
                "current": True,
                "extruder": {"count": 2},
                "heatedBed": True,
                "heatedChamber": True,
            }
            return httpx.Response(200, json={"profiles": {"_default": profile}})
        if (verb, path) == ("GET", "/api/job"):
            return httpx.Response(
                200,
                json={
                    "job": {"file": {"name": self.filename}},
                    "progress": {"completion": self.completion},
                    "state": self.state_text(),
                },
            )
        if path.startswith("/api/printer") and not self.connected:
            return self._conflict("Printer is not operational")
        if (verb, path) == ("GET", "/api/printer"):
            return httpx.Response(
                200,
                json={"temperature": self.temps, "state": {"text": self.state_text(), "flags": self.flags()}},
            )
        if path in ("/api/printer/tool", "/api/printer/bed", "/api/printer/chamber"):
            return self._heater(verb, path.rsplit("/", 1)[1], body)
        if (verb, path) == ("POST", "/api/printer/printhead"):
            if body.get("command") != "home":
                return httpx.Response(400, json={"error": "Unknown command"})
            if self.job_state == "printing":
                return self._conflict("Printer is currently printing")
            axes = body.get("axes", [])
            if not axes or set(axes) - {"x", "y", "z"}:
                return httpx.Response(400, json={"error": "Invalid axes"})
            self.homed.append(list(axes))
            return httpx.Response(204)
        if (verb, path) == ("POST", "/api/printer/command"):
            self.commands += list(body.get("commands", []))
            return httpx.Response(204)
        if (verb, path) == ("POST", "/api/job"):
            return self._job(body)
        return httpx.Response(404, json={"error": "Not found"})

    def _heater(self, verb: str, kind: str, body: dict[str, Any]) -> httpx.Response:
        if verb == "GET":
            keys = [key for key in self.temps if key.startswith("tool")] if kind == "tool" else [kind]
            return httpx.Response(200, json={key: self.temps[key] for key in keys})
        if body.get("command") != "target":
            return httpx.Response(400, json={"error": "Unknown command"})
        targets = body.get("targets", {}) if kind == "tool" else {kind: body.get("target")}
        for key, value in targets.items():
            if key not in self.temps or not isinstance(value, int | float):
                return httpx.Response(400, json={"error": f"Invalid target for {key}"})
        for key, value in targets.items():
            self.temps[key]["target"] = float(value or 0)
        return httpx.Response(204)

    def _job(self, body: dict[str, Any]) -> httpx.Response:
        command, action = body.get("command"), body.get("action")
        if command == "pause":
            if action == "pause" and self.job_state == "printing":
                self.job_state = "paused"
                return httpx.Response(204)
            if action == "resume" and self.job_state == "paused":
                self.job_state = "printing"
                return httpx.Response(204)
            return self._conflict("Printer is not printing or paused")
        if command == "cancel":
            if self.job_state not in ("printing", "paused"):
                return self._conflict("Printer is neither printing nor paused")
            self.job_state = "idle"
            return httpx.Response(204)
        return httpx.Response(400, json={"error": "Unknown command"})
