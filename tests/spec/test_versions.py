"""Spec and protocol versions are numbers, MAJOR.MINOR, that people see as v0.1 (ADR 0017).

spec/versions.json, the folders under spec/, the hub's supported versions and the generated schema
must name the same versions, so the website, the Inspector and the hub can't drift apart.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

from openhal.protocol.version import LATEST, PROTOCOL_VERSIONS, is_version, label, negotiate, parts, supported

ROOT = Path(__file__).resolve().parents[2]
SPEC = ROOT / "spec"
VERSION_FOLDER = re.compile(r"v[0-9]")
DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")


def versions() -> dict[str, Any]:
    found: dict[str, Any] = json.loads((SPEC / "versions.json").read_text(encoding="utf-8"))
    return found


def folders(pattern: re.Pattern[str]) -> list[str]:
    return sorted(path.name for path in SPEC.iterdir() if path.is_dir() and pattern.match(path.name))


def test_the_first_draft_is_version_0_1() -> None:
    assert versions() == {"latest": "0.1", "versions": [{"version": "0.1", "status": "draft"}]}
    assert (PROTOCOL_VERSIONS, LATEST, label(LATEST), supported()) == (["0.1"], "0.1", "v0.1", "0.1")


def test_every_version_has_its_folder_and_no_dated_folder_is_left() -> None:
    listed = [entry["version"] for entry in versions()["versions"]]
    assert all(is_version(version) for version in listed), listed
    assert {entry["status"] for entry in versions()["versions"]} <= {"draft", "final"}
    assert folders(VERSION_FOLDER) == sorted(label(version) for version in listed)
    assert all((SPEC / label(version) / "index.md").is_file() for version in listed)
    assert folders(DATE) == []


def test_the_hub_speaks_the_latest_version_and_every_version_it_speaks_is_published() -> None:
    assert versions()["latest"] == LATEST
    assert set(PROTOCOL_VERSIONS) <= {entry["version"] for entry in versions()["versions"]}
    assert sorted(PROTOCOL_VERSIONS, key=parts) == PROTOCOL_VERSIONS


@pytest.mark.parametrize("text", ["0.1", "0.10", "1.0", "12.34"])
def test_version_numbers(text: str) -> None:
    assert is_version(text)


@pytest.mark.parametrize("text", ["2026-10-24", "v0.1", "0.1.0", "01.1", "0.01", "1", "0.1\n", " 0.1", "", "latest"])
def test_what_is_not_a_version_number(text: str) -> None:
    assert not is_version(text)
    with pytest.raises(ValueError, match="is not a version number"):
        parts(text)


def test_versions_compare_as_numbers() -> None:
    assert parts("0.10") > parts("0.9") > parts("0.1")
    assert parts("1.0") > parts("0.99")
    assert negotiate("0.1") == "0.1"
    assert negotiate("0.2") == negotiate("1.0") == LATEST


def test_the_generated_schema_names_the_version() -> None:
    schema = json.loads((SPEC / label(LATEST) / "schema.json").read_text(encoding="utf-8"))
    assert (schema["title"], schema["protocolVersion"]) == ("OpenHAL hub protocol v0.1", "0.1")
    reference = (SPEC / label(LATEST) / "schema.md").read_text(encoding="utf-8")
    assert reference.startswith("# Schema reference, v0.1\n")
