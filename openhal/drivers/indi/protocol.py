"""The INDI XML protocol. Stream parsing, property vectors and outgoing messages, no I/O.

Written from "INDI: Instrument-Neutral Distributed Interface", protocol version 1.7, by
Elwood Downey, and the INDI standard properties page (indilib.org).

- The stream is a sequence of top-level XML elements with no document root. The parser wraps
  it in a root of its own and hands out each top-level element when it closes.
- Servers define properties with def*Vector, update them with set*Vector, remove them with
  delProperty and send text with message. Clients request properties with getProperties and
  change values with new*Vector, which carries only the members being changed.
- Vectors have a state (Idle, Ok, Busy, Alert) and a permission (ro, wo, rw). Numbers may be
  written in decimal or in sexagesimal (`12:30:15.5` or `12 30 15.5`).

Document type declarations and entities fail the parse outright, since INDI never uses them and
they are how XML parsers get attacked. Element text is capped, and BLOBs are never requested.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Final, cast
from xml.etree.ElementTree import Element, ParseError, SubElement, XMLPullParser, tostring

VERSION: Final = "1.7"
STATES: Final = ("idle", "ok", "busy", "alert")
KINDS: Final = ("number", "switch", "text", "light", "blob")
MAX_ELEMENT: Final = 1_000_000
_FORBIDDEN: Final = re.compile(rb"<!\s*(doctype|entity)", re.IGNORECASE)
_SEXAGESIMAL: Final = re.compile(r"^([+-]?)(\d+(?:\.\d*)?)(?:[:\s]+(\d+(?:\.\d*)?))?(?:[:\s]+(\d+(?:\.\d*)?))?$")


class ProtocolError(ValueError):
    """The server sent something that is not INDI."""


@dataclass
class Member:
    """One element of a vector. `value` is a float, a bool, a state word or text by kind."""

    name: str
    value: float | bool | str | None
    label: str = ""
    minimum: float | None = None
    maximum: float | None = None
    step: float | None = None


@dataclass
class Vector:
    device: str
    name: str
    kind: str
    state: str = "idle"
    perm: str = "ro"
    rule: str | None = None
    label: str = ""
    group: str = ""
    message: str = ""
    members: dict[str, Member] = field(default_factory=dict)
    at: float = 0.0
    invalid: str = ""


def parse_number(text: str) -> float:
    """Decimal or sexagesimal. Raises ProtocolError for anything else."""
    cleaned = text.strip()
    try:
        value = float(cleaned)
    except ValueError:
        match = _SEXAGESIMAL.match(cleaned)
        if match is None:
            raise ProtocolError(f"{text!r} is not a number") from None
        sign, degrees, minutes, seconds = match.groups()
        value = float(degrees) + float(minutes or 0) / 60 + float(seconds or 0) / 3600
        value = -value if sign == "-" else value
    if not math.isfinite(value):
        raise ProtocolError(f"{text!r} is not a finite number")
    return value


def _state(text: str | None) -> str:
    word = (text or "Idle").strip().lower()
    if word not in STATES:
        raise ProtocolError(f"unknown property state {text!r}")
    return word


def _switch(text: str | None) -> bool:
    word = (text or "").strip()
    if word not in ("On", "Off"):
        raise ProtocolError(f"a switch must be On or Off, not {text!r}")
    return word == "On"


def _member_value(kind: str, text: str | None) -> float | bool | str | None:
    if kind == "number":
        return parse_number(text or "")
    if kind == "switch":
        return _switch(text)
    if kind == "light":
        return _state(text)
    if kind == "text":
        return (text or "").strip()
    return None


def _limit(element: Element, name: str) -> float | None:
    text = element.get(name)
    if text is None or not text.strip():
        return None
    return parse_number(text)


def vector_from(element: Element) -> Vector:
    """Build a Vector from a def*Vector element."""
    kind = element.tag[3:-6].lower()
    if not element.tag.startswith("def") or kind not in KINDS:
        raise ProtocolError(f"{element.tag} is not a property definition")
    device, name = element.get("device"), element.get("name")
    if not device or not name:
        raise ProtocolError(f"{element.tag} has no device or name")
    vector = Vector(
        device=device,
        name=name,
        kind=kind,
        state=_state(element.get("state")),
        perm=(element.get("perm") or "ro").lower(),
        rule=element.get("rule"),
        label=element.get("label") or name,
        group=element.get("group") or "",
        message=element.get("message") or "",
    )
    for child in element:
        member_name = child.get("name")
        if not member_name:
            raise ProtocolError(f"a member of {name} has no name")
        member = Member(member_name, _member_value(kind, child.text), label=child.get("label") or member_name)
        if kind == "number":
            member.minimum, member.maximum, member.step = (
                _limit(child, "min"),
                _limit(child, "max"),
                _limit(child, "step"),
            )
        vector.members[member_name] = member
    return vector


def apply_update(vector: Vector, element: Element) -> None:
    """Apply a set*Vector to a known vector. Members that aren't listed keep their values."""
    if element.tag[3:-6].lower() != vector.kind:
        raise ProtocolError(f"{element.tag} doesn't match {vector.name}, a {vector.kind} vector")
    updates: dict[str, float | bool | str | None] = {}
    for child in element:
        name = child.get("name") or ""
        if name in vector.members:
            updates[name] = _member_value(vector.kind, child.text)
    if element.get("state") is not None:
        vector.state = _state(element.get("state"))
    vector.message = element.get("message") or ""
    for name, value in updates.items():
        vector.members[name].value = value
    vector.invalid = ""


class Stream:
    """Turns the byte stream into complete top-level elements."""

    def __init__(self, limit: int = MAX_ELEMENT) -> None:
        self._parser: XMLPullParser[Element] = XMLPullParser(events=("start", "end"))
        self._parser.feed(b"<openhal-indi-stream>")
        self._root: Element | None = None
        self._depth = 0
        self._pending = 0
        self._tail = b""
        self._limit = limit

    def feed(self, data: bytes) -> list[Element]:
        window = self._tail + data
        if _FORBIDDEN.search(window):
            raise ProtocolError("the server sent a document type or entity declaration, which INDI never uses")
        self._tail = window[-16:]
        self._pending += len(data)
        if self._pending > self._limit:
            raise ProtocolError(f"an element is longer than {self._limit} bytes")
        try:
            self._parser.feed(data)
            events = list(self._parser.read_events())
        except ParseError as exc:
            raise ProtocolError(f"the XML is malformed ({exc})") from None
        done: list[Element] = []
        for item in events:
            event, element = cast("tuple[str, object]", item)
            assert isinstance(element, Element)
            if event == "start":
                if self._root is None:
                    self._root = element
                self._depth += 1
                continue
            self._depth -= 1
            if self._depth == 1 and self._root is not None:
                done.append(element)
                self._root.remove(element)
                self._pending = 0
        return done


def get_properties(device: str | None = None, name: str | None = None) -> bytes:
    element = Element("getProperties", {"version": VERSION})
    if device:
        element.set("device", device)
    if name:
        element.set("name", name)
    return tostring(element) + b"\n"


def _number_text(value: float) -> str:
    return f"{value:.10g}"


def new_vector(kind: str, device: str, name: str, values: dict[str, float | bool | str]) -> bytes:
    """A new*Vector that changes only the listed members."""
    tag = kind.capitalize()
    element = Element(f"new{tag}Vector", {"device": device, "name": name})
    for member, value in values.items():
        child = SubElement(element, f"one{tag}", {"name": member})
        if kind == "switch":
            child.text = "On" if value else "Off"
        elif kind == "number":
            assert isinstance(value, int | float)
            assert not isinstance(value, bool)
            child.text = _number_text(float(value))
        else:
            child.text = str(value)
    return tostring(element) + b"\n"
