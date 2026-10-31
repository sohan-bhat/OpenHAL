"""OPC UA engineering units, as OpenHAL unit names.

OPC UA Part 8 gives each analog variable an `EngineeringUnits` property, an EUInformation with a
`UnitId` from UNECE Recommendation 20 and a display name. The UnitId packs the common code's
ASCII characters into an integer, `CEL` is 0x43454C. This table covers the common codes found on
process and lab equipment. Anything else falls back to the display name, then to the device
file's own `map.unit`.
"""

from __future__ import annotations

from typing import Any, Final

from openhal.drivers.serial.mapping import device_unit

UNECE: Final[dict[str, str]] = {
    "CEL": "degC",
    "FAH": "degF",
    "KEL": "K",
    "P1": "percent",
    "C62": "dimensionless",
    "MTR": "m",
    "CMT": "cm",
    "MMT": "mm",
    "KMT": "km",
    "INH": "inch",
    "FOT": "ft",
    "MTS": "m/s",
    "KMH": "km/h",
    "SEC": "s",
    "C26": "ms",
    "MIN": "min",
    "HUR": "h",
    "HTZ": "Hz",
    "KHZ": "kHz",
    "RPM": "rpm",
    "2A": "rad/s",
    "VLT": "V",
    "2Z": "mV",
    "KVT": "kV",
    "AMP": "A",
    "4K": "mA",
    "WTT": "W",
    "KWT": "kW",
    "WHR": "Wh",
    "KWH": "kWh",
    "JOU": "J",
    "BAR": "bar",
    "MBR": "mbar",
    "PAL": "Pa",
    "KPA": "kPa",
    "HPA": "hPa",
    "LTR": "L",
    "MLT": "mL",
    "L2": "L/min",
    "GRM": "g",
    "KGM": "kg",
    "NEU": "N",
    "NU": "N*m",
    "DD": "deg",
    "C81": "rad",
    "LUX": "lux",
    "OHM": "ohm",
}


def common_code(unit_id: int) -> str:
    """The UNECE common code packed into a UnitId, or an empty string."""
    if unit_id <= 0 or unit_id >= 1 << 24:
        return ""
    raw = unit_id.to_bytes(3, "big").lstrip(b"\x00")
    try:
        text = raw.decode("ascii")
    except UnicodeDecodeError:
        return ""
    return text if text.isalnum() else ""


def code_id(code: str) -> int:
    """Pack a UNECE common code into a UnitId, the inverse of common_code."""
    return int.from_bytes(code.encode("ascii"), "big")


def from_eu(information: Any) -> str | None:
    """An EUInformation as an OpenHAL unit name, or None when the registry has no such unit."""
    unit_id = getattr(information, "UnitId", None)
    if isinstance(unit_id, int):
        found = UNECE.get(common_code(unit_id))
        if found:
            return found
    display = getattr(getattr(information, "DisplayName", None), "Text", None)
    return device_unit(display)
