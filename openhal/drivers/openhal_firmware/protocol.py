"""Encoding and parsing for the OpenHAL firmware protocol (spec/FIRMWARE-PROTOCOL.md)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Final

PROTOCOL_VERSION: Final = 1
MAX_LINE: Final = 250
MAX_DESC_LINE: Final = 1500
MAX_ACTION_ARGS: Final = 3
MAX_STATES: Final = 8
NAME: Final = re.compile(r"^[a-z][a-z0-9_]{0,23}$")
NUMBER: Final = re.compile(r"^[+-]?(?:[0-9]+\.?[0-9]*|\.[0-9]+)$")


class ProtocolError(ValueError):
    """A line didn't follow the protocol. The driver discards it."""


def checksum(body: str) -> str:
    """XOR of every byte of `body`, as two uppercase hex digits."""
    value = 0
    for byte in body.encode("ascii"):
        value ^= byte
    return f"{value:02X}"


def encode(seq: int, verb: str, *args: str) -> str:
    """One complete line, with its checksum and newline."""
    if not 0 <= seq <= 65535:
        raise ProtocolError("seq must be between 0 and 65535.")
    body = " ".join([str(seq), verb, *args])
    return f"{body}*{checksum(body)}\n"


@dataclass(frozen=True, slots=True)
class Message:
    seq: int
    verb: str
    args: tuple[str, ...]


def decode(line: str) -> Message:
    """Parse one line. Raises ProtocolError for anything malformed or with a bad checksum."""
    text = line.rstrip("\r\n")
    limit = MAX_DESC_LINE if " DESC " in text else MAX_LINE
    if len(text) > limit:
        raise ProtocolError("The line is too long.")
    body, star, given = text.rpartition("*")
    if not star:
        raise ProtocolError("The line has no checksum.")
    if given.upper() != checksum(body):
        raise ProtocolError("The checksum doesn't match.")
    parts = body.split(" ")
    if len(parts) < 2 or not parts[0].isdigit():
        raise ProtocolError("The line must start with a sequence number and a verb.")
    seq = int(parts[0])
    verb = parts[1]
    if verb == "DESC":
        return Message(seq, verb, (" ".join(parts[2:]),))
    return Message(seq, verb, tuple(parts[2:]))


def parse_number(text: str) -> float:
    if not NUMBER.match(text):
        raise ProtocolError(f"{text!r} is not a number.")
    return float(text)


def format_number(value: float) -> str:
    """A compact decimal the board can parse, without exponents."""
    text = f"{value:.6f}".rstrip("0").rstrip(".")
    return "0" if text in ("-0", "") else text


def parse_description(text: str) -> dict[str, Any]:
    """Validate the DESC JSON and return it."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ProtocolError(f"DESC isn't valid JSON ({exc.msg}).") from exc
    if not isinstance(data, dict) or not isinstance(data.get("p"), str):
        raise ProtocolError("DESC must be an object with a product name p.")
    for key in ("r", "w"):
        items = data.get(key, [])
        if not isinstance(items, list):
            raise ProtocolError(f"DESC {key} must be a list.")
        for item in items:
            if not isinstance(item, dict) or not isinstance(item.get("n"), str) or not NAME.match(item["n"]):
                raise ProtocolError(f"DESC {key} has an entry without a valid name.")
            if not isinstance(item.get("u"), str):
                raise ProtocolError(f"DESC {key} entry {item['n']} has no unit.")
        if key == "w":
            for item in items:
                for field in ("min", "max", "safe"):
                    if not isinstance(item.get(field), int | float):
                        raise ProtocolError(f"DESC w entry {item['n']} needs a numeric {field}.")
        if key == "r":
            for item in items:
                _check_states(item)
    actions = data.get("a", [])
    if not isinstance(actions, list):
        raise ProtocolError("DESC a must be a list.")
    for action in actions:
        if not isinstance(action, dict) or not isinstance(action.get("n"), str) or not NAME.match(action["n"]):
            raise ProtocolError("DESC a has an action without a valid name.")
        args = action.get("g", [])
        if not isinstance(args, list) or len(args) > MAX_ACTION_ARGS:
            raise ProtocolError(f"DESC action {action['n']} has a bad argument list.")
        for arg in args:
            valid = isinstance(arg, dict) and isinstance(arg.get("n"), str) and NAME.match(arg["n"])
            if not valid or not isinstance(arg.get("u"), str):
                raise ProtocolError(f"DESC action {action['n']} has an argument without a name and unit.")
            if not all(isinstance(arg.get(field), int | float) for field in ("min", "max")):
                raise ProtocolError(f"DESC action {action['n']} argument {arg['n']} needs a numeric min and max.")
    return data


def _check_states(item: dict[str, Any]) -> None:
    states = item.get("s")
    if states is None:
        return
    valid = isinstance(states, list) and 0 < len(states) <= MAX_STATES
    if not valid or not all(isinstance(state, str) and NAME.match(state) for state in states):
        raise ProtocolError(f"DESC r entry {item['n']} has bad states.")


def description_to_sections(data: dict[str, Any]) -> dict[str, Any]:
    """Turn a DESC document into device file sections. Every limit is marked suggested."""
    read: dict[str, Any] = {}
    for item in data.get("r", []):
        channel: dict[str, Any] = {"type": "enum", "values": list(item["s"])} if item.get("s") else {"unit": item["u"]}
        if item.get("e"):
            channel["stream"] = True
        if isinstance(item.get("lo"), int | float) and isinstance(item.get("hi"), int | float):
            channel["range"] = [item["lo"], item["hi"]]
        read[item["n"]] = channel
    write: dict[str, Any] = {}
    safe: dict[str, Any] = {}
    notes: list[str] = []
    for item in data.get("w", []):
        name = item["n"]
        if item["u"] == "bool":
            write[name] = {"type": "bool", "suggested": True}
            safe[name] = bool(item["safe"])
        else:
            channel = {"unit": item["u"], "min": item["min"], "max": item["max"], "suggested": True}
            if isinstance(item.get("rate"), int | float) and item["rate"] > 0:
                channel["max_change_per_s"] = item["rate"]
            write[name] = channel
            safe[name] = item["safe"]
        if isinstance(item.get("t"), int | float) and item["t"] > 0:
            notes.append(f"The board returns {name} to its safe value after {item['t'] / 1000:g} s without a write.")
    actions: dict[str, Any] = {}
    for action in data.get("a", []):
        args = {arg["n"]: {"unit": arg["u"], "min": arg["min"], "max": arg["max"]} for arg in action.get("g", [])}
        actions[action["n"]] = {"args": args, "suggested": True} if args else {"suggested": True}
    sections: dict[str, Any] = {"match": {"firmware": {"product": data["p"]}}, "read": read, "write": write}
    if actions:
        sections["actions"] = actions
    if safe:
        sections["safe_state"] = safe
    if data.get("hb"):
        sections["watchdog"] = {"heartbeat": f"{max(int(data['hb']) // 2, 100)} ms", "on_loss": "safe_state"}
    if notes:
        sections["notes"] = " ".join(notes)
    return sections
