"""The issue forms in .github/ISSUE_TEMPLATE follow GitHub's form schema.

GitHub shows a form only when the form is valid, and skips a label that the repository lacks, so
this checks the rules from GitHub's "Syntax for GitHub's form schema" page. Each form has a unique
name, a description and a body. Each element has a known type and its required attributes, each id
uses letters, digits, dashes and underscores and is unique in its form, a dropdown's options are
distinct, and every label a form adds is one of GitHub's default labels or one of the two the
maintainers add, driver and device file.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Final

import pytest
import yaml

ROOT: Final = Path(__file__).resolve().parents[2]
FOLDER: Final = ROOT / ".github" / "ISSUE_TEMPLATE"
FORMS: Final = sorted(path for path in FOLDER.glob("*.yml") if path.name != "config.yml")
LABELS: Final = frozenset(
    {"bug", "enhancement", "documentation", "good first issue", "help wanted", "driver", "device file"}
)
REQUIRED: Final = {
    "markdown": {"value"},
    "textarea": {"label"},
    "input": {"label"},
    "dropdown": {"label", "options"},
    "checkboxes": {"label", "options"},
    "upload": {"label"},
}
ID: Final = re.compile(r"^[A-Za-z0-9_-]+$")


def form(path: Path) -> dict[str, Any]:
    data: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data


def test_the_three_forms_exist() -> None:
    assert [path.name for path in FORMS] == ["bug-report.yml", "device-file-request.yml", "driver-request.yml"]
    assert len({form(path)["name"] for path in FORMS}) == len(FORMS)


@pytest.mark.parametrize("path", FORMS, ids=lambda path: path.name)
def test_a_form_follows_the_schema(path: Path) -> None:
    data = form(path)
    assert set(data) <= {"name", "description", "title", "labels", "assignees", "projects", "type", "body"}
    assert data["name"].strip()
    assert data["description"].strip()
    assert set(data.get("labels", [])) <= LABELS
    ids = []
    for element in data["body"]:
        assert element["type"] in REQUIRED, element
        assert REQUIRED[element["type"]] <= set(element["attributes"]), element
        if element["type"] == "markdown":
            assert "id" not in element
            continue
        assert ID.match(element["id"]), element["id"]
        ids.append(element["id"])
        options = element["attributes"].get("options", [])
        if element["type"] == "dropdown":
            assert options
            assert len(set(options)) == len(options)
        if element["type"] == "checkboxes":
            assert all(set(option) <= {"label", "required"} and option["label"] for option in options)
    assert len(ids) == len(set(ids))
    assert any(element.get("validations", {}).get("required") for element in data["body"])


def test_the_chooser_points_questions_away_from_issues() -> None:
    config = yaml.safe_load((FOLDER / "config.yml").read_text(encoding="utf-8"))
    assert set(config) == {"blank_issues_enabled", "contact_links"}
    urls = [link["url"] for link in config["contact_links"]]
    assert all({"name", "url", "about"} == set(link) for link in config["contact_links"])
    assert "https://github.com/sohan-bhat/OpenHAL/discussions" in urls
    assert any(url.endswith("/security/advisories/new") for url in urls)
