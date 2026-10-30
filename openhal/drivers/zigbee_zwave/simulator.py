"""Simulated Zigbee2MQTT and zwave-js-server bridges, for tests and the conformance case.

`Zigbee2MqttSim` lives on the mqtt driver's in-process broker. It publishes the retained
`bridge/devices` list with real `exposes` for an IKEA TRADFRI bulb (`desk_lamp`) and an Aqara
temperature sensor (`hall_sensor`), `bridge/state` and per-device availability, and replies to
`<name>/set` and `<name>/get` the way Zigbee2MQTT does, by publishing the device's state.

`ZWaveJsSim` is a WebSocket server that implements the zwave-js-server API. It sends the version
message, replies to `set_api_schema`, `initialize`, `start_listening`, `node.set_value` and
`node.poll_value`, and pushes `value updated`, `dead` and `alive` events. It holds a Zooz ZEN04
plug (node 2), a Zooz ZEN72 dimmer (node 3) and an Aeotec MultiSensor 7 (node 4).

Faults. Zigbee `offline(name)`, `bridge_offline()` and `silent` (ignores commands), and the broker's
`kick_all()`. Z-Wave `kill(node)`, `revive(node)`, `fail_next` (a set_value status of 2),
`refuse_next` (an error result), `latency_s` and `drop()`.
"""

from __future__ import annotations

import asyncio
import contextlib
import copy
import json
from dataclasses import dataclass, field
from typing import Any

from openhal.drivers.mqtt.simulator import MqttBroker

LAMP_EXPOSES: list[dict[str, Any]] = [
    {
        "type": "light",
        "features": [
            {
                "type": "binary",
                "name": "state",
                "property": "state",
                "access": 7,
                "value_on": "ON",
                "value_off": "OFF",
                "value_toggle": "TOGGLE",
            },
            {
                "type": "numeric",
                "name": "brightness",
                "property": "brightness",
                "access": 7,
                "value_min": 0,
                "value_max": 254,
            },
            {
                "type": "numeric",
                "name": "color_temp",
                "property": "color_temp",
                "access": 7,
                "unit": "mired",
                "value_min": 250,
                "value_max": 454,
            },
        ],
    },
    {
        "type": "enum",
        "name": "power_on_behavior",
        "property": "power_on_behavior",
        "access": 7,
        "values": ["off", "on", "toggle", "previous"],
    },
    {
        "type": "numeric",
        "name": "linkquality",
        "property": "linkquality",
        "access": 1,
        "unit": "lqi",
        "value_min": 0,
        "value_max": 255,
    },
]
SENSOR_EXPOSES: list[dict[str, Any]] = [
    {"type": "numeric", "name": "temperature", "property": "temperature", "access": 1, "unit": "°C"},
    {"type": "numeric", "name": "humidity", "property": "humidity", "access": 1, "unit": "%"},
    {"type": "numeric", "name": "pressure", "property": "pressure", "access": 1, "unit": "hPa"},
    {
        "type": "numeric",
        "name": "battery",
        "property": "battery",
        "access": 1,
        "unit": "%",
        "value_min": 0,
        "value_max": 100,
    },
]


def zigbee_devices() -> list[dict[str, Any]]:
    """A Zigbee2MQTT `bridge/devices` payload with a coordinator, a bulb and a sensor."""
    return [
        {
            "ieee_address": "0x00124b0012345678",
            "type": "Coordinator",
            "friendly_name": "Coordinator",
            "definition": None,
        },
        {
            "ieee_address": "0x000b57fffec6a5b2",
            "type": "Router",
            "friendly_name": "desk_lamp",
            "supported": True,
            "interview_completed": True,
            "power_source": "Mains (single phase)",
            "definition": {
                "model": "LED1545G12",
                "vendor": "IKEA",
                "description": "TRADFRI bulb E26/E27",
                "exposes": LAMP_EXPOSES,
            },
        },
        {
            "ieee_address": "0x00158d0001a2b3c4",
            "type": "EndDevice",
            "friendly_name": "hall_sensor",
            "supported": True,
            "interview_completed": True,
            "power_source": "Battery",
            "definition": {
                "model": "WSDCGQ11LM",
                "vendor": "Aqara",
                "description": "Temperature, humidity and pressure",
                "exposes": SENSOR_EXPOSES,
            },
        },
    ]


@dataclass
class Zigbee2MqttSim:
    """Zigbee2MQTT on the in-process broker. Call `attach()` before connecting a driver."""

    broker: MqttBroker
    base: str = "zigbee2mqtt"
    silent: bool = False
    states: dict[str, dict[str, Any]] = field(
        default_factory=lambda: {
            "desk_lamp": {
                "state": "OFF",
                "brightness": 127,
                "color_temp": 370,
                "power_on_behavior": "previous",
                "linkquality": 120,
            },
            "hall_sensor": {
                "temperature": 21.4,
                "humidity": 48.2,
                "pressure": 1012.6,
                "battery": 91,
                "linkquality": 87,
            },
        }
    )
    commands: list[tuple[str, dict[str, Any]]] = field(default_factory=list)

    def attach(self) -> Zigbee2MqttSim:
        self.broker.publish(f"{self.base}/bridge/devices", json.dumps(zigbee_devices()), retain=True)
        self.broker.publish(f"{self.base}/bridge/state", json.dumps({"state": "online"}), retain=True)
        for name in self.states:
            self.broker.publish(f"{self.base}/{name}/availability", json.dumps({"state": "online"}), retain=True)
            self.broker.on(f"{self.base}/{name}/set", self._set)
            self.broker.on(f"{self.base}/{name}/get", self._get)
        return self

    def report(self, name: str, changes: dict[str, Any] | None = None) -> None:
        """The device reports, as after a sensor's Wake Up notification. Safe to call from any thread."""
        self.states[name].update(changes or {})
        self.broker.publish(f"{self.base}/{name}", json.dumps(self.states[name]))

    def offline(self, name: str) -> None:
        self.broker.publish(f"{self.base}/{name}/availability", json.dumps({"state": "offline"}), retain=True)

    def bridge_offline(self) -> None:
        self.broker.publish(f"{self.base}/bridge/state", json.dumps({"state": "offline"}), retain=True)

    def _name(self, topic: str) -> str:
        return topic[len(self.base) + 1 :].rsplit("/", 1)[0]

    def _set(self, broker: MqttBroker, topic: str, payload: bytes) -> None:
        name = self._name(topic)
        try:
            document = json.loads(payload)
        except ValueError:
            return
        if not isinstance(document, dict):
            return
        self.commands.append((name, copy.deepcopy(document)))
        if self.silent:
            return
        state = self.states[name]
        for key, value in document.items():
            if key == "state" and value == "TOGGLE":
                state["state"] = "OFF" if state.get("state") == "ON" else "ON"
            elif key in state:
                state[key] = value
        if "brightness" in document and document["brightness"] > 0:
            state["state"] = "ON"
        broker.route(f"{self.base}/{name}", json.dumps(state).encode(), False)

    def _get(self, broker: MqttBroker, topic: str, payload: bytes) -> None:
        name = self._name(topic)
        if not self.silent:
            broker.route(f"{self.base}/{name}", json.dumps(self.states[name]).encode(), False)


def _value(
    cc: int, name: str, prop: Any, metadata: dict[str, Any], value: Any, key: Any = None, ep: int = 0
) -> dict[str, Any]:
    item = {
        "endpoint": ep,
        "commandClass": cc,
        "commandClassName": name,
        "property": prop,
        "propertyName": prop,
        "metadata": {"readable": True, "writeable": False, **metadata},
        "value": value,
    }
    if key is not None:
        item["propertyKey"] = key
    return item


def zwave_nodes() -> list[dict[str, Any]]:
    """Three nodes in the shape zwave-js-server sends in start_listening."""
    plug = {
        "nodeId": 2,
        "status": 4,
        "ready": True,
        "firmwareVersion": "1.40",
        "deviceConfig": {"manufacturer": "Zooz", "label": "ZEN04", "description": "Smart Plug"},
        "values": [
            _value(37, "Binary Switch", "currentValue", {"type": "boolean", "label": "Current value"}, False),
            _value(
                37,
                "Binary Switch",
                "targetValue",
                {"type": "boolean", "label": "Target value", "writeable": True},
                False,
            ),
            _value(
                50, "Meter", "value", {"type": "number", "label": "Electric Consumption [W]", "unit": "W"}, 0.0, 66049
            ),
            _value(
                50,
                "Meter",
                "value",
                {"type": "number", "label": "Electric Consumption [kWh]", "unit": "kWh"},
                12.75,
                65537,
            ),
        ],
    }
    dimmer = {
        "nodeId": 3,
        "status": 4,
        "ready": True,
        "firmwareVersion": "2.20",
        "deviceConfig": {"manufacturer": "Zooz", "label": "ZEN72", "description": "Dimmer"},
        "values": [
            _value(
                38,
                "Multilevel Switch",
                "currentValue",
                {"type": "number", "label": "Current value", "min": 0, "max": 99},
                0,
            ),
            _value(
                38,
                "Multilevel Switch",
                "targetValue",
                {"type": "number", "label": "Target value", "min": 0, "max": 99, "writeable": True},
                0,
            ),
        ],
    }
    sensor = {
        "nodeId": 4,
        "status": 1,
        "ready": True,
        "firmwareVersion": "1.16",
        "deviceConfig": {"manufacturer": "AEON Labs", "label": "ZWA024", "description": "MultiSensor 7"},
        "values": [
            _value(
                49,
                "Multilevel Sensor",
                "Air temperature",
                {"type": "number", "label": "Air temperature", "unit": "°C"},
                22.1,
            ),
            _value(49, "Multilevel Sensor", "Humidity", {"type": "number", "label": "Humidity", "unit": "%"}, 44.0),
            _value(
                113,
                "Notification",
                "Home Security",
                {"type": "number", "label": "Motion sensor status", "states": {"0": "idle", "8": "Motion detection"}},
                0,
                "Motion sensor status",
            ),
        ],
    }
    return [plug, dimmer, sensor]


class ZWaveJsSim:
    """A zwave-js-server on 127.0.0.1. Start with `await start()`, stop with `await close()`."""

    def __init__(self, *, schema: int = 44, min_schema: int = 0) -> None:
        self.schema = schema
        self.min_schema = min_schema
        self.nodes = {node["nodeId"]: node for node in zwave_nodes()}
        self.calls: list[dict[str, Any]] = []
        self.port = 0
        self.fail_next = 0
        self.refuse_next = 0
        self.latency_s = 0.0
        self.chosen_schema: int | None = None
        self._server: Any = None
        self._listeners: set[Any] = set()
        self._connections: set[Any] = set()

    @property
    def url(self) -> str:
        return f"ws://127.0.0.1:{self.port}"

    async def start(self) -> ZWaveJsSim:
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

    def find(self, node: Any, cc: Any, prop: Any, key: Any = None) -> dict[str, Any]:
        values: list[dict[str, Any]] = self.nodes[node]["values"]
        for item in values:
            if item["commandClass"] == cc and item["property"] == prop and item.get("propertyKey") == key:
                return item
        raise KeyError((node, cc, prop, key))

    async def update(self, node: Any, cc: Any, prop: Any, value: Any, key: Any = None) -> None:
        """Change a value on the node and push `value updated` to listeners."""
        item = self.find(node, cc, prop, key)
        previous, item["value"] = item["value"], value
        args = {
            "commandClass": cc,
            "commandClassName": item["commandClassName"],
            "endpoint": item["endpoint"],
            "property": prop,
            "newValue": value,
            "prevValue": previous,
            "propertyName": prop,
        }
        if key is not None:
            args["propertyKey"] = key
        await self._event({"source": "node", "event": "value updated", "nodeId": node, "args": args})

    async def kill(self, node: int) -> None:
        self.nodes[node]["status"] = 3
        await self._event({"source": "node", "event": "dead", "nodeId": node})

    async def revive(self, node: int) -> None:
        self.nodes[node]["status"] = 4
        await self._event({"source": "node", "event": "alive", "nodeId": node})

    async def _event(self, event: dict[str, Any]) -> None:
        for connection in list(self._listeners):
            with contextlib.suppress(Exception):
                await connection.send(json.dumps({"type": "event", "event": event}))

    async def _session(self, connection: Any) -> None:
        self._connections.add(connection)
        try:
            await connection.send(
                json.dumps(
                    {
                        "type": "version",
                        "driverVersion": "15.10.0",
                        "serverVersion": "3.2.1",
                        "homeId": 3245146787,
                        "minSchemaVersion": self.min_schema,
                        "maxSchemaVersion": self.schema,
                    }
                )
            )
            async for raw in connection:
                await self._command(connection, raw)
        except Exception:  # noqa: BLE001, S110
            pass
        finally:
            self._connections.discard(connection)
            self._listeners.discard(connection)

    async def _result(self, connection: Any, ident: Any, result: Any = None, **error: Any) -> None:
        message: dict[str, Any] = {"type": "result", "messageId": ident}
        if error:
            message.update({"success": False, **error})
        else:
            message.update({"success": True, "result": result if result is not None else {}})
        await connection.send(json.dumps(message))

    async def _command(self, connection: Any, raw: str | bytes) -> None:
        if self.latency_s:
            await asyncio.sleep(self.latency_s)
        message = json.loads(raw)
        self.calls.append(message)
        ident, command = message.get("messageId"), message.get("command")
        if self.refuse_next:
            self.refuse_next -= 1
            await self._result(
                connection,
                ident,
                errorCode="zwave_error",
                zwaveErrorCode=204,
                zwaveErrorMessage="The node did not acknowledge the command",
            )
            return
        if command in ("set_api_schema", "initialize"):
            self.chosen_schema = int(message.get("schemaVersion", 0))
            await self._result(connection, ident)
        elif command == "start_listening":
            self._listeners.add(connection)
            state = {
                "driver": {"logConfig": {}},
                "controller": {"homeId": 3245146787, "ownNodeId": 1},
                "nodes": copy.deepcopy(list(self.nodes.values())),
            }
            await self._result(connection, ident, {"state": state})
        elif command == "node.set_value":
            await self._set_value(connection, ident, message)
        elif command == "node.poll_value":
            value_id = message.get("valueId") or {}
            item = self.find(
                message["nodeId"], value_id.get("commandClass"), value_id.get("property"), value_id.get("propertyKey")
            )
            await self._result(connection, ident, {"value": item["value"]})
        else:
            await self._result(connection, ident, errorCode="unknown_command")

    async def _set_value(self, connection: Any, ident: Any, message: dict[str, Any]) -> None:
        node, value_id, value = message.get("nodeId"), message.get("valueId") or {}, message.get("value")
        if node not in self.nodes:
            await self._result(connection, ident, errorCode="node_not_found")
            return
        cc, prop = value_id.get("commandClass"), value_id.get("property")
        try:
            self.find(node, cc, prop, value_id.get("propertyKey"))
        except KeyError:
            await self._result(
                connection,
                ident,
                {"result": {"status": 3}} if self.chosen_schema and self.chosen_schema >= 29 else {"success": False},
            )
            return
        if self.fail_next:
            self.fail_next -= 1
            await self._result(connection, ident, {"result": {"status": 2, "message": "The device did not respond"}})
            return
        old_style = self.chosen_schema is not None and self.chosen_schema < 29
        await self._result(connection, ident, {"success": True} if old_style else {"result": {"status": 255}})
        await self.update(node, cc, prop, value)
        if prop == "targetValue":
            with contextlib.suppress(KeyError):
                await self.update(node, cc, "currentValue", value)
