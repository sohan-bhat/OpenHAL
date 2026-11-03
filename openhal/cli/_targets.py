"""Targets for `openhal read`, `write`, `action` and `dry-run` when a person leaves one out (ADR 0020).

At a terminal the person picks a device, then one of its channels or actions, and then types the
value or each action argument with its unit and limits in view. Without a terminal, or with
`--json`, the error lists the devices or names that fit and one exact command to copy, built from
the person's own devices.
"""

from __future__ import annotations

import difflib
from typing import Literal

from openhal.cli import _choices, _pick
from openhal.cli._choices import NO_DEVICES, Need
from openhal.cli._common import hub, parse_quantity_text, show, typed
from openhal.cli._pick import Option
from openhal.client.models import DeviceView, WriteChannel

Kind = Literal["read", "write", "action", "control"]
WHAT: dict[Kind, str] = {
    "read": "a read channel",
    "write": "a write channel",
    "action": "an action",
    "control": "a write channel or an action",
}


def _limits(spec: WriteChannel) -> str:
    if spec.values:
        return " | ".join(spec.values)
    if spec.type == "bool":
        return "true or false"
    if spec.type == "number":
        return f"{show(spec.min, spec.unit)} to {show(spec.max, spec.unit)}"
    return spec.type


def offered(view: DeviceView, kind: Kind) -> dict[str, str]:
    """What `kind` reaches on a device, by name, with a short detail for each."""
    found: dict[str, str] = {}
    if kind == "read":
        for name, spec in view.read.items():
            found[name] = f"now {show(spec.value, spec.unit)}" if spec.known else spec.unit or spec.type
    if kind in ("write", "control"):
        for name, write in view.write.items():
            now = f", now {show(write.value, write.unit)}" if write.known else ""
            found[name] = f"{_limits(write)}{now}"
    if kind in ("action", "control"):
        for name, action in view.actions.items():
            found[name] = action.description or "action"
    return found


def sample(spec: WriteChannel) -> str:
    """A value to show in an example, the current value when known and otherwise the low end."""
    if spec.known and spec.value is not None:
        return show(spec.value, spec.unit)
    if spec.values:
        return spec.values[0]
    if spec.type == "bool":
        return "off"
    if spec.type == "number":
        return show(spec.min if spec.min is not None else 0, spec.unit)
    return "text"


def _argument(name: str, spec: dict[str, object]) -> str:
    unit = spec.get("unit")
    low = spec.get("min")
    if spec.get("type", "number") != "number":
        return f"{name}={spec.get('default', 'true')}"
    return f"{name}={show(low if isinstance(low, int | float) else 1)}{unit or ''}"


def example(command: str, view: DeviceView, name: str) -> str:
    """One exact command that reaches `name` on the device, with a value or arguments that fit."""
    rest = ""
    if name in view.write:
        rest = f" {sample(view.write[name])}"
    elif name in view.actions:
        rest = "".join(f" {_argument(arg, spec)}" for arg, spec in view.actions[name].args.items())
    return f"{command} {view.id}.{name}{rest}"


def _views(kind: Kind) -> list[DeviceView]:
    with hub() as client:
        views = [client.device(item.id) for item in client.devices()]
    return [view for view in views if offered(view, kind)]


def device(command: str, kind: Kind, *, as_json: bool = False, what: str = "a device") -> DeviceView:
    """The device the person picks, from the devices that have what `kind` reaches."""
    found: list[DeviceView] = []

    def options() -> list[Option]:
        found.extend(_views(kind))
        return [Option(view.id, f"{view.name}, {', '.join(offered(view, kind))}") for view in found]

    def run(value: str) -> str:
        view = next((view for view in found if view.id == value), None)
        return example(command, view, next(iter(offered(view, kind)))) if view else f"{command} {value}.NAME"

    spec = Need(command, what, "devices", placeholder="DEVICE", example=run, empty=NO_DEVICES, every="openhal devices")
    picked = _choices.need(spec, options, as_json=as_json)
    return next(view for view in found if view.id == picked)


def name(command: str, kind: Kind, view: DeviceView, *, as_json: bool = False) -> str:
    """The channel or action of `view` the person picks."""
    names = offered(view, kind)
    spec = Need(
        command,
        f"{WHAT[kind]} of {view.id}",
        "names",
        placeholder="NAME",
        example=lambda value: example(command, view, value),
        empty=f"{view.id} has no {WHAT[kind].removeprefix('a ').removeprefix('an ')}.",
    )
    return _choices.need(spec, lambda: [Option(key, detail) for key, detail in names.items()], as_json=as_json)


def target(command: str, kind: Kind, given: str | None, *, as_json: bool = False, what: str = "a device") -> str:
    """`device.name` from what the person gave, a device alone or nothing, picking each missing part."""
    if given:
        with hub() as client:
            view = client.device(given)
    else:
        view = device(command, kind, as_json=as_json, what=what)
    return f"{view.id}.{name(command, kind, view, as_json=as_json)}"


def unknown(view: DeviceView, wanted: str, kind: Kind) -> ValueError:
    """The error for a name the device doesn't have, with the nearest real names."""
    names = list(offered(view, kind))
    near = difflib.get_close_matches(wanted, names, n=3)
    hint = f" Did you mean {_choices.joined(near, 'or')}?" if near else ""
    noun = WHAT[kind].removeprefix("a ").removeprefix("an ")
    return ValueError(f"{view.id} has no {noun} {wanted!r}.{hint} {view.id} offers {', '.join(names) or 'none'}.")


def value(command: str, view: DeviceView, channel: str, *, as_json: bool = False) -> list[str]:
    """The value to write. At a terminal the person types the value with its limits in view."""
    spec = view.write.get(channel)
    if spec is None:
        raise unknown(view, channel, "write")
    if not _pick.available(as_json):
        need = Need(command, "a value", "limits", example=lambda _: example(command, view, channel))
        _choices.missing(need, [offered(view, "write")[channel]])

    def check(text: str) -> str | None:
        try:
            typed(text, spec.type, channel)
        except ValueError as exc:
            return str(exc)
        return None

    unit = f", with the unit, such as {sample(spec)}" if spec.type == "number" else ""
    hint = f"({_limits(spec)}{unit})"
    return [_pick.ask(f"Value for {view.id}.{channel}", check, hint=hint)]


def arguments(view: DeviceView, action: str) -> list[str]:
    """At a terminal, each argument of an action without a default, as key=value. Enter leaves one out."""
    if not _pick.available():
        return []
    found: list[str] = []
    for arg, spec in view.actions[action].args.items():
        if "default" in spec:
            continue
        number = spec.get("type", "number") == "number"

        def check(text: str, number: bool = number, arg: str = arg) -> str | None:
            if not text or not number:
                return None
            try:
                parse_quantity_text(text, arg)
            except ValueError as exc:
                return str(exc)
            return None

        unit = spec.get("unit")
        low, high = spec.get("min"), spec.get("max")
        bounds = f", {show(low, str(unit))} to {show(high, str(unit))}" if low is not None and high is not None else ""
        hint = f"(in {unit}{bounds}. Enter leaves the argument out)" if unit else "(Enter leaves the argument out)"
        text = _pick.ask(f"{arg} for {view.id}.{action}", check, hint=hint)
        if text:
            found.append(f"{arg}={text}")
    return found
