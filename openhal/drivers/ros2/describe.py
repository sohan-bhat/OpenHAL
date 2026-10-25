"""What describe() proposes for a ROS 2 graph, from rosapi's topic, service and action lists.

Only rosapi services that read the graph are called. Topics with well known message types become
channels, Twist topics become velocity commands with small suggested limits, Trigger and SetBool
services become actions, and everything else is listed in the notes to map by hand.
"""

from __future__ import annotations

import contextlib
import re
from typing import Any

from openhal.drivers.base import DriverError
from openhal.drivers.ros2.bridge import Rosbridge

READ_FIELDS: dict[str, list[tuple[str, str, dict[str, Any]]]] = {
    "sensor_msgs/msg/BatteryState": [
        ("percentage", "percentage", {"unit": "percent", "map": {"unit": "dimensionless"}}),
        ("voltage", "voltage", {"unit": "V"}),
    ],
    "sensor_msgs/msg/Temperature": [("temperature", "temperature", {"unit": "degC"})],
    "sensor_msgs/msg/RelativeHumidity": [
        ("humidity", "relative_humidity", {"unit": "percent", "map": {"unit": "dimensionless"}})
    ],
    "sensor_msgs/msg/Range": [("range", "range", {"unit": "m"})],
    "nav_msgs/msg/Odometry": [
        ("x", "pose.pose.position.x", {"unit": "m"}),
        ("y", "pose.pose.position.y", {"unit": "m"}),
        ("speed", "twist.twist.linear.x", {"unit": "m/s"}),
    ],
    "std_msgs/msg/Bool": [("", "data", {"type": "bool"})],
    "std_msgs/msg/String": [("", "data", {"type": "string"})],
    **{
        f"std_msgs/msg/{kind}": [("", "data", {"unit": "dimensionless"})]
        for kind in ("Float32", "Float64", "Int32", "Int64", "UInt8", "UInt16")
    },
}
SKIP = re.compile(
    r"^/(rosapi|rosbridge|rosout|parameter_events)|/(describe|get|list|set)_parameters(_atomically)?$|/get_parameter_types$|/get_type_description$"
)


def _name(*parts: str) -> str:
    text = "_".join(part for part in parts if part)
    text = re.sub(r"[^a-z0-9_]+", "_", text.lower()).strip("_")
    text = re.sub(r"_+", "_", text)
    if not text or not text[0].isalpha():
        text = f"ros_{text}"
    return text[:48].rstrip("_")


async def _list(bridge: Rosbridge, service: str, key: str) -> list[Any]:
    with contextlib.suppress(DriverError, TimeoutError):
        values = await bridge.call(service)
        found = values.get(key, [])
        return found if isinstance(found, list) else []
    return []


async def proposal(bridge: Rosbridge) -> dict[str, Any]:
    topics = await _list(bridge, "/rosapi/topics", "topics")
    types = await _list(bridge, "/rosapi/topics", "types")
    if not topics:
        raise DriverError(
            "rosapi didn't list any topics. Launch rosbridge with rosapi, which the default launch file does."
        )
    services = await _list(bridge, "/rosapi/services", "services")
    servers = await _list(bridge, "/rosapi/action_servers", "action_servers")
    read: dict[str, Any] = {}
    write: dict[str, Any] = {}
    actions: dict[str, Any] = {}
    safe: dict[str, Any] = {}
    others: list[str] = []
    for topic, kind in zip(topics, types, strict=False):
        if not isinstance(topic, str) or SKIP.search(topic):
            continue
        if kind == "geometry_msgs/msg/Twist":
            for axis, field, unit, top in (("linear", "linear.x", "m/s", 0.2), ("angular", "angular.z", "rad/s", 0.5)):
                name = _name(topic, axis)
                write[name] = {
                    "unit": unit,
                    "min": -top,
                    "max": top,
                    "max_change_per_s": top * 2,
                    "confirm": "confirm-each-time",
                    "suggested": True,
                    "map": {"topic": topic, "type": kind, "field": field, "unit": unit},
                }
                safe[name] = 0
            continue
        fields = READ_FIELDS.get(str(kind))
        if fields is None:
            others.append(topic)
            continue
        for short, field, entry in fields:
            spec = {key: value for key, value in entry.items() if key != "map"}
            extra = entry.get("map", {})
            read[_name(topic, short)] = {**spec, "map": {"topic": topic, "type": kind, "field": field, **extra}}
    for service in services:
        if not isinstance(service, str) or SKIP.search(service):
            continue
        with contextlib.suppress(DriverError, TimeoutError):
            kind = (await bridge.call("/rosapi/service_type", {"service": service})).get("type")
            if kind == "std_srvs/srv/Trigger":
                actions[_name(service)] = {
                    "confirm": "confirm-each-time",
                    "suggested": True,
                    "map": {"service": service, "type": kind},
                }
                continue
            if kind == "std_srvs/srv/SetBool":
                actions[_name(service)] = {
                    "args": {"data": {"type": "bool"}},
                    "confirm": "confirm-each-time",
                    "suggested": True,
                    "map": {"service": service, "type": kind, "args": {"data": "data"}},
                }
                continue
        others.append(service)
    others += [server for server in servers if isinstance(server, str)]
    notes = "Proposed from rosapi. Every limit is a suggestion. Velocity limits start small on purpose."
    if others:
        notes += f" Map these by hand if you need them, {', '.join(sorted(others)[:40])}."
    proposal: dict[str, Any] = {
        "device": {"name": "ROS 2 robot"},
        "read": read,
        "write": write,
        "actions": actions,
        "notes": notes[:4000],
    }
    if safe:
        proposal["safe_state"] = [safe]
    return proposal
