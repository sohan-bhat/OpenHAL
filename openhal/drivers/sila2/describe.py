"""What describe() proposes for a SiLA 2 server, from the Feature Definitions it implements.

Properties become read channels with the unit and range from their constraints, and observable
properties are marked as streams. Commands become actions with one argument per parameter.
Numeric arguments take their limits from MinimalInclusive and MaximalInclusive, or 0 to 0 when
the feature gives none, so nothing runs until a person sets real limits. SiLAService and
structures are listed in the notes instead.
"""

from __future__ import annotations

import re
from typing import Any

from openhal.drivers.serial.mapping import device_unit
from openhal.drivers.sila2 import channels

EACH = {"confirm": "confirm-each-time", "suggested": True}


def _snake(*parts: str) -> str:
    text = "_".join(re.sub(r"(?<!^)(?=[A-Z])", "_", part).lower() for part in parts)
    text = re.sub(r"[^a-z0-9_]+", "_", text).strip("_")
    return (text if text[:1].isalpha() else f"s_{text}")[:48].rstrip("_")


def _spec(kind: str, label: str | None, span: tuple[float | None, float | None]) -> dict[str, Any] | None:
    if kind == "Boolean":
        return {"type": "bool"}
    if kind == "String":
        return {"type": "string", "max_length": 256}
    if kind in ("Real", "Integer"):
        low, high = span
        spec: dict[str, Any] = {"unit": device_unit(label) or "dimensionless", "min": low or 0, "max": high or 0}
        if kind == "Integer":
            spec["step"] = 1
        return spec
    return None


def proposal(client: Any) -> dict[str, Any]:
    from sila2.client import (
        ClientObservableCommand,
        ClientObservableProperty,
        ClientUnobservableCommand,
        ClientUnobservableProperty,
    )

    read: dict[str, Any] = {}
    actions: dict[str, Any] = {}
    skipped: list[str] = []
    for feature_name, feature in sorted(getattr(client, "_features", {}).items()):
        if feature_name == "SiLAService":
            continue
        for member_name in sorted(name for name in dir(feature) if name[:1].isupper()):
            member = getattr(feature, member_name)
            if isinstance(member, ClientObservableProperty | ClientUnobservableProperty):
                kind, label, span = channels.type_info(member._wrapped_property.data_type)  # noqa: SLF001
                spec = _spec(kind, label, span)
                if spec is None:
                    skipped.append(f"{feature_name}.{member_name}")
                    continue
                entry = {key: value for key, value in spec.items() if key not in ("min", "max", "step", "max_length")}
                if span[0] is not None and span[1] is not None and kind in ("Real", "Integer"):
                    entry["range"] = [span[0], span[1]]
                if isinstance(member, ClientObservableProperty):
                    entry["stream"] = True
                entry["map"] = {"feature": feature_name, "property": member_name}
                read[_snake(feature_name, member_name)] = entry
            elif isinstance(member, ClientObservableCommand | ClientUnobservableCommand):
                args: dict[str, Any] = {}
                parameters: dict[str, str] = {}
                for parameter in member._wrapped_command.parameters.fields:  # noqa: SLF001
                    spec = _spec(*channels.type_info(parameter.data_type))
                    if spec is None:
                        break
                    arg = _snake(parameter._identifier)  # noqa: SLF001
                    args[arg] = spec
                    parameters[arg] = parameter._identifier  # noqa: SLF001
                else:
                    action: dict[str, Any] = {
                        **EACH,
                        "map": {"feature": feature_name, "command": member_name, "parameters": parameters},
                    }
                    if args:
                        action["args"] = args
                    actions[_snake(feature_name, member_name)] = action
                    continue
                skipped.append(f"{feature_name}.{member_name}")
    name = "SiLA 2 device"
    notes = "Proposed from the server's Feature Definitions. Numeric limits come from the constraints, or 0 to 0."
    if skipped:
        notes += f" These use types the driver doesn't map yet, {', '.join(skipped[:40])}."
    return {"device": {"name": name}, "read": read, "actions": actions, "notes": notes[:4000]}
