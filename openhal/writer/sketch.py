"""Static reading of an Arduino or ESP32 sketch (driver writer, step 4).

No model is involved. The parser finds what the code states plainly: the baud rate, the OpenHAL
library's own channel declarations, the serial command vocabulary, the pins it drives and reads,
and value ranges from `constrain()` and `map()`. Everything it infers is a suggestion. The user's
model can add what static parsing misses through `propose`, and a human confirms every limit.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Final

MAX_SKETCH_BYTES: Final = 512_000

_COMMENT = re.compile(r"//[^\n]*|/\*.*?\*/", re.S)
_NUMBER = r"[-+]?\d+(?:\.\d+)?"
_BAUD = re.compile(r"Serial\d?\s*\.\s*begin\s*\(\s*(\d+)")
_PIN_MODE = re.compile(r"pinMode\s*\(\s*(\w+)\s*,\s*(OUTPUT|INPUT_PULLUP|INPUT)\s*\)")
_ANALOG_WRITE = re.compile(r"(?:analogWrite|ledcWrite)\s*\(\s*(\w+)")
_ANALOG_READ = re.compile(r"analogRead\s*\(\s*(\w+)\s*\)")
_CONSTANT = re.compile(
    r"(?:const\s+)?(?:int|byte|uint8_t|uint16_t|long|float)\s+(\w+)\s*=\s*(" + _NUMBER + r"|A\d+)\s*;"
)
_DEFINE = re.compile(r"#define\s+(\w+)\s+(" + _NUMBER + r"|A\d+)\b")
_CONSTRAIN = re.compile(r"constrain\s*\(\s*[^,]+,\s*(" + _NUMBER + r")\s*,\s*(" + _NUMBER + r")\s*\)")
_MAP = re.compile(
    r"\bmap\s*\(\s*[^,]+,\s*("
    + _NUMBER
    + r")\s*,\s*("
    + _NUMBER
    + r")\s*,\s*("
    + _NUMBER
    + r")\s*,\s*("
    + _NUMBER
    + r")\s*\)"
)
_EXACT = re.compile(
    r"""(?:==\s*"([^"\n]{1,32})"|\.equals(?:IgnoreCase)?\s*\(\s*"([^"\n]{1,32})"\s*\)|"""
    r"""strcmp\s*\(\s*\w+\s*,\s*"([^"\n]{1,32})"\s*\)\s*==\s*0)"""
)
_PREFIX = re.compile(r"""(?:\.startsWith\s*\(\s*"([^"\n]{1,32})"\s*\)|strncmp\s*\(\s*\w+\s*,\s*"([^"\n]{1,32})"\s*,)""")
_CHAR = re.compile(r"""(?:case\s+'([^'\\])'\s*:|==\s*'([^'\\])')""")
_PRINT = re.compile(r"""Serial\d?\s*\.\s*print(?:ln)?\s*\(\s*"([^"\n]{1,40})"\s*\)""")
_OPENHAL_READING = re.compile(
    r"""\.\s*(?:reading|read)\s*\(\s*"([a-z][a-z0-9_]{0,23})"\s*,\s*"([^"]{1,24})"\s*,\s*\w+\s*\)((?:\s*\.\s*\w+\s*\([^)]*\))*)"""
)
_OPENHAL_OUTPUT = re.compile(
    r"""\.\s*output\s*\(\s*"([a-z][a-z0-9_]{0,23})"\s*,\s*"([^"]{1,24})"\s*,\s*\w+\s*\)((?:\s*\.\s*\w+\s*\([^)]*\))*)"""
)
_OPENHAL_WRITE = re.compile(
    r"""\.\s*write\s*\(\s*"([a-z][a-z0-9_]{0,23})"\s*,\s*"([^"]{1,24})"\s*,\s*("""
    + _NUMBER
    + r""")\s*,\s*("""
    + _NUMBER
    + r""")\s*,\s*\w+\s*\)((?:\s*\.\s*\w+\s*\([^)]*\))*)"""
)
_CHAIN = re.compile(r"\.\s*(\w+)\s*\(([^)]*)\)")
_OPENHAL_ACTION = re.compile(
    r"""\.\s*action\s*\(\s*"([a-z][a-z0-9_]{0,23})"\s*,\s*\w+\s*\)((?:\s*\.\s*\w+\s*\([^)]*\))*)"""
)
_ACTION_ARG = re.compile(
    r"""\.\s*arg\s*\(\s*"([a-z][a-z0-9_]{0,23})"\s*,\s*"([^"]{1,24})"\s*,\s*("""
    + _NUMBER
    + r""")\s*,\s*("""
    + _NUMBER
    + r""")\s*\)"""
)
_STATES = re.compile(r"\.\s*states\s*\(\s*(\w+)\s*,")
_LABELS = re.compile(r"""(\w+)\s*\[\s*\]\s*=\s*\{((?:\s*"[a-z][a-z0-9_]{0,23}"\s*,?)+)\}""")
_OPENHAL_PRODUCT = re.compile(r"""OpenHAL\s+\w+\s*\(\s*"([^"]{1,40})"\s*,\s*"([^"]{1,20})"\s*\)""")
_HEARTBEAT = re.compile(r"\.\s*heartbeat\s*\(\s*(\d+)\s*\)")


@dataclass
class Command:
    """One command the sketch listens for."""

    text: str
    takes_value: bool
    line: int
    replies: list[str] = field(default_factory=list)
    ranges: list[tuple[float, float]] = field(default_factory=list)

    def view(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "takes_value": self.takes_value,
            "line": self.line,
            "replies": self.replies,
            "ranges": [list(item) for item in self.ranges],
        }


@dataclass
class SketchFindings:
    baud: int | None = None
    openhal_product: str | None = None
    openhal_version: str | None = None
    heartbeat_ms: int | None = None
    openhal_reads: list[dict[str, Any]] = field(default_factory=list)
    openhal_outputs: list[dict[str, Any]] = field(default_factory=list)
    openhal_actions: list[dict[str, Any]] = field(default_factory=list)
    commands: list[Command] = field(default_factory=list)
    outputs: dict[str, str] = field(default_factory=dict)
    inputs: dict[str, str] = field(default_factory=dict)
    pwm: list[str] = field(default_factory=list)
    analog_inputs: list[str] = field(default_factory=list)
    prints: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def uses_openhal_library(self) -> bool:
        return bool(self.openhal_reads or self.openhal_outputs or self.openhal_actions)

    def view(self) -> dict[str, Any]:
        return {
            "baud": self.baud,
            "openhal_library": self.uses_openhal_library,
            "openhal_product": self.openhal_product,
            "heartbeat_ms": self.heartbeat_ms,
            "openhal_reads": self.openhal_reads,
            "openhal_outputs": self.openhal_outputs,
            "openhal_actions": self.openhal_actions,
            "commands": [command.view() for command in self.commands],
            "output_pins": self.outputs,
            "input_pins": self.inputs,
            "pwm_pins": self.pwm,
            "analog_inputs": self.analog_inputs,
            "prints": self.prints,
            "notes": self.notes,
        }


def _strip_comments(text: str) -> str:
    return _COMMENT.sub(lambda match: "\n" * match.group(0).count("\n"), text)


def _block_after(text: str, start: int) -> str:
    """The brace block that follows `start`, or the rest of the statement if there are no braces."""
    open_at = text.find("{", start, start + 200)
    semicolon = text.find(";", start)
    if open_at == -1 or (semicolon != -1 and semicolon < open_at):
        return text[start : semicolon + 1 if semicolon != -1 else len(text)]
    depth = 0
    for index in range(open_at, min(len(text), open_at + 4000)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return text[open_at : index + 1]
    return text[open_at : open_at + 4000]


def _ranges(block: str) -> list[tuple[float, float]]:
    found = [(float(low), float(high)) for low, high in _CONSTRAIN.findall(block)]
    for from_low, from_high, _to_low, _to_high in _MAP.findall(block):
        found.append((float(from_low), float(from_high)))
    return [(low, high) if low <= high else (high, low) for low, high in found]


def _chain(text: str) -> dict[str, list[float]]:
    found: dict[str, list[float]] = {}
    for name, args in _CHAIN.findall(text):
        numbers = [float(value) for value in re.findall(_NUMBER, args)]
        found[name] = numbers
    return found


def _resolve(name: str, constants: dict[str, str]) -> str:
    return constants.get(name, name)


def parse(text: str) -> SketchFindings:
    """Read a sketch. Never runs or compiles anything."""
    if len(text.encode("utf-8", errors="replace")) > MAX_SKETCH_BYTES:
        raise ValueError(f"The sketch is larger than {MAX_SKETCH_BYTES // 1000} KB. Point the writer at the main file.")
    code = _strip_comments(text)
    findings = SketchFindings()

    baud = _BAUD.search(code)
    findings.baud = int(baud.group(1)) if baud else None

    constants = {name: value for name, value in _CONSTANT.findall(code)}
    constants.update({name: value for name, value in _DEFINE.findall(code)})

    product = _OPENHAL_PRODUCT.search(code)
    if product:
        findings.openhal_product, findings.openhal_version = product.group(1), product.group(2)
    heartbeat = _HEARTBEAT.search(code)
    findings.heartbeat_ms = int(heartbeat.group(1)) if heartbeat else None
    labels = {name: re.findall(r'"([a-z][a-z0-9_]{0,23})"', body) for name, body in _LABELS.findall(code)}
    for name, unit, chain in _OPENHAL_READING.findall(code):
        calls = _chain(chain)
        entry: dict[str, Any] = {"name": name, "unit": unit}
        states = _STATES.search(chain)
        if states and labels.get(states.group(1)):
            entry["states"] = labels[states.group(1)]
        if len(calls.get("range", [])) == 2:
            entry["range"] = calls["range"]
        if calls.get("every"):
            entry["every_ms"] = calls["every"][0]
        findings.openhal_reads.append(entry)
    outputs = [(name, unit, None, None, chain) for name, unit, chain in _OPENHAL_OUTPUT.findall(code)]
    outputs += [(name, unit, low, high, chain) for name, unit, low, high, chain in _OPENHAL_WRITE.findall(code)]
    for name, unit, low, high, chain in outputs:
        calls = _chain(chain)
        entry = {"name": name, "unit": unit}
        if low is not None and high is not None:
            entry["min"], entry["max"], entry["safe"] = float(low), float(high), float(low)
        if len(calls.get("limits", [])) == 2:
            entry["min"], entry["max"] = calls["limits"]
        if calls.get("safe"):
            entry["safe"] = calls["safe"][0]
        if calls.get("rate"):
            entry["rate"] = calls["rate"][0]
        if calls.get("timeout"):
            entry["timeout_ms"] = calls["timeout"][0]
        if "onOff" in calls or unit == "bool":
            entry.update(unit="bool", min=0.0, max=1.0)
            entry.setdefault("safe", 0.0)
        if "internal" in calls:
            entry["internal"] = True
        findings.openhal_outputs.append(entry)
    for name, chain in _OPENHAL_ACTION.findall(code):
        args = [
            {"name": arg, "unit": unit, "min": float(low), "max": float(high)}
            for arg, unit, low, high in _ACTION_ARG.findall(chain)
        ]
        findings.openhal_actions.append({"name": name, "args": args})

    seen: set[str] = set()
    for pattern, takes_value in ((_EXACT, False), (_PREFIX, True), (_CHAR, False)):
        for match in pattern.finditer(code):
            command = next(group for group in match.groups() if group is not None)
            if findings.uses_openhal_library or command in seen:
                continue
            seen.add(command)
            block = _block_after(code, match.end())
            replies = [reply for reply in _PRINT.findall(block)]
            value = takes_value or command.endswith((" ", "=", ":"))
            findings.commands.append(
                Command(command, value, code.count("\n", 0, match.start()) + 1, replies, _ranges(block))
            )

    for pin, mode in _PIN_MODE.findall(code):
        target = findings.outputs if mode == "OUTPUT" else findings.inputs
        target[_resolve(pin, constants)] = pin
    findings.pwm = sorted({_resolve(pin, constants) for pin in _ANALOG_WRITE.findall(code)})
    findings.analog_inputs = sorted({_resolve(pin, constants) for pin in _ANALOG_READ.findall(code)})
    findings.prints = sorted({text for text in _PRINT.findall(code)})[:40]

    if not findings.uses_openhal_library and not findings.commands:
        findings.notes.append(
            "No serial commands were found. The sketch may only stream values, or use a protocol the "
            "parser doesn't know. Ask your AI client to read it and propose a draft."
        )
    return findings


def _channel_name(command: str) -> str:
    name = re.sub(r"[^a-z0-9]+", "_", command.strip().lower()).strip("_")
    if not name or not name[0].isalpha():
        name = f"cmd_{name}" if name else "command"
    return name[:24]


def draft(findings: SketchFindings, *, device_name: str = "Arduino board") -> dict[str, Any]:
    """A draft device file from the findings. Every limit is suggested, and no file is confirmed."""
    if findings.uses_openhal_library:
        return _openhal_draft(findings, device_name)
    read: dict[str, Any] = {}
    write: dict[str, Any] = {}
    actions: dict[str, Any] = {}
    for command in findings.commands:
        name = _channel_name(command.text)
        if command.text.endswith("?") and not command.takes_value:
            pattern = _reply_pattern(command.replies)
            read[name] = {"unit": "dimensionless", "map": {"query": command.text, "parse": pattern}}
        elif command.takes_value:
            low, high = command.ranges[0] if command.ranges else (0.0, 255.0)
            write[name] = {
                "unit": "dimensionless",
                "min": low,
                "max": high,
                "suggested": True,
                "map": {"command": f"{command.text.rstrip()} {{value:.0f}}"},
            }
        else:
            actions[name] = {"map": {"command": command.text}, "confirm": "confirm"}
    data: dict[str, Any] = {
        "device": device_name,
        "connect": {"serial": "auto", "baud": findings.baud or 9600, "settle": "2 s"},
    }
    if read:
        data["read"] = read
    if write:
        data["write"] = write
        data["safe_state"] = {name: spec["min"] for name, spec in write.items()}
    if actions:
        data["actions"] = actions
    data["provenance"] = {"source": "sketch", "tool": "openhal driver writer"}
    return data


def _reply_pattern(replies: list[str]) -> str:
    for reply in replies:
        if reply.endswith(("=", ":", " ")):
            return "^" + re.escape(reply) + r"\s*(?P<value>[-0-9.]+)$"
    return r"(?P<value>[-0-9.]+)"


def _openhal_draft(findings: SketchFindings, device_name: str) -> dict[str, Any]:
    read: dict[str, Any] = {}
    for entry in findings.openhal_reads:
        channel: dict[str, Any] = (
            {"type": "enum", "values": entry["states"]} if entry.get("states") else {"unit": entry["unit"]}
        )
        if entry.get("every_ms"):
            channel["stream"] = True
            channel["every"] = f"{max(entry['every_ms'], 50) / 1000:g} s"
        if entry.get("range"):
            channel["range"] = entry["range"]
        read[entry["name"]] = channel
    write: dict[str, Any] = {}
    safe: dict[str, Any] = {}
    for entry in findings.openhal_outputs:
        if entry.get("internal"):
            continue
        if entry["unit"] == "bool":
            write[entry["name"]] = {"type": "bool", "suggested": True}
            safe[entry["name"]] = bool(entry.get("safe", 0))
            continue
        channel = {"unit": entry["unit"], "suggested": True}
        if "min" in entry and "max" in entry:
            channel["min"], channel["max"] = entry["min"], entry["max"]
        if entry.get("rate"):
            channel["max_change_per_s"] = entry["rate"]
        write[entry["name"]] = channel
        safe[entry["name"]] = entry.get("safe", entry.get("min", 0.0))
    data: dict[str, Any] = {"device": device_name, "connect": {"openhal-firmware": "auto", "boot_s": 2}}
    if findings.openhal_product:
        data["match"] = {"firmware": {"product": findings.openhal_product}}
    if read:
        data["read"] = read
    if write:
        data["write"] = write
        data["safe_state"] = safe
    actions = {
        entry["name"]: {
            "args": {arg["name"]: {"unit": arg["unit"], "min": arg["min"], "max": arg["max"]} for arg in entry["args"]},
            "suggested": True,
        }
        if entry["args"]
        else {"suggested": True}
        for entry in findings.openhal_actions
    }
    if actions:
        data["actions"] = actions
    if findings.heartbeat_ms:
        data["watchdog"] = {"heartbeat": f"{max(findings.heartbeat_ms // 2, 100)} ms", "on_loss": "safe_state"}
    data["provenance"] = {"source": "sketch", "tool": "openhal driver writer"}
    return data
