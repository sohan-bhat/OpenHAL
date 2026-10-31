"""The Matter clusters `describe()` supports, with the attribute scaling the Matter specification gives them.

Each entry proposes channels for one cluster on one endpoint. Ids are the decimal ids the Matter
Server uses in attribute paths. Scales follow the Matter 1.3 Application Cluster specification,
for example TemperatureMeasurement MeasuredValue is in 0.01 degC and LevelControl CurrentLevel runs
from 1 to 254.
"""

from __future__ import annotations

from typing import Any, Final

ON_OFF: Final = 6
LEVEL: Final = 8
BOOLEAN_STATE: Final = 69
WINDOW_COVERING: Final = 258
DOOR_LOCK: Final = 257
THERMOSTAT: Final = 513
FAN: Final = 514
COLOR: Final = 768
TEMPERATURE: Final = 1026
PRESSURE: Final = 1027
HUMIDITY: Final = 1029
OCCUPANCY: Final = 1030
POWER_SOURCE: Final = 47
ELECTRICAL_POWER: Final = 144
LEVEL_PERCENT: Final = 0.39370078740157477


def proposals(endpoint: int, cluster: int) -> dict[str, dict[str, Any]]:
    """Channels proposed for one cluster, keyed `read.<name>`, `write.<name>` or `actions.<name>`."""
    path = {"endpoint": endpoint, "cluster": cluster}
    found: dict[str, dict[str, Any]] = {}
    if cluster == ON_OFF:
        found["write.power"] = {
            "type": "bool",
            "map": {**path, "attribute": 0, "on_command": "On", "off_command": "Off"},
        }
    elif cluster == LEVEL:
        found["write.level"] = {
            "unit": "percent",
            "min": 0,
            "max": 100,
            "map": {
                **path,
                "attribute": 0,
                "scale": LEVEL_PERCENT,
                "command": "MoveToLevelWithOnOff",
                "payload": {"level": "{value}", "transitionTime": 0, "optionsMask": 0, "optionsOverride": 0},
            },
        }
    elif cluster == COLOR:
        found["write.color_temp"] = {
            "unit": "dimensionless",
            "min": 153,
            "max": 500,
            "map": {
                **path,
                "attribute": 7,
                "command": "MoveToColorTemperature",
                "payload": {
                    "colorTemperatureMireds": "{value}",
                    "transitionTime": 0,
                    "optionsMask": 0,
                    "optionsOverride": 0,
                },
            },
        }
    elif cluster == BOOLEAN_STATE:
        found["read.contact"] = {"type": "bool", "map": {**path, "attribute": 0}}
    elif cluster == TEMPERATURE:
        found["read.temperature"] = {"unit": "degC", "map": {**path, "attribute": 0, "scale": 0.01}}
    elif cluster == HUMIDITY:
        found["read.humidity"] = {"unit": "percent", "map": {**path, "attribute": 0, "scale": 0.01}}
    elif cluster == PRESSURE:
        found["read.pressure"] = {"unit": "kPa", "map": {**path, "attribute": 0, "scale": 0.1}}
    elif cluster == OCCUPANCY:
        found["read.occupied"] = {"type": "bool", "map": {**path, "attribute": 0, "bit": 0}}
    elif cluster == POWER_SOURCE:
        found["read.battery"] = {"unit": "percent", "map": {**path, "attribute": 12, "scale": 0.5}}
    elif cluster == ELECTRICAL_POWER:
        found["read.active_power"] = {"unit": "W", "map": {**path, "attribute": 8, "scale": 0.001}}
    elif cluster == THERMOSTAT:
        found["read.local_temperature"] = {"unit": "degC", "map": {**path, "attribute": 0, "scale": 0.01}}
        found["write.heating_setpoint"] = {
            "unit": "degC",
            "min": 7,
            "max": 30,
            "map": {**path, "attribute": 18, "scale": 0.01},
        }
    elif cluster == FAN:
        found["write.fan_percent"] = {"unit": "percent", "min": 0, "max": 100, "map": {**path, "attribute": 2}}
    elif cluster == WINDOW_COVERING:
        found["read.position"] = {"unit": "percent", "map": {**path, "attribute": 14, "scale": 0.01}}
        found["actions.stop_motion"] = {"map": {**path, "command": "StopMotion"}}
    elif cluster == DOOR_LOCK:
        found["read.lock_state"] = {
            "type": "enum",
            "values": ["not_fully_locked", "locked", "unlocked"],
            "map": {**path, "attribute": 0, "lookup": {0: "not_fully_locked", 1: "locked", 2: "unlocked"}},
        }
        found["actions.lock"] = {
            "confirm": "confirm-each-time",
            "map": {**path, "command": "LockDoor", "timed_ms": 1000},
        }
    return found
