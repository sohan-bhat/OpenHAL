"""Fixtures for the CLI tests. A fake runner and a temporary HOME for the init and service tests.

`FakeRunner` records every command and answers from a table, and real subprocesses are refused, so
no test can load, start or enable a real launchd or systemd service. Every config file the tests
write lands in a temporary HOME.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

from openhal.cli import _common, service_cmd
from openhal.service import runner as runner_module
from openhal.service.runner import Ran, Runner


class FakeRunner(Runner):
    def __init__(self, dry_run: bool = False, answers: dict[str, tuple[int, str]] | None = None) -> None:
        super().__init__(dry_run=dry_run, echo=lambda line: _common.console.print(line))
        self.commands: list[str] = []
        self.answers = answers or {}

    def _execute(self, words: tuple[str, ...]) -> Ran:
        line = " ".join(words)
        self.commands.append(line)
        for prefix, (code, output) in self.answers.items():
            if line.startswith(prefix):
                return Ran(words, code, output)
        return Ran(words, 0, "")


@dataclass
class Machine:
    home: Path
    config: Path
    runner: FakeRunner


def _refuse(*args: object, **kwargs: object) -> object:
    raise AssertionError(f"A test tried to run a real command: {args}")


@pytest.fixture
def machine(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Machine:
    """A temporary HOME and config folder, a fake runner, and macOS unless a test picks Linux."""
    home = tmp_path / "user"
    home.mkdir()
    config = tmp_path / "config"
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("OPENHAL_HOME", str(config))
    monkeypatch.setenv("USER", "pi")
    monkeypatch.setenv("LOGNAME", "pi")
    monkeypatch.delenv("OPENHAL_TOKEN", raising=False)
    monkeypatch.delenv("OPENHAL_URL", raising=False)
    monkeypatch.setattr(runner_module.subprocess, "run", _refuse)
    monkeypatch.setattr(subprocess, "Popen", _refuse)
    fake = FakeRunner()

    def runner_for(dry_run: bool) -> Runner:
        fake.dry_run = dry_run
        return fake

    monkeypatch.setattr(service_cmd, "runner_for", runner_for)
    monkeypatch.setattr(service_cmd, "this_platform", lambda: "macos")
    return Machine(home, config, fake)
