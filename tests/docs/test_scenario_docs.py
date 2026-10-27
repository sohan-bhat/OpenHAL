"""Every page tells the print babysitter story with the numbers docs/demo/scenario.yaml records.

The README and the docs quickstart show the recorded trace exactly. Every page that names a printer
value (the 260 degC and 110 degC limits, their rates, the requested nozzle temperature of 300 degC,
the bed from 60 degC to 70 degC, the reason, the confirmation, the audit log's counts and the
printer's state after the owner's approval) names the recorded one. Pages about the Arduino plant
waterer name the values of its mock device file and of docs/demo/e2e.yaml, which `openhal demo
--full` records. The desk fan stays in spec/examples/, and user-facing copy says command or change
instead of write or layer.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest
from typer.testing import CliRunner

from openhal.cli.main import app
from openhal.demo import e2e, plant, readme, scenario
from openhal.spec import load

ROOT = Path(__file__).resolve().parents[2]
README = ROOT / "README.md"
DESCRIPTION = "An open-source protocol for AI agents to control hardware."
COPY = [
    README,
    ROOT / "docs" / "QUICKSTART.md",
    ROOT / "examples" / "plant-waterer" / "README.md",
    ROOT / "examples" / "print-babysitter" / "README.md",
]
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

RECORD = scenario.read()
FULL = e2e.read()
MOCK = load(plant.example_file())


@pytest.mark.parametrize("page", readme.PAGES, ids=lambda page: page.name)
def test_pages_match_the_recorded_scenario(page: Path) -> None:
    text = page.read_text(encoding="utf-8")
    assert readme.synced(text, RECORD) == text, "Run uv run python -m openhal.demo.readme"
    assert "<!-- trace:start -->\n```" in text
    assert "# the owner approves the cancel\n→ hal/confirmations/approve" in text


def test_the_docs_quickstart_ends_with_the_audit_log() -> None:
    text = (ROOT / "docs" / "QUICKSTART.md").read_text(encoding="utf-8")
    block = text[text.index("<!-- audit:start -->") : text.index("<!-- audit:end -->")]
    assert "\n".join(RECORD["audit"]["lines"]) in block
    assert "6 requests, 1 refused, 1 confirmed by a person." in block
    assert "`TIME` stands in for the time of each entry." in text


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


def test_the_readme_and_the_flow_diagram_use_the_printer() -> None:
    text = README.read_text(encoding="utf-8")
    assert "desk-fan" not in text
    assert "desk fan" not in text.lower()
    assert "examples/print-babysitter/" in text
    refused = scenario.exchange(RECORD, "nozzle-too-hot")["error"]
    nozzle = f"{refused['data']['requested']['value']:g} °C"
    source = (ROOT / "docs" / "diagrams" / "flow.d2").read_text(encoding="utf-8")
    assert 'client: "Agent" {' in source
    assert 'device: "3D printer" {' in source
    assert f'"{refused["data"]["name"]}:\\nnozzle {nozzle}"' in source
    for name in ("flow-light", "flow-dark", "flow-narrow-light", "flow-narrow-dark"):
        built = (ROOT / "docs" / "diagrams" / f"{name}.svg").read_text(encoding="utf-8")
        assert "3D printer" in built
        assert "LIMIT_EXCEEDED" in built
        assert f"A {nozzle} nozzle is blocked" in built


def demo_pages() -> list[Path]:
    """Every page that can show the demo's numbers. Verification records keep what was true then."""
    found = [README]
    for folder in ("docs", "spec"):
        found.extend(sorted((ROOT / folder).rglob("*.md")))
    for example in ("plant-waterer", "print-babysitter"):
        found += sorted((ROOT / "examples" / example).glob("*.md"))
    found.append(ROOT / "firmware" / "arduino" / "OpenHAL" / "README.md")
    skipped = ("docs/agents/", "docs/research/", "docs/verification/")
    return [path for path in found if path.is_file() and not any(part in path.as_posix() for part in skipped)]


def shown(value: float) -> str:
    return f"{float(value):g}"


DEGREES = r" ?(?:°C|degC)"


def printer_facts() -> dict[str, tuple[str, ...]]:
    """What each printer value pattern must say, from docs/demo/scenario.yaml."""
    printer = next(device for device in RECORD["devices"] if device["id"] == scenario.DEVICE)
    nozzle, bed = printer["limits"]["extruder_target"], printer["limits"]["bed_target"]
    hottest, warmest = shown(nozzle["max"]["value"]), shown(bed["max"]["value"])
    rates = (shown(nozzle["max_change_per_s"]["value"]), shown(bed["max_change_per_s"]["value"]))
    refused = scenario.exchange(RECORD, "nozzle-too-hot")["error"]["data"]
    asked = shown(refused["requested"]["value"])
    warmer = scenario.exchange(RECORD, "bed-warmer")["bed_target"]
    citation = rf"\({re.escape(printer['file'])}, confirmed by (\S+) (\d{{4}}-\d{{2}}-\d{{2}})\)"
    counts = RECORD["audit"]["counts"]
    approved = scenario.exchange(RECORD, "owner-approves")
    d = DEGREES
    return {
        r"(\d+) requests, (\d+) refused,? (?:and )?(\d+) confirmed by a person": (
            str(counts["requests"]),
            str(counts["refused"]),
            str(counts["confirmed_by_a_person"]),
        ),
        r"printer's state becomes (\w+)": (approved["printer"]["state"],),
        r"extruder_target (\d+) degC exceeds the limit of (\d+) degC": (asked, shown(refused["limit"]["value"])),
        citation: (printer["confirmed"]["by"], printer["confirmed"]["at"]),
        rf"(?:bed|`?bed_target`?) from (\d+){d} to (\d+){d}": (
            shown(warmer["before"]["value"]),
            shown(warmer["after"]["value"]),
        ),
        rf"\b(\d+){d} nozzle": (asked,),
        rf"nozzle temperature of (\d+){d}": (asked,),
        rf"at the (\d+){d} limit": (hottest,),
        rf"since the limit is (\d+){d}": (hottest,),
        rf"`?extruder_target`? (?:is )?limited to (\d+){d}": (hottest,),
        rf"`?bed_target`? (?:is )?limited to (\d+){d}": (warmest,),
        rf"`extruder_target` takes 0 to (\d+){d} and `bed_target` takes 0 to (\d+){d}": (hottest, warmest),
        rf"nozzle target stays at or below (\d+){d} and the bed target at or below (\d+){d}": (hottest, warmest),
        rf"changing by at most (\d+) and (\d+){d} per second": rates,
        rf"nozzle target changes by at most (\d+){d} per second, and the bed target by at most (\d+){d}": rates,
    }


def plant_facts() -> dict[str, tuple[str, ...]]:
    """What each plant waterer value pattern must say, from its mock file and docs/demo/e2e.yaml."""
    water = MOCK.actions["water"]
    duration = water.args["duration"]
    assert duration.min is not None
    assert duration.max is not None
    assert water.max_runs is not None
    longest, shortest = shown(duration.max), shown(duration.min)
    runs = str(water.max_runs.count)
    window = f"{shown(water.max_runs.per / 3600)} h"
    tank = next(item.message for item in water.require if not isinstance(item, str))
    soil = e2e.step(FULL, "agent-reads-again")["soil_moisture"]
    before, after = shown(soil["before"]["value"]), shown(soil["after"]["value"])
    asked = shown(e2e.step(FULL, "too-long")["arguments"]["args"]["duration"]["value"])
    return {
        r"water duration \d+ s exceeds the limit of (\d+) s": (longest,),
        r"water duration \d+ s is below the limit of (\d+) s": (shortest,),
        r"The duration limit is (\d+) s \(max\)": (longest,),
        r"ERR limit duration max (\d+)": (longest,),
        r"[Ww]atering runs at most (\d+) s": (longest,),
        r"water may run at most (\d+) times per (\d+ \w+)": (runs, window),
        r"(?:pump|water|watering)[^.\n]*?\b(\d+) (?:runs|times) (?:per|an|each) (?:hour|1 h)\b": (runs,),
        r"(?i)(pump can.?t run while[^.\"\n]*?empty)": (tank or "",),
        r"rises from (\d+) ?% to (\d+) ?%": (before, after),
        r"VAL soil_moisture (\d+)": (before,),
        r"EVT soil_moisture (\d+)": (after,),
        r"request to water for (\d+) s": (asked,),
    }


def facts() -> dict[str, tuple[str, ...]]:
    return {**printer_facts(), **plant_facts()}


def demo_values(text: str) -> dict[str, list[tuple[str, ...]]]:
    flat = re.sub(r"\s+", " ", text)
    return {pattern: [match.groups() for match in re.finditer(pattern, flat)] for pattern in facts()}


def disagreements(text: str) -> list[str]:
    """Every demo value in the text that differs from the recorded values."""
    wrong = []
    expected_by_pattern = facts()
    for pattern, found in demo_values(text).items():
        expected = expected_by_pattern[pattern]
        for groups in found:
            said = tuple(group[:1].lower() + group[1:] for group in groups)
            if said != tuple(value[:1].lower() + value[1:] for value in expected):
                wrong.append(f"{groups} where the record gives {expected} ({pattern})")
    return wrong


def test_the_value_check_catches_drifted_numbers() -> None:
    text = (
        "water duration 120 s exceeds the limit of 25 s. Soil moisture rises from 31 % to 50 %. "
        "Pump can't run while the tank is empty. The pump runs at most 4 times per hour. "
        "extruder_target 300 degC exceeds the limit of 250 degC. It warms the bed from 60 °C to 75 °C."
    )
    assert len(disagreements(text)) == 6
    assert not disagreements(
        "water duration 120 s exceeds the limit of 30 s. Pump can't run while tank is empty. "
        "extruder_target 300 degC exceeds the limit of 260 degC. It warms the bed from 60 °C to 70 °C."
    )


@pytest.mark.parametrize("page", demo_pages(), ids=lambda page: str(page.relative_to(ROOT)))
def test_demo_values_match_the_recorded_scenario(page: Path) -> None:
    wrong = disagreements(page.read_text(encoding="utf-8"))
    assert not wrong, f"{page.relative_to(ROOT)} disagrees with the records:\n" + "\n".join(wrong)


def test_every_demo_value_check_finds_something() -> None:
    seen = {pattern: 0 for pattern in facts()}
    for page in demo_pages():
        for pattern, found in demo_values(page.read_text(encoding="utf-8")).items():
            seen[pattern] += len(found)
    assert all(seen.values()), [pattern for pattern, count in seen.items() if not count]


def test_the_recorded_limits_are_the_printer_files_limits() -> None:
    file = load(scenario.example(scenario.FOLDER, scenario.FILES[scenario.DEVICE]))
    printer = next(device for device in RECORD["devices"] if device["id"] == scenario.DEVICE)
    for name, limits in printer["limits"].items():
        channel = file.write[name]
        assert (limits["max"]["value"], limits["max_change_per_s"]["value"]) == (channel.max, channel.max_change_per_s)
    assert file.confirmed is not None
    assert printer["confirmed"] == {"by": file.confirmed.by, "at": str(file.confirmed.at)}


DESK_FAN = re.compile(r"(?i)\bdesk[- _]fan\b")
DESK_FAN_ALLOWED = {
    "docs/DESIGN.md": "says the desk fan stays only in spec/examples/",
}
"""Pages outside spec/examples/ that may still name the desk fan, and why."""


def test_the_desk_fan_stays_in_spec_examples() -> None:
    pages = [page for page in demo_pages() if str(page.relative_to(ROOT)) not in DESK_FAN_ALLOWED]
    found = [str(page.relative_to(ROOT)) for page in pages if DESK_FAN.search(page.read_text(encoding="utf-8"))]
    assert not found, f"These pages still show the desk fan: {found}"


def test_the_package_never_explains_itself_with_the_desk_fan() -> None:
    """Docstrings, help text and tool descriptions. Driver fixtures and simulators keep the desk fan."""
    package = ROOT / "openhal"
    found = [
        str(path.relative_to(ROOT))
        for path in sorted(package.rglob("*.py"))
        if "drivers" not in path.relative_to(package).parts and DESK_FAN.search(path.read_text(encoding="utf-8"))
    ]
    assert not found, f"These modules still show the desk fan: {found}"
