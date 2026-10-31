"""The text `openhal demo --full` prints, made from a record of the whole run (openhal/demo/e2e.py).

Each part names who acts. MCP tool calls and their results are shown as a message trace, in the
style of openhal/demo/trace.py, and the rest as short indented lines.
"""

from __future__ import annotations

from typing import Any, Final

from openhal.demo.trace import ARROWS, INDENT, compact
from openhal.protocol.errors import shown

LABEL: Final = 20


def _board(received: list[str]) -> str:
    return f"{INDENT}the board got {', '.join(received) if received else 'nothing'}"


def _call(arrow: str, tool: str, arguments: dict[str, Any]) -> list[str]:
    head = f"{arrow} {tool}".ljust(LABEL)
    if "args" not in arguments:
        return [head + compact(arguments)]
    first = compact({key: value for key, value in arguments.items() if key != "args"})
    return [head + first[:-2] + ",", " " * LABEL + "  " + f'"args": {compact(arguments["args"])}' + " }"]


def _reason(message: str) -> list[str]:
    cut = message.find(" (")
    if cut > 0 and message.endswith(")"):
        return [INDENT + message[:cut], INDENT + message[cut + 1 :]]
    return [INDENT + message]


def _set_up(steps: dict[str, dict[str, Any]]) -> list[str]:
    discovery, writer, interview, saved = (steps[name] for name in ("discovery", "writer", "interview", "save"))
    found = discovery["found"]
    duration = writer["draft"]["actions"]["water"]["args"]["duration"]
    low = shown({"value": duration["min"], "unit": duration["unit"]})
    high = shown({"value": duration["max"], "unit": duration["unit"]})
    confirmed = saved["confirmed"]
    out = [
        f"discovery by {discovery['actor']}",
        f"{INDENT}found {found['label']} at {found['address']}, driver {found['driver']}",
        _board(discovery["board_received"]),
        "",
        f"driver writer by {writer['actor']}",
        f"{INDENT}read {', '.join(writer['sources'])}",
        _board(writer["board_received"]),
        f"{INDENT}drafted water with duration {low} to {high}, every limit suggested",
        "",
        f"limits interview by {interview['actor']}",
    ]
    out += [f"{INDENT}{answer['question']} {answer['answer']}" for answer in interview["answers"]]
    out += [
        f"{INDENT}saved {saved['saved']}, confirmed by {confirmed['by']} {confirmed['at']}",
        f"{INDENT}{steps['restart']['note']}",
    ]
    return out


def _agent(steps: dict[str, dict[str, Any]], arrows: tuple[str, str]) -> list[str]:
    to_hub, back = arrows
    read, drafted, checked = (steps[name] for name in ("agent-reads", "agent-drafts", "agent-dry-runs"))
    result = drafted["result"]
    out = [f"{read['actor']} over {read['via']}"]
    out += _call(to_hub, read["tool"], read["arguments"])
    out.append(f"{back} result".ljust(LABEL) + compact(read["result"]))
    out += _call(to_hub, drafted["tool"], {"routine_id": drafted["arguments"]["routine_id"]})
    out += [INDENT * 2 + line for line in drafted["arguments"]["source"].splitlines()]
    out.append(
        f"{back} result".ljust(LABEL)
        + compact({"enabled": result["enabled"], "disabled_reason": result["disabled_reason"]})
    )
    out += _call(to_hub, checked["tool"], checked["arguments"])
    out.append(f"{back} result".ljust(LABEL) + compact({"ok": checked["result"]["ok"]}))
    return out


def _routine(steps: dict[str, dict[str, Any]]) -> list[str]:
    enabled, ran, reread = (steps[name] for name in ("person-enables", "routine-runs", "agent-reads-again"))
    soil = reread["soil_moisture"]
    return [
        f"{enabled['actor']} enables {enabled['args']['routine_id']}",
        f"{INDENT}{ran['actor']} runs {ran['status']}, {ran['trigger']}",
        _board(ran["board_received"]),
        f"{INDENT}soil_moisture rises from {shown(soil['before'])} to {shown(soil['after'])}",
    ]


def _refusal(steps: dict[str, dict[str, Any]], arrows: tuple[str, str]) -> list[str]:
    to_hub, back = arrows
    refused = steps["too-long"]
    error = refused["result"]["error"]
    out = [f"{refused['actor']} over {refused['via']}"]
    out += _call(to_hub, refused["tool"], refused["arguments"])
    out.append(f"{back} error {error['code']} {error['name']}")
    out += _reason(error["message"])
    out.append(_board(refused["board_received"]))
    return out


def lines(record: dict[str, Any], arrows: tuple[str, str] = ARROWS) -> list[str]:
    """The whole run, parts separated by a blank line. CLI output passes ASCII_ARROWS."""
    steps = {step["id"]: step for step in record["steps"]}
    parts = [_set_up(steps), _agent(steps, arrows), _routine(steps), _refusal(steps, arrows)]
    out: list[str] = []
    for index, part in enumerate(parts):
        if index:
            out.append("")
        out += part
    return out
