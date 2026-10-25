"""Every page names the protocol, the conformance checks and the glossary terms one way.

- Every `hal/` name in README.md, docs/, spec/ and the example and firmware READMEs is a method or
  notification of ADR 0015, of openhal.protocol and of the generated schema.
- Every error code shown next to a name, in prose or in JSON, is that name's code in the registry.
- Every JSON message trace (lines that start with → or ←) validates against openhal.protocol. Params
  and results match their models, each error's message is the reason its name's template forms
  from its data, and each kernel code belongs to the error's name.
- The firmware sessions have real checksums.
- The conformance checks the spec and the guide list are the suite's checks, at the suite's levels.
- GLOSSARY.md and the spec's terminology define the same terms. The dated spec writes its
  multi-word terms capitalized, and no page uses a known misspelling such as "Websocket".

tests/spec/test_spec_names.py covers the names in spec/ against the ADR. This file covers the
rest of the pages and the parts that need the code.
"""

from __future__ import annotations

import json
import re
from functools import cache
from pathlib import Path
from typing import Any, Final

import pytest
from pydantic import TypeAdapter

from openhal.drivers.openhal_firmware.protocol import checksum
from openhal.protocol import messages as m
from openhal.protocol.errors import BY_KERNEL_CODE, BY_NAME, RpcError
from tests.spec.test_spec_names import METHOD, PAIRINGS, adr

ROOT: Final = Path(__file__).resolve().parents[2]
FENCE: Final = re.compile(r"^([ \t]*)```([A-Za-z]*)([^\n]*)\n(.*?)^\1```", re.M | re.S)
FIRMWARE_LINE: Final = re.compile(r"^(?:host|board)\s+(\d+ [^*\n]+)\*([0-9A-F]{2})$", re.M)
CHECK_ROW: Final = re.compile(r"^\| `([a-z ]+)` \| (Core|Control|Full) \|", re.M)
SUITE_CHECK: Final = re.compile(r'\("([a-z ]+)", "(core|control|full)", \w+\)')
GLOSSARY: Final = ROOT / "spec" / "GLOSSARY.md"
TERMINOLOGY: Final = ROOT / "spec" / "2026-10-24" / "index.md"
MISSPELLINGS: Final[dict[str, str]] = {
    r"\b(?:Websockets?|[Ww]eb [Ss]ockets?|websocket)\b": "WebSocket",
    r"\b(?:JSON ?RPC|JSONRPC|json-rpc|Json-Rpc)\b": "JSON-RPC",
    r"\b(?:Openhal|OpenHal|openHAL|Open HAL|Open-HAL)\b": "OpenHAL",
    r"\bread only\b": "read-only",
    r"\b[Dd]evice-files?\b(?![./\w-])": "device file",
    r"\b[Ss]afety-[Kk]ernel\b(?![./\w-])": "safety kernel",
    r"\bplant-waterer (?:example|board|sketch|mock)\b": "plant waterer",
}
"""Spellings that drifted from the one the docs use, and the spelling to use instead."""


def pages() -> list[Path]:
    found = [ROOT / "README.md"]
    for folder in ("docs", "spec"):
        found.extend(sorted((ROOT / folder).rglob("*.md")))
    found += sorted((ROOT / "examples").rglob("*.md"))
    found.append(ROOT / "firmware" / "arduino" / "OpenHAL" / "README.md")
    return [path for path in found if path.is_file() and "docs/agents/" not in path.as_posix()]


def prose(text: str) -> str:
    """The running text, with fences, code, links, comments and headings blanked out."""
    text = FENCE.sub(lambda match: re.sub(r"[^\n]", " ", match.group(0)), text)
    text = re.sub(r"<!--.*?-->", lambda match: re.sub(r"[^\n]", " ", match.group(0)), text, flags=re.S)
    text = re.sub(r"`[^`\n]*`", " ", text)
    text = re.sub(r"\[[^\]\n]*\]\([^)\n]*\)", " ", text)
    text = re.sub(r"https?://\S+", " ", text)
    return re.sub(r"^#{1,6} .*$", "", text, flags=re.M)


ids = {"ids": lambda path: str(path.relative_to(ROOT))}


@cache
def schema_names() -> frozenset[str]:
    document = json.loads((ROOT / "spec" / "2026-10-24" / "schema.json").read_text(encoding="utf-8"))
    return (
        frozenset(document["methods"])
        | frozenset(document["notifications"])
        | frozenset(document["clientNotifications"])
    )


@pytest.mark.parametrize("page", pages(), **ids)
def test_every_method_name_is_in_the_adr_the_code_and_the_schema(page: Path) -> None:
    named = set(METHOD.findall(page.read_text(encoding="utf-8")))
    registry = adr()
    code = set(m.METHODS) | set(m.NOTIFICATIONS) | set(m.CLIENT_NOTIFICATIONS)
    for source, known in (("ADR 0015", registry.methods | registry.notifications), ("the code", code)):
        assert named <= known, f"{page.name} names methods {source} doesn't have: {sorted(named - known)}"
    assert named <= schema_names(), f"{page.name} names methods the schema lacks: {sorted(named - schema_names())}"


@pytest.mark.parametrize("page", pages(), **ids)
def test_every_error_code_shown_with_a_name_is_the_registry_code(page: Path) -> None:
    text = page.read_text(encoding="utf-8")
    pairs: set[tuple[str, int]] = set()
    for pattern in PAIRINGS:
        for match in pattern.finditer(text):
            first, second = match.groups()
            name, code = (second, first) if first.startswith("-") else (first, second)
            pairs.add((name, int(code)))
    wrong = sorted((name, code) for name, code in pairs if name in BY_NAME and BY_NAME[name].code != code)
    unknown = sorted((name, code) for name, code in pairs if name not in BY_NAME)
    assert not wrong, f"{page.name} pairs codes with the wrong names: {wrong}"
    assert not unknown, f"{page.name} shows codes with names the registry lacks: {unknown}"
    names = set(re.findall(r'"name":\s*"([A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+)"', text))
    assert names <= set(BY_NAME), f"{page.name} gives error names the registry lacks: {sorted(names - set(BY_NAME))}"


def traces(text: str) -> list[list[dict[str, Any]]]:
    """Every JSON fence that is a message trace, as its list of messages."""
    found = []
    for fence in FENCE.finditer(text):
        body = fence.group(4)
        if fence.group(2) != "json" or body.lstrip()[:1] not in ("→", "←"):
            continue
        messages: list[str] = []
        for line in body.splitlines():
            if line.lstrip()[:1] in ("→", "←"):
                messages.append(line.lstrip()[1:])
            elif line.strip():
                messages[-1] += "\n" + line
        found.append([json.loads(message) for message in messages])
    return found


def error_problems(error: dict[str, Any]) -> list[str]:
    data = dict(error["data"])
    name = data.pop("name")
    expected = RpcError(name, data)
    problems = []
    if (error["code"], error["message"]) != (expected.code, expected.reason):
        problems.append(
            f"{name} should be {expected.code} {expected.reason!r}, not {error['code']} {error['message']!r}"
        )
    kernel = data.get("kernelCode")
    if kernel is not None and (kernel not in BY_KERNEL_CODE or BY_KERNEL_CODE[kernel].name != name):
        problems.append(f"kernel code {kernel} doesn't belong to {name}")
    return problems


def trace_problems(trace: list[dict[str, Any]]) -> list[str]:
    problems: list[str] = []
    methods: dict[Any, str] = {}
    for message in trace:
        assert message.get("jsonrpc") == "2.0", message
        try:
            if "method" in message and "id" in message:
                m.METHODS[message["method"]].params.model_validate(message.get("params", {}))
                methods[message["id"]] = message["method"]
            elif "method" in message:
                if message["method"] in m.CLIENT_NOTIFICATIONS:
                    continue
                model, _ = m.NOTIFICATIONS[message["method"]]
                model.model_validate(message.get("params", {}))
                if "error" in message["params"]:
                    problems += error_problems(message["params"]["error"])
            elif "error" in message:
                problems += error_problems(message["error"])
            else:
                result = TypeAdapter(m.METHODS[methods[message["id"]]].result).validate_python(message["result"])
                for item in getattr(result, "readings", []) + getattr(result, "decisions", []):
                    if getattr(item, "error", None) is not None:
                        problems += error_problems(item.error.model_dump(by_alias=True, exclude_none=True))
        except Exception as exc:  # noqa: BLE001 (every bad message is reported, not just the first)
            problems.append(f"{json.dumps(message)[:100]} {type(exc).__name__}: {str(exc)[:300]}")
    return problems


@pytest.mark.parametrize("page", [page for page in pages() if traces(page.read_text(encoding="utf-8"))], **ids)
def test_every_message_trace_matches_the_protocol(page: Path) -> None:
    problems = [problem for trace in traces(page.read_text(encoding="utf-8")) for problem in trace_problems(trace)]
    assert not problems, f"{page.relative_to(ROOT)}\n" + "\n".join(problems)


def test_the_messages_page_has_a_trace_for_every_method() -> None:
    page = ROOT / "spec" / "2026-10-24" / "basic" / "messages.md"
    shown = {
        message["method"]
        for trace in traces(page.read_text(encoding="utf-8"))
        for message in trace
        if "method" in message
    }
    assert set(m.METHODS) - {"hal/initialize"} <= shown
    assert set(m.NOTIFICATIONS) <= shown


def test_the_trace_check_catches_a_drifted_example() -> None:
    error = {
        "code": -32010,
        "message": "water duration 120 s exceeds the limit of 30 s",
        "data": {
            "name": "LIMIT_EXCEEDED",
            "kernelCode": "interlock",
            "action": "water",
            "argument": "duration",
            "requested": {"value": 120, "unit": "s"},
            "limit": {"value": 25, "unit": "s"},
        },
    }
    assert len(error_problems(error)) == 2
    request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "hal/action",
        "params": {"device": "plant-waterer", "action": "water", "args": {"duration": "20 s"}, "extra": True},
    }
    assert trace_problems([request])


@pytest.mark.parametrize("page", [ROOT / "spec" / "FIRMWARE-PROTOCOL.md"], **ids)
def test_firmware_sessions_carry_real_checksums(page: Path) -> None:
    lines = FIRMWARE_LINE.findall(page.read_text(encoding="utf-8"))
    assert len(lines) >= 10
    wrong = [f"{body}*{given} should end *{checksum(body)}" for body, given in lines if checksum(body) != given]
    assert not wrong, "\n".join(wrong)


@cache
def suite_checks() -> frozenset[tuple[str, str]]:
    source = (ROOT / "openhal" / "conformance" / "suite.py").read_text(encoding="utf-8")
    return frozenset(SUITE_CHECK.findall(source))


@pytest.mark.parametrize(
    "page", [ROOT / "spec" / "2026-10-24" / "drivers.md", ROOT / "docs" / "guide" / "conformance.md"], **ids
)
def test_the_listed_conformance_checks_are_the_suites(page: Path) -> None:
    listed = {(name, level.lower()) for name, level in CHECK_ROW.findall(page.read_text(encoding="utf-8"))}
    assert len(suite_checks()) >= 15
    assert listed == suite_checks()


def terms(path: Path, heading: str | None = None) -> list[str]:
    text = path.read_text(encoding="utf-8")
    if heading is not None:
        text = text[text.index(heading) :]
    table = re.search(r"^\| Term \| Definition \|\n\|---\|---\|\n((?:\|.*\n)+)", text, re.M)
    assert table is not None, path
    return [row.split("|")[1].strip() for row in table.group(1).splitlines()]


def test_the_glossary_and_the_spec_define_the_same_terms() -> None:
    assert terms(GLOSSARY) == terms(TERMINOLOGY, "## Terminology")


def spec_pages() -> list[Path]:
    dated = sorted((ROOT / "spec" / "2026-10-24").rglob("*.md"))
    top = [ROOT / "spec" / name for name in ("GLOSSARY.md", "CONFORMANCE.md", "ERRORS.md")]
    return [path for path in [*dated, *top] if path.name != "schema.md"]


@pytest.mark.parametrize("page", spec_pages(), **ids)
def test_the_spec_capitalizes_its_defined_terms(page: Path) -> None:
    text = prose(page.read_text(encoding="utf-8"))
    wrong = []
    for term in (term for term in terms(GLOSSARY) if " " in term):
        for match in re.finditer(rf"\b{re.escape(term)}s?\b", text, flags=re.I):
            if match.group(0) not in (term, term + "s"):
                wrong.append(match.group(0))
    assert not wrong, f"{page.name} writes {sorted(set(wrong))} in lowercase. Defined terms are capitalized."


@pytest.mark.parametrize("page", pages(), **ids)
def test_no_page_uses_a_drifted_spelling(page: Path) -> None:
    text = prose(page.read_text(encoding="utf-8"))
    found = [
        f"{match.group(0)!r} (use {spelling})"
        for pattern, spelling in MISSPELLINGS.items()
        for match in re.finditer(pattern, text)
    ]
    assert not found, f"{page.relative_to(ROOT)} uses {found}"
