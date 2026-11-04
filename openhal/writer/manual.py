"""Command lists from a device manual (driver writer, step 5).

The text comes from the user, usually pasted from a PDF or a web page. The parser searches for lines
that start with a command, in the shapes manuals use: SCPI (`VOLTage <value>`, `MEAS:CURR?`,
`*IDN?`), G-code (`M104 S<temp>`), plain uppercase words with an argument (`FAN <0-255>`), and
short command codes followed by an en or em dash and a description, as instrument command sets
such as Mettler Toledo's MT-SICS list them (S, then a dash, then Stable weight value). A table of
contents line keeps its command and description, and its dot leader and page number are dropped.
A command summary line of two to four capitals, bracketed arguments and a capitalized description,
as New Era's pump manuals print one (DIA, then [ <float> ], then Syringe inside diameter), is read
with its nested brackets balanced.

A short code has no question mark, so its description decides its kind. A description that names
a value, such as a weight value or a serial number, and starts with no verb that changes the
device is a query. Every other short code is an action.

Every extracted command is unconfirmed. The hub never sends one during detection, because a
command that isn't marked read-only might change something. Commands whose description
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
_CODE_LINE: Final = re.compile(
    r"^\s*(?P<command>@|[A-Z][A-Z0-9]{0,5})\s+[\u2013\u2014]\s+"
    r"(?P<description>[^\n]*?[A-Za-z][^\n]*?)(?:\s*\.{2,}\s*\d*)?\s*$"
)
_VALUE_WORDS: Final = re.compile(
    r"\b(value|values|number|data|information|status|version|level|state|temperature|weight|reading|serial)\b",
    re.I,
)
_CHANGE_VERBS: Final = re.compile(
    r"^(clear|set|preset|start|stop|reset|restart|switch|cancel|adjust|calibrat\w*|zero|lock|unlock|enable|"
    r"disable|define|delete|write|store|save|initiali[sz]e)\b",
    re.I,
)
_CAREFUL: Final = re.compile(
    r"\b(reset|reboot|erase|format|factory|delete|firmware|flash|bootloader|calibrat\w*|power|output on|"
    r"enable|fire|laser|spindle|heat\w*|motor|move|home|zero|unlock|override|repeat|continuous\w*|start\w*|purge)\b",
    re.I,
)
_WORDS_ONLY: Final = re.compile(r"^[A-Z]{2,}$")
_SUMMARY_HEAD: Final = re.compile(r"^\s*(?P<command>[A-Z]{2,4}) +(?P<rest>\S.*)$")
_ACTION_VERBS: Final = re.compile(r"^(start|stop|pause|run|purge|sound|clear|reset|trigger|jump|loop)", re.I)
_OPEN, _CLOSE = "[{<", "]}>"

Kind = Literal["query", "set", "action"]


@dataclass(frozen=True)
class ManualCommand:
    command: str
    kind: Kind
    argument: str
    description: str
    line: int
    careful: bool
    short: bool = False

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


def _summary(line: str) -> tuple[str, str, str] | None:
    """A command summary line as (command, argument, description), or None.

    The argument is every bracketed group after the command, nested or not, and the description
    starts at the first capitalized word outside every bracket.
    """
    head = _SUMMARY_HEAD.match(line)
    if head is None:
        return None
    rest, depth = head.group("rest"), 0
    for index, char in enumerate(rest):
        if char in _OPEN:
            depth += 1
        elif char in _CLOSE:
            depth = max(0, depth - 1)
        elif depth == 0 and re.match(r"[A-Z][a-z]", rest[index : index + 2]) and (index == 0 or rest[index - 1] == " "):
            description = rest[index:].strip()
            if len(description) < 6:
                return None
            return head.group("command"), rest[:index].strip(), description
        elif depth == 0 and not char.isspace():
            return None
    return None


def _summary_kind(argument: str, description: str) -> Kind:
    if description.lower().startswith("query"):
        return "query"
    if _ACTION_VERBS.match(description):
        return "action"
    if argument:
        return "set"
    return "query" if _VALUE_WORDS.search(description) and not _CHANGE_VERBS.match(description) else "action"


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
        summary = _summary(line)
        match = None if summary is not None else _LINE.match(line)
        code = None if summary is not None or match is not None else _CODE_LINE.match(line)
        if summary is None and match is None and code is None:
            continue
        if summary is not None:
            command, argument, description = summary
            kind: Kind = _summary_kind(argument, description)
        elif code is not None:
            command, argument = code.group("command"), ""
            description = code.group("description").strip()
            named = _VALUE_WORDS.search(description) and not _CHANGE_VERBS.match(description)
            kind = "query" if named else "action"
        else:
            assert match is not None
            command = match.group("command")
            argument = match.group("argument").strip()
            description = match.group("description").strip()
            if _WORDS_ONLY.match(command) and not (argument or description):
                continue
            if _WORDS_ONLY.match(command) and not argument and not command.endswith("?") and len(description) < 8:
                continue
            kind = "query" if command.endswith("?") else "set" if argument else "action"
        key = command.upper().lstrip(":")
        if key in seen:
            continue
        seen.add(key)
        careful = bool(_CAREFUL.search(description) or _CAREFUL.search(command))
        found.append(ManualCommand(command, kind, argument, description[:200], number, careful, code is not None))
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
    person, so the interview has a question for every one. Actions are listed in notes, never as channels."""
    read: dict[str, Any] = {}
    write: dict[str, Any] = {}
    listed: list[str] = []
    for command in commands:
        name = _name(" ".join(command.description.split()[:4]) if command.short else command.command)
        if command.kind == "query" and not command.careful and name not in read:
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
