"""Search every device's channels and actions, so a client needs no device id in advance.

`find` reads only what the hub already holds (device files and the latest values) and never
reaches a driver, so a search never shows up as a read. Free text matches device ids and names,
channel and action names, descriptions, enum values, units and the physical quantity a unit
measures, such as temperature for degC or power for W. A unit filter matches every channel a
value in that unit converts to, by the same conversion the kernel uses for a command.
"""

from __future__ import annotations

import functools
import re
from typing import TYPE_CHECKING, Any, Final, Literal

import pint

from openhal.hub import views
from openhal.spec.units import UnitError, convert, normalize_unit, parse_quantity, parse_unit, registry, wire_unit

if TYPE_CHECKING:
    from openhal.hub.hub import Hub
    from openhal.kernel.runtime import DeviceRuntime
    from openhal.spec.models import ArgSpec, ReadChannel, WriteChannel

Kind = Literal["readable", "writable", "action"]
KINDS: Final[tuple[Kind, ...]] = ("readable", "writable", "action")
_WORD: Final = re.compile(r"[a-z0-9%]+")
MAX_RESULTS: Final = 500


class FindError(ValueError):
    """A search the hub can't run, such as a unit it doesn't know."""


@functools.cache
def _dimension_names() -> dict[Any, tuple[str, ...]]:
    found: dict[Any, list[str]] = {}
    for name in registry()._dimensions:  # noqa: SLF001 (pint lists its named dimensions nowhere else)
        if name == "[]" or "esu_" in name or "gaussian" in name:
            continue
        found.setdefault(registry().get_dimensionality(name), []).append(name.strip("[]").replace("_", " "))
    return {key: tuple(names) for key, names in found.items()}


def measures(unit: str | None) -> tuple[str, ...]:
    """The physical quantities a unit measures, such as temperature for degC. Empty for plain numbers."""
    if not unit:
        return ()
    try:
        parsed: pint.Unit = parse_unit(unit)
    except UnitError:
        return ()
    if not parsed.dimensionality:
        return ()
    return _dimension_names().get(parsed.dimensionality, ())


def _unit_words(unit: str | None) -> list[str]:
    if not unit:
        return []
    return [unit, normalize_unit(unit), str(parse_unit(unit)).replace("_", " "), *measures(unit)]


def converts(query: str, unit: str | None) -> bool:
    """True when a value in `query` converts to `unit`, exactly as a command would."""
    if not unit:
        return False
    try:
        convert(parse_quantity(f"1 {query}"), unit)
    except UnitError:
        return False
    return True


def _channel(runtime: DeviceRuntime, name: str, kind: Kind, now: float) -> dict[str, Any]:
    file = runtime.file
    spec = file.write[name] if kind == "writable" else file.read[name]
    entry: dict[str, Any] = {"type": spec.type, "unit": wire_unit(spec.unit), "values": spec.values or None}
    if kind == "writable":
        write = file.write[name]
        hazard = file.effective_hazard
        entry |= {
            "min": write.min,
            "max": write.max,
            "step": write.step,
            "max_change_per_s": write.max_change_per_s,
            "confirm": "confirm-each-time" if hazard == "high" else write.confirm,
        }
    return entry | views.latest_value(runtime, name, now)


def _argument(spec: ArgSpec) -> dict[str, Any]:
    shown = {key: value for key, value in spec.model_dump(exclude_none=True).items() if value != []}
    if spec.unit:
        shown["unit"] = wire_unit(spec.unit)
    return shown


def _entries(hub: Hub) -> list[dict[str, Any]]:
    """Every channel and action on the hub, with the words a search matches."""
    now = hub.kernel.clock()
    found: list[dict[str, Any]] = []
    for device_id, runtime in hub.kernel.devices.items():
        file = runtime.file
        device = {
            "device": device_id,
            "device_name": file.device.name,
            "hazard": file.effective_hazard,
            "connected": runtime.connected,
            "takes_commands": file.writable and runtime.available is None and not hub.kernel.stopped,
        }
        about = [device_id, file.device.name, file.device.model or "", file.device.manufacturer or ""]
        channels: list[tuple[str, Kind, ReadChannel | WriteChannel]] = [
            *((name, "readable", spec) for name, spec in file.read.items()),
            *((name, "writable", spec) for name, spec in file.write.items()),
        ]
        for name, kind, spec in channels:
            entry = {"target": f"{device_id}.{name}", "name": name, "kind": kind, **device}
            entry |= _channel(runtime, name, kind, now)
            words = [*about, name, kind, spec.type, *spec.values, *_unit_words(spec.unit)]
            found.append({**entry, "_words": words, "_units": [spec.unit]})
        for name, action in file.actions.items():
            args = {arg: _argument(spec) for arg, spec in action.args.items()}
            units = [spec.unit for spec in action.args.values()]
            entry = {
                "target": f"{device_id}.{name}",
                "name": name,
                "kind": "action",
                **device,
                "description": action.description,
                "args": args,
                "require": [condition for condition, _message in action.conditions] or None,
                "confirm": "confirm-each-time" if file.effective_hazard == "high" else action.confirm,
            }
            words = [*about, name, "action", action.description or "", *args]
            words += [word for unit in units for word in _unit_words(unit)]
            found.append({**entry, "_words": words, "_units": units})
    return found


def _matched(query: list[str], words: list[str]) -> list[str]:
    text = " ".join(words).lower().replace("_", " ").replace("-", " ")
    return [word for word in query if word in text or word.replace("_", " ") in text]


def find(
    hub: Hub,
    *,
    text: str | None = None,
    unit: str | None = None,
    kind: Kind | None = None,
    hazard: str | None = None,
    connected: bool | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    """Channels and actions that match every filter given, best text matches first.

    `kind` readable matches write channels too, since a write channel reads back. Each match
    names its target as device.channel or device.action.
    """
    if unit is not None:
        try:
            parse_unit(unit)
        except UnitError as exc:
            raise FindError(f"{unit!r} is not a unit the hub knows. {exc}") from exc
    query = [word for word in _WORD.findall((text or "").lower()) if len(word) > 1 or word == "%"]
    ranked: list[tuple[int, dict[str, Any]]] = []
    for entry in _entries(hub):
        if kind is not None and not (entry["kind"] == kind or (kind == "readable" and entry["kind"] == "writable")):
            continue
        if hazard is not None and entry["hazard"] != hazard:
            continue
        if connected is not None and entry["connected"] != connected:
            continue
        if unit is not None and not any(converts(unit, own) for own in entry["_units"]):
            continue
        matched = _matched(query, entry["_words"])
        if query and not matched:
            continue
        shown = {key: value for key, value in entry.items() if not key.startswith("_") and value is not None}
        if query:
            shown["matched"] = matched
        ranked.append((len(matched), shown))
    ranked.sort(key=lambda pair: (-pair[0], pair[1]["device"], KINDS.index(pair[1]["kind"]), pair[1]["name"]))
    matches = [entry for _score, entry in ranked]
    return {"count": len(matches), "matches": matches[: max(1, min(limit, MAX_RESULTS))]}
