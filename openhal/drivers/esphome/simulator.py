"""An ESPHome native API simulator, served on a local TCP port in plaintext.

It speaks the native API framing (a 0x00 preamble, a varint length, a varint message type, then
a protobuf payload) with the message classes generated from ESPHome's api.proto, which ship in
aioesphomeapi (`aioesphomeapi.api_pb2`, MIT). So the driver runs the real `APIClient` against
it, including the hello handshake, device info, entity listing, state subscription and commands.

Entities. A soil moisture sensor, a firmware text sensor, a tank binary sensor, a pump switch, a
dimmable grow light, a three-speed fan with presets, a pump duration number, a mode select and
a calibrate button.

Faults. `latency_s`, `ignore_commands` (accept commands without changing state, like a device
whose relay is stuck), `drop_connections()` and `garbage_next` (send an invalid preamble).
"""

from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass, field
from typing import Any

from aioesphomeapi import api_pb2
from aioesphomeapi.core import MESSAGE_TYPE_TO_PROTO

pb: Any = api_pb2

TYPE_OF = {cls: number for number, cls in MESSAGE_TYPE_TO_PROTO.items()}


def varuint(value: int) -> bytes:
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            return bytes(out)


@dataclass
class SimEntity:
    kind: str
    object_id: str
    key: int
    name: str
    info: dict[str, Any] = field(default_factory=dict)
    state: dict[str, Any] = field(default_factory=dict)


def default_entities() -> list[SimEntity]:
    return [
        SimEntity(
            "sensor",
            "soil_moisture",
            101,
            "Soil moisture",
            {"unit_of_measurement": "%", "accuracy_decimals": 1},
            {"state": 41.5},
        ),
        SimEntity("sensor", "air_temperature", 102, "Air temperature", {"unit_of_measurement": "°F"}, {"state": 68.0}),
        SimEntity("text_sensor", "firmware", 103, "Firmware", {}, {"state": "2026.10.1"}),
        SimEntity("binary_sensor", "tank_empty", 104, "Tank empty", {"device_class": "problem"}, {"state": False}),
        SimEntity("switch", "pump", 105, "Pump", {}, {"state": False}),
        SimEntity(
            "light",
            "grow_light",
            106,
            "Grow light",
            {"supported_color_modes": [3]},
            {"state": False, "brightness": 1.0},
        ),
        SimEntity(
            "fan",
            "vent_fan",
            107,
            "Vent fan",
            {"supports_speed": True, "supported_speed_count": 3, "supported_preset_modes": ["auto", "night"]},
            {"state": False, "speed_level": 0, "preset_mode": ""},
        ),
        SimEntity(
            "number",
            "pump_seconds",
            108,
            "Pump seconds",
            {"min_value": 1.0, "max_value": 30.0, "step": 1.0, "unit_of_measurement": "s"},
            {"state": 10.0},
        ),
        SimEntity("select", "mode", 109, "Mode", {"options": ["manual", "schedule", "off"]}, {"state": "manual"}),
        SimEntity("button", "calibrate", 110, "Calibrate", {}, {}),
    ]


LIST = {
    "sensor": pb.ListEntitiesSensorResponse,
    "text_sensor": pb.ListEntitiesTextSensorResponse,
    "binary_sensor": pb.ListEntitiesBinarySensorResponse,
    "switch": pb.ListEntitiesSwitchResponse,
    "light": pb.ListEntitiesLightResponse,
    "fan": pb.ListEntitiesFanResponse,
    "number": pb.ListEntitiesNumberResponse,
    "select": pb.ListEntitiesSelectResponse,
    "button": pb.ListEntitiesButtonResponse,
}
STATE = {
    "sensor": pb.SensorStateResponse,
    "text_sensor": pb.TextSensorStateResponse,
    "binary_sensor": pb.BinarySensorStateResponse,
    "switch": pb.SwitchStateResponse,
    "light": pb.LightStateResponse,
    "fan": pb.FanStateResponse,
    "number": pb.NumberStateResponse,
    "select": pb.SelectStateResponse,
}


class EspHomeSim:
    """One simulated ESPHome node."""

    def __init__(self, name: str = "plant-node", model: str = "esp32dev") -> None:
        self.name = name
        self.model = model
        self.entities = {entity.key: entity for entity in default_entities()}
        self.latency_s = 0.0
        self.ignore_commands = False
        self.garbage_next = False
        self.commands: list[tuple[str, dict[str, Any]]] = []
        self.port: int | None = None
        self.button_presses = 0
        self._server: asyncio.Server | None = None
        self._writers: set[asyncio.StreamWriter] = set()
        self._subscribed: set[asyncio.StreamWriter] = set()

    def entity(self, object_id: str) -> SimEntity:
        return next(entity for entity in self.entities.values() if entity.object_id == object_id)

    async def start(self) -> int:
        self._server = await asyncio.start_server(self._client, "127.0.0.1", 0)
        self.port = int(self._server.sockets[0].getsockname()[1])
        return self.port

    async def _client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self._writers.add(writer)
        try:
            while True:
                preamble = await reader.readexactly(1)
                if preamble != b"\x00":
                    return
                length = await self._varuint(reader)
                kind = await self._varuint(reader)
                payload = await reader.readexactly(length) if length else b""
                cls = MESSAGE_TYPE_TO_PROTO.get(kind)
                if cls is None:
                    continue
                message = cls()
                message.ParseFromString(payload)
                if await self._handle(writer, message) is False:
                    return
        except (asyncio.IncompleteReadError, ConnectionError, OSError):
            return
        finally:
            self._writers.discard(writer)
            self._subscribed.discard(writer)
            with contextlib.suppress(Exception):
                writer.close()

    @staticmethod
    async def _varuint(reader: asyncio.StreamReader) -> int:
        value = shift = 0
        while True:
            byte = (await reader.readexactly(1))[0]
            value |= (byte & 0x7F) << shift
            if not byte & 0x80:
                return value
            shift += 7

    async def _send(self, writer: asyncio.StreamWriter, message: Any) -> None:
        if self.garbage_next:
            self.garbage_next = False
            writer.write(b"\x7fgarbage")
            return
        data = message.SerializeToString()
        writer.write(b"\x00" + varuint(len(data)) + varuint(TYPE_OF[type(message)]) + data)
        with contextlib.suppress(ConnectionError):
            await writer.drain()

    async def _handle(self, writer: asyncio.StreamWriter, message: Any) -> bool | None:
        if self.latency_s:
            await asyncio.sleep(self.latency_s)
        if isinstance(message, pb.HelloRequest):
            await self._send(
                writer,
                pb.HelloResponse(api_version_major=1, api_version_minor=10, server_info="openhal-sim", name=self.name),
            )
        elif isinstance(message, pb.DisconnectRequest):
            await self._send(writer, pb.DisconnectResponse())
            return False
        elif isinstance(message, pb.PingRequest):
            await self._send(writer, pb.PingResponse())
        elif isinstance(message, pb.DeviceInfoRequest):
            await self._send(
                writer,
                pb.DeviceInfoResponse(
                    name=self.name,
                    friendly_name="Plant node",
                    mac_address="AA:BB:CC:DD:EE:FF",
                    esphome_version="2026.10.1",
                    compilation_time="Oct 20 2026, 10:00:00",
                    model=self.model,
                    manufacturer="Espressif",
                ),
            )
        elif isinstance(message, pb.ListEntitiesRequest):
            for entity in self.entities.values():
                fields = {"object_id": entity.object_id, "key": entity.key, "name": entity.name, **entity.info}
                await self._send(writer, LIST[entity.kind](**fields))
            await self._send(writer, pb.ListEntitiesDoneResponse())
        elif isinstance(message, pb.SubscribeStatesRequest):
            self._subscribed.add(writer)
            for entity in self.entities.values():
                await self._publish(entity, [writer])
        else:
            await self._command(message)
        return None

    async def _publish(self, entity: SimEntity, writers: list[asyncio.StreamWriter] | None = None) -> None:
        cls = STATE.get(entity.kind)
        if cls is None:
            return
        for writer in writers or list(self._subscribed):
            await self._send(writer, cls(key=entity.key, **entity.state))

    async def _command(self, message: Any) -> None:
        entity = self.entities.get(getattr(message, "key", -1))
        if entity is None:
            return
        name = type(message).__name__
        self.commands.append((name, {f.name: getattr(message, f.name) for f in message.DESCRIPTOR.fields}))
        if self.ignore_commands:
            return
        if isinstance(message, pb.SwitchCommandRequest):
            entity.state["state"] = message.state
        elif isinstance(message, pb.LightCommandRequest):
            if message.has_state:
                entity.state["state"] = message.state
            if message.has_brightness:
                entity.state["brightness"] = message.brightness
        elif isinstance(message, pb.FanCommandRequest):
            if message.has_state:
                entity.state["state"] = message.state
            if message.has_speed_level:
                entity.state["speed_level"] = message.speed_level
                entity.state["state"] = message.speed_level > 0
            if message.has_preset_mode:
                entity.state["preset_mode"] = message.preset_mode
        elif isinstance(message, pb.NumberCommandRequest):
            low, high = entity.info["min_value"], entity.info["max_value"]
            entity.state["state"] = min(max(message.state, low), high)
        elif isinstance(message, pb.SelectCommandRequest):
            if message.state in entity.info["options"]:
                entity.state["state"] = message.state
        elif isinstance(message, pb.ButtonCommandRequest):
            self.button_presses += 1
            return
        await self._publish(entity)

    async def set_state(self, object_id: str, **state: Any) -> None:
        """Change a state on the device side, like a sensor update."""
        entity = self.entity(object_id)
        entity.state.update(state)
        await self._publish(entity)

    async def drop_connections(self) -> None:
        for writer in list(self._writers):
            with contextlib.suppress(Exception):
                writer.close()

    async def close(self) -> None:
        await self.drop_connections()
        if self._server is not None:
            self._server.close()
            with contextlib.suppress(Exception):
                await self._server.wait_closed()
            self._server = None


class ThreadedSim:
    """Runs an `EspHomeSim` on its own event loop in a daemon thread.

    The conformance suite builds drivers synchronously, so it can't await `start()`. This wrapper
    starts the server before the suite runs and lets the case reach it from any loop.
    """

    def __init__(self, sim: EspHomeSim | None = None) -> None:
        import threading

        self.sim = sim or EspHomeSim()
        self.loop = asyncio.new_event_loop()
        ready = threading.Event()

        def run() -> None:
            asyncio.set_event_loop(self.loop)
            self.loop.run_until_complete(self.sim.start())
            ready.set()
            self.loop.run_forever()

        self._thread = threading.Thread(target=run, name="openhal-esphome-sim", daemon=True)
        self._thread.start()
        ready.wait(5)
        assert self.sim.port is not None
        self.port: int = self.sim.port

    async def call(self, coro: Any) -> Any:
        """Run a coroutine on the simulator's loop and wait for it from another loop."""
        return await asyncio.wrap_future(asyncio.run_coroutine_threadsafe(coro, self.loop))

    async def _shutdown(self) -> None:
        await self.sim.close()
        current = asyncio.current_task()
        tasks = [task for task in asyncio.all_tasks() if task is not current]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    def stop(self) -> None:
        future = asyncio.run_coroutine_threadsafe(self._shutdown(), self.loop)
        with contextlib.suppress(Exception):
            future.result(5)
        self.loop.call_soon_threadsafe(self.loop.stop)
        self._thread.join(5)
        self.loop.close()
