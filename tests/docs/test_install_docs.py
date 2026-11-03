"""Every install command in the docs comes from website/src/config/install.json.

scripts/install_docs.py writes the one-line installers and the uv and pipx commands into the
install guide and the quickstart, and the installers and the demo command into the README. The
home page's install box and demo section read the same file, so no install command is written
twice. The installers are the first thing the install guide and the quickstart show, and the
README names the Python versions that pyproject.toml's requires-python allows.
"""

from __future__ import annotations

import importlib.util
import re
import tomllib
from pathlib import Path
from types import ModuleType
from typing import Final

import pytest

from openhal._brand import DISTRIBUTION_NAME

ROOT: Final = Path(__file__).resolve().parents[2]
HISTORY: Final = ("docs/agents/", "docs/design-rounds/", "docs/verification/", "docs/adr/", "docs/releases/")
BLOCK: Final = re.compile(r"<!-- (install|tools|demo):start -->.*?<!-- \1:end -->", re.DOTALL)
README: Final = ROOT / "README.md"


def generator() -> ModuleType:
    spec = importlib.util.spec_from_file_location("install_docs", ROOT / "scripts" / "install_docs.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


DOCS: Final = generator()
CONFIG: Final = DOCS.read()


@pytest.mark.parametrize("page", DOCS.PAGES, ids=lambda page: page.name)
def test_pages_match_install_json(page: Path) -> None:
    text = page.read_text(encoding="utf-8")
    assert "<!-- install:start -->" in text
    assert DOCS.synced(text, CONFIG) == text, "Run uv run python scripts/install_docs.py"


def test_the_installers_come_first() -> None:
    guide = (ROOT / "docs" / "guide" / "install.md").read_text(encoding="utf-8")
    assert guide.startswith("# Install\n\n<!-- install:start -->\n")
    assert guide.index("<!-- tools:start -->") < guide.index("## From a clone")
    quickstart = (ROOT / "docs" / "guide" / "quickstart.md").read_text(encoding="utf-8")
    assert quickstart.index("<!-- install:start -->") < quickstart.index("## Run the demo")
    assert "uv run openhal" not in quickstart, "the quickstart runs the openhal the installer put on PATH"


def test_both_installers_are_on_both_pages() -> None:
    for page in DOCS.PAGES:
        text = page.read_text(encoding="utf-8")
        for name in ("install.sh | sh", "install.ps1 | iex"):
            assert f"{CONFIG['site']}/{name}" in text, f"{page.name} lacks {name}"
    for name in ("install.sh", "install.ps1"):
        assert (ROOT / "website" / "public" / name).is_file()


def test_uv_and_pipx_install_from_pypi_once_install_json_says_so() -> None:
    before = DOCS.tools({**CONFIG, "onPyPI": False})
    assert "isn't on PyPI yet" in before
    assert "uv tool install git+https://github.com/sohan-bhat/OpenHAL" in before
    after = DOCS.tools({**CONFIG, "onPyPI": True})
    assert f"\nuv tool install {DISTRIBUTION_NAME}\npipx install {DISTRIBUTION_NAME}\n" in after
    assert "git+" not in after
    assert DOCS.tools(CONFIG) == (after if CONFIG["onPyPI"] else before)


def test_the_readme_installs_then_runs_the_demo() -> None:
    text = README.read_text(encoding="utf-8")
    assert text.index("<!-- install:start -->") < text.index("<!-- demo:start -->") < text.index("## Why OpenHAL")
    assert "<!-- tools:start -->" not in text, "the README shows the one-line installers and links the install guide"
    assert "uv run openhal" not in text, "the README runs the openhal the installer put on PATH"


def test_the_demo_runs_with_uvx_once_install_json_says_so() -> None:
    uvx = f"uvx {DISTRIBUTION_NAME} demo"
    before = DOCS.demo({**CONFIG, "onPyPI": False})
    assert "```text\nopenhal demo\n```" in before
    assert "uvx" not in before
    after = DOCS.demo({**CONFIG, "onPyPI": True})
    assert f"```text\n{uvx}\n```" in after
    assert after.index("openhal demo") < after.index(uvx)
    assert DOCS.demo(CONFIG) == (after if CONFIG["onPyPI"] else before)


def test_no_page_runs_uvx_with_the_command_name() -> None:
    """`uvx openhal` would fetch a different project from PyPI, because the distribution is named halkit."""
    wrong = [
        str(path.relative_to(ROOT))
        for path in [*current_files(), ROOT / "website" / "src" / "config" / "install.json"]
        if re.search(r"\buvx (?:--\S+ )*openhal\b", path.read_text(encoding="utf-8", errors="ignore"))
    ]
    assert not wrong, f"Run uvx {DISTRIBUTION_NAME}, not uvx openhal, in {wrong}"


def test_the_readme_names_the_python_versions_from_pyproject() -> None:
    required = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["requires-python"]
    found = re.fullmatch(r">=\s*(\d+\.\d+)", required)
    assert found, f"requires-python is {required!r}, so the README sentence needs a new form"
    text = README.read_text(encoding="utf-8")
    assert f"OpenHAL runs on Python {found.group(1)} or newer." in text
    assert set(re.findall(r"Python (\d+\.\d+)", text)) == {found.group(1)}


def test_install_json_names_the_distribution_only_through_the_brand() -> None:
    text = (ROOT / "website" / "src" / "config" / "install.json").read_text(encoding="utf-8")
    assert DISTRIBUTION_NAME not in text
    assert "{distribution}" in text


def current_files() -> list[Path]:
    found = [ROOT / "README.md", ROOT / "CONTRIBUTING.md"]
    found += sorted((ROOT / "docs").rglob("*.md"))
    found += sorted(path for path in (ROOT / "website" / "src").rglob("*") if path.is_file())
    return [
        path
        for path in found
        if not path.relative_to(ROOT).as_posix().startswith(HISTORY) and path.name != "install.json"
    ]


def test_no_install_command_is_written_by_hand() -> None:
    commands = [DOCS.fill(channel["command"], CONFIG) for channel in CONFIG["channels"]]
    commands += [DOCS.fill(channel["beforePyPI"], CONFIG) for channel in CONFIG["channels"] if "beforePyPI" in channel]
    commands.append(DOCS.fill(CONFIG["demo"]["fromPyPI"], CONFIG))
    by_hand = []
    for path in current_files():
        try:
            text = BLOCK.sub("", path.read_text(encoding="utf-8"))
        except UnicodeDecodeError:
            continue
        for command in commands:
            if re.search(rf"^\s*{re.escape(command)}\s*$|`{re.escape(command)}`", text, re.M):
                by_hand.append(f"{path.relative_to(ROOT)} writes {command}")
        for name in ("install.sh", "install.ps1"):
            if f"{CONFIG['site']}/{name}" in text:
                by_hand.append(f"{path.relative_to(ROOT)} points at {name}")
    assert not by_hand, "Take these from install.json\n" + "\n".join(by_hand)
