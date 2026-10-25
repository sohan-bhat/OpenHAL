"""library/README.md is generated from the files and lists every one of them."""

from __future__ import annotations

from pathlib import Path

from openhal.cli import library_cmd

LIBRARY = Path(__file__).resolve().parents[2] / "library"


def test_the_readme_is_current() -> None:
    expected = library_cmd.readme(library_cmd.entries([LIBRARY]))
    assert (LIBRARY / "README.md").read_text(encoding="utf-8") == expected, (
        "library/README.md is out of date. Run uv run python -m openhal.cli.library_cmd"
    )


def test_the_readme_links_every_file() -> None:
    text = (LIBRARY / "README.md").read_text(encoding="utf-8")
    for path in sorted(LIBRARY.rglob("*.hal.yaml")):
        assert f"({path.parent.name}/{path.name})" in text, path.name


def test_every_driver_in_the_library_has_a_section_title() -> None:
    drivers = {entry.file.connect.driver for entry in library_cmd.entries([LIBRARY])}
    assert drivers <= set(library_cmd.FAMILIES)
