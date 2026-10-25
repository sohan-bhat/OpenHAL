"""Keep the README and the docs quickstart in step with docs/demo/scenario.yaml.

    uv run python -m openhal.demo.readme

Rewrites the text between `<!-- trace:start -->` and `<!-- trace:end -->`, and between
`<!-- outcome:start -->` and `<!-- outcome:end -->`, in every page listed in PAGES.
tests/docs/test_scenario_docs.py fails when a page differs from what this would write.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path
from typing import Any, Final

from openhal.demo import scenario, trace

ROOT: Final = Path(__file__).resolve().parents[2]
PAGES: Final = (ROOT / "README.md", ROOT / "docs" / "QUICKSTART.md")


def blocks(record: dict[str, Any]) -> dict[str, str]:
    """The generated text for each marker name."""
    return {
        "trace": "```\n" + trace.text(record) + "```",
        "outcome": trace.outcome(record),
    }


def synced(text: str, record: dict[str, Any]) -> str:
    for name, body in blocks(record).items():
        pattern = re.compile(rf"(<!-- {name}:start -->\n)(?:.*?\n)?(<!-- {name}:end -->)", re.DOTALL)
        text = pattern.sub(_filler(body), text)
    return text


def _filler(body: str) -> Callable[[re.Match[str]], str]:
    def fill(match: re.Match[str]) -> str:
        return match.group(1) + body + "\n" + match.group(2)

    return fill


def main() -> None:
    record = scenario.read()
    for page in PAGES:
        page.write_text(synced(page.read_text(encoding="utf-8"), record), encoding="utf-8")
        print(f"synced {page.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
