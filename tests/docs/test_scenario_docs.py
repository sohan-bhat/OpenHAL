"""The README and the docs quickstart show the canonical scenario exactly as docs/demo/scenario.yaml records it."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest
from typer.testing import CliRunner

from openhal.cli.main import app
from openhal.demo import readme, scenario

ROOT = Path(__file__).resolve().parents[2]
README = ROOT / "README.md"
DESCRIPTION = "An open-source protocol for AI agents to control hardware."
COPY = [README, ROOT / "docs" / "QUICKSTART.md", ROOT / "examples" / "plant-waterer" / "README.md"]


@pytest.mark.parametrize("page", readme.PAGES, ids=lambda page: page.name)
def test_pages_match_the_recorded_scenario(page: Path) -> None:
    text = page.read_text(encoding="utf-8")
    assert readme.synced(text, scenario.read()) == text, "Run uv run python -m openhal.demo.readme"
    assert "<!-- trace:start -->\n```" in text


def test_the_readme_runs_in_order() -> None:
    text = README.read_text(encoding="utf-8")
    marks = [
        "docs/assets/wordmark-light.svg",
        f"\n{DESCRIPTION}\n",
        "[![License]",
        "[![CI]",
        "docs/diagrams/flow-light.svg",
        "## Quickstart",
        "## Message trace",
    ]
    places = [text.index(mark) for mark in marks]
    assert places == sorted(places)
    between = text[text.index("[![CI]") : text.index("<picture>", text.index("[![CI]"))]
    assert between.count("\n") == 2, "the diagram comes directly under the badges"
    quickstart = text[text.index("## Quickstart") : text.index("## Message trace")]
    commands = quickstart.split("```")[1].strip().splitlines()
    assert len(commands) == 3


def test_the_one_line_description_is_the_same_everywhere() -> None:
    assert f"\n{DESCRIPTION}\n\n" in README.read_text(encoding="utf-8")
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert project["description"] == DESCRIPTION
    assert DESCRIPTION in CliRunner().invoke(app, ["--help"]).output.replace("\n", " ").replace("  ", " ")


def prose(text: str) -> str:
    text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
    text = re.sub(r"<!--.*?-->|<[^>]+>", "", text, flags=re.DOTALL)
    text = re.sub(r"`[^`]*`", "", text)
    return re.sub(r"\]\([^)]*\)", "]", text)


@pytest.mark.parametrize("page", COPY, ids=lambda page: page.parent.name + "/" + page.name)
def test_copy_says_command_or_change_not_write_or_layer(page: Path) -> None:
    words = re.findall(r"\b(?:writ\w*|layers?)\b", prose(page.read_text(encoding="utf-8")), flags=re.IGNORECASE)
    assert not words, f"{page.name} uses {sorted(set(words))}"


def test_the_readme_uses_the_plant_waterer() -> None:
    text = README.read_text(encoding="utf-8")
    assert "desk-fan" not in text
    assert "desk fan" not in text.lower()
    source = (ROOT / "docs" / "diagrams" / "flow.d2").read_text(encoding="utf-8")
    assert 'device: "Arduino\\nplant waterer"' in source
    assert '"INTERLOCK_BLOCKED:\\ntank empty"' in source
    for name in ("flow-light", "flow-dark", "flow-narrow-light", "flow-narrow-dark"):
        built = (ROOT / "docs" / "diagrams" / f"{name}.svg").read_text(encoding="utf-8")
        assert "Arduino plant waterer" in built
        assert "INTERLOCK_BLOCKED" in built
