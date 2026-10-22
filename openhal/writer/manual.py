"""Command lists from a device manual (driver writer, step 5).

The text comes from the user, usually pasted from a PDF or a web page. The parser looks for lines
that start with a command, in the shapes manuals use: SCPI (`VOLTage <value>`, `MEAS:CURR?`,
`*IDN?`), G-code (`M104 S<temp>`) and plain uppercase words with an argument (`FAN <0-255>`).

Every extracted command is unconfirmed. The hub never sends one during detection, because a
command it hasn't been told is read-only might change something. Commands whose description
mentions resets, erasing, firmware or power are flagged so the interview and the test plan
treat them with care.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Final, Literal

MAX_MANUAL_CHARS: Final = 400_000
MAX_COMMANDS: Final = 300

_SCPI: Final = r"(?:\*[A-Z]{3}\??|:?[A-Z]{2,}[a-z]*(?::[A-Z]{2,}[a-z]*|:\[[A-Z]{2,}[a-z]*\])*\??)"
_GCODE: Final = r"[GM]\d{1,4}"
_LINE: Final = re.compile(
    r"^\s*(?P<command>" + _GCODE + r"|" + _SCPI + r")"
    r"(?P<argument>(?:\s+(?:<[^>\n]{1,40}>|\{[^}\n]{1,40}\}|\[[^\]\n]{1,40}\]|[A-Z]<[^>\n]{1,20}>|[A-Z]n{1,3}\b))*)"
    r"(?P<gap>\s{2,}|\s*[\t|]\s*|\s+-\s+|\s*$)"
    r"(?P<description>.*)$"
)
_CAREFUL: Final = re.compile(
    r"\b(reset|reboot|erase|format|factory|delete|firmware|flash|bootloader|calibrat\w*|power|output on|"
    r"enable|fire|laser|spindle|heat\w*|motor|move|home|zero|unlock|override)\b",
    re.I,
)
_WORDS_ONLY: Final = re.compile(r"^[A-Z]{2,}$")

Kind = Literal["query", "set", "action"]


@dataclass(frozen=True)
class ManualCommand:
    command: str
    kind: Kind
    argument: str
    description: str
    line: int
    careful: bool

    def view(self) -> dict[str, Any]:
        return {
            "command": self.command,
            "kind": self.kind,
            "argument": self.argument,
            "description": self.description,
            "line": self.line,
            "careful": self.careful,
            "confirmed": False,
        }


def extract(text: str) -> list[ManualCommand]:
    """Find candidate commands. Returns at most MAX_COMMANDS, in the order the manual lists them."""
    if len(text) > MAX_MANUAL_CHARS:
        raise ValueError(
            f"The manual text is longer than {MAX_MANUAL_CHARS // 1000} k characters. Paste the command section."
        )
    found: list[ManualCommand] = []
    seen: set[str] = set()
    for number, line in enumerate(text.splitlines(), start=1):
        if len(line) > 400:
            continue
        match = _LINE.match(line)
        if match is None:
            continue
        command = match.group("command")
        argument = match.group("argument").strip()
        description = match.group("description").strip()
        if _WORDS_ONLY.match(command) and not (argument or description):
            continue  # a heading in capitals, not a command
        if _WORDS_ONLY.match(command) and not argument and not command.endswith("?") and len(description) < 8:
            continue
        key = command.upper().lstrip(":")
        if key in seen:
            continue
        seen.add(key)
        kind: Kind = "query" if command.endswith("?") else "set" if argument else "action"
        careful = bool(_CAREFUL.search(description) or _CAREFUL.search(command))
        found.append(ManualCommand(command, kind, argument, description[:200], number, careful))
        if len(found) >= MAX_COMMANDS:
            break
    return found


def _name(command: str) -> str:
    name = re.sub(r"[^a-z0-9]+", "_", command.lower().replace("?", "")).strip("_")
    if not name or not name[0].isalpha():
        name = f"cmd_{name}"
    return name[:24]


def draft_sections(commands: list[ManualCommand]) -> dict[str, Any]:
    """Draft read and write channels from queries and set commands. Units and limits are left to the
    person, so the interview asks for every one. Actions are listed in notes, never as channels."""
    read: dict[str, Any] = {}
    write: dict[str, Any] = {}
    listed: list[str] = []
    for command in commands:
        name = _name(command.command)
        if command.kind == "query" and name not in read:
            read[name] = {"type": "string", "map": {"query": command.command, "parse": r"(?P<value>.+)"}}
        elif command.kind == "set" and not command.careful and name not in write:
            write[name] = {
                "unit": "dimensionless",
                "suggested": True,
                "map": {"command": f"{command.command} {{value}}"},
            }
        else:
            listed.append(command.command)
    sections: dict[str, Any] = {}
    if read:
        sections["read"] = read
    if write:
        sections["write"] = write
    if listed:
        sections["notes"] = (
            "Commands from the manual that are not channels yet, some of which may change the device. "
            + ", ".join(listed[:60])
        )
    return sections
