"""The PyPI distribution is DISTRIBUTION_NAME everywhere, and the package keeps one version number.

ADR 0002 names the distribution `halkit`. The import package, the CLI and the product keep the name
openhal. Release builds publish the tag `v<version>`, and `openhal --version` prints
`openhal.__version__`, so pyproject.toml, uv.lock and the package carry the same version.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path
from typing import Final

import yaml

import openhal
from openhal._brand import CLI_NAME, DAEMON_ALIAS, DISTRIBUTION_NAME, PACKAGE_NAME

ROOT: Final = Path(__file__).resolve().parents[2]
PROJECT: Final = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
RETIRED: Final = re.compile(r"openhal[-_]hub(?!-protocol)")
INSTALL_SPECS: Final = (
    re.compile(r'"([\w.-]+)\[[\w,-]+\] @ git\+'),
    re.compile(r'install (?:--[\w-]+ )*"([\w.-]+)\['),
)
HISTORY: Final = (
    "docs/agents/",
    "docs/internal/",
    "docs/design-rounds/",
    "docs/verification/",
    "docs/adr/0002-naming-and-distribution.md",
)
"""Records of past work, which keep the names they were written with."""


def current_files() -> list[Path]:
    found = [ROOT / "README.md", ROOT / ".github" / "CONTRIBUTING.md", ROOT / ".github" / "SECURITY.md"]
    for folder, pattern in (("docs", "*.md"), ("spec", "*.md"), ("examples", "*.md"), ("openhal", "*.py")):
        found += sorted((ROOT / folder).rglob(pattern))
    found += sorted(path for path in (ROOT / "scripts").iterdir() if path.is_file())
    found += sorted(path for path in (ROOT / "website" / "src").rglob("*") if path.is_file())
    found.append(ROOT / "firmware" / "arduino" / "OpenHAL" / "README.md")
    return [path for path in found if not path.relative_to(ROOT).as_posix().startswith(HISTORY)]


def text_of(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return ""


def test_pyproject_names_the_brand_distribution() -> None:
    assert PROJECT["name"] == DISTRIBUTION_NAME


def test_the_import_package_and_commands_keep_their_names() -> None:
    assert PACKAGE_NAME == "openhal"
    cli = "openhal.cli.main:app"
    assert PROJECT["scripts"] == {CLI_NAME: cli, DISTRIBUTION_NAME: cli, DAEMON_ALIAS: "openhal.hub.daemon:main"}
    assert openhal.__name__ == PACKAGE_NAME


def test_the_install_matrix_runs_every_python_the_classifiers_name() -> None:
    """CI installs the wheel and the sdist on each Python the package says it supports, and on no other."""
    prefix = "Programming Language :: Python :: "
    named = {item.removeprefix(prefix) for item in PROJECT["classifiers"] if item.startswith(prefix + "3.")}
    ci = yaml.safe_load((ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8"))
    assert set(ci["jobs"]["install"]["strategy"]["matrix"]["python"]) == named


def test_the_lock_file_follows_pyproject() -> None:
    lock = (ROOT / "uv.lock").read_text(encoding="utf-8")
    entry = f'name = "{DISTRIBUTION_NAME}"\nversion = "{PROJECT["version"]}"\nsource = {{ editable = "." }}'
    assert f"[[package]]\n{entry}" in lock, "Run uv lock after changing the name or the version in pyproject.toml"


def test_the_package_version_is_the_project_version() -> None:
    assert openhal.__version__ == PROJECT["version"], "openhal/__init__.py and pyproject.toml must give one version"


def test_install_commands_name_the_distribution() -> None:
    wrong: list[str] = []
    for path in current_files():
        text = text_of(path)
        where = path.relative_to(ROOT).as_posix()
        wrong += [f"{where} names {found!r}" for found in RETIRED.findall(text)]
        for pattern in INSTALL_SPECS:
            wrong += [f"{where} installs {name!r}" for name in pattern.findall(text) if name != DISTRIBUTION_NAME]
    assert not wrong, f"Install {DISTRIBUTION_NAME}, not\n" + "\n".join(wrong)


def test_the_install_check_catches_an_old_name() -> None:
    page = 'uv tool install --compile-bytecode "openhal-hub[serial] @ git+https://github.com/sohan-bhat/OpenHAL"'
    assert RETIRED.search(page)
    assert [name for pattern in INSTALL_SPECS for name in pattern.findall(page)] == ["openhal-hub", "openhal-hub"]
