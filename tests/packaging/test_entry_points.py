"""Both installed commands run the same CLI.

`openhal` is the command every page uses. `halkit` is the same CLI under the distribution's name,
because `uvx halkit` and `pipx run halkit` run the command named like the package, so
`uvx halkit demo` works with no clone and no install.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from importlib.metadata import distribution
from pathlib import Path

import pytest

from openhal import __version__
from openhal._brand import CLI_NAME, DISTRIBUTION_NAME

COMMANDS = (CLI_NAME, DISTRIBUTION_NAME)


def test_both_entry_points_are_the_cli() -> None:
    scripts = {
        entry.name: entry.value
        for entry in distribution(DISTRIBUTION_NAME).entry_points
        if entry.group == "console_scripts"
    }
    assert {scripts[name] for name in COMMANDS} == {"openhal.cli.main:app"}


@pytest.mark.parametrize("name", COMMANDS)
def test_the_installed_command_runs(name: str) -> None:
    command = shutil.which(name, path=str(Path(sys.executable).parent))
    if command is None:
        pytest.skip(f"{name} is not installed next to {sys.executable}. Run uv sync.")
    done = subprocess.run([command, "--version"], capture_output=True, text=True, timeout=120, check=False)
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == f"{CLI_NAME} {__version__}"
