"""How seabreeze device file channels and actions map onto a spectrum.

Every reading comes from one scan, the wavelengths and the counts of each pixel, so a map names
what to take from the scan. Channel names cover the usual cases without a map.

    { spectrum: plot }              the spectrum as a PNG chart, `spectrum` by name
    { peak: wavelength }            the wavelength of the highest pixel, `peak_wavelength` by name
    { peak: intensity }             the highest pixel's counts, `peak_intensity` by name
    { wavelength: 532 nm }          the counts at one wavelength, averaged over 5 pixels
    { band: [500 nm, 550 nm] }      the mean counts over a band
    { absorbance: 532 nm }          -log10 of the sample over the reference, both less the dark
    { transmittance: 532 nm }       the sample over the reference in percent, both less the dark
    { status: saturated }           true when any pixel reaches the detector's maximum
    { setting: integration_time }   the integration time, `integration_time` by name

Actions are `store_dark`, `store_reference` and `clear_references`. Absorbance and
transmittance need a stored dark and a stored reference.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, ValidationError, field_validator, model_validator

from openhal.drivers.base import DriverError
from openhal.spec.models import DeviceFile
from openhal.spec.units import Quantity, UnitError, convert, parse_quantity, parse_unit


def nanometres(value: Any) -> float:
    """A wavelength written as 532 nm or 0.532 um, or a bare number in nm."""
    if isinstance(value, int | float) and not isinstance(value, bool):
        return float(value)
    try:
        return convert(parse_quantity(value), "nm")
    except UnitError as exc:
        raise ValueError(f"a wavelength needs a length such as 532 nm ({exc}).") from None


class ReadMap(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    spectrum: Literal["plot"] | None = None
    peak: Literal["wavelength", "intensity"] | None = None
    wavelength: float | None = None
    band: tuple[float, float] | None = None
    absorbance: float | None = None
    transmittance: float | None = None
    status: Literal["saturated"] | None = None
    setting: Literal["integration_time"] | None = None

    @field_validator("wavelength", "absorbance", "transmittance", mode="before")
    @classmethod
    def _nm(cls, value: Any) -> Any:
        return None if value is None else nanometres(value)

    @field_validator("band", mode="before")
    @classmethod
    def _band(cls, value: Any) -> Any:
        if not isinstance(value, list | tuple) or len(value) != 2:
            raise ValueError("a band is two wavelengths, such as [500 nm, 550 nm].")
        low, high = (nanometres(item) for item in value)
        if low >= high:
            raise ValueError("a band is written low then high.")
        return (low, high)

    @model_validator(mode="after")
    def _one(self) -> ReadMap:
        fields = ("spectrum", "peak", "wavelength", "band", "absorbance", "transmittance", "status", "setting")
        if sum(getattr(self, name) is not None for name in fields) != 1:
            raise ValueError(f"give exactly one of {', '.join(fields)}.")
        return self

    @property
    def kind(self) -> str:
        fields = ("spectrum", "peak", "wavelength", "band", "absorbance", "transmittance", "status", "setting")
        return next(name for name in fields if getattr(self, name) is not None)


class ActionMap(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    command: Literal["store_dark", "store_reference", "clear_references"]


READ_DEFAULTS: dict[str, dict[str, Any]] = {
    "spectrum": {"spectrum": "plot"},
    "peak_wavelength": {"peak": "wavelength"},
    "peak_intensity": {"peak": "intensity"},
    "saturated": {"status": "saturated"},
    "integration_time": {"setting": "integration_time"},
}
WANTED: dict[str, tuple[str, str | None]] = {
    "spectrum": ("image", None),
    "peak:wavelength": ("number", "nm"),
    "peak:intensity": ("number", "dimensionless"),
    "wavelength": ("number", "dimensionless"),
    "band": ("number", "dimensionless"),
    "absorbance": ("number", "dimensionless"),
    "transmittance": ("number", "percent"),
    "status": ("bool", None),
    "setting": ("number", "us"),
}


def validate(model: type[BaseModel], raw: dict[str, Any] | None, default: dict[str, Any] | None, where: str) -> Any:
    data = raw if raw is not None else default
    if data is None:
        raise DriverError(f"{where} needs a map, see docs/drivers/seabreeze.md.")
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        problems = "; ".join(f"{'.'.join(str(p) for p in e['loc']) or 'map'}: {e['msg']}" for e in exc.errors())
        raise DriverError(f"{where}.map is not valid for the seabreeze driver ({problems}).") from exc


def native_unit(read_map: ReadMap) -> str | None:
    key = f"peak:{read_map.peak}" if read_map.kind == "peak" else read_map.kind
    return WANTED[key][1]


def check(where: str, kind: str, unit: str | None, read_map: ReadMap) -> None:
    key = f"peak:{read_map.peak}" if read_map.kind == "peak" else read_map.kind
    wanted, native = WANTED[key]
    if kind != wanted:
        raise DriverError(f"{where}: {key.replace(':', ' ')} is {'an' if wanted == 'image' else 'a'} {wanted}.")
    if native is not None:
        try:
            convert(Quantity(1.0, parse_unit(unit or "")), native)
        except UnitError:
            raise DriverError(f"{where} needs a unit that converts to {native}, not {unit!r}.") from None


def build(device: DeviceFile) -> tuple[dict[str, ReadMap], dict[str, ReadMap], dict[str, ActionMap]]:
    reads: dict[str, ReadMap] = {}
    writes: dict[str, ReadMap] = {}
    actions: dict[str, ActionMap] = {}
    for name, spec in device.read.items():
        read_map = validate(ReadMap, spec.map, READ_DEFAULTS.get(name), f"read.{name}")
        check(f"read.{name}", spec.type, spec.unit, read_map)
        reads[name] = read_map
    for name, write_spec in device.write.items():
        write_map = validate(ReadMap, write_spec.map, READ_DEFAULTS.get(name), f"write.{name}")
        if write_map.kind != "setting":
            raise DriverError(f"write.{name}: only the integration time can be set. Read the rest.")
        check(f"write.{name}", write_spec.type, write_spec.unit, write_map)
        writes[name] = write_map
    for name, action in device.actions.items():
        default = {"command": name} if name in ("store_dark", "store_reference", "clear_references") else None
        actions[name] = validate(ActionMap, action.map, default, f"actions.{name}")
        if action.args:
            raise DriverError(f"actions.{name}: {actions[name].command} takes no arguments.")
    return reads, writes, actions
