"""Z-Wave nodes through zwave-js-server, over its WebSocket API with the websockets package.

On connect the server sends `{"type": "version", ...}` with the schema versions it supports. The
client picks one with `set_api_schema`, then `start_listening` returns the whole state, including
every node and its values with metadata, and the server pushes events from then on. A value is
named by command class, endpoint, property and property key. Changes go out with
`node.set_value`, whose result is `{"result": {"status": n}}` from schema 29 on and
`{"success": bool}` before it. zwave-js reports status 255 for success, 254 for success without
supervision and 1 for working, and the rest are failures.
"""

from __future__ import annotations

import asyncio
import contextlib
import itertools
import json
import time
from typing import Any, Final

from openhal.drivers.base import DriverError
from openhal.drivers.zigbee_zwave.common import UNKNOWN, ChannelMap, Feature

SCHEMA: Final = 40
OK_STATUS: Final = frozenset({1, 254, 255})
NODE_STATUS: Final = {0: "unknown", 1: "asleep", 2: "awake", 3: "dead", 4: "alive"}
ValueKey = tuple[int, int, str, str]


def key_of(command_class: int, endpoint: int, prop: Any, property_key: Any) -> ValueKey:
    return command_class, endpoint, str(prop), "" if property_key is None else str(property_key)


def feature_of(metadata: dict[str, Any]) -> Feature:
    """A feature from zwave-js value metadata."""
    kind = metadata.get("type")
    states = {str(raw): str(label) for raw, label in (metadata.get("states") or {}).items()}
    common: dict[str, Any] = {
        "readable": bool(metadata.get("readable", True)),
        "writable": bool(metadata.get("writeable", False)),
        "label": str(metadata.get("label") or ""),
        "unit": metadata.get("unit"),
        "minimum": metadata.get("min"),
        "maximum": metadata.get("max"),
        "step": metadata.get("steps") if isinstance(metadata.get("steps"), int | float) else None,
        "states": states,
    }
    if kind == "boolean":
        return Feature("bool", **common)
    if kind == "number" and states and not metadata.get("unit"):
        return Feature("enum", values=tuple(states.values()), **common)
    if kind == "number":
        return Feature("number", **common)
    if kind == "string":
        return Feature("string", **common)
    return Feature("unknown", **common)


class ZWaveJsLink:
    """One Z-Wave node, by node id."""

    def __init__(self, url: str, node: int, *, timeout: float) -> None:
        self.url = url
        self.node = node
        self.timeout = timeout
        self._ws: Any = None
        self._task: asyncio.Task[None] | None = None
        self._pending: dict[str, asyncio.Future[dict[str, Any]]] = {}
        self._ids = itertools.count(1)
        self._lost = ""
        self.version: dict[str, Any] = {}
        self.schema = 0
        self.info: dict[str, Any] = {}
        self.status = 0
        self.values: dict[ValueKey, tuple[Any, float]] = {}
        self.metadata: dict[ValueKey, dict[str, Any]] = {}

    @property
    def where(self) -> str:
        return f"Z-Wave node {self.node} on {self.url}"

    async def open(self, wanted: list[str]) -> None:
        from websockets.asyncio.client import connect

        try:
            ws = await connect(self.url, open_timeout=self.timeout, proxy=None, max_size=16 * 2**20)
        except (OSError, TimeoutError) as exc:
            raise DriverError(
                f"Could not open zwave-js-server at {self.url} ({exc}). Check the URL and port 3000."
            ) from None
        except Exception as exc:  # noqa: BLE001
            raise DriverError(f"zwave-js-server at {self.url} refused the WebSocket ({exc}).") from None
        try:
            hello = json.loads(await asyncio.wait_for(ws.recv(), self.timeout))
        except Exception as exc:  # noqa: BLE001
            await ws.close()
            raise DriverError(f"zwave-js-server at {self.url} sent no version message ({exc}).") from None
        if not isinstance(hello, dict) or hello.get("type") != "version":
            await ws.close()
            raise DriverError(f"{self.url} isn't zwave-js-server. It didn't start with a version message.")
        low, high = int(hello.get("minSchemaVersion", 0)), int(hello.get("maxSchemaVersion", 0))
        if low > SCHEMA:
            await ws.close()
            raise DriverError(f"zwave-js-server needs schema {low} or newer, and this driver speaks up to {SCHEMA}.")
        self.version = hello
        self.schema = min(SCHEMA, high)
        self._ws = ws
        self._lost = ""
        self._task = asyncio.create_task(self._reader(ws))
        await self.call({"command": "set_api_schema", "schemaVersion": self.schema})
        result = await self.call({"command": "start_listening"})
        nodes = ((result or {}).get("state") or {}).get("nodes") or []
        node = next((item for item in nodes if isinstance(item, dict) and item.get("nodeId") == self.node), None)
        if node is None:
            await self.close()
            raise DriverError(
                f"zwave-js-server has no node {self.node}. Check node against the Z-Wave JS UI node list."
            )
        self._load(node)

    def _load(self, node: dict[str, Any]) -> None:
        self.info = node
        self.status = int(node.get("status") or 0)
        now = time.time()
        self.values.clear()
        self.metadata.clear()
        for item in node.get("values") or []:
            if not isinstance(item, dict) or "commandClass" not in item:
                continue
            key = key_of(
                item["commandClass"], int(item.get("endpoint") or 0), item.get("property"), item.get("propertyKey")
            )
            self.metadata[key] = dict(item.get("metadata") or {})
            if "value" in item:
                self.values[key] = (item["value"], now)

    async def _reader(self, ws: Any) -> None:
        try:
            async for raw in ws:
                self._message(raw)
            self._lost = "zwave-js-server closed the WebSocket"
        except Exception as exc:  # noqa: BLE001
            self._lost = f"the WebSocket failed ({exc})"
        for future in self._pending.values():
            if not future.done():
                future.set_exception(DriverError(f"{self.where} disconnected ({self._lost}). Reconnect it."))
                future.exception()
        self._pending.clear()

    def _message(self, raw: str | bytes) -> None:
        try:
            message = json.loads(raw)
        except ValueError:
            return
        if not isinstance(message, dict):
            return
        if message.get("type") == "result":
            future = self._pending.pop(str(message.get("messageId")), None)
            if future is None or future.done():
                return
            if message.get("success") is True:
                future.set_result(message.get("result") or {})
            else:
                code = message.get("errorCode") or "unknown error"
                detail = message.get("zwaveErrorMessage") or message.get("message") or ""
                future.set_exception(
                    DriverError(f"zwave-js-server refused the command ({code}{f', {detail}' if detail else ''}).")
                )
                future.exception()
            return
        if message.get("type") == "event":
            self._event(message.get("event") or {})

    def _event(self, event: dict[str, Any]) -> None:
        if event.get("source") != "node" or event.get("nodeId") != self.node:
            return
        kind = event.get("event")
        args = event.get("args") or {}
        if kind in ("value updated", "value added", "value notification") and "commandClass" in args:
            key = key_of(
                args["commandClass"], int(args.get("endpoint") or 0), args.get("property"), args.get("propertyKey")
            )
            self.values[key] = (args.get("newValue", args.get("value")), time.time())
        elif kind == "value removed" and "commandClass" in args:
            key = key_of(
                args["commandClass"], int(args.get("endpoint") or 0), args.get("property"), args.get("propertyKey")
            )
            self.values.pop(key, None)
        elif kind == "metadata updated" and "commandClass" in args:
            key = key_of(
                args["commandClass"], int(args.get("endpoint") or 0), args.get("property"), args.get("propertyKey")
            )
            self.metadata[key] = dict(args.get("metadata") or {})
        elif kind in ("dead", "alive", "sleep", "wake up"):
            self.status = {"dead": 3, "alive": 4, "sleep": 1, "wake up": 2}[kind]

    async def call(self, message: dict[str, Any]) -> dict[str, Any]:
        if self._ws is None or self._lost:
            raise DriverError(f"{self.where} is not connected{f', {self._lost}' if self._lost else ''}. Reconnect it.")
        ident = str(next(self._ids))
        future: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
        self._pending[ident] = future
        try:
            await self._ws.send(json.dumps({"messageId": ident, **message}))
            return await asyncio.wait_for(future, self.timeout)
        except TimeoutError:
            raise TimeoutError(
                f"zwave-js-server didn't answer {message['command']} within {self.timeout:g} s."
            ) from None
        except DriverError:
            raise
        except Exception as exc:  # noqa: BLE001
            self._lost = f"sending failed ({exc})"
            raise DriverError(f"{self.where} disconnected while sending {message['command']} ({exc}).") from None
        finally:
            self._pending.pop(ident, None)

    async def close(self) -> None:
        ws, task = self._ws, self._task
        self._ws = None
        self._task = None
        if ws is not None:
            with contextlib.suppress(Exception):
                await ws.close()
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task

    @property
    def connected(self) -> bool:
        return self._ws is not None and not self._lost

    def health(self) -> tuple[bool, str]:
        if not self.connected:
            return False, f"{self.where} {self._lost or 'not connected'}"
        if self.status == 3:
            return False, f"{self.where} is dead. Check its power and range."
        return True, f"{self.where}, {NODE_STATUS.get(self.status, 'unknown')}"

    def check_open(self) -> None:
        if not self.connected:
            raise DriverError(f"{self.where} is not connected{f', {self._lost}' if self._lost else ''}. Reconnect it.")

    @staticmethod
    def _key(channel_map: ChannelMap, *, target: bool) -> ValueKey:
        prop = channel_map.property or ""
        if target:
            prop = channel_map.target or ("targetValue" if prop == "currentValue" else prop)
        return key_of(channel_map.command_class or 0, channel_map.endpoint, prop, channel_map.property_key)

    def feature(self, channel_map: ChannelMap, *, target: bool = False) -> Feature:
        metadata = self.metadata.get(self._key(channel_map, target=target))
        return UNKNOWN if metadata is None else feature_of(metadata)

    def value(self, channel_map: ChannelMap) -> tuple[Any, float] | None:
        self.check_open()
        return self.values.get(self._key(channel_map, target=False))

    async def send(self, channel_map: ChannelMap, raw: Any) -> None:
        command_class, endpoint, prop, _ = self._key(channel_map, target=True)
        value_id: dict[str, Any] = {"commandClass": command_class, "endpoint": endpoint, "property": prop}
        if channel_map.property_key is not None:
            value_id["propertyKey"] = channel_map.property_key
        result = await self.call({"command": "node.set_value", "nodeId": self.node, "valueId": value_id, "value": raw})
        if "result" in result and isinstance(result["result"], dict):
            status = int(result["result"].get("status", 2))
            if status not in OK_STATUS:
                message = result["result"].get("message") or f"status {status}"
                raise DriverError(f"{self.where} didn't take the value ({message}).")
        elif result.get("success") is False:
            raise DriverError(f"{self.where} didn't take the value.")

    def identity(self) -> dict[str, str]:
        config = self.info.get("deviceConfig") or {}
        identity = {"bridge": "zwave-js-server", "node": str(self.node)}
        for key, value in (
            ("manufacturer", config.get("manufacturer")),
            ("model", config.get("label")),
            ("firmware", self.info.get("firmwareVersion")),
            ("server", self.version.get("serverVersion")),
            ("driver", self.version.get("driverVersion")),
        ):
            if value:
                identity[key] = str(value)
        return identity

    def proposal(self) -> dict[str, Any]:
        from openhal.drivers.serial import mapping

        read: dict[str, Any] = {}
        write: dict[str, Any] = {}
        names: set[str] = set()
        for key, metadata in sorted(self.metadata.items(), key=lambda item: str(item[0])):
            command_class, endpoint, prop, property_key = key
            feature = feature_of(metadata)
            if feature.kind == "unknown" or prop == "targetValue":
                continue
            base = "_".join(part for part in (feature.label or prop, f"ep{endpoint}" if endpoint else "") if part)
            name = "".join(char if char.isalnum() else "_" for char in base.lower()).strip("_")[:44] or "value"
            if not name[0].isalpha():
                name = f"v_{name}"[:44]
            while name in names:
                name = f"{name[:40]}_{len(names)}"
            names.add(name)
            channel_map: dict[str, Any] = {"command_class": command_class, "endpoint": endpoint, "property": prop}
            if property_key:
                channel_map["property_key"] = int(property_key) if property_key.isdigit() else property_key
            spec: dict[str, Any]
            if feature.kind == "bool":
                spec = {"type": "bool"}
            elif feature.kind == "enum":
                spec = {"type": "enum", "values": list(feature.values)}
            elif feature.kind == "string":
                spec = {"type": "string"}
            else:
                spec = {"unit": mapping.device_unit(feature.unit) or "dimensionless"}
            settable = feature.writable or key_of(command_class, endpoint, "targetValue", property_key) in self.metadata
            if (settable and prop == "currentValue") or feature.writable:
                if spec.get("unit"):
                    spec.update(
                        {"min": feature.minimum or 0, "max": feature.maximum if feature.maximum is not None else 99}
                    )
                write[name] = {**spec, "suggested": True, "map": channel_map}
            elif feature.readable:
                read[name] = {**spec, "map": channel_map}
        config = self.info.get("deviceConfig") or {}
        device = {"name": config.get("label") or f"Z-Wave node {self.node}", "manufacturer": config.get("manufacturer")}
        return {"device": {key: value for key, value in device.items() if value}, "read": read, "write": write}
