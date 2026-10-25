"""Every page tells the plant waterer story with the numbers docs/demo/scenario.yaml records.

The README and the docs quickstart show the recorded trace exactly. Every page that names a demo
value (the 30 s and 1 s limits, the 120 s and 20 s requests, 3 runs per 1 h, soil moisture from
31 % to 46 %, the reasons and the confirmation) names the recorded one. The desk fan stays in
spec/examples/, and user-facing copy says command or change instead of write or layer.
"""

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
REFERENCE_COPY = [
    ROOT / "docs" / "ARCHITECTURE.md",
    ROOT / "docs" / "interfaces" / "CLI.md",
    ROOT / "docs" / "interfaces" / "PYTHON.md",
    ROOT / "docs" / "guide" / "conformance.md",
    ROOT / "docs" / "drivers" / "openhal-firmware.md",
    ROOT / "docs" / "hardware-tests" / "openhal-firmware.md",
    ROOT / "firmware" / "arduino" / "OpenHAL" / "README.md",
    ROOT / "spec" / "FIRMWARE-PROTOCOL.md",
    ROOT / "spec" / "GLOSSARY.md",
    ROOT / "spec" / "CONFORMANCE.md",
    *(ROOT / "spec" / "2026-10-24" / name for name in ("index.md", "architecture.md", "safety.md", "security.md")),
    *(ROOT / "spec" / "2026-10-24" / name for name in ("device-files.md", "drivers.md", "basic/messages.md")),
]
"""Reference pages. They keep protocol and command names such as hal/write and openhal write, the
device file's `write` section and the product name driver writer, and say command or change
everywhere else."""


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


@pytest.mark.parametrize("page", REFERENCE_COPY, ids=lambda page: str(page.relative_to(ROOT)))
def test_reference_copy_says_command_or_change(page: Path) -> None:
    text = prose(page.read_text(encoding="utf-8"))
    text = re.sub(r"\b(?:openhal|hal)[ /][a-z-]+|\S*/\S*|\S+\.md\b", " ", text)
    words = re.findall(r"\b(?:writ(?:e|es|ing)\b(?! channels?\b)|layers?\b)", text, flags=re.IGNORECASE)
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


RECORD = scenario.read()


def demo_pages() -> list[Path]:
    """Every page that can show the demo's numbers."""
    found = [README]
    for folder in ("docs", "spec"):
        found.extend(sorted((ROOT / folder).rglob("*.md")))
    found += sorted((ROOT / "examples" / "plant-waterer").glob("*.md"))
    found.append(ROOT / "firmware" / "arduino" / "OpenHAL" / "README.md")
    skipped = ("docs/agents/", "docs/research/")
    return [path for path in found if path.is_file() and not any(part in path.as_posix() for part in skipped)]


def facts() -> dict[str, tuple[str, ...]]:
    """What each demo value pattern must say, from docs/demo/scenario.yaml."""
    limits = RECORD["limits"]
    too_long, empty, watered = RECORD["exchanges"]
    longest = str(limits["water_duration"]["max"]["value"])
    shortest = str(limits["water_duration"]["min"]["value"])
    runs = limits["water_runs"]
    window = f"{runs['per']['value']} {runs['per']['unit']}"
    before = str(watered["soil_moisture"]["before"]["value"])
    after = str(watered["soil_moisture"]["after"]["value"])
    asked = str(too_long["request"]["params"]["args"]["duration"]["value"])
    ran = str(watered["request"]["params"]["args"]["duration"]["value"])
    confirmed = RECORD["confirmed"]
    return {
        r"water duration \d+ s exceeds the limit of (\d+) s": (longest,),
        r"water duration \d+ s is below the limit of (\d+) s": (shortest,),
        r"The duration limit is (\d+) s \(max\)": (longest,),
        r"ERR limit duration max (\d+)": (longest,),
        r"duration`? from (\d+) s to (\d+) s": (shortest, longest),
        r"[Ww]atering runs at most (\d+) s": (longest,),
        r"water may run at most (\d+) times per (\d+ \w+)": (str(runs["count"]), window),
        r"(?:pump|water|watering)[^.\n]*?\b(\d+) (?:runs|times) (?:per|an|each) (?:hour|1 h)\b": (str(runs["count"]),),
        r"\b(\d+) runs per 1 h\b": (str(runs["count"]),),
        r"(?i)(pump can.?t run while[^.\"\n]*?empty)": (empty["error"]["message"],),
        r"rises from (\d+) ?% to (\d+) ?%": (before, after),
        r"soil reads (\d+) ?%": (before,),
        r"VAL soil_moisture (\d+)": (before,),
        r"EVT soil_moisture (\d+)": (after,),
        r"refuse a (\d+) s watering": (asked,),
        r"water for (\d+) s as soil moisture": (ran,),
        rf"\({re.escape(RECORD['file'])}, confirmed by (\S+) (\d{{4}}-\d{{2}}-\d{{2}})\)": (
            confirmed["by"],
            confirmed["at"],
        ),
    }


def demo_values(text: str) -> dict[str, list[tuple[str, ...]]]:
    flat = re.sub(r"\s+", " ", text)
    return {pattern: [match.groups() for match in re.finditer(pattern, flat)] for pattern in facts()}


def disagreements(text: str) -> list[str]:
    """Every demo value in the text that differs from the recorded scenario."""
    wrong = []
    for pattern, found in demo_values(text).items():
        expected = facts()[pattern]
        for groups in found:
            said = tuple(group[:1].lower() + group[1:] for group in groups)
            if said != tuple(value[:1].lower() + value[1:] for value in expected):
                wrong.append(f"{groups} where docs/demo/scenario.yaml gives {expected} ({pattern})")
    return wrong


def test_the_value_check_catches_drifted_numbers() -> None:
    text = (
        "water duration 120 s exceeds the limit of 25 s. Soil moisture rises from 31 % to 50 %. "
        "Pump can't run while the tank is empty. The pump runs at most 4 times per hour."
    )
    assert len(disagreements(text)) == 4
    assert not disagreements("water duration 120 s exceeds the limit of 30 s. Pump can't run while tank is empty.")


@pytest.mark.parametrize("page", demo_pages(), ids=lambda page: str(page.relative_to(ROOT)))
def test_demo_values_match_the_recorded_scenario(page: Path) -> None:
    wrong = disagreements(page.read_text(encoding="utf-8"))
    assert not wrong, f"{page.relative_to(ROOT)} disagrees with the scenario:\n" + "\n".join(wrong)


def test_every_demo_value_check_finds_something() -> None:
    seen = {pattern: 0 for pattern in facts()}
    for page in demo_pages():
        for pattern, found in demo_values(page.read_text(encoding="utf-8")).items():
            seen[pattern] += len(found)
    assert all(seen.values()), [pattern for pattern, count in seen.items() if not count]


def test_the_scenario_limits_are_the_mock_files_limits() -> None:
    from openhal.demo.scenario import example_file
    from openhal.spec import load

    water = load(example_file()).actions["water"]
    limits = RECORD["limits"]
    duration = water.args["duration"]
    assert (duration.min, duration.max) == (
        limits["water_duration"]["min"]["value"],
        limits["water_duration"]["max"]["value"],
    )
    assert water.max_runs is not None
    assert water.max_runs.count == limits["water_runs"]["count"]
    assert water.max_runs.per == limits["water_runs"]["per"]["value"] * 3600
    assert [item.message for item in water.require if not isinstance(item, str)] == [
        RECORD["exchanges"][1]["error"]["message"]
    ]


DESK_FAN = re.compile(r"(?i)\bdesk[- _]fan\b")
DESK_FAN_ALLOWED = {
    "docs/DESIGN.md": "says the desk fan stays only in spec/examples/",
}
"""Pages outside spec/examples/ that may still name the desk fan, and why."""


def test_the_desk_fan_stays_in_spec_examples() -> None:
    pages = [page for page in demo_pages() if str(page.relative_to(ROOT)) not in DESK_FAN_ALLOWED]
    found = [str(page.relative_to(ROOT)) for page in pages if DESK_FAN.search(page.read_text(encoding="utf-8"))]
    assert not found, f"These pages still show the desk fan: {found}"


def test_the_package_explains_itself_with_the_plant_waterer() -> None:
    """Docstrings, help text and tool descriptions. Driver fixtures and simulators keep the desk fan."""
    package = ROOT / "openhal"
    found = [
        str(path.relative_to(ROOT))
        for path in sorted(package.rglob("*.py"))
        if "drivers" not in path.relative_to(package).parts and DESK_FAN.search(path.read_text(encoding="utf-8"))
    ]
    assert not found, f"These modules still show the desk fan: {found}"
