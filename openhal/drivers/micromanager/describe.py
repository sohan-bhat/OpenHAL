"""Device file sections proposed from a loaded Micro-Manager configuration.

MMCore reports which devices the configuration loaded, their roles, the labels of every state
device, the presets of every group, property limits and the focus direction. It reports no stage
travel, so the stage ranges sit around the current position and a person sets the real ranges. Every limit
is marked suggested.
"""

from __future__ import annotations

import re
from typing import Any, Final

LIGHT_WORDS: Final = re.compile(r"intensity|power|level|brightness", re.IGNORECASE)
XY_SPAN_UM: Final = 10000.0
Z_TOWARD_UM: Final = 50.0
Z_AWAY_UM: Final = 500.0


def _slug(label: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")
    return (slug if slug[:1].isalpha() else f"device_{slug}")[:40] or "device"


def _state_type() -> Any:
    from pymmcore_plus import DeviceType

    return DeviceType.State


def proposal(core: Any) -> dict[str, Any]:
    """Read, write, action and safe state sections for the loaded configuration."""
    each = {"suggested": True}
    read: dict[str, Any] = {}
    write: dict[str, Any] = {}
    actions: dict[str, Any] = {"stop": {"suggested": True}}
    notes = ["Proposed from the loaded Micro-Manager configuration."]
    camera = str(core.getCameraDevice())
    if camera:
        read["image"] = {"type": "image"}
        read["pixel_size"] = {"unit": "um"}
        low, high = 0.1, 2000.0
        if core.hasPropertyLimits(camera, "Exposure"):
            low = max(0.01, float(core.getPropertyLowerLimit(camera, "Exposure")))
            high = min(60000.0, float(core.getPropertyUpperLimit(camera, "Exposure")))
        write["exposure"] = {"unit": "ms", "min": low, "max": high, **each}
    xy = str(core.getXYStageDevice())
    if xy:
        x, y = (float(value) for value in core.getXYPosition(xy))
        for axis, at in (("x", x), ("y", y)):
            write[axis] = {"unit": "um", "min": round(at - XY_SPAN_UM), "max": round(at + XY_SPAN_UM), **each}
        actions["move_xy"] = {
            "args": {axis: {"unit": "um", "min": write[axis]["min"], "max": write[axis]["max"]} for axis in ("x", "y")},
            "effects": ["x", "y"],
            **each,
        }
    focus = str(core.getFocusDevice())
    if focus:
        z = float(core.getPosition(focus))
        direction = int(core.getFocusDirection(focus))
        toward = {1: 1, 2: -1}.get(direction)
        if toward is None:
            low_z, high_z = z - Z_TOWARD_UM, z + Z_TOWARD_UM
            notes.append("The focus drive doesn't report which way the sample is, so z sits 50 um either side of now.")
        else:
            near, far = z + toward * Z_TOWARD_UM, z - toward * Z_AWAY_UM
            low_z, high_z = min(near, far), max(near, far)
            side = "maximum" if toward == 1 else "minimum"
            notes.append(
                f"A {'larger' if toward == 1 else 'smaller'} z moves the objective toward the sample, so the z {side} "
                "is the crash limit. Focus on a slide and set the limit a little past focus, short of where the "
                "objective touches the slide."
            )
        write["z"] = {"unit": "um", "min": round(low_z, 1), "max": round(high_z, 1), **each}
        autofocus: dict[str, Any] = {"effects": ["z"], **each}
        if not str(core.getAutoFocusDevice()):
            autofocus["map"] = {"command": "autofocus", "method": "image", "span": "40 um"}
        actions["autofocus"] = autofocus
    if xy or focus:
        actions["home"] = {
            "effects": [name for name in ("x", "y", "z") if name in write],
            "confirm": "confirm-each-time",
            **each,
        }
    for label in core.getLoadedDevicesOfType(_state_type()):
        name = "objective" if re.search(r"objective|nosepiece|turret", label, re.IGNORECASE) else _slug(label)
        if name in write:
            name = _slug(label)
        write[name] = {"type": "enum", "values": list(core.getStateLabels(label)), "map": {"state": label}, **each}
    for group in core.getAvailableConfigGroups():
        presets = list(core.getAvailableConfigs(group))
        name = _slug(group)
        if presets and name not in write:
            write[name] = {"type": "enum", "values": presets, "map": {"group": group}, **each}
    shutter = str(core.getShutterDevice())
    if shutter:
        write["shutter"] = {"type": "bool", **each}
    for label in core.getLoadedDevices():
        if label in (camera, "Core"):
            continue
        for prop in core.getDevicePropertyNames(label):
            if (
                not LIGHT_WORDS.search(prop)
                or not core.hasPropertyLimits(label, prop)
                or core.isPropertyReadOnly(label, prop)
            ):
                continue
            name = _slug(f"{label}_{prop}")
            low, high = float(core.getPropertyLowerLimit(label, prop)), float(core.getPropertyUpperLimit(label, prop))
            write[name] = {
                "unit": "dimensionless",
                "min": low,
                "max": high,
                "map": {"device": label, "property": prop},
                **each,
            }
    read["busy"] = {"type": "bool"}
    proposed: dict[str, Any] = {
        "device": {"name": "Micro-Manager microscope"},
        "read": read,
        "write": write,
        "actions": actions,
        "notes": " ".join(
            [
                *notes,
                "MMCore reports no stage travel, so x and y sit 10 mm either side of now. "
                "Set x and y to the stage's travel.",
            ]
        ),
    }
    if shutter:
        proposed["safe_state"] = [{"shutter": False}]
    return proposed
