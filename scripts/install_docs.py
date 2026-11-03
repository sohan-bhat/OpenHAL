"""Keep the install commands in the docs in step with website/src/config/install.json.

    uv run python scripts/install_docs.py

install.json holds every install command once, and the home page's install box reads the same
file. This rewrites the text between `<!-- install:start -->` and `<!-- install:end -->`, the
one-line installers, and between `<!-- tools:start -->` and `<!-- tools:end -->`, the uv and pipx
commands, in every page listed in PAGES. A page leaves out the blocks it has no markers for.
Until install.json says the distribution is on PyPI, uv and pipx install from the repository.
tests/docs/test_install_docs.py fails when a page differs from what this would write.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any, Final

from openhal._brand import DISTRIBUTION_NAME

ROOT: Final = Path(__file__).resolve().parents[1]
CONFIG: Final = ROOT / "website" / "src" / "config" / "install.json"
REPO_CONFIG: Final = ROOT / "website" / "src" / "config" / "repo.mjs"
PAGES: Final = (ROOT / "docs" / "guide" / "install.md", ROOT / "docs" / "guide" / "quickstart.md")


def read() -> dict[str, Any]:
    data: dict[str, Any] = json.loads(CONFIG.read_text(encoding="utf-8"))
    return data


def repository() -> str:
    found = re.search(r'REPOSITORY_URL = "([^"]+)"', REPO_CONFIG.read_text(encoding="utf-8"))
    assert found, f"{REPO_CONFIG} has no REPOSITORY_URL"
    return found.group(1)


def fill(template: str, config: dict[str, Any]) -> str:
    """A command with its {site}, {distribution} and {repository} filled in, as website/src/lib/install.ts does."""
    return (
        template.replace("{site}", config["site"])
        .replace("{distribution}", DISTRIBUTION_NAME)
        .replace("{repository}", repository())
    )


def installers(config: dict[str, Any]) -> str:
    parts = []
    for channel in config["channels"]:
        if "runIn" in channel:
            lead = f"On {channel['label']}, run this command in {channel['runIn']}."
            parts.append(f"{lead}\n\n```text\n{fill(channel['command'], config)}\n```")
    return "\n\n".join(parts)


def tools(config: dict[str, Any]) -> str:
    chosen = [channel for channel in config["channels"] if "beforePyPI" in channel]
    labels = [channel["label"] for channel in chosen]
    if config["onPyPI"]:
        lead = f"With {' or '.join(labels)} already installed, install `{DISTRIBUTION_NAME}` from PyPI."
        commands = [fill(channel["command"], config) for channel in chosen]
    else:
        lead = f"OpenHAL isn't on PyPI yet, so {' and '.join(labels)} install OpenHAL from GitHub, which needs git."
        commands = [fill(channel["beforePyPI"], config) for channel in chosen]
    return lead + "\n\n```text\n" + "\n".join(commands) + "\n```"


def blocks(config: dict[str, Any]) -> dict[str, str]:
    """The generated text for each marker name."""
    return {"install": installers(config), "tools": tools(config)}


def synced(text: str, config: dict[str, Any]) -> str:
    for name, body in blocks(config).items():
        pattern = re.compile(rf"(<!-- {name}:start -->\n)(?:.*?\n)?(<!-- {name}:end -->)", re.DOTALL)
        text = pattern.sub(_filler(body), text)
    return text


def _filler(body: str) -> Callable[[re.Match[str]], str]:
    def fill_block(match: re.Match[str]) -> str:
        return match.group(1) + body + "\n" + match.group(2)

    return fill_block


def main() -> None:
    config = read()
    for page in PAGES:
        page.write_text(synced(page.read_text(encoding="utf-8"), config), encoding="utf-8")
        print(f"synced {page.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
