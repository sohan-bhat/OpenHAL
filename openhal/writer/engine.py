"""Driver writer sessions (ADR 0006, routes in ADR 0014).

A session turns an unknown device into a confirmed device file in this order.

1. Library match. Discovery already offers library files, so an unknown device has none.
2. Protocol match and self-description. If a driver can talk to the device, the driver connects
   with its read-only commands and `describe()` maps what the device exposes into sections.
3. A sketch, parsed statically (writer/sketch.py).
4. A manual, with its commands extracted and every one unconfirmed (writer/manual.py).
5. A draft from any of those, or from the user's agent through `propose`. Every limit in a draft
   is forced to suggested, and any confirmation in the draft is dropped.
6. The limits interview. A human principal answers every question, and the confirmed entry is
   bound to the hash of the limits.
7. The staged test plan, generated and dry-run through a kernel, never executed.
8. Saving. The file goes into the devices folder with provenance, plus a library submission
   bundle with a test report template.

Text from sketches, manuals and devices is only ever returned inside data blocks.
"""

from __future__ import annotations

import asyncio
import contextlib
import copy
import datetime as dt
import re
import secrets
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

import yaml

from openhal._brand import DEVICE_FILE_SUFFIX
from openhal.drivers import registry
from openhal.kernel.principals import Principal
from openhal.spec.loader import DeviceFileError, from_data, parse_yaml
from openhal.spec.models import PRIMARY_PARAM
from openhal.writer import interview, manual, plan, sketch

if TYPE_CHECKING:
    from openhal.hub.hub import Hub

MAX_SESSIONS: Final = 50
DESCRIBE_TIMEOUT_S: Final = 20.0
SKETCH_SUFFIXES: Final = (".ino", ".pde", ".cpp", ".c", ".h", ".hpp")
FILE_NAME: Final = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


class WriterError(ValueError):
    """A request the writer refuses. The message says why and what to do."""


class NotHumanError(PermissionError):
    """Answering the limits interview or saving a device file takes a human principal."""


@dataclass
class Session:
    id: str
    created_by: str
    created_at: float
    status: str = "detecting"
    detected: dict[str, Any] = field(default_factory=dict)
    sources: list[tuple[str, str]] = field(default_factory=list)
    draft: dict[str, Any] | None = None
    confirmed: dict[str, Any] | None = None
    answers: dict[str, Any] = field(default_factory=dict)
    problems: list[str] = field(default_factory=list)
    saved_path: str | None = None


def _dump(data: dict[str, Any]) -> str:
    return yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=100)


def force_suggested(data: dict[str, Any]) -> dict[str, Any]:
    """Nothing a draft says can confirm a limit. Mark every limit suggested and drop confirmations."""
    cleaned = copy.deepcopy(data)
    for key in ("confirmed", "approvals"):
        cleaned.pop(key, None)
    for spec in (cleaned.get("write") or {}).values():
        if isinstance(spec, dict):
            spec.pop("confirmed", None)
            spec["suggested"] = True
    for spec in (cleaned.get("actions") or {}).values():
        if isinstance(spec, dict):
            spec.pop("confirmed", None)
            spec["suggested"] = True
    provenance = cleaned.get("provenance")
    if isinstance(provenance, dict):
        provenance.pop("verification", None)
    return cleaned


OWN_KEYS: Final = frozenset({"driver", "source", "kind", "type", "unit", "status"})
"""Detected fields OpenHAL sets itself. Every other string came from a device, sketch or manual."""


def _as_data(value: Any, source: str, key: str | None = None) -> Any:
    """Detected facts with every string a device, sketch or manual produced wrapped as data (red team RT-02)."""
    from openhal.hub.views import data_block

    if isinstance(value, str):
        return (
            value if key in OWN_KEYS else data_block(f"{source} {key or 'value'}", value, "a sketch, manual or device")
        )
    if isinstance(value, dict):
        return {name: _as_data(item, source, str(name)) for name, item in value.items()}
    if isinstance(value, list):
        return [_as_data(item, source, key) for item in value]
    return value


class WriterEngine:
    def __init__(self, hub: Hub) -> None:
        self.hub = hub
        self.sessions: dict[str, Session] = {}

    def view(self, session: Session) -> dict[str, Any]:
        from openhal.hub.views import data_block

        draft = session.confirmed or session.draft
        unconfirmed: list[str] = []
        if session.draft is not None and session.confirmed is None:
            unconfirmed = [q.id for q in interview.questions(session.draft) if q.id not in session.answers]
        return {
            "id": session.id,
            "status": session.status,
            "detected": _as_data(session.detected, "driver writer findings"),
            "sources": [data_block(label, text, "a sketch, manual or device") for label, text in session.sources],
            "draft_yaml": _dump(draft) if draft is not None else None,
            "problems": session.problems,
            "unconfirmed": unconfirmed,
        }

    def get(self, session_id: str) -> Session:
        session = self.sessions.get(session_id)
        if session is None:
            raise KeyError(f"There is no driver writer session {session_id!r}.")
        return session

    async def start(
        self,
        who: Principal,
        *,
        unknown_id: str | None = None,
        driver: str | None = None,
        params: dict[str, Any] | None = None,
        sketch_path: str | None = None,
        manual_text: str | None = None,
    ) -> Session:
        if not (unknown_id or driver or sketch_path or manual_text):
            raise WriterError("Give an unknown device id, a driver, a sketch or a manual to start from.")
        if len(self.sessions) >= MAX_SESSIONS:
            oldest = min(self.sessions.values(), key=lambda item: item.created_at)
            del self.sessions[oldest.id]
        session = Session(secrets.token_hex(4), who.label, time.time())
        self.sessions[session.id] = session
        self.hub.audit.append("writer_start", who.label, target=session.id)
        drafts: list[dict[str, Any]] = []

        address = None
        if unknown_id:
            unknown = self._unknown(unknown_id)
            driver = driver or unknown.driver
            address = unknown.address
            session.detected.update(
                unknown_id=unknown_id, driver=unknown.driver, address=unknown.address, identifiers=unknown.identifiers
            )
            if unknown.label:
                session.detected["label"] = unknown.label
        if driver:
            described = await self._describe(session, driver, address, params or {})
            if described is not None:
                drafts.append(described)
        if sketch_path:
            drafts.append(self._from_sketch(session, sketch_path))
        if manual_text:
            drafts.append(self._from_manual(session, manual_text))

        merged = self._merge(drafts)
        if merged is not None:
            self._set_draft(session, merged)
        else:
            session.status = "drafting"
        return session

    def _unknown(self, unknown_id: str) -> Any:
        result = self.hub.last_discovery
        for unknown in getattr(result, "unknown", []):
            if unknown.id == unknown_id:
                return unknown
        raise WriterError(f"There is no unknown device {unknown_id!r}. Run openhal discover first.")

    async def _describe(
        self, session: Session, driver: str, address: str | None, params: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Connect with the driver's read-only commands and ask it to describe the device."""
        try:
            driver_class = registry.load(driver)
        except registry.UnknownDriver as exc:
            session.problems.append(str(exc))
            return None
        connect: dict[str, Any] = dict(params)
        if address and PRIMARY_PARAM.get(driver, "target") not in connect:
            connect = {**registry.connect_params(driver, address), **connect}
        try:
            probe_file = from_data(
                {"device": "Device being described", "connect": {"driver": driver, "params": connect}}
            )
            instance = driver_class(probe_file)
        except (DeviceFileError, ValueError) as exc:
            session.problems.append(f"The {driver} driver can't use these parameters. {exc}")
            return None
        session.detected["driver"] = driver
        try:
            await asyncio.wait_for(instance.connect(), DESCRIBE_TIMEOUT_S)
            identity = await asyncio.wait_for(instance.identify(), DESCRIBE_TIMEOUT_S)
            described = await asyncio.wait_for(instance.describe(), DESCRIBE_TIMEOUT_S)
        except Exception as exc:  # noqa: BLE001 (any driver failure is a session problem, not a crash)
            session.problems.append(f"The {driver} driver couldn't describe the device. {type(exc).__name__}: {exc}")
            return None
        finally:
            with contextlib.suppress(Exception):
                await asyncio.wait_for(instance.close(), 5.0)
        if identity:
            session.detected["identity"] = identity
            session.sources.append((f"{driver} identity", "\n".join(f"{k}: {v}" for k, v in identity.items())))
        if not described:
            session.problems.append(
                f"The {driver} driver can't describe this device on its own. Add a sketch or manual."
            )
            return None
        data = dict(described)
        device = data.pop("device", None)
        name = device.get("name") if isinstance(device, dict) else None
        primary = connect.pop(PRIMARY_PARAM.get(driver, "target"), "auto")
        data = {
            "device": name or session.detected.get("label") or "New device",
            "connect": {driver: primary, **connect},
            **data,
        }
        source = "self-described" if driver == "openhal-firmware" else "driver-describe"
        data["provenance"] = {"source": source, "tool": "openhal driver writer"}
        session.detected["source"] = source
        return data

    def _from_sketch(self, session: Session, sketch_path: str) -> dict[str, Any]:
        path = Path(sketch_path).expanduser()
        if path.suffix.lower() not in SKETCH_SUFFIXES or not path.is_file():
            raise WriterError(f"{sketch_path} is not a sketch file. Give an .ino, .cpp or .h file.")
        if path.stat().st_size > sketch.MAX_SKETCH_BYTES:
            raise WriterError("The sketch is too large. Point the writer at the main .ino file.")
        text = path.read_text(encoding="utf-8", errors="replace")
        findings = sketch.parse(text)
        session.detected["sketch"] = findings.view()
        session.sources.append((f"sketch {path.name}", text))
        session.problems.extend(findings.notes)
        name = (findings.openhal_product or path.stem).replace("-", " ").replace("_", " ").strip().capitalize()
        return sketch.draft(findings, device_name=name or "Arduino board")

    def _from_manual(self, session: Session, text: str) -> dict[str, Any]:
        commands = manual.extract(text)
        session.detected["manual_commands"] = [command.view() for command in commands]
        session.sources.append(("manual", text[:20_000]))
        if not commands:
            session.problems.append("No commands were found in the manual text. Paste the command reference section.")
        sections = manual.draft_sections(commands)
        sections["provenance"] = {"source": "manual", "tool": "openhal driver writer"}
        return sections

    @staticmethod
    def _merge(drafts: list[dict[str, Any]]) -> dict[str, Any] | None:
        """The first complete draft wins. Later ones only add channels it doesn't have."""
        complete = [draft for draft in drafts if "device" in draft and "connect" in draft]
        if not complete:
            return None
        merged = copy.deepcopy(complete[0])
        for extra in drafts:
            if extra is complete[0]:
                continue
            for section in ("read", "write", "actions"):
                for name, spec in (extra.get(section) or {}).items():
                    merged.setdefault(section, {}).setdefault(name, spec)
            if extra.get("notes") and not merged.get("notes"):
                merged["notes"] = extra["notes"]
        return merged

    def _set_draft(self, session: Session, data: dict[str, Any]) -> None:
        cleaned = force_suggested(data)
        session.confirmed = None
        session.answers = {}
        try:
            from_data(cleaned)
        except DeviceFileError as exc:
            session.draft = cleaned
            session.status = "drafting"
            session.problems = [problem for problem in session.problems if not problem.startswith("Draft. ")]
            session.problems.extend(f"Draft. {problem}" for problem in exc.problems)
            return
        session.draft = cleaned
        session.status = "interview"

    def propose(self, who: Principal, session_id: str, draft_yaml: str) -> Session:
        session = self.get(session_id)
        if session.status == "saved":
            raise WriterError("This session is saved already. Start a new one to change the file.")
        try:
            data = parse_yaml(draft_yaml)
        except DeviceFileError as exc:
            raise WriterError(" ".join(exc.problems)) from exc
        if not isinstance(data, dict):
            raise WriterError("A draft must be a device file mapping.")
        given = data.get("provenance")
        provenance: dict[str, Any] = dict(given) if isinstance(given, dict) else {}
        provenance.setdefault("source", session.detected.get("source", "hand-written"))
        provenance["tool"] = "openhal driver writer"
        data["provenance"] = provenance
        self._set_draft(session, data)
        self.hub.audit.append("writer_propose", who.label, target=session.id, status=session.status)
        return session

    def questions(self, session_id: str) -> list[interview.Question]:
        session = self.get(session_id)
        if session.draft is None or session.confirmed is not None:
            return []
        return [question for question in interview.questions(session.draft) if question.id not in session.answers]

    def answer(self, who: Principal, session_id: str, answers: dict[str, Any]) -> Session:
        if who.kind != "human":
            self.hub.audit.append("writer_answer", who.label, target=session_id, status="blocked", code="not_permitted")
            raise NotHumanError(
                "Answering the limits interview takes a human principal, and an agent can suggest answers for a "
                "person to confirm."
            )
        session = self.get(session_id)
        if session.draft is None:
            raise WriterError("There is no valid draft to interview yet. Propose one first.")
        if session.status not in ("interview", "ready"):
            raise WriterError(f"The session is {session.status}, so it can't take answers.")
        known = {question.id for question in interview.questions(session.draft)}
        unknown = sorted(set(answers) - known)
        if unknown:
            raise WriterError(f"There are no questions {', '.join(unknown)}.")
        session.answers.update({key: value for key, value in answers.items() if str(value).strip()})
        session.problems = [problem for problem in session.problems if not problem.startswith("Interview. ")]
        if known <= set(session.answers):
            try:
                session.confirmed = interview.apply(session.draft, session.answers, by=who.name)
            except interview.AnswerError as exc:
                session.problems.append(f"Interview. {exc}")
                session.confirmed = None
                session.status = "interview"
            else:
                session.status = "ready"
        self.hub.audit.append("writer_answer", who.label, target=session.id, status=session.status)
        return session

    def _current_file(self, session: Session) -> Any:
        data = session.confirmed or session.draft
        if data is None:
            raise WriterError("There is no draft yet.")
        try:
            return from_data(data)
        except DeviceFileError as exc:
            raise WriterError("The draft is not valid yet. " + " ".join(exc.problems)) from exc

    async def test_plan(self, session_id: str) -> dict[str, Any]:
        session = self.get(session_id)
        file = self._current_file(session)
        steps = plan.build(file)
        problems = (
            await plan.validate(file, steps)
            if session.confirmed is not None
            else ["The limits are not confirmed yet, so the plan is a preview and was not checked by the kernel."]
        )
        return {"steps": [step.view() for step in steps], "problems": problems}

    async def finish(self, who: Principal, session_id: str, save_as: str | None = None) -> dict[str, Any]:
        if who.kind != "human":
            self.hub.audit.append("writer_finish", who.label, target=session_id, status="blocked", code="not_permitted")
            raise NotHumanError("Saving a device file from the driver writer takes a human principal.")
        session = self.get(session_id)
        if session.status == "saved":
            raise WriterError(f"This session is saved already, at {session.saved_path}.")
        file = self._current_file(session)
        source = session.confirmed if session.confirmed is not None else session.draft
        data: dict[str, Any] = copy.deepcopy(source) if source is not None else {}
        name = (save_as or file.device_id).removesuffix(DEVICE_FILE_SUFFIX)
        if not FILE_NAME.fullmatch(name):
            raise WriterError(f"{name!r} is not a usable file name. Use lowercase letters, digits, - and _.")
        provenance: dict[str, Any] = data.setdefault("provenance", {})
        provenance.update(by=who.label, at=dt.date.today().isoformat(), tool="openhal driver writer")
        provenance["verification"] = {"status": "unverified"}
        file = from_data(data)

        folder = self.hub.config.devices_dir
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{name}{DEVICE_FILE_SUFFIX}"
        if path.exists():
            raise FileExistsError(f"{path} exists already. Choose another name with save_as.")
        path.write_text(_dump(data), encoding="utf-8")
        session.saved_path = str(path)
        session.status = "saved"

        steps = plan.build(file)
        bundle = self.hub.config.home / "writer" / "bundles" / file.device_id
        bundle.mkdir(parents=True, exist_ok=True)
        (bundle / f"{name}{DEVICE_FILE_SUFFIX}").write_text(_dump(data), encoding="utf-8")
        (bundle / "TEST-REPORT.md").write_text(_report_template(file, steps), encoding="utf-8")
        self.hub.audit.append(
            "writer_finish", who.label, target=session.id, device=file.device_id, status="done", path=str(path)
        )
        if file.device_id not in self.hub.kernel.devices:
            try:
                await self.hub.add_and_start(file, path=path)
            except Exception as exc:  # noqa: BLE001 (saved anyway, the person restarts the hub)
                session.problems.append(f"Saved, but the hub couldn't load it now. {exc}")
        return {"path": str(path), "device_id": file.device_id, "writable": file.writable, "bundle": str(bundle)}


def _report_template(file: Any, steps: list[plan.TestStep]) -> str:
    lines = [
        f"# Hardware test report for {file.device.name}",
        "",
        f"Device id `{file.device_id}`, driver `{file.connect.driver}`, hazard {file.effective_hazard}.",
        "Fill this in while you walk through `openhal writer plan`, and attach it to the library submission.",
        "",
        "| Step | Command | Expected | Result | Notes |",
        "|---|---|---|---|---|",
    ]
    for step in steps:
        command = step.command if isinstance(step.command, str) else " ".join(str(v) for v in step.command.values())
        lines.append(f"| {step.step} | `{command}` | {step.expected} | pass or fail | |")
    lines += ["", "Hardware, firmware version, host OS and hub version.", "", "Anything unexpected.", ""]
    return "\n".join(lines)
