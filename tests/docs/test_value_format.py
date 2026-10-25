"""Every example carries numbers as a number and a unit (ADR 0016).

The README, docs/, spec/, the example and firmware READMEs and every docstring in the openhal
package are checked. A protocol message, REST body or client call that sends a number as one
string such as `"150 %"` fails this test. Device files and routine triggers are human-written
formats and keep quantity strings, so YAML like `max: 100 %` is not checked.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
QUANTITY = r'"[-+]?\d+(?:\.\d+)?\s?[A-Za-z%°µΩ][A-Za-z%°µΩ/]*"'
PATTERNS = {
    "a message field": re.compile(r'"(?:value|limit|requested|duration|per|expected|min|max|rate)"\s*:\s*' + QUANTITY),
    "an action argument": re.compile(r'"args"\s*:\s*\{[^{}]*?"\w+"\s*:\s*' + QUANTITY),
    "a client call": re.compile(r"\.(?:write|action|tighten|tighten_limits|dry_run)\([^()\n]*" + QUANTITY),
}


def documents() -> list[Path]:
    found = [ROOT / "README.md"]
    for folder in ("docs", "spec"):
        found.extend(sorted((ROOT / folder).rglob("*.md")))
    found += sorted((ROOT / "examples").rglob("*.md"))
    found.append(ROOT / "firmware" / "arduino" / "OpenHAL" / "README.md")
    return [path for path in found if path.is_file()]


def docstrings() -> list[tuple[str, str]]:
    """Every docstring in the openhal package, with the place it starts."""
    found = []
    for path in sorted((ROOT / "openhal").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
                text = ast.get_docstring(node, clean=False)
                if text:
                    found.append((f"{path.relative_to(ROOT)}:{getattr(node, 'lineno', 1)}", text))
    return found


def test_docstrings_carry_numbers_with_units_apart() -> None:
    found = docstrings()
    assert len(found) > 500
    hits = [f"{where} {hit}" for where, text in found for hit in offenders(text)]
    assert not hits, "Docstrings use quantity strings (ADR 0016):\n" + "\n".join(hits)


def offenders(text: str) -> list[str]:
    hits = []
    for kind, pattern in PATTERNS.items():
        for match in pattern.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            hits.append(f"line {line}: {kind} sends {match.group(0)[-30:]!r}")
    return hits


@pytest.mark.parametrize("path", documents(), ids=lambda path: str(path.relative_to(ROOT)))
def test_examples_carry_numbers_with_units_apart(path: Path) -> None:
    hits = offenders(path.read_text(encoding="utf-8"))
    assert not hits, f"{path.relative_to(ROOT)} uses quantity strings (ADR 0016):\n" + "\n".join(hits)


def test_the_check_catches_both_shapes() -> None:
    assert offenders('{"device": "plant-waterer", "channel": "x", "value": "150 %"}')
    assert offenders('"args": {"duration": "120 s"}')
    assert offenders('hub.write("desk-fan", "fan_speed", "40 %")')
    assert not offenders('{"value": 150, "unit": "%"}')
    assert not offenders('"args": {"duration": {"value": 120, "unit": "s"}}')
    assert not offenders('"requestId": "9f2c41d07a3b6e15"')
    assert not offenders("max: 100 %")
