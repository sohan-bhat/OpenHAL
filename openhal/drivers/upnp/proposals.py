"""Channels `describe()` proposes from a UPnP device's service descriptions.

Get actions whose only inputs are InstanceID, Channel or Speed become read channels, one per
output. A Set action with one other input becomes a channel under `write`, read back through its
Get action when there is one. Other actions with no outputs and only those inputs become actions.
"""

from __future__ import annotations

import re
from typing import Any, Final

from async_upnp_client.client import UpnpAction, UpnpService

INTEGER_TYPES: Final = frozenset({"ui1", "ui2", "ui4", "ui8", "i1", "i2", "i4", "i8", "int"})
FLOAT_TYPES: Final = frozenset({"r4", "r8", "number", "fixed.14.4", "float"})
DEFAULT_ARGS: Final = {"InstanceID": 0, "Channel": "Master", "Speed": "1"}


def snake(text: str) -> str:
    """CurrentVolume to current_volume, for proposed channel names."""
    words = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", text).lower()
    name = re.sub(r"[^a-z0-9]+", "_", words).strip("_")[:48]
    return name if name and name[0].isalpha() else f"v_{name}"[:48]


def _fixed(arguments: list[Any]) -> dict[str, Any] | None:
    """Default values for InstanceID, Channel and Speed, or None if another argument is needed."""
    values: dict[str, Any] = {}
    for argument in arguments:
        if argument.name not in DEFAULT_ARGS:
            return None
        values[argument.name] = DEFAULT_ARGS[argument.name]
    return values


def _spec_for(variable: Any) -> dict[str, Any] | None:
    data_type = variable.data_type
    if data_type == "boolean":
        return {"type": "bool"}
    if data_type in INTEGER_TYPES | FLOAT_TYPES:
        spec: dict[str, Any] = {"unit": "dimensionless"}
        if variable.min_value is not None and variable.max_value is not None:
            spec.update({"min": variable.min_value, "max": variable.max_value})
        return spec
    if data_type == "string" and variable.allowed_values:
        return {"type": "enum", "values": sorted(str(value) for value in variable.allowed_values)}
    if data_type == "string":
        return {"type": "string"}
    return None


def propose(short: str, service: UpnpService, action: UpnpAction) -> list[tuple[str, str, dict[str, Any]]]:
    found: list[tuple[str, str, dict[str, Any]]] = []
    inputs = action.in_arguments()
    fixed = _fixed(inputs)
    if action.name.startswith("Get") and fixed is not None:
        for argument in action.out_arguments():
            spec = _spec_for(argument.related_state_variable)
            if spec is None:
                continue
            spec.pop("min", None)
            spec.pop("max", None)
            call = {"service": short, "action": action.name, "args": fixed, "output": argument.name}
            found.append(("read", snake(argument.name), {**spec, "map": call}))
    others = [argument for argument in inputs if argument.name not in DEFAULT_ARGS]
    if action.name.startswith("Set") and len(others) == 1:
        spec = _spec_for(others[0].related_state_variable)
        if spec is not None and spec.get("type") != "string":
            if spec.get("unit") and "min" not in spec:
                spec.update({"min": 0, "max": 100})
            args = {argument.name: DEFAULT_ARGS.get(argument.name, "{value}") for argument in inputs}
            setter: dict[str, Any] = {"service": short, "action": action.name, "args": args}
            getter = f"Get{action.name[3:]}"
            if service.has_action(getter):
                get_action = service.action(getter)
                get_fixed = _fixed(get_action.in_arguments())
                outputs = get_action.out_arguments()
                if get_fixed is not None and len(outputs) == 1:
                    setter["state"] = {"service": short, "action": getter, "args": get_fixed, "output": outputs[0].name}
            found.append(("write", snake(action.name[3:]), {**spec, "suggested": True, "map": setter}))
    if not action.out_arguments() and fixed is not None and not action.name.startswith(("Set", "Get")):
        found.append(
            (
                "actions",
                snake(action.name),
                {"suggested": True, "map": {"service": short, "action": action.name, "args": fixed}},
            )
        )
    return found
