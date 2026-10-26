"""The message trace, one of the signature elements of the OpenHAL theme (docs/DESIGN.md).

`lines()` turns a recorded scenario into the text trace the README, the docs and `openhal demo`
show. Requests and errors are shown as the hub sent them. A read shows the value it carried, and
an image shows its format and size with its base64 `data` elided, never the pixels. Long payloads
wrap at a comma, and reasons wrap before the device file citation, so the trace stays narrow.
Narration that is not a message, such as what held before an exchange, is a comment line that
starts with `#`.
"""

from __future__ import annotations

import json
from typing import Any, Final

from openhal.protocol.errors import shown

INDENT: Final = "  "
LABEL: Final = 14
WIDTH: Final = 72
COMMENT: Final = "# "
ARROWS: Final = ("→", "←")
ASCII_ARROWS: Final = ("->", "<-")
ELIDED: Final = {ARROWS: "…", ASCII_ARROWS: "..."}


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
    return json.dumps(value, ensure_ascii=False)


def wrapped(head: str, payload: Any) -> list[str]:
    """`head` and the payload as compact JSON, wrapped at commas to WIDTH under the payload's start."""
    pieces = compact(payload).split(", ")
    out: list[str] = []
    line = head.ljust(LABEL)
    fresh = True
    for index, piece in enumerate(pieces):
        text = piece + ("," if index < len(pieces) - 1 else "")
        if not fresh and len(line) + 1 + len(text) > WIDTH:
            out.append(line)
            line = " " * (LABEL + 2)
            fresh = True
        line += text if fresh else " " + text
        fresh = False
    out.append(line)
    return out


def _reason(message: str) -> list[str]:
    cut = message.find(" (")
    if cut > 0 and message.endswith(")"):
        return [INDENT + message[:cut], INDENT + message[cut + 1 :]]
    return [INDENT + message]


def _value(value: Any, elided: str) -> Any:
    if isinstance(value, dict) and "mimeType" in value:
        return {**value, "data": elided}
    return value


def _result(request: dict[str, Any], result: dict[str, Any], elided: str) -> dict[str, Any]:
    if request["method"] in ("hal/read", "hal/value"):
        return {"value": _value(result.get("value"), elided)}
    if result.get("status") == "pending":
        return {key: result[key] for key in ("status", "requestId", "expiresInS") if key in result}
    return {"status": result.get("status")}


def exchange(entry: dict[str, Any], arrows: tuple[str, str] = ARROWS) -> list[str]:
    """One exchange: what held before it as a comment, the request and the hub's answer."""
    to_hub, back = arrows
    out: list[str] = []
    if entry.get("before"):
        out.append(f"{COMMENT}{entry['before']}")
    request = entry["request"]
    out += wrapped(f"{to_hub} {request['method']}", request["params"])
    error = entry.get("error")
    if error:
        out.append(f"{back} error {error['code']} {error['data']['name']}")
        out += _reason(error["message"])
    else:
        out += wrapped(f"{back} result", _result(request, entry.get("result") or {}, ELIDED[arrows]))
    return out


def lines(record: dict[str, Any], arrows: tuple[str, str] = ARROWS, only: tuple[str, ...] = ()) -> list[str]:
    """The trace, exchanges separated by a blank line. CLI output passes ASCII_ARROWS.

    `only` keeps the exchanges with those ids, such as the kernel moments the README shows.
    """
    out: list[str] = []
    for entry in record["exchanges"]:
        if only and entry["id"] not in only:
            continue
        if out:
            out.append("")
        out += exchange(entry, arrows)
    return out


def text(record: dict[str, Any], only: tuple[str, ...] = ()) -> str:
    return "\n".join(lines(record, only=only)) + "\n"


def celsius(quantity: dict[str, Any]) -> str:
    """A quantity as prose shows it. `{"value": 70, "unit": "degC"}` reads `70 °C`."""
    return shown(quantity).replace(" degC", " °C")


def outcome(record: dict[str, Any]) -> str:
    """One sentence saying what the demo shows, with every number from the record."""
    exchanges = {entry["id"]: entry for entry in record["exchanges"]}
    bed = exchanges["bed-warmer"]["bed_target"]
    refused = exchanges["nozzle-too-hot"]["error"]["data"]
    return (
        f"You'll see the agent warm the bed from {celsius(bed['before'])} to {celsius(bed['after'])}, "
        f"have a {celsius(refused['requested'])} nozzle refused at the {celsius(refused['limit'])} limit, "
        "pause the print when it comes loose and wait for a person to approve the cancel."
    )
