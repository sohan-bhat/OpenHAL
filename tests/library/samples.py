"""What a driver would report for a library file's `match`, so tests can run discovery without hardware.

Each regex identifier becomes the shortest text that matches it and each glob becomes a text that
fits it, so a synthetic `Discovered` carries exactly the identifiers the file asks for.
"""

from __future__ import annotations

import fnmatch
import re
from re import _constants as sre
from re import _parser as parser
from typing import Any

from openhal.spec.models import Match

KIND_KEYS = frozenset({"usb_class", "mdns"})
"""Match keys that name a kind of device. Discovery never matches on them alone."""


def _first(items: list[tuple[Any, Any]]) -> str:
    op, arg = items[0]
    if op is sre.LITERAL:
        return chr(arg)
    if op is sre.RANGE:
        return chr(arg[0])
    if op is sre.CATEGORY:
        return {sre.CATEGORY_DIGIT: "0", sre.CATEGORY_WORD: "a", sre.CATEGORY_SPACE: " "}[arg]
    raise ValueError(f"No sample for the character set {items!r}.")


def _render(items: Any) -> str:
    out: list[str] = []
    for op, arg in items:
        if op is sre.LITERAL:
            out.append(chr(arg))
        elif op is sre.ANY:
            out.append("x")
        elif op is sre.IN:
            out.append(_first(arg))
        elif op in (sre.MAX_REPEAT, sre.MIN_REPEAT, sre.POSSESSIVE_REPEAT):
            low, _high, inner = arg
            out.append(_render(inner) * low)
        elif op is sre.SUBPATTERN:
            out.append(_render(arg[-1]))
        elif op is sre.BRANCH:
            out.append(_render(arg[1][0]))
        elif op is sre.AT:
            continue
        else:
            raise ValueError(f"No sample for the regex part {op}.")
    return "".join(out)


def regex_sample(pattern: str) -> str:
    """The shortest text the pattern finds, taking the first branch of each choice."""
    text = _render(parser.parse(pattern))
    if re.search(pattern, text) is None:
        raise ValueError(f"The sample {text!r} doesn't match {pattern!r}.")
    return text


def glob_sample(pattern: str) -> str:
    text = pattern.replace("*", "x1").replace("?", "x")
    if not fnmatch.fnmatchcase(text, pattern):
        raise ValueError(f"The sample {text!r} doesn't fit {pattern!r}.")
    return text


def specific_keys(match: Match) -> set[str]:
    """The match keys a file sets that name a product, not only a kind of device."""
    return {key for key, value in match.model_dump().items() if value not in (None, [], {})} - KIND_KEYS


def identifiers(match: Match) -> dict[str, str]:
    """The identifiers discovery would report for a device this match describes."""
    found: dict[str, str] = {}
    if match.usb:
        found["usb"] = match.usb[0]
    if match.usb_class:
        found["usb_class"] = match.usb_class
    for key in ("serial_number", "scpi_idn", "ble_name"):
        pattern = getattr(match, key)
        if pattern:
            found[key] = regex_sample(pattern)
    if match.ble_services:
        found["ble_services"] = ",".join(match.ble_services)
    if match.mdns:
        found["mdns"] = match.mdns
    if match.modbus_id is not None:
        found["modbus_id"] = str(match.modbus_id)
    if match.homeassistant:
        found["homeassistant"] = glob_sample(match.homeassistant)
    for section in ("moonraker", "esphome", "firmware"):
        for key, value in getattr(match, section).items():
            found[f"{section}.{key}"] = glob_sample(value)
    return found
