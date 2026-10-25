"""What describe() proposes for an OPC UA server, by browsing its Objects folder.

Variables become read channels with their engineering units and EURange. Writable numeric
variables become write channels with the EURange as suggested limits, or 0 to 0 when the server
gives no range, so nothing moves until a person sets real limits. Methods become actions with
their input arguments. The Server object and anything in namespace 0 are skipped. At most 200
nodes are proposed.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from openhal.drivers.opcua.driver import OpcuaDriver

LIMIT = 200
NUMBERS = {"SByte", "Byte", "Int16", "UInt16", "Int32", "UInt32", "Int64", "UInt64", "Float", "Double"}
TYPES = {1: "bool", 12: "string", **dict.fromkeys(range(2, 12), "number")}


def _name(path: list[str], taken: set[str]) -> str:
    text = re.sub(r"[^a-z0-9_]+", "_", "_".join(path).lower()).strip("_") or "node"
    if not text[0].isalpha():
        text = f"n_{text}"
    text = text[:44]
    candidate, counter = text, 2
    while candidate in taken:
        candidate, counter = f"{text}_{counter}", counter + 1
    taken.add(candidate)
    return candidate


async def proposal(driver: OpcuaDriver, client: Any, depth: int) -> dict[str, Any]:
    from asyncua import ua

    read: dict[str, Any] = {}
    write: dict[str, Any] = {}
    actions: dict[str, Any] = {}
    taken: set[str] = set()
    count = 0

    async def visit(node: Any, path: list[str], level: int) -> None:
        nonlocal count
        if count >= LIMIT or level > depth:
            return
        for child in await driver.request(node.get_children(), "browsing"):
            if count >= LIMIT:
                return
            if child.nodeid.NamespaceIndex == 0:
                continue
            browse = await driver.request(child.read_browse_name(), "browsing")
            node_class = await driver.request(child.read_node_class(), "browsing")
            here = [*path, browse.Name]
            node_id = child.nodeid.to_string()
            if node_class == ua.NodeClass.Variable:
                count += 1
                await _variable(driver, child, node_id, _name(here, taken), read, write)
            elif node_class == ua.NodeClass.Method:
                count += 1
                actions[_name(here, taken)] = await _method(driver, child, node.nodeid.to_string(), node_id)
            elif node_class == ua.NodeClass.Object:
                await visit(child, here, level + 1)

    await visit(client.nodes.objects, [], 1)
    return {
        "device": {"name": driver.settings.endpoint.split("//", 1)[-1].split("/", 1)[0]},
        "read": read,
        "write": write,
        "actions": actions,
        "notes": "Proposed by browsing the Objects folder. Limits come from EURange where the server has one, "
        "and are 0 to 0 otherwise, so set them before confirming.",
    }


async def _variable(
    driver: OpcuaDriver, node: Any, node_id: str, name: str, read: dict[str, Any], write: dict[str, Any]
) -> None:
    from asyncua import ua

    kind = await driver.request(node.read_data_type_as_variant_type(), "browsing")
    channel_type = TYPES.get(int(kind.value), "string") if kind is not None else "string"
    unit, span = await driver.properties(node, node_id, strict=False)
    entry: dict[str, Any] = {"map": {"node": node_id}}
    if channel_type == "number":
        entry["unit"] = unit or "dimensionless"
        if span:
            entry["range"] = list(span)
    elif channel_type != "number":
        entry["type"] = channel_type
    if channel_type == "string":
        entry["max_length"] = 256
    access = await driver.request(node.get_user_access_level(), "browsing")
    if ua.AccessLevel.CurrentWrite in access and kind is not None:
        changed = {key: value for key, value in entry.items() if key != "range"}
        if channel_type == "number":
            low, high = span or (0.0, 0.0)
            changed.update({"min": low, "max": high})
        write[name] = {**changed, "suggested": True}
        return
    entry.pop("max_length", None)
    read[name] = entry


async def _method(driver: OpcuaDriver, node: Any, parent: str, node_id: str) -> dict[str, Any]:
    args: dict[str, Any] = {}
    inputs: list[str] = []
    for prop in await driver.request(node.get_properties(), "browsing"):
        if (await driver.request(prop.read_browse_name(), "browsing")).Name != "InputArguments":
            continue
        for index, argument in enumerate(await driver.request(prop.read_value(), "browsing") or []):
            arg = re.sub(r"[^a-z0-9_]+", "_", str(getattr(argument, "Name", "") or f"arg{index}").lower()).strip("_")
            arg = arg if arg and arg[0].isalpha() else f"arg{index}"
            identifier = getattr(getattr(argument, "DataType", None), "Identifier", 0)
            kind = TYPES.get(identifier, "string") if isinstance(identifier, int) else "string"
            spec: dict[str, Any] = {"type": kind}
            if kind == "number":
                spec = {"unit": "dimensionless", "min": 0, "max": 0}
            elif kind == "string":
                spec["max_length"] = 256
            args[arg] = spec
            inputs.append(arg)
    action: dict[str, Any] = {
        "confirm": "confirm-each-time",
        "suggested": True,
        "map": {"object": parent, "method": node_id, "inputs": inputs},
    }
    if args:
        action["args"] = args
    return action
