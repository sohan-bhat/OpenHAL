"""Every command and code snippet the website writes is run against the real CLI and library.

Snippets live in Markdown with a `tested` fence attribute, in docs/guide/ and in the website's own
content. Each document gets a fresh OPENHAL_HOME and runs its snippets in order, like a reader
following along. Shell lines that start with `$ ` are commands, and the lines under a command are
output it must print. Python runs as written against the same hub. YAML must load as a device
file, or as a routine with `kind=routine`. `file=NAME` saves a YAML or Python snippet in the working
folder for later commands and imports. JSON client configs must start `openhal mcp`, and JSON message
traces must match openhal.protocol's methods, schemas and error reasons.
Nothing touches real hardware or the real ~/.openhal.
"""

from __future__ import annotations

import contextlib
import io
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest
import yaml
from pydantic import TypeAdapter

from openhal.protocol.errors import RpcError
from openhal.protocol.messages import METHODS
from openhal.routines.models import Routine
from openhal.spec import loads
from tests.website.shell import ROOT, Session, SnippetError, uv_project_command

SOURCES = [
    *sorted((ROOT / "docs" / "guide").rglob("*.md")),
    *sorted((ROOT / "website" / "src" / "content").rglob("*.md")),
]
NOT_OURS = {ROOT / "docs" / "guide" / "driver-writer.md"}
FENCE = re.compile(r"^```([a-z]+)([^\n]*)\n(.*?)^```", re.M | re.S)
CHECKED_LANGUAGES = {"sh", "bash", "console", "python", "yaml", "json"}


@dataclass
class Snippet:
    source: Path
    language: str
    meta: str
    body: str
    line: int

    @property
    def tested(self) -> bool:
        return "tested" in self.meta.split()

    def option(self, name: str) -> str | None:
        match = re.search(rf"\b{name}=(\S+)", self.meta)
        return match.group(1) if match else None


def snippets(path: Path) -> list[Snippet]:
    text = path.read_text(encoding="utf-8")
    return [
        Snippet(path, match.group(1), match.group(2).strip(), match.group(3), text[: match.start()].count("\n") + 1)
        for match in FENCE.finditer(text)
    ]


def squash(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def run_shell(session: Session, snippet: Snippet) -> None:
    lines = snippet.body.splitlines()
    if not any(line.startswith("$ ") for line in lines):
        raise SnippetError("Shell snippets mark each command with a leading $.")
    blocks: list[tuple[str, list[str]]] = []
    for line in lines:
        if line.startswith("$ "):
            blocks.append((line[2:], []))
        elif line.strip():
            blocks[-1][1].append(line)
    for command, expected in blocks:
        result = session.run(command)
        wanted_failure = bool(expected) and expected[0].split()[0] in ("blocked", "failed", "error")
        if wanted_failure:
            assert result.code != 0, f"{command} should have failed.\n{result.output}"
        else:
            assert result.code == 0, f"{command} exited {result.code}.\n{result.output}"
        for line in expected:
            assert squash(line) in squash(result.output), (
                f"{command} didn't print {line!r}.\nIt printed\n{result.output}"
            )


def save(session: Session, snippet: Snippet) -> Path | None:
    name = snippet.option("file")
    if not name:
        return None
    path = session.workdir / name
    path.write_text(snippet.body, encoding="utf-8")
    return path


def run_python(session: Session, snippet: Snippet) -> None:
    saved = save(session, snippet)
    out = io.StringIO()
    before = set(sys.modules)
    sys.path.insert(0, str(session.workdir))
    try:
        with session.environment(), contextlib.chdir(session.workdir), contextlib.redirect_stdout(out):
            code = compile(snippet.body, f"{snippet.source.name}:{snippet.line}", "exec")
            exec(code, {"__name__": saved.stem if saved else "__snippet__"})
    finally:
        sys.path.remove(str(session.workdir))
        for name in set(sys.modules) - before:
            module = sys.modules[name]
            if str(session.workdir) in str(getattr(module, "__file__", "") or ""):
                del sys.modules[name]


def run_yaml(session: Session, snippet: Snippet) -> None:
    if snippet.option("kind") == "routine":
        routine = Routine.model_validate(yaml.safe_load(snippet.body))
        assert routine.id
    else:
        file = loads(snippet.body)
        assert file.device.name
    save(session, snippet)


def run_trace(snippet: Snippet) -> None:
    """Check a message trace against openhal.protocol: methods, params, results and error reasons."""
    messages = []
    for line in snippet.body.splitlines():
        if line[:1] in ("→", "←"):
            messages.append(line[1:])
        elif line.strip():
            messages[-1] += "\n" + line
    methods: dict[object, str] = {}
    for text in messages:
        message = json.loads(text)
        assert message["jsonrpc"] == "2.0"
        if "method" in message:
            spec = METHODS[message["method"]]
            spec.params.model_validate(message.get("params", {}))
            methods[message["id"]] = message["method"]
        elif "error" in message:
            error = message["error"]
            data = dict(error["data"])
            expected = RpcError(data.pop("name"), data)
            assert (error["code"], error["message"]) == (expected.code, expected.reason)
        else:
            TypeAdapter(METHODS[methods[message["id"]]].result).validate_python(message["result"])


def run_json(session: Session, snippet: Snippet) -> None:
    if snippet.body.lstrip()[:1] in ("→", "←"):
        run_trace(snippet)
        return
    data = json.loads(snippet.body)
    server = data["mcpServers"]["openhal"]
    command = uv_project_command([server["command"], *server["args"]])
    assert Path(command[0]).name == "openhal"
    assert command[1] == "mcp"
    help_text = session.openhal(["mcp", "--help"]).output
    for option in (word for word in command[2:] if word.startswith("--")):
        assert option in help_text, f"openhal mcp has no option {option}."


RUNNERS = {
    "sh": run_shell,
    "bash": run_shell,
    "console": run_shell,
    "python": run_python,
    "yaml": run_yaml,
    "json": run_json,
}


@pytest.mark.parametrize(
    "path", [path for path in SOURCES if path not in NOT_OURS], ids=lambda path: str(path.relative_to(ROOT))
)
def test_document_snippets_run(path: Path, tmp_path: Path) -> None:
    session = Session(tmp_path / "home")
    try:
        for snippet in snippets(path):
            if not snippet.tested:
                continue
            try:
                RUNNERS[snippet.language](session, snippet)
            except (AssertionError, SnippetError, Exception) as exc:
                raise AssertionError(
                    f"{path.relative_to(ROOT)} line {snippet.line} ({snippet.language}) failed. {exc}"
                ) from exc
    finally:
        session.close()


def test_every_code_snippet_we_write_is_tested() -> None:
    untested = [
        f"{snippet.source.relative_to(ROOT)}:{snippet.line}"
        for path in SOURCES
        if path not in NOT_OURS
        for snippet in snippets(path)
        if snippet.language in CHECKED_LANGUAGES and not snippet.tested
    ]
    assert not untested, f"Mark these snippets tested, or show them as text. {untested}"


def test_there_are_tested_snippets() -> None:
    count = sum(snippet.tested for path in SOURCES for snippet in snippets(path))
    assert count >= 10


def commands(text: str) -> list[str]:
    block = re.search(r"^## Quickstart\n.*?^```[a-z]*\n(.*?)^```", text, re.M | re.S)
    assert block, "README.md has no Quickstart code block."
    return [line.strip() for line in block.group(1).splitlines() if line.strip()]


def test_home_quickstart_matches_the_readme() -> None:
    readme = commands((ROOT / "README.md").read_text(encoding="utf-8"))
    home = snippets(ROOT / "website" / "src" / "content" / "snippets" / "quickstart.md")[0]
    ours = [line[2:] for line in home.body.splitlines() if line.startswith("$ ")]
    assert ours == readme
