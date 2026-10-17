"""Loading files safely, malicious inputs, examples and the published schema (threat T16)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from openhal.spec import DeviceFileError, loads, validate_path
from openhal.spec.loader import MAX_FILE_BYTES
from openhal.spec.schema import device_file_schema

ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = sorted((ROOT / "spec" / "examples").glob("*.hal.yaml"))


@pytest.mark.parametrize(
    ("text", "fragment"),
    [
        ("a: &x 1\nb: *x\n", "anchors"),
        ("device: !!python/object/apply:os.system ['true']\n", "tags"),
        ("device: !custom thing\n", "tags"),
        ("- just\n- a list\n", "mapping"),
        ("device: [unclosed\n", "YAML error"),
        ("device: x\nconnect: {driver: mock}\nwrite: {v: {unit: V, min: 0, max: .nan}}\n", "finite"),
        ("device: x\nconnect: {driver: mock}\nwrite: {v: {unit: V, min: 0, max: 1e999}}\n", "finite"),
    ],
)
def test_malicious_and_broken_files(text: str, fragment: str) -> None:
    with pytest.raises(DeviceFileError) as caught:
        loads(text)
    assert fragment.lower() in " ".join(caught.value.problems).lower()


def test_size_limit() -> None:
    with pytest.raises(DeviceFileError, match="larger than"):
        loads("device: x\nnotes: '" + "a" * MAX_FILE_BYTES + "'\n")


def test_problem_locations_are_readable() -> None:
    with pytest.raises(DeviceFileError) as caught:
        loads("device: x\nconnect: {driver: mock}\nwrite: {speed: {unit: percent, min: 10, max: 1}}\n")
    assert caught.value.problems[0].startswith("write.speed")


def test_missing_file() -> None:
    report = validate_path(ROOT / "does-not-exist.hal.yaml")
    assert not report.ok
    assert "Could not read" in report.problems[0]


@pytest.mark.parametrize("path", EXAMPLES, ids=lambda path: path.name)
def test_every_example_is_valid(path: Path) -> None:
    report = validate_path(path)
    assert report.ok, report.problems


def test_there_are_at_least_ten_examples() -> None:
    assert len(EXAMPLES) >= 10


def test_research_fan_example_stays_short() -> None:
    text = (ROOT / "spec" / "examples" / "desk-fan.hal.yaml").read_text()
    assert len(text.strip().splitlines()) <= 8


def test_published_schema_matches_models() -> None:
    published = json.loads((ROOT / "spec" / "schema" / "device-file.schema.json").read_text())
    assert published == json.loads(json.dumps(device_file_schema(), sort_keys=True))
