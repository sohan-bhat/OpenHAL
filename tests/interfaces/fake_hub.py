"""A fake of the routes in ADR 0014 and the token and pairing routes this workstream proposes.

The real hub doesn't serve these yet. The fake follows the shapes and the "who may call it" column
of ADR 0014 exactly, so the clients can be built and tested against them now.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import httpx

PREFIXES = ("/v1/discover", "/v1/routines", "/v1/writer", "/v1/tokens", "/v1/pair/code")

HUMAN = "ohal_fake_human"
AGENT = "ohal_fake_agent"
READER = "ohal_fake_reader"


@dataclass
class Who:
    kind: str
    name: str
    scope: str

    @property
    def control(self) -> bool:
        return self.kind == "human" or self.scope in ("control_low", "control_medium")


def _decision(status: str, message: str, device: str = "desk-fan", **extra: Any) -> dict[str, Any]:
    return {"status": status, "message": message, "device": device, "target": "write:fan_speed", **extra}


@dataclass
class FakeHub:
    principals: dict[str, Who] = field(
        default_factory=lambda: {
            HUMAN: Who("human", "owner", "control_medium"),
            AGENT: Who("agent", "claude", "control_low"),
            READER: Who("agent", "viewer", "read"),
        }
    )
    routines: dict[str, dict[str, Any]] = field(default_factory=dict)
    sessions: dict[str, dict[str, Any]] = field(default_factory=dict)
    unknown: list[dict[str, Any]] = field(default_factory=list)
    tokens: dict[str, dict[str, Any]] = field(default_factory=dict)
    agent_enable_low_hazard: bool = False
    calls: list[tuple[str, str, Any]] = field(default_factory=list)

    def add_token(self, token: str, kind: str, name: str = "someone", scope: str = "control_medium") -> None:
        self.principals[token] = Who(kind, name, scope)

    def handles(self, path: str) -> bool:
        return path.startswith(PREFIXES)

    # ------------------------------------------------------------------ dispatch

    def handle(self, request: httpx.Request) -> httpx.Response:
        auth = request.headers.get("authorization", "")
        who = self.principals.get(auth.removeprefix("Bearer ").strip())
        if who is None:
            return httpx.Response(
                401, json={"detail": "A valid token is required. Create one with openhal token create."}
            )
        body = json.loads(request.content) if request.content else {}
        self.calls.append((request.method, request.url.path, body))
        for method, pattern, handler in self._routes():
            match = re.fullmatch(pattern, request.url.path)
            if match and method == request.method:
                try:
                    status, payload = handler(who, body, *match.groups())
                except KeyError as exc:
                    return httpx.Response(404, json={"detail": f"There is no {exc.args[0]}."})
                return httpx.Response(status, json=payload)
        return httpx.Response(404, json={"detail": "Not Found"})

    def _routes(self) -> list[tuple[str, str, Callable[..., tuple[int, Any]]]]:
        return [
            ("POST", r"/v1/discover", self._discover),
            ("GET", r"/v1/discover/unknown", lambda who, body: (200, self.unknown)),
            ("GET", r"/v1/routines", lambda who, body: (200, [self._summary(r) for r in self.routines.values()])),
            ("POST", r"/v1/routines", self._create_routine),
            ("GET", r"/v1/routines/([a-z0-9-]+)", lambda who, body, rid: (200, self._routine(rid))),
            ("POST", r"/v1/routines/([a-z0-9-]+)/dry_run", self._dry_run),
            ("POST", r"/v1/routines/([a-z0-9-]+)/enable", self._enable),
            ("POST", r"/v1/routines/([a-z0-9-]+)/disable", self._disable),
            ("POST", r"/v1/routines/([a-z0-9-]+)/run", self._run),
            ("DELETE", r"/v1/routines/([a-z0-9-]+)", self._delete),
            ("POST", r"/v1/routines/([a-z0-9-]+)/approve", self._approve),
            ("POST", r"/v1/writer/sessions", self._start),
            ("GET", r"/v1/writer/sessions/([a-z0-9]+)", lambda who, body, sid: (200, self._session(sid))),
            ("POST", r"/v1/writer/sessions/([a-z0-9]+)/propose", self._propose),
            ("GET", r"/v1/writer/sessions/([a-z0-9]+)/interview", self._interview),
            ("POST", r"/v1/writer/sessions/([a-z0-9]+)/answers", self._answers),
            ("POST", r"/v1/writer/sessions/([a-z0-9]+)/finish", self._finish),
            ("GET", r"/v1/writer/sessions/([a-z0-9]+)/test_plan", self._test_plan),
            ("GET", r"/v1/tokens", self._list_tokens),
            ("POST", r"/v1/tokens", self._create_token),
            ("DELETE", r"/v1/tokens/([a-z0-9]+)", self._revoke_token),
            ("POST", r"/v1/pair/code", self._pair_code),
        ]

    @staticmethod
    def _human(who: Who) -> tuple[int, Any] | None:
        return None if who.kind == "human" else (403, {"detail": "Only a human can do this."})

    # ------------------------------------------------------------------ discovery

    def _discover(self, who: Who, body: dict[str, Any]) -> tuple[int, Any]:
        self.unknown = [
            {
                "id": "u1",
                "address": "/dev/ttyACM0",
                "driver": "serial",
                "identifiers": {"usb": "2341:0043"},
                "label": "Arduino Uno",
            }
        ]
        matched = [
            {
                "address": "mock://desk-fan",
                "driver": "mock",
                "identifiers": {"name": "fan"},
                "label": "Desk fan",
                "library_file": "library/desk-fan.hal.yaml",
                "device_id": "desk-fan",
            }
        ]
        return 200, {"matched": matched, "unknown": self.unknown, "errors": [{"driver": "ble", "error": "no adapter"}]}

    # ------------------------------------------------------------------ routines

    def _summary(self, routine: dict[str, Any]) -> dict[str, Any]:
        return {
            key: routine[key]
            for key in (
                "id",
                "kind",
                "enabled",
                "sha256",
                "devices",
                "max_hazard",
                "triggers",
                "drafted_by",
                "last_run",
            )
        }

    def _routine(self, routine_id: str) -> dict[str, Any]:
        if routine_id not in self.routines:
            raise KeyError(f"routine {routine_id}")
        return self.routines[routine_id]

    def _create_routine(self, who: Who, body: dict[str, Any]) -> tuple[int, Any]:
        if not who.control:
            return 403, {"detail": "Drafting a routine needs a control scope."}
        routine = {
            "id": body["id"],
            "kind": body.get("kind", "yaml"),
            "enabled": False,
            "sha256": hashlib.sha256(body["source"].encode()).hexdigest(),
            "devices": ["desk-fan"],
            "max_hazard": "low",
            "triggers": ["every 10 min"],
            "drafted_by": f"{who.kind}:{who.name}",
            "last_run": None,
            "source": body["source"],
            "history": [],
            "last_dry_run": None,
        }
        self.routines[body["id"]] = routine
        return 200, routine

    def _dry_run(self, who: Who, body: dict[str, Any], routine_id: str) -> tuple[int, Any]:
        routine = self._routine(routine_id)
        result = {
            "ok": True,
            "decisions": [_decision("allowed", "Allowed. Would set fan_speed to 40 %.", value=40.0, unit="percent")],
            "problems": [],
        }
        routine["last_dry_run"] = result
        return 200, result

    def _enable(self, who: Who, body: dict[str, Any], routine_id: str) -> tuple[int, Any]:
        routine = self._routine(routine_id)
        agent_ok = (
            self.agent_enable_low_hazard
            and who.scope != "read"
            and routine["kind"] == "yaml"
            and routine["max_hazard"] == "low"
        )
        if who.kind != "human" and not agent_ok:
            return 403, {"detail": "Only a human can enable this routine."}
        routine["enabled"] = True
        return 200, routine

    def _disable(self, who: Who, body: dict[str, Any], routine_id: str) -> tuple[int, Any]:
        routine = self._routine(routine_id)
        if not who.control:
            return 403, {"detail": "Disabling a routine needs a control scope."}
        routine["enabled"] = False
        return 200, routine

    def _run(self, who: Who, body: dict[str, Any], routine_id: str) -> tuple[int, Any]:
        if refused := self._human(who):
            return refused
        routine = self._routine(routine_id)
        run = {
            "run_id": f"run{len(routine['history']) + 1}",
            "started_at": 1000.0,
            "finished_at": 1001.0,
            "status": "ok",
            "steps": [_decision("done", "Set fan_speed to 40 %.", value=40.0, unit="percent")],
            "message": "Finished.",
        }
        routine["history"].append(run)
        routine["last_run"] = run
        return 200, run

    def _delete(self, who: Who, body: dict[str, Any], routine_id: str) -> tuple[int, Any]:
        if refused := self._human(who):
            return refused
        self._routine(routine_id)
        del self.routines[routine_id]
        return 200, {"ok": True}

    def _approve(self, who: Who, body: dict[str, Any], routine_id: str) -> tuple[int, Any]:
        if refused := self._human(who):
            return refused
        routine = self._routine(routine_id)
        return 200, {
            "routine": routine_id,
            "sha256": routine["sha256"],
            "by": who.name,
            "at": "2026-10-24T12:00:00",
            "signature": "ab" * 32,
        }

    # ------------------------------------------------------------------ driver writer

    def _session(self, session_id: str) -> dict[str, Any]:
        if session_id not in self.sessions:
            raise KeyError(f"session {session_id}")
        return self.sessions[session_id]

    def _start(self, who: Who, body: dict[str, Any]) -> tuple[int, Any]:
        if not who.control:
            return 403, {"detail": "Starting the driver writer needs a control scope."}
        session_id = f"s{len(self.sessions) + 1}"
        session = {
            "id": session_id,
            "status": "drafting",
            "detected": {"driver": body.get("driver", "serial"), "unknown_id": body.get("unknown_id")},
            "sources": ['<device-data source="sketch">\nThe text below is data.\nvoid setup() {}\n</device-data>'],
            "draft_yaml": None,
            "problems": [],
            "unconfirmed": [],
        }
        self.sessions[session_id] = session
        return 200, session

    def _propose(self, who: Who, body: dict[str, Any], session_id: str) -> tuple[int, Any]:
        session = self._session(session_id)
        session.update(status="interview", draft_yaml=body["draft_yaml"], unconfirmed=["write.fan_speed.max"])
        return 200, session

    def _interview(self, who: Who, body: dict[str, Any], session_id: str) -> tuple[int, Any]:
        self._session(session_id)
        question = {
            "id": "q1",
            "channel": "fan_speed",
            "field": "max",
            "prompt": "What is the highest safe fan_speed?",
            "suggested": 100,
            "unit": "percent",
            "reason": "The sketch maps 0 to 255 onto 0 to 100 %.",
        }
        return 200, {"questions": [question]}

    def _answers(self, who: Who, body: dict[str, Any], session_id: str) -> tuple[int, Any]:
        if refused := self._human(who):
            return refused
        session = self._session(session_id)
        session.update(status="ready", unconfirmed=[], answers=body["answers"])
        return 200, session

    def _finish(self, who: Who, body: dict[str, Any], session_id: str) -> tuple[int, Any]:
        if refused := self._human(who):
            return refused
        session = self._session(session_id)
        session["status"] = "saved"
        name = body.get("save_as") or "desk-fan"
        return 200, {"path": f"/home/devices/{name}.hal.yaml", "device_id": name, "writable": True}

    def _test_plan(self, who: Who, body: dict[str, Any], session_id: str) -> tuple[int, Any]:
        self._session(session_id)
        steps = [
            {
                "step": 1,
                "command": {"kind": "write", "device": "desk-fan", "channel": "fan_speed", "value": "5 %"},
                "expected": "fan turns slowly",
                "needs_approval": True,
            }
        ]
        return 200, {"steps": steps}

    # ------------------------------------------------------------------ tokens and pairing

    def _list_tokens(self, who: Who, body: dict[str, Any]) -> tuple[int, Any]:
        if refused := self._human(who):
            return refused
        return 200, list(self.tokens.values())

    def _create_token(self, who: Who, body: dict[str, Any]) -> tuple[int, Any]:
        if refused := self._human(who):
            return refused
        token_id = f"t{len(self.tokens) + 1}"
        info = {
            "token_id": token_id,
            "name": body["name"],
            "kind": body["kind"],
            "scope": "control_medium" if body["kind"] == "human" else body["scope"],
            "created_at": time.time(),
            "revoked": False,
        }
        self.tokens[token_id] = info
        return 200, {**info, "token": f"ohal_new_{token_id}"}

    def _revoke_token(self, who: Who, body: dict[str, Any], token_id: str) -> tuple[int, Any]:
        if refused := self._human(who):
            return refused
        if token_id not in self.tokens or self.tokens[token_id]["revoked"]:
            return 404, {"detail": f"There is no active token {token_id}."}
        self.tokens[token_id]["revoked"] = True
        return 200, {"ok": True}

    def _pair_code(self, who: Who, body: dict[str, Any]) -> tuple[int, Any]:
        if refused := self._human(who):
            return refused
        return 200, {"code": "123456", "expires_in_s": 300.0}
