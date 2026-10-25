"""How device file channels and actions map onto SiLA 2 features, and SiLA data types.

    read    { feature: TemperatureController, property: CurrentTemperature }
            { feature: TemperatureController, property: Status, field: Lid.Closed }
    write   { feature: TemperatureController, command: SetTargetTemperature, parameter: TargetTemperature,
              readback: TargetTemperature }
    action  { feature: Shaker, command: Shake, parameters: { speed: Speed, seconds: Duration }, base: { Mode: Gentle } }

SiLA properties are read only, so a channel changes through a command with one parameter and is
read back from a property. `feature` is the feature identifier or its fully qualified form.
`unit` overrides the SiLA Unit constraint, and `scale` multiplies the SiLA value into it.
"""

from __future__ import annotations

from typing import Any, Final

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from openhal.drivers.base import DriverError

IDENT: Final = r"^[A-Z][A-Za-z0-9]{0,254}$"
FEATURE: Final = r"^([a-z][a-z0-9.]*/[a-z][a-z0-9.]*/)?[A-Z][A-Za-z0-9]{0,254}(/v\d+)?$"


class _Map(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    feature: str = Field(pattern=FEATURE)


class ReadMap(_Map):
    property: str = Field(pattern=IDENT)
    field: str | None = Field(default=None, pattern=r"^[A-Za-z0-9]+(\.[A-Za-z0-9]+){0,7}$")
    unit: str | None = None
    scale: float = 1.0


class WriteMap(_Map):
    command: str = Field(pattern=IDENT)
    parameter: str = Field(pattern=IDENT)
    readback: str | None = Field(default=None, pattern=IDENT)
    base: dict[str, Any] = {}
    unit: str | None = None
    scale: float = 1.0


class ActionMap(_Map):
    command: str = Field(pattern=IDENT)
    parameters: dict[str, str] = {}
    base: dict[str, Any] = {}


def validate(model: type[BaseModel], raw: dict[str, Any] | None, where: str) -> Any:
    if raw is None:
        raise DriverError(
            f"{where} needs a map with its SiLA feature and property or command. See docs/drivers/sila2.md."
        )
    try:
        return model.model_validate(raw)
    except ValidationError as exc:
        problems = "; ".join(f"{'.'.join(str(p) for p in e['loc']) or 'map'}: {e['msg']}" for e in exc.errors())
        raise DriverError(f"{where}.map is not valid for the SiLA 2 driver ({problems}).") from exc


def type_info(data_type: Any) -> tuple[str, str | None, tuple[float | None, float | None]]:
    """The basic type name, the Unit constraint's label and any min and max constraints."""
    from sila2.framework.constraints.maximal_inclusive import MaximalInclusive
    from sila2.framework.constraints.minimal_inclusive import MinimalInclusive
    from sila2.framework.constraints.unit import Unit
    from sila2.framework.data_types.constrained import Constrained

    label: str | None = None
    low: float | None = None
    high: float | None = None
    current = data_type
    while isinstance(current, Constrained):
        for constraint in current.constraints:
            if isinstance(constraint, Unit):
                label = str(constraint.label)
            elif isinstance(constraint, MinimalInclusive) and isinstance(constraint.reference_value, int | float):
                low = float(constraint.reference_value)
            elif isinstance(constraint, MaximalInclusive) and isinstance(constraint.reference_value, int | float):
                high = float(constraint.reference_value)
        current = current.base_type
    return type(current).__name__, label, (low, high)


def get_field(value: Any, path: str | None) -> Any:
    """Follow a dotted path into a SiLA structure, which the client returns as named tuples."""
    if path is None:
        return value
    current = value
    for part in path.split("."):
        if not hasattr(current, part):
            raise KeyError(path)
        current = getattr(current, part)
    return current
