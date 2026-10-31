"""Copy never makes an object act like a person (docs/DESIGN.md, Copy voice).

The hub, the kernel, a printer, a device, a driver, a board, a server, a client, an SDK, the
Inspector and OpenHAL itself take mechanical verbs, so the hub blocks, holds, passes or returns a
request. This test reads the prose of every published page (the README, docs/, spec/, the example
and firmware READMEs and the website's own pages), every string and docstring in the openhal
package and every string in the Inspector, and fails on an object that refuses, rejects, asks,
tries, waits for a person, knows, sees, says, tells, answers, lets, talks or speaks.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
HISTORY = ("docs/agents/", "docs/design-rounds/", "docs/verification/", "docs/adr/", "docs/research/", "docs/DESIGN.md")
OBJECT = (
    r"(?:hubs?|kernels?|printers?|devices?|drivers?|boards?|firmware|servers?|clients?|SDKs?|Inspector|bridges?|OpenHAL"
    r"|cameras?|webcams?|sensors?|robots?|machines?|protocols?|specification|spec|files?|pages?|site|apps?|tools?"
    r"|library|routines?|scripts?|CLI)"
)
VERB = (
    r"(?:refus(?:e|es|ed|ing)|reject(?:s|ed|ing)?|ask(?:s|ed|ing)?|tr(?:y|ies|ied|ying)|want(?:s|ed)?|decid(?:e|es|ed)"
    r"|know(?:s|n)?|knew|remember(?:s|ed)?|forg(?:et|ets|ot)|trust(?:s|ed)?|understand(?:s)?|understood|believe(?:s)?"
    r"|think(?:s)?|hope(?:s)?|say(?:s)?|said|tell(?:s)?|told|answer(?:s|ed)?|let(?:s)?|talk(?:s|ed)?|speak(?:s)?|spoke"
    r"|obey(?:s)?|complain(?:s)?|notic(?:e|es|ed)|see(?:s)?|saw|watch(?:es|ed|ing)?|steps? in"
    r"|wait(?:s|ed|ing)? for (?:you|a person|the owner|approval|your|someone|people|a human))"
)
LINK = (
    r"(?:also|then|still|never|always|only|now|just|first|can|could|will|would|may|might|must|should"
    r"|does|did|do|not|cannot|can't|doesn't|won't|didn't)"
)
PATTERN = re.compile(rf"\b{OBJECT}\b(?:\s+{LINK})*\s+{VERB}\b", re.IGNORECASE)
MARKUP = {".astro", ".ts", ".tsx", ".svelte", ".mjs", ".json"}
QUOTED = re.compile(r"\"((?:[^\"\\\n]|\\.){8,})\"|'((?:[^'\\\n]|\\.){8,})'|`([^`]{8,})`|>([^<>{}\n]{8,})<")


def published() -> list[Path]:
    found = [ROOT / "README.md", ROOT / "firmware" / "arduino" / "OpenHAL" / "README.md"]
    for folder in ("docs", "spec", "examples", "website/src/content"):
        found.extend(sorted((ROOT / folder).rglob("*.md")))
    return [path for path in found if path.is_file() and not str(path.relative_to(ROOT)).startswith(HISTORY)]


def prose(text: str) -> list[tuple[int, str]]:
    """Each Markdown line outside code, with inline code and link targets taken out."""
    lines, fence = [], False
    for number, line in enumerate(text.split("\n"), 1):
        if line.lstrip().startswith(("```", "~~~")):
            fence = not fence
            continue
        if not fence:
            lines.append((number, re.sub(r"\]\([^)]*\)", "]", re.sub(r"`[^`]*`", "CODE", line))))
    return lines


def python_strings(path: Path) -> list[tuple[int, str]]:
    """Every string constant in a module, docstrings and f-string parts included."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [
        (node.lineno, node.value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    ]


def markup_strings(path: Path) -> list[tuple[int, str]]:
    """Every quoted string and every run of element text with a space in it, outside style blocks."""
    text = re.sub(
        r"<style[\s\S]*?</style>", lambda block: "\n" * block.group(0).count("\n"), path.read_text(encoding="utf-8")
    )
    found = []
    for number, line in enumerate(text.split("\n"), 1):
        for match in QUOTED.finditer(line):
            text = next(group for group in match.groups() if group)
            if " " in text:
                found.append((number, text))
    return found


def sources() -> list[tuple[Path, list[tuple[int, str]]]]:
    found = [(path, prose(path.read_text(encoding="utf-8"))) for path in published()]
    found += [(path, python_strings(path)) for path in sorted((ROOT / "openhal").rglob("*.py"))]
    for folder in ("website/src", "dashboard/src"):
        found += [(path, markup_strings(path)) for path in sorted((ROOT / folder).rglob("*")) if path.suffix in MARKUP]
    return found


def offenders(lines: list[tuple[int, str]]) -> list[str]:
    return [f"line {number}: {match.group(0)!r}" for number, text in lines for match in PATTERN.finditer(text)]


@pytest.mark.parametrize(
    ("path", "lines"), sources(), ids=lambda value: str(value.relative_to(ROOT)) if isinstance(value, Path) else ""
)
def test_objects_take_mechanical_verbs(path: Path, lines: list[tuple[int, str]]) -> None:
    hits = offenders(lines)
    assert not hits, f"{path.relative_to(ROOT)} makes an object act like a person:\n" + "\n".join(hits)
