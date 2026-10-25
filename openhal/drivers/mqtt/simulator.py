"""A minimal in-process MQTT 3.1.1 broker and a simulated fan that lives on it.

Written from the OASIS MQTT Version 3.1.1 standard (sections 2 and 3). It speaks enough of the
protocol for a real paho-mqtt client to connect, subscribe, publish and get retained messages.
CONNECT and CONNACK with username and password checks, PUBLISH at QoS 0 and 1 with PUBACK,
SUBSCRIBE and SUBACK (every subscription is granted QoS 0), UNSUBSCRIBE, PINGREQ and DISCONNECT.
Topic filters support `+` and `#`. QoS 2 and persistent sessions are not implemented.

The broker runs on 127.0.0.1 in a background thread with its own event loop, so tests can
start it from synchronous code. Fault injection. `kick_all()` drops every client, `paused`
stops the broker from answering, `hold_acks` withholds PUBACK, and `password` makes it refuse
clients with the wrong credentials.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import socket
import threading
from collections.abc import Callable
from concurrent.futures import Future
from dataclasses import dataclass, field
from typing import Any

Handler = Callable[["MqttBroker", str, bytes], None]


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def topic_matches(pattern: str, topic: str) -> bool:
    """MQTT 3.1.1 section 4.7 topic filter matching."""
    pattern_parts = pattern.split("/")
    topic_parts = topic.split("/")
    for index, part in enumerate(pattern_parts):
        if part == "#":
            return True
        if index >= len(topic_parts):
            return False
        if part not in ("+", topic_parts[index]):
            return False
    return len(pattern_parts) == len(topic_parts)


def _encode_length(length: int) -> bytes:
    out = bytearray()
    while True:
        byte = length % 128
        length //= 128
        out.append(byte | 0x80 if length else byte)
        if not length:
            return bytes(out)


def _string(text: str) -> bytes:
    data = text.encode()
    return len(data).to_bytes(2, "big") + data


def _packet(kind: int, flags: int, body: bytes) -> bytes:
    return bytes([(kind << 4) | flags]) + _encode_length(len(body)) + body


@dataclass
class _Client:
    writer: asyncio.StreamWriter
    client_id: str = ""
    subscriptions: set[str] = field(default_factory=set)


class MqttBroker:
    """Start with `start()`, stop with `stop()`. Listens on 127.0.0.1:`port`."""

    def __init__(self, *, username: str | None = None, password: str | None = None) -> None:
        self.port = _free_port()
        self.username = username
        self.password = password
        self.retained: dict[str, bytes] = {}
        self.published: list[tuple[str, bytes, int, bool]] = []
        self.handlers: list[tuple[str, Handler]] = []
        self.paused = False
        self.hold_acks = False
        self.connections = 0
        self._clients: list[_Client] = []
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._server: asyncio.Server | None = None
        self._stopped: asyncio.Event | None = None

    # ------------------------------------------------------------------ control

    def start(self) -> MqttBroker:
        if self._thread is not None:
            return self
        ready: Future[None] = Future()
        loop = asyncio.new_event_loop()
        self._loop = loop

        async def serve() -> None:
            self._stopped = asyncio.Event()
            self._server = await asyncio.start_server(self._session, "127.0.0.1", self.port)
            ready.set_result(None)
            await self._stopped.wait()
            self._server.close()
            for client in list(self._clients):
                client.writer.close()
            await self._server.wait_closed()

        def run() -> None:
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(serve())
            except Exception as exc:  # noqa: BLE001 (reported to the starting thread)
                if not ready.done():
                    ready.set_exception(exc)
            finally:
                pending = [task for task in asyncio.all_tasks(loop) if not task.done()]
                for task in pending:
                    task.cancel()
                loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
                loop.close()

        self._thread = threading.Thread(target=run, name="openhal-mqtt-broker", daemon=True)
        self._thread.start()
        ready.result(timeout=5)
        return self

    def stop(self) -> None:
        loop, thread, stopped = self._loop, self._thread, self._stopped
        self._loop = self._thread = None
        if loop is None or thread is None or stopped is None:
            return
        loop.call_soon_threadsafe(stopped.set)
        thread.join(timeout=5)

    def __enter__(self) -> MqttBroker:
        return self.start()

    def __exit__(self, *exc: object) -> None:
        self.stop()

    def _call(self, function: Callable[[], None]) -> None:
        if self._loop is None:
            function()
            return
        done: Future[None] = Future()

        def wrapped() -> None:
            try:
                function()
                done.set_result(None)
            except Exception as exc:  # noqa: BLE001 (re-raised in the calling thread)
                done.set_exception(exc)

        self._loop.call_soon_threadsafe(wrapped)
        done.result(timeout=5)

    def kick_all(self) -> None:
        """Drop every connected client without a DISCONNECT, as when the network goes away."""

        def kick() -> None:
            for client in list(self._clients):
                client.writer.transport.abort()

        self._call(kick)

    def publish(self, topic: str, payload: bytes | str, *, retain: bool = False) -> None:
        """Publish as if another client sent it. Safe to call from any thread."""
        data = payload.encode() if isinstance(payload, str) else payload
        self._call(lambda: self.route(topic, data, retain))

    def on(self, pattern: str, handler: Handler) -> None:
        """Call `handler(broker, topic, payload)` for every publish matching `pattern`."""
        self.handlers.append((pattern, handler))

    @property
    def client_count(self) -> int:
        return len(self._clients)

    # ------------------------------------------------------------------ protocol

    def route(self, topic: str, payload: bytes, retain: bool) -> None:
        """Deliver a publish. Only call this from the broker thread, for example inside a handler."""
        if retain:
            if payload:
                self.retained[topic] = payload
            else:
                self.retained.pop(topic, None)
        for client in list(self._clients):
            if any(topic_matches(pattern, topic) for pattern in client.subscriptions):
                self._deliver(client, topic, payload, retain=False)
        for pattern, handler in list(self.handlers):
            if topic_matches(pattern, topic):
                handler(self, topic, payload)

    def _deliver(self, client: _Client, topic: str, payload: bytes, *, retain: bool) -> None:
        with contextlib.suppress(RuntimeError, ConnectionError):
            client.writer.write(_packet(3, 1 if retain else 0, _string(topic) + payload))

    async def _read_packet(self, reader: asyncio.StreamReader) -> tuple[int, int, bytes]:
        header = await reader.readexactly(1)
        multiplier, length = 1, 0
        for _ in range(4):
            byte = (await reader.readexactly(1))[0]
            length += (byte & 0x7F) * multiplier
            if not byte & 0x80:
                break
            multiplier *= 128
        else:
            raise ConnectionError("malformed remaining length")
        body = await reader.readexactly(length)
        return header[0] >> 4, header[0] & 0x0F, body

    async def _session(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        client = _Client(writer)
        try:
            kind, _, body = await self._read_packet(reader)
            if kind != 1 or not await self._accept(client, body):
                return
            self._clients.append(client)
            self.connections += 1
            while True:
                kind, flags, body = await self._read_packet(reader)
                while self.paused:  # noqa: ASYNC110 (paused is set from other threads)
                    await asyncio.sleep(0.05)
                if kind == 14:
                    return
                await self._handle(client, kind, flags, body)
                await writer.drain()
        except (asyncio.IncompleteReadError, ConnectionError, OSError):
            return
        finally:
            if client in self._clients:
                self._clients.remove(client)
            with contextlib.suppress(Exception):
                writer.close()

    async def _accept(self, client: _Client, body: bytes) -> bool:
        def take_string(offset: int) -> tuple[str, int]:
            size = int.from_bytes(body[offset : offset + 2], "big")
            return body[offset + 2 : offset + 2 + size].decode(), offset + 2 + size

        name, offset = take_string(0)
        level, flags = body[offset], body[offset + 1]
        offset += 4
        if name != "MQTT" or level != 4:
            client.writer.write(_packet(2, 0, bytes([0, 1])))
            return False
        client.client_id, offset = take_string(offset)
        if flags & 0x04:
            _, offset = take_string(offset)
            _, offset = take_string(offset)
        username = password = None
        if flags & 0x80:
            username, offset = take_string(offset)
        if flags & 0x40:
            password, offset = take_string(offset)
        if self.password is not None and (username != self.username or password != self.password):
            client.writer.write(_packet(2, 0, bytes([0, 5])))
            await client.writer.drain()
            return False
        client.writer.write(_packet(2, 0, bytes([0, 0])))
        await client.writer.drain()
        return True

    async def _handle(self, client: _Client, kind: int, flags: int, body: bytes) -> None:
        writer = client.writer
        if kind == 3:
            qos = (flags >> 1) & 0x03
            size = int.from_bytes(body[:2], "big")
            topic = body[2 : 2 + size].decode()
            offset = 2 + size
            packet_id = body[offset : offset + 2] if qos else b""
            payload = body[offset + 2 :] if qos else body[offset:]
            if qos > 1:
                raise ConnectionError("QoS 2 is not supported by the simulator")
            retain = bool(flags & 0x01)
            self.published.append((topic, payload, qos, retain))
            if qos == 1 and not self.hold_acks:
                writer.write(_packet(4, 0, packet_id))
            self.route(topic, payload, retain)
        elif kind == 8:
            packet_id, offset, filters = body[:2], 2, []
            while offset < len(body):
                size = int.from_bytes(body[offset : offset + 2], "big")
                filters.append(body[offset + 2 : offset + 2 + size].decode())
                offset += 3 + size
            client.subscriptions.update(filters)
            writer.write(_packet(9, 0, packet_id + bytes(len(filters))))
            for topic, payload in list(self.retained.items()):
                if any(topic_matches(pattern, topic) for pattern in filters):
                    self._deliver(client, topic, payload, retain=True)
        elif kind == 10:
            packet_id, offset = body[:2], 2
            while offset < len(body):
                size = int.from_bytes(body[offset : offset + 2], "big")
                client.subscriptions.discard(body[offset + 2 : offset + 2 + size].decode())
                offset += 2 + size
            writer.write(_packet(11, 0, packet_id))
        elif kind == 12:
            writer.write(_packet(13, 0, b""))
        elif kind == 4:
            return
        else:
            raise ConnectionError(f"unexpected packet type {kind}")


@dataclass
class SimulatedFan:
    """A fan that follows the Tasmota and Zigbee2MQTT habits. Commands on `.../set`, state retained."""

    broker: MqttBroker
    base: str = "lab/fan"
    speed: float = 0.0
    power: bool = False
    mode: str = "auto"
    temperature: float = 24.5
    humidity: float = 41.0
    echo: bool = True

    def attach(self) -> SimulatedFan:
        self.broker.on(f"{self.base}/speed/set", self._speed)
        self.broker.on(f"{self.base}/power/set", self._power)
        self.broker.on(f"{self.base}/mode/set", self._mode)
        self.publish_all()
        return self

    def publish_all(self) -> None:
        self.broker.publish(f"{self.base}/speed", f"{self.speed:g}", retain=True)
        self.broker.publish(f"{self.base}/power", "ON" if self.power else "OFF", retain=True)
        self.broker.publish(f"{self.base}/mode", json.dumps({"mode": self.mode}), retain=True)
        self.broker.publish(
            f"{self.base}/sensor",
            json.dumps({"climate": {"temperature": self.temperature, "humidity": self.humidity}}),
            retain=True,
        )

    def _speed(self, broker: MqttBroker, topic: str, payload: bytes) -> None:
        try:
            self.speed = float(payload)
        except ValueError:
            return
        if self.echo:
            broker.route(f"{self.base}/speed", f"{self.speed:g}".encode(), True)

    def _power(self, broker: MqttBroker, topic: str, payload: bytes) -> None:
        word = payload.decode(errors="replace").upper()
        if word in ("ON", "OFF"):
            self.power = word == "ON"
            if self.echo:
                broker.route(f"{self.base}/power", word.encode(), True)

    def _mode(self, broker: MqttBroker, topic: str, payload: bytes) -> None:
        try:
            document: Any = json.loads(payload)
        except json.JSONDecodeError:
            return
        if isinstance(document, dict) and document.get("mode") in ("auto", "eco", "boost"):
            self.mode = document["mode"]
            if self.echo:
                state = json.dumps({"mode": self.mode}).encode()
                broker.route(f"{self.base}/mode", state, True)
