"""A simulated Matter Server, a WebSocket server that speaks the python-matter-server message format.

It sends the server info object on connect and answers `start_listening`, `get_nodes`, `get_node`,
`server_info`, `read_attribute`, `write_attribute` and `device_command`. Nodes follow the Matter
data model with decimal `endpoint/cluster/attribute` paths.

- Node 5, a dimmable bulb. Endpoint 1 has OnOff (6) with the On, Off and Toggle commands,
  LevelControl (8) with MoveToLevel and MoveToLevelWithOnOff, and Identify (3) with Identify.
- Node 6, a weather sensor. Endpoint 1 has TemperatureMeasurement (1026) in 0.01 degC,
  RelativeHumidityMeasurement (1029) in 0.01 percent and PowerSource (47) with the battery in half
  percent. It is battery powered, so nothing on it can be set.
- Node 7, a thermostat. Endpoint 1 has Thermostat (513) with a writable OccupiedHeatingSetpoint (18)
  limited to 700 to 3000.

Every change pushes `attribute_updated`. Faults. `unavailable(node)` pushes `node_updated` with
`available: false`, `fail_next` answers the next command with error code 7, `latency_s` slows
answers, and `drop()` closes every connection.
"""

from __future__ import annotations

import asyncio
import contextlib
import copy
import json
from typing import Any

BASIC = {"0/40/0": 17, "0/40/2": 4447, "0/40/4": 1, "0/40/65533": 2}


def matter_nodes() -> dict[int, dict[str, Any]]:
    """Three nodes as the Matter Server reports them."""
    bulb = {
        **BASIC,
        "0/40/1": "Nanoleaf",
        "0/40/3": "Essentials A19",
        "0/40/10": "3.5.10",
        "0/40/15": "NL67A1B2C3",
        "1/3/0": 0,
        "1/6/0": False,
        "1/6/65533": 5,
        "1/8/0": 127,
        "1/8/2": 1,
        "1/8/3": 254,
        "1/8/65533": 5,
    }
    sensor = {
        **BASIC,
        "0/40/1": "Eve Systems",
        "0/40/3": "Eve Weather",
        "0/40/10": "2.1.1",
        "1/1026/0": 2154,
        "1/1026/1": -4000,
        "1/1026/2": 8500,
        "1/1029/0": 4820,
        "1/47/12": 182,
    }
    thermostat = {
        **BASIC,
        "0/40/1": "Ecobee",
        "0/40/3": "Smart Thermostat Premium",
        "1/513/0": 2050,
        "1/513/18": 2000,
        "1/513/21": 700,
        "1/513/22": 3000,
    }
    nodes: dict[int, dict[str, Any]] = {}
    for node_id, attributes in ((5, bulb), (6, sensor), (7, thermostat)):
        nodes[node_id] = {
            "node_id": node_id,
            "date_commissioned": "2026-09-30T18:02:11.000000",
            "last_interview": "2026-10-24T08:15:40.000000",
            "interview_version": 6,
            "available": True,
            "is_bridge": False,
            "attributes": attributes,
            "attribute_subscriptions": [],
        }
    return nodes


class MatterServerSim:
    """A Matter Server on 127.0.0.1. Start with `await start()`, stop with `await close()`."""

    def __init__(self, *, schema: int = 11) -> None:
        self.schema = schema
        self.nodes = matter_nodes()
        self.calls: list[dict[str, Any]] = []
        self.port = 0
        self.fail_next = 0
        self.latency_s = 0.0
        self._server: Any = None
        self._listeners: set[Any] = set()
        self._connections: set[Any] = set()

    @property
    def url(self) -> str:
        return f"ws://127.0.0.1:{self.port}/ws"

    async def start(self) -> MatterServerSim:
        from websockets.asyncio.server import serve

        self._server = await serve(self._session, "127.0.0.1", 0)
        self.port = int(next(iter(self._server.sockets)).getsockname()[1])
        return self

    async def close(self) -> None:
        await self.drop()
        if self._server is not None:
            self._server.close()
            with contextlib.suppress(Exception):
                await self._server.wait_closed()
            self._server = None

    async def drop(self) -> None:
        for connection in list(self._connections):
            with contextlib.suppress(Exception):
                await connection.close()

    async def set_attribute(self, node: int, path: str, value: Any) -> None:
        """Change an attribute and push `attribute_updated`, as a report from the device would."""
        self.nodes[node]["attributes"][path] = value
        await self._event("attribute_updated", [node, path, value])

    async def unavailable(self, node: int) -> None:
        self.nodes[node]["available"] = False
        await self._event("node_updated", copy.deepcopy(self.nodes[node]))

    async def available(self, node: int) -> None:
        self.nodes[node]["available"] = True
        await self._event("node_updated", copy.deepcopy(self.nodes[node]))

    async def _event(self, event: str, data: Any) -> None:
        for connection in list(self._listeners):
            with contextlib.suppress(Exception):
                await connection.send(json.dumps({"event": event, "data": data}))

    async def _session(self, connection: Any) -> None:
        self._connections.add(connection)
        info = {
            "fabric_id": 1,
            "compressed_fabric_id": 1234567890,
            "schema_version": self.schema,
            "min_supported_schema_version": 1,
            "sdk_version": "2025.7.0",
            "wifi_credentials_set": False,
            "thread_credentials_set": True,
            "bluetooth_enabled": False,
        }
        try:
            await connection.send(json.dumps(info))
            async for raw in connection:
                await self._command(connection, raw)
        except Exception:  # noqa: BLE001, S110
            pass
        finally:
            self._connections.discard(connection)
            self._listeners.discard(connection)

    async def _answer(
        self, connection: Any, ident: Any, result: Any = None, *, error: int | None = None, details: str = ""
    ) -> None:
        if error is None:
            await connection.send(json.dumps({"message_id": ident, "result": result}))
        else:
            await connection.send(json.dumps({"message_id": ident, "error_code": error, "details": details}))

    async def _command(self, connection: Any, raw: str | bytes) -> None:
        if self.latency_s:
            await asyncio.sleep(self.latency_s)
        message = json.loads(raw)
        self.calls.append(message)
        ident, command, args = message.get("message_id"), message.get("command"), message.get("args") or {}
        if self.fail_next:
            self.fail_next -= 1
            await self._answer(connection, ident, error=7, details="Chip Stack Error: timeout waiting for response")
            return
        node = self.nodes.get(int(args["node_id"])) if isinstance(args.get("node_id"), int) else None
        if "node_id" in args and node is None:
            await self._answer(connection, ident, error=5, details=f"Node {args.get('node_id')} does not exist")
            return
        if command == "start_listening":
            self._listeners.add(connection)
            await self._answer(connection, ident, copy.deepcopy(list(self.nodes.values())))
        elif command == "get_nodes":
            await self._answer(connection, ident, copy.deepcopy(list(self.nodes.values())))
        elif command == "get_node" and node is not None:
            await self._answer(connection, ident, copy.deepcopy(node))
        elif command == "server_info":
            await self._answer(connection, ident, {"schema_version": self.schema})
        elif command == "read_attribute" and node is not None:
            path = args.get("attribute_path")
            await self._answer(connection, ident, {path: node["attributes"].get(path)})
        elif command == "write_attribute" and node is not None:
            await self._write_attribute(connection, ident, args, node)
        elif command == "device_command" and node is not None:
            await self._device_command(connection, ident, args, node)
        else:
            await self._answer(connection, ident, error=9, details=f"Invalid command: {command}")

    async def _write_attribute(self, connection: Any, ident: Any, args: dict[str, Any], node: dict[str, Any]) -> None:
        path, value = str(args.get("attribute_path")), args.get("value")
        endpoint, cluster, attribute = (int(part) for part in path.split("/"))
        status = 0
        if path not in node["attributes"]:
            status = 0x86
        elif path != "1/513/18":
            status = 0x88
        elif not isinstance(value, int) or not 700 <= value <= 3000:
            status = 0x87
        result = [{"Path": {"EndpointId": endpoint, "ClusterId": cluster, "AttributeId": attribute}, "Status": status}]
        await self._answer(connection, ident, result)
        if status == 0:
            await self.set_attribute(node["node_id"], path, value)

    async def _device_command(self, connection: Any, ident: Any, args: dict[str, Any], node: dict[str, Any]) -> None:
        endpoint, cluster = args.get("endpoint_id"), args.get("cluster_id")
        name, payload = args.get("command_name"), args.get("payload") or {}
        attributes = node["attributes"]
        if f"{endpoint}/{cluster}/65533" not in attributes and not any(
            key.startswith(f"{endpoint}/{cluster}/") for key in attributes
        ):
            await self._answer(connection, ident, error=8, details=f"Cluster {cluster} not on endpoint {endpoint}")
            return
        changes: dict[str, Any] = {}
        if cluster == 6 and name in ("On", "Off", "Toggle"):
            current = attributes[f"{endpoint}/6/0"]
            changes[f"{endpoint}/6/0"] = {"On": True, "Off": False, "Toggle": not current}[name]
        elif cluster == 8 and name in ("MoveToLevel", "MoveToLevelWithOnOff"):
            level = payload.get("level")
            if not isinstance(level, int) or not 0 <= level <= 254:
                await self._answer(connection, ident, error=8, details="level must be 0 to 254")
                return
            changes[f"{endpoint}/8/0"] = level
            if name == "MoveToLevelWithOnOff":
                changes[f"{endpoint}/6/0"] = level > 0
        elif cluster == 3 and name == "Identify":
            changes[f"{endpoint}/3/0"] = int(payload.get("identifyTime", 0))
        else:
            await self._answer(connection, ident, error=9, details=f"Unsupported command {name}")
            return
        await self._answer(connection, ident, None)
        for path, value in changes.items():
            await self.set_attribute(node["node_id"], path, value)
