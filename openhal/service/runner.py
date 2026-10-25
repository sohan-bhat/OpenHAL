"""One small runner for every command and file change a setup step makes.

`Runner` runs commands and writes files. With `dry_run` it prints each step instead and changes
nothing, which is what `--dry-run` shows. Tests use a subclass that records the steps.
"""

from __future__ import annotations

import shlex
import shutil
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Ran:
    """A finished command, with stdout and stderr together."""

    argv: tuple[str, ...]
    code: int
    output: str = ""

    @property
    def ok(self) -> bool:
        return self.code == 0


class RunError(RuntimeError):
    """A command failed. The message names the command and repeats its output."""


@dataclass
class Runner:
    """Runs commands and changes files, or with `dry_run` only says what it would do."""

    dry_run: bool = False
    echo: Callable[[str], None] = field(default=print)
    timeout_s: float = 60.0

    def run(self, argv: Sequence[str], *, check: bool = True) -> Ran:
        words = tuple(str(word) for word in argv)
        if self.dry_run:
            self.echo(f"would run    {shlex.join(words)}")
            return Ran(words, 0)
        result = self._execute(words)
        if check and not result.ok:
            raise RunError(f"{shlex.join(words)} exited {result.code}. {result.output}".strip())
        return result

    def _execute(self, words: tuple[str, ...]) -> Ran:
        try:
            done = subprocess.run(  # noqa: S603 (an argument list, never a shell string)
                list(words), capture_output=True, text=True, timeout=self.timeout_s, check=False
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return Ran(words, 127, str(exc))
        return Ran(words, done.returncode, (done.stdout + done.stderr).strip())

    def write(self, path: Path, text: str, mode: int = 0o644) -> None:
        """Write a file in one step, through a temporary file next to it."""
        if self.dry_run:
            self.echo(f"would write  {path}")
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.openhal-tmp")
        temporary.write_text(text, encoding="utf-8")
        temporary.chmod(mode)
        temporary.replace(path)

    def copy(self, source: Path, target: Path) -> None:
        if self.dry_run:
            self.echo(f"would copy   {source} to {target}")
            return
        shutil.copy2(source, target)

    def remove(self, path: Path) -> None:
        if self.dry_run:
            self.echo(f"would remove {path}")
            return
        path.unlink(missing_ok=True)
