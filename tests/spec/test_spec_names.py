"""Every protocol name in the specification matches ADR 0015 and the registry in code.

Each check runs twice, once against the ADR's Markdown tables and once against `openhal.protocol`
(the error registry and the method and notification tables), so the spec, the ADR and the code
can't drift apart.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from functools import cache
from pathlib import Path

import pytest

from openhal.kernel.commands import BLOCK_CODES

ROOT = Path(__file__).resolve().parents[2]
ADR = ROOT / "docs" / "adr" / "0015-openhal-hub-protocol.md"
SPEC = ROOT / "spec"
VERSION = SPEC / "2026-10-24"
TOP_LEVEL = ("SPEC.md", "CHANGELOG.md", "VERSIONING.md", "ERRORS.md", "CONFORMANCE.md", "GLOSSARY.md")
NOT_ERROR_NAMES = frozenset({"HA_TOKEN"})

METHOD = re.compile(r"(?<![A-Za-z0-9_./-])hal/[A-Za-z]+(?:/[A-Za-z]+)*")
UPPER_SNAKE = re.compile(r"(?<![\w/.-])[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+(?![\w-]|\.\w)")
CODE = r"(-32\d{3})"
NAME = r"([A-Z][A-Z0-9]{2,}(?:_[A-Z0-9]+)*)"
PAIRINGS = (
    re.compile(rf"\|\s*{CODE}\s*\|\s*{NAME}\s*\|"),
    re.compile(rf"`?{NAME}`?\s*\({CODE}\)"),
    re.compile(rf"{CODE}\s+{NAME}"),
    re.compile(rf'"code":\s*{CODE}(?:(?!"code").)*?"name":\s*"{NAME}"', re.DOTALL),
)


@dataclass(frozen=True)
class Registry:
    methods: frozenset[str]
    notifications: frozenset[str]
    errors: dict[str, int]
    kernel_codes: dict[str, tuple[str, ...]]


def _section(text: str, heading: str) -> str:
    start = text.index(heading)
    rest = text[start + len(heading) :]
    following = re.search(r"^#{1,3} ", rest, re.MULTILINE)
    return rest if following is None else rest[: following.start()]


def _rows(block: str) -> list[list[str]]:
    rows = []
    for line in block.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|") or set(stripped) <= {"|", "-", " "}:
            continue
        rows.append([cell.strip() for cell in stripped.strip("|").split("|")])
    return rows[1:]


def _first_name(cell: str) -> str:
    found = METHOD.search(cell)
    assert found is not None, f"no hal/ name in ADR table cell {cell!r}"
    return found.group(0)


@cache
def adr() -> Registry:
    text = ADR.read_text(encoding="utf-8")
    methods = frozenset(_first_name(row[0]) for row in _rows(_section(text, "### Methods").split("Notifications")[0]))
    notification_block = _section(text, "### Methods").split("Notifications", 1)[1]
    notifications = {_first_name(row[0]) for row in _rows(notification_block)}
    notifications |= set(METHOD.findall(_section(text, "### Lifecycle"))) - methods
    errors: dict[str, int] = {}
    kernel_codes: dict[str, tuple[str, ...]] = {}
    for row in _rows(_section(text, "### Error registry")):
        code, name, kernel = int(row[0]), row[1], row[2]
        errors[name] = code
        kernel_codes[name] = tuple(re.findall(r"`([a-z_]+)`", kernel))
    return Registry(methods, frozenset(notifications), errors, kernel_codes)


@cache
def code() -> Registry:
    from openhal.protocol import errors, messages

    return Registry(
        methods=frozenset(messages.METHODS),
        notifications=frozenset(messages.NOTIFICATIONS) | frozenset(messages.CLIENT_NOTIFICATIONS),
        errors={spec.name: spec.code for spec in errors.REGISTRY},
        kernel_codes={spec.name: spec.kernel_codes for spec in errors.REGISTRY},
    )


SOURCES: dict[str, Callable[[], Registry]] = {"adr": adr, "code": code}
source = pytest.mark.parametrize("registry_of", list(SOURCES.values()), ids=list(SOURCES))


def spec_files() -> list[Path]:
    files = sorted(VERSION.rglob("*.md"))
    files += [SPEC / name for name in TOP_LEVEL]
    return [path for path in files if path.name != "schema.md"]


def spec_text() -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in spec_files())


def test_the_adr_tables_parse() -> None:
    registry = adr()
    assert "hal/write" in registry.methods
    assert "hal/value" in registry.notifications
    assert {"hal/initialized", "hal/shutdown"} <= registry.notifications
    assert registry.errors["LIMIT_EXCEEDED"] == -32010
    assert len(set(registry.errors.values())) == len(registry.errors)


def test_the_code_registry_matches_the_adr() -> None:
    assert code() == adr()


@source
@pytest.mark.parametrize("path", spec_files(), ids=lambda path: str(path.relative_to(SPEC)))
def test_every_protocol_name_in_the_spec_is_in_the_adr(path: Path, registry_of: Callable[[], Registry]) -> None:
    registry = registry_of()
    text = path.read_text(encoding="utf-8")
    unknown_methods = set(METHOD.findall(text)) - registry.methods - registry.notifications
    unknown_errors = set(UPPER_SNAKE.findall(text)) - set(registry.errors) - NOT_ERROR_NAMES
    assert not unknown_methods, f"{path.name} names methods the ADR doesn't have: {sorted(unknown_methods)}"
    assert not unknown_errors, f"{path.name} names errors the ADR doesn't have: {sorted(unknown_errors)}"


@source
def test_every_adr_name_is_in_the_spec(registry_of: Callable[[], Registry]) -> None:
    registry = registry_of()
    text = spec_text()
    named = set(METHOD.findall(text))
    named |= {name for name in registry.errors if re.search(rf"(?<![\w/.-]){name}(?![\w-])", text)}
    expected = registry.methods | registry.notifications | set(registry.errors)
    assert not expected - named, f"the spec never names {sorted(expected - named)}"


@source
@pytest.mark.parametrize("path", spec_files(), ids=lambda path: str(path.relative_to(SPEC)))
def test_every_code_shown_next_to_a_name_matches(path: Path, registry_of: Callable[[], Registry]) -> None:
    registry = registry_of()
    text = path.read_text(encoding="utf-8")
    pairs: set[tuple[str, int]] = set()
    for pattern in PAIRINGS:
        for match in pattern.finditer(text):
            first, second = match.groups()
            name, code = (second, first) if first.startswith("-") else (first, second)
            pairs.add((name, int(code)))
    wrong = sorted((name, code) for name, code in pairs if registry.errors.get(name) != code)
    assert not wrong, f"{path.name} pairs codes with the wrong names: {wrong}"


@source
def test_the_registry_table_matches_the_adr_row_for_row(registry_of: Callable[[], Registry]) -> None:
    registry = registry_of()
    text = (VERSION / "safety.md").read_text(encoding="utf-8")
    rows = _rows(_section(text, "## Error registry").split("### Reason messages")[0])
    table = {row[1]: (int(row[0]), tuple(re.findall(r"`([a-z_]+)`", row[2]))) for row in rows}
    expected = {name: (code, registry.kernel_codes[name]) for name, code in registry.errors.items()}
    assert table == expected


@source
def test_every_kernel_code_maps_to_exactly_one_name(registry_of: Callable[[], Registry]) -> None:
    owners: dict[str, list[str]] = {}
    for name, codes in registry_of().kernel_codes.items():
        for code in codes:
            owners.setdefault(code, []).append(name)
    assert set(BLOCK_CODES) <= set(owners), f"unmapped kernel codes {sorted(set(BLOCK_CODES) - set(owners))}"
    assert all(len(names) == 1 for names in owners.values()), owners


def test_the_limit_exceeded_reason_is_quoted_exactly() -> None:
    reason = "fan_speed 150 % exceeds the limit of 100 % (desk-fan.hal.yaml, confirmed by sohan 2026-10-24)"
    for name in ("architecture.md", "safety.md", "basic/messages.md"):
        assert reason in (VERSION / name).read_text(encoding="utf-8"), name


def test_versions_file_names_this_version_as_latest() -> None:
    import json

    versions = json.loads((SPEC / "versions.json").read_text(encoding="utf-8"))
    assert versions["latest"] == VERSION.name
    assert {"version": VERSION.name, "status": "draft"} in versions["versions"]
