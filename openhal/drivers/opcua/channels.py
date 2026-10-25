"""How device file channels and actions map onto OPC UA nodes.

    read    { node: "ns=2;s=Pump.Speed" }
            { node: "nsu=urn:example:pump;s=Pump.Speed", unit: rpm }
    write   { node: "ns=2;s=Pump.Setpoint" }
    action  { object: "ns=2;s=Pump", method: "ns=2;s=Pump.Start", inputs: [rate] }

Node ids use the OPC UA string form. `nsu=<namespace uri>` is resolved to a namespace index
when the driver connects, so files keep working when a server renumbers its namespaces.
`unit` overrides the node's EngineeringUnits and `scale` multiplies the OPC UA value into it.
`inputs` lists the action's arguments in the order the method takes them.
"""

from __future__ import annotations

import re
from typing import Any, Final

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from openhal.drivers.base import DriverError

NODE: Final = re.compile(
    r"^(ns=\d{1,5};|nsu=[^;]{1,256};)?(i=\d{1,10}|s=.{1,256}|g=[0-9a-fA-F-]{36}|b=[A-Za-z0-9+/=]{1,256})$"
)


def _node(value: str) -> str:
    if not NODE.match(value):
        raise ValueError(f"{value!r} is not an OPC UA node id such as ns=2;s=Pump.Speed or i=2258")
    return value


class _Map(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ReadMap(_Map):
    node: str
    unit: str | None = None
    scale: float = 1.0

    @field_validator("node")
    @classmethod
    def _node_id(cls, value: str) -> str:
        return _node(value)


class WriteMap(ReadMap):
    pass


class ActionMap(_Map):
    object: str
    method: str
    inputs: list[str] = Field(default=[], max_length=32)

    @field_validator("object", "method")
    @classmethod
    def _nodes(cls, value: str) -> str:
        return _node(value)


def validate(model: type[BaseModel], raw: dict[str, Any] | None, where: str) -> Any:
    if raw is None:
        raise DriverError(f"{where} needs a map with the OPC UA node id. See docs/drivers/opcua.md.")
    try:
        return model.model_validate(raw)
    except ValidationError as exc:
        problems = "; ".join(f"{'.'.join(str(p) for p in e['loc']) or 'map'}: {e['msg']}" for e in exc.errors())
        raise DriverError(f"{where}.map is not valid for the OPC UA driver ({problems}).") from exc


def resolve(node: str, namespaces: list[str]) -> str:
    """Turn `nsu=<uri>;...` into `ns=<index>;...` with the server's namespace array."""
    if not node.startswith("nsu="):
        return node
    uri, _, rest = node[4:].partition(";")
    if uri not in namespaces:
        raise DriverError(f"The server has no namespace {uri!r}. It has {', '.join(namespaces)}.")
    return f"ns={namespaces.index(uri)};{rest}"
