"""What describe() proposes for an Alpaca device, from its `can*` properties and limits.

Only read-only GET requests are sent. Every write and action is marked suggested.
"""

from __future__ import annotations

from typing import Any

from openhal.drivers.alpaca import channels
from openhal.drivers.alpaca.client import AlpacaClient, AlpacaError
from openhal.drivers.base import DriverError

SUGGESTED = {"suggested": True}
EACH = {"confirm": "confirm-each-time", "suggested": True}


async def _get(client: AlpacaClient, path: str, params: dict[str, str] | None = None) -> Any:
    try:
        return await client.get(path, params)
    except AlpacaError:
        return None


def _reads(kind: str) -> dict[str, Any]:
    found: dict[str, Any] = {}
    for name, entry in channels.READS.get(kind, {}).items():
        if "states" in entry:
            found[name] = {"type": "enum", "values": entry["states"]}
        elif "unit" in entry:
            found[name] = {"unit": entry["unit"]}
        else:
            found[name] = {"type": "bool"}
    return found


async def proposal(client: AlpacaClient, target: tuple[str, int], server: dict[str, Any]) -> dict[str, Any]:
    kind, number = target
    base = f"/api/v1/{kind}/{number}"
    name = await _get(client, f"{base}/name")
    read = _reads(kind)
    write: dict[str, Any] = {}
    actions: dict[str, Any] = {}
    notes = "Proposed from the device's can properties. Every limit is a suggestion. Lower them for your site."
    if kind == "telescope":
        write["tracking"] = {"type": "bool", **SUGGESTED}
        actions["abort_slew"] = dict(SUGGESTED)
        if await _get(client, f"{base}/canpark"):
            actions["park"] = dict(EACH)
            actions["unpark"] = dict(EACH)
        if await _get(client, f"{base}/canfindhome"):
            actions["find_home"] = dict(EACH)
        if await _get(client, f"{base}/canslewasync"):
            actions["slew_to_coordinates"] = {
                "args": {
                    "right_ascension": {"unit": "deg", "min": 0, "max": 359.99},
                    "declination": {"unit": "deg", "min": -30, "max": 90},
                },
                "require": ["at_park == false", "tracking == true"],
                **EACH,
            }
        if await _get(client, f"{base}/canslewaltazasync"):
            actions["slew_to_alt_az"] = {
                "args": {
                    "azimuth": {"unit": "deg", "min": 0, "max": 359.99},
                    "altitude": {"unit": "deg", "min": 15, "max": 90},
                },
                "require": ["at_park == false", "tracking == false"],
                **EACH,
            }
        notes += " Raise the minimum altitude and declination to keep the tube clear of the pier and the horizon."
    elif kind == "focuser":
        top = await _get(client, f"{base}/maxstep")
        if await _get(client, f"{base}/absolute") is False:
            notes += " This focuser is relative only, so the position channel can't be written."
        elif isinstance(top, int):
            write["position"] = {"unit": "dimensionless", "min": 0, "max": top, "step": 1, **SUGGESTED}
        actions["halt"] = dict(SUGGESTED)
    elif kind == "camera":
        write["cooler"] = {"type": "bool", **SUGGESTED}
        if await _get(client, f"{base}/cansetccdtemperature"):
            write["target_temperature"] = {"unit": "degC", "min": -20, "max": 20, "max_change_per_s": 1, **SUGGESTED}
        actions["start_exposure"] = {
            "args": {"duration": {"unit": "s", "min": 0.001, "max": 600}, "light": {"type": "bool"}},
            "require": ["camera_state == idle"],
            **SUGGESTED,
        }
        actions["abort_exposure"] = dict(SUGGESTED)
    elif kind == "dome":
        actions["abort_slew"] = dict(SUGGESTED)
        if await _get(client, f"{base}/cansetshutter"):
            actions["open_shutter"] = dict(EACH)
            actions["close_shutter"] = dict(EACH)
        if await _get(client, f"{base}/canpark"):
            actions["park"] = dict(EACH)
        if await _get(client, f"{base}/cansetazimuth"):
            actions["slew_to_azimuth"] = {"args": {"azimuth": {"unit": "deg", "min": 0, "max": 359.99}}, **EACH}
    elif kind == "switch":
        notes += await _switches(client, base, read, write)
    proposal: dict[str, Any] = {
        "device": {"name": str(name or f"Alpaca {kind} {number}")},
        "read": read,
        "write": write,
        "actions": actions,
        "notes": notes,
    }
    if server.get("Manufacturer"):
        proposal["device"]["manufacturer"] = str(server["Manufacturer"])
    return proposal


async def _switches(client: AlpacaClient, base: str, read: dict[str, Any], write: dict[str, Any]) -> str:
    """Propose one channel per switch and return a note that names each one."""
    count = await _get(client, f"{base}/maxswitch")
    if not isinstance(count, int):
        raise DriverError("The switch device didn't report maxswitch.")
    labels: list[str] = []
    for index in range(min(count, 64)):
        query = {"Id": str(index)}
        low = await _get(client, f"{base}/minswitchvalue", query)
        high = await _get(client, f"{base}/maxswitchvalue", query)
        step = await _get(client, f"{base}/switchstep", query)
        writable = await _get(client, f"{base}/canwrite", query)
        label = await _get(client, f"{base}/getswitchname", query)
        binary = low == 0 and high == 1 and step == 1
        entry: dict[str, Any] = (
            {"type": "bool"}
            if binary
            else {"unit": "dimensionless", "min": low, "max": high, **({"step": step} if step else {})}
        )
        name = f"switch_{index}"
        if writable:
            write[name] = {**entry, **SUGGESTED}
        else:
            read[name] = {"type": "bool"} if binary else {"unit": "dimensionless", "range": [low, high]}
        if label:
            labels.append(f"{name} is {str(label)[:60]}")
    return f" Switch names from the device. {', '.join(labels)}." if labels else ""
