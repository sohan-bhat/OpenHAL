"""What describe() proposes for an INDI device, from the properties the server defined.

Channels follow the conventions for the device's kind when the matching standard property
exists. Number limits come from the members' min and max. Every write and action is marked
suggested. Other properties are listed in the notes so they can be mapped by hand.
"""

from __future__ import annotations

from typing import Any

from openhal.drivers.indi import channels
from openhal.drivers.indi.session import IndiSession

EACH = {"confirm": "confirm-each-time", "suggested": True}


def _limits(session: IndiSession, device: str, entry: dict[str, Any]) -> tuple[float | None, float | None]:
    vector = session.vectors.get((device, entry["property"]))
    member = vector.members.get(entry.get("element") or "") if vector else None
    if member is None or member.minimum is None or member.maximum is None:
        return None, None
    scale = float(entry.get("scale", 1.0))
    return member.minimum * scale, member.maximum * scale


def proposal(session: IndiSession, device: str, kind: str) -> dict[str, Any]:
    defined = {name for owner, name in session.vectors if owner == device}
    read: dict[str, Any] = {}
    write: dict[str, Any] = {}
    actions: dict[str, Any] = {}
    for name, entry in channels.READS.get(kind, {}).items():
        if entry["property"] not in defined:
            continue
        vector = session.vectors[(device, entry["property"])]
        if entry.get("state") or vector.kind == "switch":
            read[name] = {"type": "bool"}
        else:
            read[name] = {"unit": entry.get("unit", "dimensionless")}
    for name, entry in channels.WRITES.get(kind, {}).items():
        if entry["property"] not in defined:
            continue
        vector = session.vectors[(device, entry["property"])]
        if vector.kind == "switch":
            write[name] = {"type": "bool", "suggested": True}
            read.pop(name, None)
            continue
        low, high = _limits(session, device, entry)
        write[name] = {"unit": entry.get("unit", "dimensionless"), "min": low or 0, "max": high or 0, "suggested": True}
        read.pop(name, None)
    for name, entry in channels.ACTIONS.get(kind, {}).items():
        if entry["property"] not in defined:
            continue
        action: dict[str, Any] = dict(EACH) if entry.get("args") or name in ("park", "unpark") else {"suggested": True}
        if entry.get("args"):
            args: dict[str, Any] = {}
            for arg, spec in entry["args"].items():
                low, high = _limits(session, device, {"property": entry["property"], **spec})
                args[arg] = {"unit": spec.get("unit", "dimensionless"), "min": low or 0, "max": high or 0}
            if kind == "telescope" and "declination" in args:
                args["declination"]["min"] = -30
            action["args"] = args
        actions[name] = action
    used = {
        entry["property"]
        for table in (channels.READS, channels.WRITES, channels.ACTIONS)
        for entry in table.get(kind, {}).values()
    }
    others = sorted(defined - used - {"CONNECTION", "DRIVER_INFO", "ON_COORD_SET"})
    notes = "Proposed from the INDI properties. Every limit is a suggestion. Lower them for your setup."
    if others:
        notes += f" Other properties, which need a map, are {', '.join(others[:40])}."
    return {
        "device": {"name": device},
        "read": read,
        "write": write,
        "actions": actions,
        "notes": notes[:4000],
    }
