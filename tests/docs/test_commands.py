"""Every `openhal` command in README.md, docs/ and spec/ runs as written, or says why it can't here.

Commands come from fenced shell blocks and from inline code in the prose. Each one is checked
against the real command line first, so a command, option or argument the CLI doesn't have fails.
Then every runnable command in a page runs in order against the mock setup, the way a reader
follows the page. Each page gets a fresh OPENHAL_HOME. A hub on a loopback port with the simulated
plant waterer starts when the page starts one with `openhald`, or before the first command that
needs one. A command shown with output must print it, and output that starts with `blocked`,
`failed` or `error` means the command must exit non-zero. A fence with `file=NAME` is saved in the
working folder for the commands after it.

Discovery is stubbed for every driver while pages run, so no command can probe a real port, the
network or Bluetooth. `SKIPPED` lists what the check doesn't run and why. Nothing reaches hardware.
"""

from __future__ import annotations

import contextlib
import dataclasses
import functools
import re
import shlex
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final
from unittest import mock

import pytest
import typer
from typer.testing import CliRunner

from openhal.cli.main import app
from openhal.drivers import registry
from tests.website.shell import ROOT, Session
from tests.website.test_snippets import NOT_OURS, SOURCES

SNIPPET_PAGES: Final = frozenset(SOURCES) - NOT_OURS
"""Pages whose `tested` fences tests/website/test_snippets.py runs with their output."""

SKIPPED: Final[dict[tuple[str, ...], str]] = {
    ("discover",): "probes the machine's serial ports, network and Bluetooth",
    ("mcp",): "serves MCP on stdio until its client disconnects",
    ("rpc",): "bridges stdio to the hub until its client disconnects",
    ("service",): "installs or queries a launchd or systemd service on the machine",
    ("driver", "new"): "adds a driver package to the checkout. tests/cli/test_driver_cmd.py runs it on a copy",
    ("driver", "test", "x-acme-pump"): "tests the driver that openhal driver new adds to the checkout",
    ("writer", "interview"): "asks a person every limit question at the terminal",
}
"""Commands checked for syntax only, by their first words, with the reason they don't run here."""

SKIPPED_PAGES: Final[dict[str, str]] = {
    "docs/hardware-tests/": "needs the real device the plan tests",
}
"""Pages whose commands are checked for syntax only."""

NO_HUB: Final = frozenset({"init", "file", "demo", "driver", "--version", "--help"})
"""First words of commands that run without a hub, so the check doesn't start one for them."""

MOCK_SETUP: Final = (
    "openhal init",
    "openhal file confirm ~/.openhal/devices/plant-waterer.hal.yaml",
    "openhald",
)
DAEMON_OPTIONS: Final = frozenset({"--host", "--port", "--verbose", "--help"})
TARGETED: Final = (["write"], ["action"], ["dry-run"])
PLANNED: Final[dict[tuple[str, ...], str]] = {
    ("file", "migrate"): "ships with the first major version of the device file format (spec/VERSIONING.md)",
    ("file", "import"): "comes with the MHS adapter (spec/MHS-MAPPING.md)",
    ("file", "export"): "comes with the MHS adapter (spec/MHS-MAPPING.md)",
}
"""Commands the pages name as planned. The syntax check accepts them until they exist."""
SHELL_LANGUAGES: Final = frozenset({"", "sh", "bash", "console", "shell", "text"})
FAILURE_WORDS: Final = ("blocked", "failed", "error")
FENCE = re.compile(r"^([ \t]*)```([A-Za-z]*)([^\n]*)\n(.*?)^\1```", re.M | re.S)
INLINE = re.compile(r"(?<!`)`((?:uv run )?openhald?(?: [^`\n]*)?)`(?!`)")
COMMAND = re.compile(r"^(?:\$ )?((?:uv run )?openhald?(?:\s.*)?)$")
PLACEHOLDER = re.compile(r"<[^<>]+>")
UPPER_WORD = re.compile(r"^[A-Z][A-Z0-9_]+(?:[.=][A-Z][A-Z0-9_]*)*$")


@dataclass(frozen=True)
class Command:
    page: Path
    line: int
    text: str
    expected: tuple[str, ...] = ()
    tested: bool = False
    inline: bool = False
    usage: bool = False

    @property
    def where(self) -> str:
        return f"{self.page.relative_to(ROOT)}:{self.line}"

    @property
    def words(self) -> list[str]:
        text = self.text.removeprefix("uv run ")
        return shlex.split(PLACEHOLDER.sub("x", text.split(" | ")[0]))

    @property
    def synopsis(self) -> bool:
        """A usage line such as `openhal read DEVICE.CHANNEL [--json]`, not a command to type."""
        if "[" in self.text or "..." in self.text:
            return True
        return any(UPPER_WORD.match(word.strip("[]")) for word in self.text.split())

    @property
    def skip_reason(self) -> str | None:
        """Why this command is checked for syntax only, or None when it runs."""
        if self.inline:
            return "inline in the prose"
        if self.synopsis or self.usage:
            return "a usage line"
        if PLACEHOLDER.search(self.text):
            return "has a placeholder"
        if self.tested and self.page in SNIPPET_PAGES:
            return "runs with its output in tests/website/test_snippets.py"
        relative = str(self.page.relative_to(ROOT))
        for prefix, reason in SKIPPED_PAGES.items():
            if relative.startswith(prefix):
                return reason
        words = self.words[1:]
        for key, reason in SKIPPED.items():
            if tuple(words[: len(key)]) == key:
                return reason
        return None


@dataclass(frozen=True)
class Saved:
    """A fenced file the page shows, saved in the working folder before the commands after it."""

    page: Path
    line: int
    name: str
    body: str


def pages() -> list[Path]:
    found = [ROOT / "README.md"]
    for folder in ("docs", "spec"):
        found.extend(sorted((ROOT / folder).rglob("*.md")))
    return [path for path in found if path.is_file() and "docs/agents/" not in path.as_posix()]


def _without_fences(text: str) -> str:
    """The text with every fence blanked out, so positions and line numbers stay the same."""
    return FENCE.sub(lambda match: re.sub(r"[^\n]", " ", match.group(0)), text)


def steps(page: Path) -> list[Command | Saved]:
    """Every command and saved file in a page, in reading order."""
    text = page.read_text(encoding="utf-8")
    found: list[tuple[int, Command | Saved]] = []
    for fence in FENCE.finditer(text):
        indent, language, meta, body = fence.groups()
        start = text.count("\n", 0, fence.start()) + 2
        name = re.search(r"\bfile=(\S+)", meta)
        if name:
            found.append((fence.start(), Saved(page, start - 1, name.group(1), body)))
        if language.lower() not in SHELL_LANGUAGES:
            continue
        tested = "tested" in meta.split()
        lines = [line.removeprefix(indent) for line in body.splitlines()]
        prompted = any(line.startswith("$ ") for line in lines)
        current: list[str] | None = None
        commands: list[tuple[int, str, list[str]]] = []
        for number, line in enumerate(lines):
            match = COMMAND.match(line.strip())
            if match and (line.startswith("$ ") or not prompted):
                current = []
                commands.append((start + number, match.group(1).strip(), current))
            elif prompted and line.startswith("$ "):
                current = None
            elif current is not None and prompted and line.strip():
                current.append(line)
        shown = [Command(page, number, command, tuple(expected), tested) for number, command, expected in commands]
        usage = not prompted and any(command.synopsis for command in shown)
        for command in shown:
            found.append((fence.start(), dataclasses.replace(command, usage=usage)))
    prose = _without_fences(text)
    for match in INLINE.finditer(prose):
        number = prose.count("\n", 0, match.start()) + 1
        found.append((match.start(), Command(page, number, match.group(1).strip(), inline=True)))
    return [item for _, item in sorted(found, key=lambda pair: pair[0])]


def commands() -> list[Command]:
    return [step for page in pages() for step in steps(page) if isinstance(step, Command)]


def _synopsis_words(text: str) -> list[str]:
    """The words of a usage line with brackets, alternatives and placeholders taken out."""
    words = []
    for raw in text.removeprefix("uv run ").split():
        word = raw.strip("[]").split("|")[0].removesuffix("...")
        if word and not UPPER_WORD.match(word):
            words.append(PLACEHOLDER.sub("x", word))
    return words


def syntax_problems(command: Command) -> list[str]:
    """What the CLI wouldn't accept in this command: an unknown command, option or extra argument."""
    words = _synopsis_words(command.text) if command.synopsis else command.words
    program, rest = words[0], words[1:]
    if any(tuple(rest[: len(key)]) == key for key in PLANNED):
        return []
    if program == "openhald":
        unknown = [word for word in rest if word.startswith("-") and word.split("=")[0] not in DAEMON_OPTIONS]
        return [f"openhald has no option {word}" for word in unknown]
    node: Any = cli()
    path = ["openhal"]
    while True:
        positional, problem = _parse(node, rest, stop_at_command=_is_group(node))
        if problem:
            return [f"{' '.join(path)} {problem}"]
        if not _is_group(node):
            break
        if not positional:
            return []
        word = positional[0]
        if word not in node.commands:
            return [f"{' '.join(path)} has no command {word}"]
        node = node.commands[word]
        path.append(word)
        rest = rest[rest.index(word) + 1 :]
    if command.synopsis:
        return []
    arguments = [param for param in node.params if param.param_type_name == "argument"]
    allowed = sum(param.nargs for param in arguments)
    if all(param.nargs >= 0 for param in arguments) and len(positional) > allowed:
        return [f"{' '.join(path)} takes {allowed} arguments, not {len(positional)}: {positional}"]
    return _target_problems(path[1:], positional)


def _target_problems(path: list[str], positional: list[str]) -> list[str]:
    """Targets are device.channel or device.action, and action arguments are KEY=VALUE."""
    targets = positional if path == ["read"] else positional[:1] if path in TARGETED else []
    problems = [f"{word} is not device.channel or device.action" for word in targets if "." not in word]
    if path == ["action"]:
        problems += [f"the action argument {word} is not KEY=VALUE" for word in positional[1:] if "=" not in word]
    return problems


@functools.cache
def cli() -> Any:
    """The command line as Typer builds it, with every command and option."""
    return typer.main.get_command(app)


def _is_group(node: Any) -> bool:
    return isinstance(getattr(node, "commands", None), dict)


def _parse(node: Any, words: list[str], *, stop_at_command: bool) -> tuple[list[str], str | None]:
    """The positional words, or the first option this command doesn't have."""
    options = {param.opts[0]: param for param in node.params if param.param_type_name == "option"}
    names = {"--help": None} | {
        opt: param for param in options.values() for opt in [*param.opts, *param.secondary_opts]
    }
    positional: list[str] = []
    waiting = False
    for word in words:
        if waiting:
            waiting = False
            continue
        if word.startswith("-") and len(word) > 1 and not _number(word):
            name = word.split("=")[0]
            if name not in names:
                return positional, f"has no option {word}"
            param = names[name]
            waiting = param is not None and not param.is_flag and "=" not in word
            continue
        positional.append(word)
        if stop_at_command:
            break
    return positional, None


def _number(word: str) -> bool:
    return re.fullmatch(r"-\d+(?:\.\d+)?\S*", word) is not None


def _outcome(line: str) -> str:
    """The first word of an output line, after any `1.` numbering."""
    words = re.sub(r"^\s*\d+\.\s*", "", line).split()
    return words[0] if words else ""


def squash(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


@contextlib.contextmanager
def no_discovery() -> Iterator[None]:
    """Every installed driver finds nothing, so no page can probe real hardware while it runs."""
    with contextlib.ExitStack() as stack:
        for name in registry.names():
            try:
                driver = registry.load(name)
            except Exception:  # noqa: BLE001 (a driver whose extra is missing can't discover either)
                continue
            stack.enter_context(mock.patch.object(driver, "discover", new=mock.AsyncMock(return_value=[])))
        yield


def needs_hub(command: Command) -> bool:
    words = command.words
    return words[0] == "openhal" and len(words) > 1 and words[1] not in NO_HUB


def run_page(page: Path, home: Path) -> list[str]:
    """Run a page's commands in order and return what went wrong."""
    problems: list[str] = []
    session = Session(home)
    try:
        with no_discovery():
            for step in steps(page):
                if isinstance(step, Saved):
                    (session.workdir / step.name).write_text(step.body, encoding="utf-8")
                    continue
                if step.skip_reason is not None:
                    continue
                if needs_hub(step) and session.hub is None:
                    for line in MOCK_SETUP:
                        session.run(line)
                result = session.run(step.text)
                failure = any(_outcome(line) in FAILURE_WORDS for line in step.expected)
                if failure and result.code == 0:
                    problems.append(f"{step.where} {step.text} should have failed.\n{result.output}")
                elif not failure and result.code != 0:
                    problems.append(f"{step.where} {step.text} exited {result.code}.\n{result.output}")
                missing = [line for line in step.expected if squash(line) not in squash(result.output)]
                if missing:
                    problems.append(f"{step.where} {step.text} didn't print {missing}.\nIt printed\n{result.output}")
    finally:
        session.close()
    return problems


def runnable_pages() -> list[Path]:
    return [page for page in pages() if any(isinstance(s, Command) and s.skip_reason is None for s in steps(page))]


@pytest.mark.parametrize("page", pages(), ids=lambda page: str(page.relative_to(ROOT)))
def test_every_command_is_one_the_cli_has(page: Path) -> None:
    wrong = [
        f"{step.where} `{step.text}`: {problem}"
        for step in steps(page)
        if isinstance(step, Command)
        for problem in syntax_problems(step)
    ]
    assert not wrong, "\n".join(wrong)


@pytest.mark.parametrize("page", runnable_pages(), ids=lambda page: str(page.relative_to(ROOT)))
def test_every_runnable_command_runs_as_written(page: Path, tmp_path: Path) -> None:
    problems = run_page(page, tmp_path / "home")
    assert not problems, "\n\n".join(problems)


def test_the_pages_have_commands_to_run() -> None:
    found = commands()
    run = [command for command in found if command.skip_reason is None]
    assert len(found) >= 300
    assert len(run) >= 8
    assert {"README.md", "CLI.md"} <= {command.page.name for command in run}


def skipped() -> dict[str, list[str]]:
    """Every command the check doesn't run, by reason."""
    found: dict[str, list[str]] = {}
    for command in commands():
        if command.skip_reason is not None:
            found.setdefault(command.skip_reason, []).append(f"{command.where} {command.text}")
    return found


def test_every_command_that_does_not_run_says_why() -> None:
    found = skipped()
    assert all(reason.strip() for reason in found)
    assert set(found) <= {
        *SKIPPED.values(),
        *SKIPPED_PAGES.values(),
        "inline in the prose",
        "a usage line",
        "has a placeholder",
        "runs with its output in tests/website/test_snippets.py",
    }


def check(text: str) -> list[str]:
    return syntax_problems(Command(ROOT / "README.md", 1, text))


def test_the_syntax_check_catches_commands_the_cli_lacks() -> None:
    assert check("openhal device add /dev/ttyACM0")
    assert check("openhal hub stop")
    assert check("openhal log verify")
    assert check("openhal read plant-waterer soil_moisture")
    assert check("openhal write desk-fan fan_speed 20%")
    assert check("openhal action plant-waterer.water duration 20s")
    assert check("openhal action plant-waterer.water --seconds 2")
    assert check("openhald --daemon")
    assert not check("openhal log --verify")
    assert not check("openhal file migrate")
    assert not check("openhal dry-run --file plan.yaml")
    assert not check("openhal read plant-waterer.soil_moisture plant-waterer.tank")
    assert not check("uv run openhal action plant-waterer.water duration=20s")
    assert not check(
        "openhal token create --agent --scope control_low --name claude | tail -1 > ~/.openhal/claude.token"
    )
    assert not check("openhal token create --name NAME [--agent | --human] [--scope read|control_low|control_medium]")
    assert not check("openhal confirm approve <request id>")
    assert not check("openhal --url http://127.0.0.1:7420 status --json")


def test_a_missing_plan_file_is_a_usage_error(tmp_path: Path) -> None:
    result = CliRunner().invoke(app, ["dry-run", "--file", str(tmp_path / "plan.yaml")])
    assert result.exit_code == 2, "CLI.md gives exit code 2 for a usage error"
    assert "does not exist" in result.output


def test_steps_keep_output_and_saved_files_in_order(tmp_path: Path) -> None:
    page = tmp_path / "page.md"
    page.write_text(
        "Run `openhal status` first.\n\n"
        "```yaml file=plan.yaml\n- { device: plant-waterer, action: water, args: { duration: 20 s } }\n```\n\n"
        "```\n$ openhal dry-run --file plan.yaml\n1. allowed  Allowed.\n$ openhal stop\n```\n",
        encoding="utf-8",
    )
    with mock.patch(f"{__name__}.ROOT", tmp_path):
        found = steps(page)
    assert [type(step).__name__ for step in found] == ["Command", "Saved", "Command", "Command"]
    first, saved, dry_run, stop = found
    assert isinstance(first, Command)
    assert first.inline
    assert isinstance(saved, Saved)
    assert saved.name == "plan.yaml"
    assert isinstance(dry_run, Command)
    assert dry_run.expected == ("1. allowed  Allowed.",)
    assert isinstance(stop, Command)
    assert stop.expected == ()
