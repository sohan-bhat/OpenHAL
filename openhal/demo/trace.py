"""The message trace, one of the two signature elements of the OpenHAL theme (docs/DESIGN.md).

`lines()` turns a recorded scenario into the text trace the README, the docs and `openhal demo`
show. Requests and errors are shown as the hub sent them. Reasons wrap before the device file
citation so the trace stays narrow. Narration that is not a message, such as what held before an
exchange, is a comment line that starts with `#`.
"""

from __future__ import annotations

import json
from typing import Any

from openhal.protocol.errors import shown

INDENT = "  "
LABEL = 14
COMMENT = "# "


def compact(value: Any) -> str:
    """JSON with a space inside braces, `{ "value": 20, "unit": "s" }`."""
    if isinstance(value, dict):
        if not value:
            return "{}"
        return "{ " + ", ".join(f"{json.dumps(key)}: {compact(item)}" for key, item in value.items()) + " }"
    if isinstance(value, list):
        return "[" + ", ".join(compact(item) for item in value) + "]"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return json.dumps(value)


ARROWS = ("→", "←")
ASCII_ARROWS = ("->", "<-")


def _request(method: str, params: dict[str, Any], out: str) -> list[str]:
    head = f"{out} {method}".ljust(LABEL)
    keys = list(params)
    if "args" not in keys or len(keys) == 1:
        return [head + compact(params)]
    first = {key: params[key] for key in keys if key != "args"}
    body = compact(first)
    return [head + body[:-2] + ",", " " * LABEL + "  " + f'"args": {compact(params["args"])}' + " }"]


def _reason(message: str) -> list[str]:
    cut = message.find(" (")
    if cut > 0 and message.endswith(")"):
        return [INDENT + message[:cut], INDENT + message[cut + 1 :]]
    return [INDENT + message]


def exchange(entry: dict[str, Any], arrows: tuple[str, str] = ARROWS) -> list[str]:
    """One exchange: what held before it as a comment, the request and the hub's answer."""
    to_hub, back = arrows
    out: list[str] = []
    if entry.get("before"):
        out.append(f"{COMMENT}{entry['before']}")
    out += _request(entry["request"]["method"], entry["request"]["params"], to_hub)
    error = entry.get("error")
    if error:
        out.append(f"{back} error {error['code']} {error['data']['name']}")
        out += _reason(error["message"])
    else:
        result = entry.get("result") or {}
        out.append(f"{back} result".ljust(LABEL) + compact({"status": result.get("status")}))
    soil = entry.get("soil_moisture")
    if soil:
        before, after = shown(soil["before"]), shown(soil["after"])
        out.append(f"{back} hal/value".ljust(LABEL) + f"soil_moisture rises from {before} to {after}")
    return out


def lines(record: dict[str, Any], arrows: tuple[str, str] = ARROWS) -> list[str]:
    """The whole trace, exchanges separated by a blank line. CLI output passes ASCII_ARROWS."""
    out: list[str] = []
    for index, entry in enumerate(record["exchanges"]):
        if index:
            out.append("")
        out += exchange(entry, arrows)
    return out


def text(record: dict[str, Any]) -> str:
    return "\n".join(lines(record)) + "\n"


def outcome(record: dict[str, Any]) -> str:
    """One sentence saying what the demo shows, with every number from the record."""
    too_long, _empty, watered = record["exchanges"]
    asked = shown(too_long["request"]["params"]["args"]["duration"])
    duration = shown(watered["request"]["params"]["args"]["duration"])
    soil = watered["soil_moisture"]
    return (
        f"You'll see the hub refuse a {asked} watering, hold the pump while the tank is empty, "
        f"then water for {duration} as soil moisture rises from {shown(soil['before'])} to {shown(soil['after'])}."
    )
