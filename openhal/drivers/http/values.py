"""Small value helpers for text protocols. JSON paths, payload coercion and body templates.

The http and mqtt drivers share these. They have no third-party dependencies.

JSON paths are a small, safe subset of JSONPath (RFC 9535). A path is a dotted list of object
keys with optional list indexes, with or without the leading `$`, for example `$.relays[0].on`,
`temp.c` or `[2]`. Nothing is evaluated as code.

Templates are JSON-like structures from the device file. A string that is exactly `{name}` is
replaced by the typed value, and `{name}` inside a longer string is replaced by its text. Only
names the driver declares can appear, and the device file can't run code through a template.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Callable, Iterable, Mapping
from typing import Any, Final

from openhal.drivers.base import DriverError

_KEY: Final = re.compile(r"[A-Za-z_][A-Za-z0-9_\-]*")
_PLACEHOLDER: Final = re.compile(r"\{([a-z][a-z0-9_]*)\}")
DEFAULT_ON: Final = ("on", "true", "1", "yes", "open", "high")
DEFAULT_OFF: Final = ("off", "false", "0", "no", "closed", "low")


def parse_path(path: str) -> tuple[str | int, ...]:
    """Split a JSON path into keys and indexes. Raises ValueError for anything outside the subset."""
    text = path.strip()
    if text.startswith("$"):
        text = text[1:]
    parts: list[str | int] = []
    position = 0
    while position < len(text):
        char = text[position]
        if char == ".":
            position += 1
            match = _KEY.match(text, position)
            if match is None:
                raise ValueError(f"JSON path {path!r} has an empty or invalid key at position {position}.")
            parts.append(match.group(0))
            position = match.end()
        elif char == "[":
            end = text.find("]", position)
            if end == -1:
                raise ValueError(f"JSON path {path!r} has an unclosed bracket.")
            inner = text[position + 1 : end].strip()
            if inner.isdigit():
                parts.append(int(inner))
            elif len(inner) >= 2 and inner[0] == inner[-1] and inner[0] in "'\"":
                parts.append(inner[1:-1])
            else:
                raise ValueError(f"JSON path {path!r} supports only [number] or ['key'] in brackets.")
            position = end + 1
        else:
            match = _KEY.match(text, position)
            if match is None or position != 0:
                raise ValueError(f"JSON path {path!r} is not in the supported form, for example $.data.temp.")
            parts.append(match.group(0))
            position = match.end()
    return tuple(parts)


def extract(document: Any, path: tuple[str | int, ...], where: str) -> Any:
    """Follow a parsed JSON path. Raises DriverError naming the missing part."""
    current = document
    for index, part in enumerate(path):
        shown = _format_path(path[: index + 1])
        if isinstance(part, int):
            if not isinstance(current, list) or part >= len(current):
                raise DriverError(f"{where} has no item {shown}. Check the json path in the channel map.")
        elif not isinstance(current, dict) or part not in current:
            raise DriverError(f"{where} has no field {shown}. Check the json path in the channel map.")
        current = current[part]
    return current


def _format_path(path: Iterable[str | int]) -> str:
    text = "$"
    for part in path:
        text += f"[{part}]" if isinstance(part, int) else f".{part}"
    return text


def build_nested(path: tuple[str | int, ...], value: Any) -> Any:
    """Build the smallest JSON document that has `value` at `path`, for command payloads."""
    result: Any = value
    for part in reversed(path):
        if isinstance(part, int):
            raise ValueError("A command path can only use object keys, not list indexes.")
        result = {part: result}
    return result


def words(raw: Any, default: tuple[str, ...]) -> tuple[str, ...]:
    """Normalise an `on` or `off` setting from a channel map into lowercase words."""
    if raw is None:
        return default
    items = raw if isinstance(raw, list | tuple) else [raw]
    return tuple(str(item).lower() for item in items)


def to_number(raw: Any, where: str) -> float:
    if isinstance(raw, bool):
        return 1.0 if raw else 0.0
    if isinstance(raw, int | float):
        value = float(raw)
    elif isinstance(raw, str | bytes):
        text = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else raw
        try:
            value = float(text.strip())
        except ValueError:
            raise DriverError(f"{where} sent {text[:60]!r}, which is not a number.") from None
    else:
        raise DriverError(f"{where} sent a {type(raw).__name__} where a number is required.")
    if not math.isfinite(value):
        raise DriverError(f"{where} sent a value that is not a finite number.")
    return value


def device_number(value: float, scale: float, offset: float) -> int | float:
    """Undo `channel = device * scale + offset`. Results within 1e-6 of a whole number become ints."""
    exact = (float(value) - offset) / scale
    nearest = round(exact)
    if abs(exact - nearest) <= 1e-6 * max(1.0, abs(exact)):
        return int(nearest)
    return exact


def to_bool(raw: Any, on: tuple[str, ...], off: tuple[str, ...], where: str) -> bool:
    if isinstance(raw, bool):
        return raw
    text = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else str(raw)
    if isinstance(raw, int | float) and not isinstance(raw, bool):
        text = f"{raw:g}"
    lowered = text.strip().lower()
    if lowered in on:
        return True
    if lowered in off:
        return False
    raise DriverError(f"{where} sent {text[:60]!r}, which is neither an on word ({on[0]}) nor an off word ({off[0]}).")


def to_text(raw: Any) -> str:
    if isinstance(raw, bytes):
        return raw.decode("utf-8", "replace")
    if isinstance(raw, str):
        return raw
    return json.dumps(raw, separators=(",", ":"))


def placeholders(template: Any) -> set[str]:
    """Every `{name}` used anywhere in a template."""
    found: set[str] = set()
    if isinstance(template, str):
        found.update(_PLACEHOLDER.findall(template))
    elif isinstance(template, Mapping):
        for key, item in template.items():
            found |= placeholders(key) | placeholders(item)
    elif isinstance(template, list | tuple):
        for item in template:
            found |= placeholders(item)
    return found


def show(item: Any) -> str:
    """The text form of a value inside a longer string, a URL path or a query."""
    if isinstance(item, bool):
        return "true" if item else "false"
    if isinstance(item, float):
        return str(int(item)) if item.is_integer() and abs(item) < 1e15 else repr(item)
    return str(item)


def render_text(template: str, values: Mapping[str, Any], quote: Callable[[str], str] | None = None) -> str:
    """Replace every `{name}` in a string with the value's text."""

    def text(match: re.Match[str]) -> str:
        shown = show(values[match.group(1)])
        return quote(shown) if quote is not None else shown

    return _PLACEHOLDER.sub(text, template)


def render(template: Any, values: Mapping[str, Any]) -> Any:
    """Fill a JSON template. A string that is exactly `{name}` keeps the value's type."""
    if isinstance(template, str):
        whole = _PLACEHOLDER.fullmatch(template)
        if whole is not None:
            return values[whole.group(1)]
        return render_text(template, values)
    if isinstance(template, Mapping):
        return {render_text(str(key), values): render(item, values) for key, item in template.items()}
    if isinstance(template, list | tuple):
        return [render(item, values) for item in template]
    return template
