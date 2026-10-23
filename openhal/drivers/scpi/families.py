"""Channel proposals for common SCPI instrument families, chosen from the `*IDN?` reply.

`propose(idn)` returns device file sections for `describe()`. Every write channel and action is
marked `suggested: true`, so the proposal loads read-only until a human confirms the limits.
Command sets come from each vendor's programming guide, listed in docs/drivers/scpi.md.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Identity:
    manufacturer: str
    model: str
    serial: str
    firmware: str

    @classmethod
    def parse(cls, reply: str) -> Identity:
        parts = [part.strip() for part in reply.split(",")]
        parts += [""] * (4 - len(parts))
        return cls(parts[0], parts[1], parts[2], ",".join(parts[3:]).strip(","))


# Rated output per channel (volts, amps), used for suggested limits on known supplies.
RATINGS: dict[str, list[tuple[float, float]]] = {
    "DP832": [(30, 3), (30, 3), (5, 3)],
    "DP832A": [(30, 3), (30, 3), (5, 3)],
    "DP821": [(60, 1), (8, 10)],
    "DP811": [(20, 10)],
    "SPD3303X": [(32, 3.2), (32, 3.2)],
    "SPD3303X-E": [(32, 3.2), (32, 3.2)],
    "SPD1168X": [(16, 8)],
    "E36312A": [(6, 5), (25, 1), (25, 1)],
    "E36313A": [(6, 10), (25, 2), (25, 2)],
}


def _supply(identity: Identity, style: str) -> dict[str, Any]:
    ratings = RATINGS.get(identity.model.upper(), [])
    count = len(ratings) or 1
    read: dict[str, Any] = {}
    write: dict[str, Any] = {}
    actions: dict[str, Any] = {}
    for index in range(1, count + 1):
        where = f"CH{index}" if style == "rigol" else f"(@{index})"
        read[f"ch{index}_voltage"] = {"unit": "V", "every": "1 s", "map": {"query": f"MEAS:VOLT? {where}"}}
        read[f"ch{index}_current"] = {"unit": "A", "every": "1 s", "map": {"query": f"MEAS:CURR? {where}"}}
        if style == "rigol":
            output = {"set": f"OUTP CH{index},{{on_off}}", "get": f"OUTP? CH{index}"}
            command = f"APPL CH{index},{{volts}},{{amps}}"
        else:
            output = {"set": f"OUTP {{on_off}},(@{index})", "get": f"OUTP? (@{index})"}
            command = f"VOLT {{volts}},(@{index});CURR {{amps}},(@{index})"
        write[f"ch{index}_output"] = {
            "type": "bool",
            "confirm": "confirm-each-time",
            "suggested": True,
            "map": output,
        }
        if ratings:
            volts, amps = ratings[index - 1]
            actions[f"set_ch{index}"] = {
                "description": f"Set channel {index} voltage and current limit.",
                "args": {
                    "volts": {"unit": "V", "min": 0, "max": volts, "step": 0.001},
                    "amps": {"unit": "A", "min": 0, "max": amps, "step": 0.001},
                },
                "confirm": "confirm-each-time",
                "suggested": True,
                "map": {"command": command},
            }
    sections: dict[str, Any] = {"read": read, "write": write}
    if actions:
        sections["actions"] = actions
    notes = "Proposed for a bench power supply. Lower the voltage and current limits to what your circuit needs."
    if not ratings:
        notes += " The model's ratings are unknown, so no set action is proposed."
    sections["notes"] = notes
    return sections


def _multimeter() -> dict[str, Any]:
    return {
        "read": {
            "dc_voltage": {"unit": "V", "every": "1 s", "map": {"query": "MEAS:VOLT:DC?"}},
            "dc_current": {"unit": "A", "map": {"query": "MEAS:CURR:DC?"}},
            "resistance": {"unit": "ohm", "map": {"query": "MEAS:RES?"}},
        },
        "notes": "Proposed for a digital multimeter. Each MEAS query reconfigures the range, so poll one at a time.",
    }


def _load() -> dict[str, Any]:
    return {
        "read": {
            "voltage": {"unit": "V", "every": "1 s", "map": {"query": "MEAS:VOLT?"}},
            "current": {"unit": "A", "every": "1 s", "map": {"query": "MEAS:CURR?"}},
            "power": {"unit": "W", "map": {"query": "MEAS:POW?"}},
        },
        "write": {
            "input": {
                "type": "bool",
                "confirm": "confirm-each-time",
                "suggested": True,
                "map": {"set": ":INP {on_off}", "get": ":INP?"},
            }
        },
        "notes": "Proposed for an electronic load. Set the load mode and level on the front panel first.",
    }


def _generator() -> dict[str, Any]:
    return {
        "read": {"ch1_frequency": {"unit": "Hz", "map": {"query": ":SOUR1:FREQ?"}}},
        "write": {
            "ch1_output": {
                "type": "bool",
                "confirm": "confirm",
                "suggested": True,
                "map": {"set": ":OUTP1 {on_off}", "get": ":OUTP1?"},
            }
        },
        "notes": "Proposed for a function generator. Amplitude and frequency writes need limits for your circuit.",
    }


def _scope() -> dict[str, Any]:
    return {
        "read": {"trigger_status": {"type": "string", "map": {"query": ":TRIG:STAT?"}}},
        "notes": (
            "Proposed for an oscilloscope. Measurement commands differ by vendor, so only the trigger state is read."
        ),
    }


FAMILIES: list[tuple[str, str, str]] = [
    (r"RIGOL", r"^DP8\d\d", "supply-rigol"),
    (r"SIGLENT", r"^SPD\d", "supply-rigol"),
    (r"KEYSIGHT|AGILENT", r"^E363\d\dA", "supply-keysight"),
    (r"KEYSIGHT|AGILENT|HEWLETT", r"^344\d\d", "multimeter"),
    (r"RIGOL", r"^DM\d", "multimeter"),
    (r"SIGLENT", r"^SDM\d", "multimeter"),
    (r"KEITHLEY", r"^(MODEL )?(2000|2010|2100|2110|DMM\d)", "multimeter"),
    (r"RIGOL", r"^DL3\d", "load"),
    (r"SIGLENT", r"^SDL\d", "load"),
    (r"RIGOL", r"^DG\d", "generator"),
    (r"SIGLENT", r"^SDG\d", "generator"),
    (r"KEYSIGHT|AGILENT", r"^33[56]\d\d", "generator"),
    (r"RIGOL", r"^(DS|MSO|DHO)\d", "scope"),
    (r"SIGLENT", r"^SDS\d", "scope"),
]


def classify(identity: Identity) -> str | None:
    for manufacturer, model, kind in FAMILIES:
        if re.search(manufacturer, identity.manufacturer, re.IGNORECASE) and re.search(
            model, identity.model, re.IGNORECASE
        ):
            return kind
    return None


def propose(reply: str) -> dict[str, Any]:
    identity = Identity.parse(reply)
    kind = classify(identity)
    sections: dict[str, Any] = {
        "device": {
            "name": f"{identity.manufacturer.title()} {identity.model}".strip(),
            "manufacturer": identity.manufacturer,
            "model": identity.model,
        },
        "match": {"scpi_idn": "^" + re.escape(f"{identity.manufacturer},{identity.model}")},
    }
    if kind == "supply-rigol":
        sections.update(_supply(identity, "rigol"))
    elif kind == "supply-keysight":
        sections.update(_supply(identity, "keysight"))
    elif kind == "multimeter":
        sections.update(_multimeter())
    elif kind == "load":
        sections.update(_load())
    elif kind == "generator":
        sections.update(_generator())
    elif kind == "scope":
        sections.update(_scope())
    else:
        sections["notes"] = "Unknown instrument class. Add channels from the programming guide by hand."
    return sections
