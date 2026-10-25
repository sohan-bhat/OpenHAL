"""Run the shell commands the website shows, against the real CLI and an embedded hub.

A `Session` owns a temporary OPENHAL_HOME. `openhal ...` runs the real Typer app in-process.
`openhald` starts the real hub on a free loopback port. Install and client setup commands that
can't run offline are checked against pyproject.toml and the CLI's own options instead. Commands
that need a person's typed phrase get it, as a person at a terminal would type it.
"""

from __future__ import annotations

import contextlib
import os
import re
import shlex
import subprocess
import sys
import time
import tomllib
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from unittest import mock

from typer.testing import CliRunner

from openhal.cli import _tty
from openhal.cli.main import app
from tests.website.embedded_hub import EmbeddedHub

ROOT = Path(__file__).resolve().parents[2]
PHRASES = {
    ("file", "confirm"): "confirm",
    ("unlock",): "unlock",
    ("confirm", "approve"): "approve",
    ("routine", "enable"): "enable",
    ("routine", "run"): "run",
    ("routine", "approve"): "approve",
    ("writer", "finish"): "save",
}


@dataclass
class Result:
    command: str
    code: int
    output: str


class SnippetError(AssertionError):
    pass


HUB_SETTLE_S = 2.5
"""After `openhald`, wait as long as a person takes to type the next command, so rate limits
measured from the hub's first reading behave as they would at a real terminal."""


class Session:
    def __init__(self, home: Path) -> None:
        self.home = home
        self.workdir = home.parent / "work"
        self.workdir.mkdir(parents=True, exist_ok=True)
        self.hub: EmbeddedHub | None = None
        self.runner = CliRunner()

    def close(self) -> None:
        if self.hub is not None:
            self.hub.stop()
            self.hub = None

    @contextlib.contextmanager
    def environment(self) -> Iterator[None]:
        saved = {key: os.environ.get(key) for key in ("OPENHAL_HOME", "OPENHAL_URL", "OPENHAL_TOKEN")}
        os.environ["OPENHAL_HOME"] = str(self.home)
        os.environ.pop("OPENHAL_TOKEN", None)
        if self.hub is not None:
            os.environ["OPENHAL_URL"] = self.hub.url
        else:
            os.environ.pop("OPENHAL_URL", None)
        try:
            yield
        finally:
            for key, value in saved.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

    def expand(self, text: str) -> str:
        return text.replace("~/.openhal", str(self.home)).replace("$OPENHAL_HOME", str(self.home))

    def tidy(self, output: str) -> str:
        """Show paths as a reader would see them, under ~/.openhal."""
        return output.replace(str(self.home), "~/.openhal")

    def run(self, line: str) -> Result:
        line = line.strip()
        redirect: Path | None = None
        tail: int | None = None
        match = re.match(r"^(.*?)\s*\|\s*tail -(\d+)\s*>\s*(\S+)$", line)
        if match:
            line, tail, redirect = match.group(1), int(match.group(2)), Path(self.expand(match.group(3)))
        words = shlex.split(self.expand(line))
        if not words:
            return Result(line, 0, "")
        program = words[0]
        if program == "openhald":
            return self.start_hub(words[1:])
        if program == "openhal":
            result = self.openhal(words[1:])
        elif program == "chmod":
            os.chmod(words[2], int(words[1], 8))
            result = Result(line, 0, "")
        elif words[:3] == ["uv", "run", "pytest"]:
            result = self.pytest(words[3:])
        elif program in ("uv", "pipx", "pip"):
            result = self.check_install(words)
        elif program == "claude":
            result = self.check_claude(words)
        else:
            raise SnippetError(
                f"The snippet runner doesn't know how to run {program!r}. Add support or drop the tested mark."
            )
        if redirect is not None:
            lines = [item for item in result.output.splitlines() if item.strip()]
            redirect.write_text("\n".join(lines[-(tail or 1) :]) + "\n", encoding="utf-8")
            result = Result(result.command, result.code, "")
        return result

    def openhal(self, args: list[str]) -> Result:
        phrase = next((value for key, value in PHRASES.items() if tuple(args[: len(key)]) == key), None)
        with self.environment(), contextlib.chdir(self.workdir), contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch("getpass.getuser", return_value="owner"))
            if phrase is not None:
                stack.enter_context(mock.patch.object(_tty, "interactive", return_value=True))
                stack.enter_context(mock.patch.object(_tty, "read_phrase", return_value=phrase))
            result = self.runner.invoke(app, args, catch_exceptions=False)
        return Result("openhal " + shlex.join(args), result.exit_code, self.tidy(result.output))

    def start_hub(self, args: list[str]) -> Result:
        if args and args != ["&"]:
            raise SnippetError(f"openhald is only run without options in snippets, not {args}.")
        if self.hub is None:
            self.hub = EmbeddedHub(self.home)
            self.hub.start()
            time.sleep(HUB_SETTLE_S)
        return Result("openhald", 0, "")

    def pytest(self, args: list[str]) -> Result:
        """Run pytest on part of the repository's own suite, as a contributor would."""
        for arg in args:
            if not arg.startswith("-") and not (ROOT / arg.split("::")[0]).exists():
                raise SnippetError(f"pytest target {arg} doesn't exist in the repository.")
        done = subprocess.run(
            [sys.executable, "-m", "pytest", *args, "-p", "no:cacheprovider"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=600,
            check=False,
        )
        return Result("uv run pytest " + shlex.join(args), done.returncode, done.stdout + done.stderr)

    def check_install(self, words: list[str]) -> Result:
        project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
        target = words[-1]
        match = re.fullmatch(r"(?:([A-Za-z][A-Za-z0-9_.-]*)|\.)\[([a-z,]+)\]", target)
        if not match:
            raise SnippetError(f"Can't check the install target {target!r}.")
        name, extras = match.group(1), match.group(2).split(",")
        if name is not None and name != project["name"]:
            raise SnippetError(f"Install snippet names {name}, but the distribution is {project['name']}.")
        missing = set(extras) - set(project.get("optional-dependencies", {}))
        if missing:
            raise SnippetError(f"Install snippet asks for extras {sorted(missing)} that pyproject.toml lacks.")
        for script in ("openhal", "openhald"):
            if script not in project["scripts"]:
                raise SnippetError(f"pyproject.toml has no {script} script.")
        return Result(shlex.join(words), 0, "")

    def check_claude(self, words: list[str]) -> Result:
        if words[:3] != ["claude", "mcp", "add"] or "--" not in words:
            raise SnippetError("Only `claude mcp add NAME [options] -- openhal mcp ...` snippets can be checked.")
        inner = words[words.index("--") + 1 :]
        if inner[:2] != ["openhal", "mcp"]:
            raise SnippetError(f"The client should start `openhal mcp`, not {inner}.")
        help_text = self.openhal(["mcp", "--help"]).output
        for option in (word for word in inner[2:] if word.startswith("--")):
            if option not in help_text:
                raise SnippetError(f"openhal mcp has no option {option}.")
        return Result(shlex.join(words), 0, "")
