"""A small rosbridge v2 WebSocket server with a simulated differential drive robot.

It follows the rosbridge v2 protocol (rosbridge_suite, ROSBRIDGE_PROTOCOL.md) closely enough to
run the driver's real client. The robot publishes /battery_state, /odom, /temperature and
/lamp_state, listens on /cmd_vel and /lamp, offers /reset_odometry (std_srvs/srv/Trigger) and
/set_lamp (std_srvs/srv/SetBool), runs a /navigate action, and answers the rosapi services the
driver uses. Odometry integrates /cmd_vel in simulated time.

Fault hooks. `silent` stops all output, `drop_clients()` closes every connection and `inject()`
sends a raw text frame.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import math
import threading
import time
from dataclasses import dataclass
from typing import Any

TOPICS: dict[str, str] = {
    "/battery_state": "sensor_msgs/msg/BatteryState",
    "/odom": "nav_msgs/msg/Odometry",
    "/temperature": "sensor_msgs/msg/Temperature",
    "/lamp_state": "std_msgs/msg/Bool",
    "/mode": "std_msgs/msg/String",
    "/cmd_vel": "geometry_msgs/msg/Twist",
    "/lamp": "std_msgs/msg/Bool",
    "/rosout": "rcl_interfaces/msg/Log",
}
SERVICES: dict[str, str] = {
    "/reset_odometry": "std_srvs/srv/Trigger",
    "/set_lamp": "std_srvs/srv/SetBool",
    "/turtle/get_parameters": "rcl_interfaces/srv/GetParameters",
    "/rosapi/topics": "rosapi_msgs/srv/Topics",
    "/rosapi/services": "rosapi_msgs/srv/Services",
}
ACTIONS: dict[str, str] = {"/navigate": "turtle_msgs/action/Navigate"}


@dataclass
class SimGoal:
    id: str
    client: Any
    target: tuple[float, float]
    ends: float


class RosbridgeSim:
    """The robot and its rosbridge. `await start()` returns the port."""

    def __init__(self) -> None:
        self.time_scale = 1.0
        self.silent = False
        self.port = 0
        self.received: list[dict[str, Any]] = []
        self.x = self.y = self.theta = 0.0
        self.linear = self.angular = 0.0
        self.lamp = False
        self.battery = 0.87
        self.temperature = 31.5
        self.navigate_s = 1.0
        self.goals: dict[str, SimGoal] = {}
        self._subscriptions: dict[Any, set[str]] = {}
        self._advertised: dict[Any, set[str]] = {}
        self._server: Any = None
        self._ticker: asyncio.Task[None] | None = None
        self._last = time.monotonic()

    async def start(self) -> int:
        from websockets.asyncio.server import serve

        self._server = await serve(self._client, "127.0.0.1", 0)
        self.port = next(iter(self._server.sockets)).getsockname()[1]
        self._ticker = asyncio.create_task(self._tick())
        return self.port

    def ops(self, op: str) -> list[dict[str, Any]]:
        return [message for message in self.received if message.get("op") == op]

    def message(self, topic: str) -> dict[str, Any]:
        if topic == "/battery_state":
            return {
                "voltage": 12.3,
                "current": -0.4,
                "percentage": self.battery,
                "present": True,
                "cell_voltage": [4.1, 4.1, 4.1],
            }
        if topic == "/odom":
            return {
                "header": {"frame_id": "odom"},
                "child_frame_id": "base_link",
                "pose": {
                    "pose": {
                        "position": {"x": self.x, "y": self.y, "z": 0.0},
                        "orientation": {"z": math.sin(self.theta / 2), "w": math.cos(self.theta / 2)},
                    }
                },
                "twist": {
                    "twist": {
                        "linear": {"x": self.linear, "y": 0.0, "z": 0.0},
                        "angular": {"x": 0.0, "y": 0.0, "z": self.angular},
                    }
                },
            }
        if topic == "/temperature":
            return {"temperature": self.temperature, "variance": 0.0}
        if topic == "/lamp_state":
            return {"data": self.lamp}
        if topic == "/mode":
            return {"data": "auto"}
        return {}

    async def _send(self, client: Any, message: dict[str, Any]) -> None:
        if self.silent:
            return
        with contextlib.suppress(Exception):
            await client.send(json.dumps(message))

    def inject(self, text: str) -> None:
        for client in list(self._subscriptions):
            task = asyncio.ensure_future(client.send(text))
            task.add_done_callback(lambda done: done.exception())

    def drop_clients(self) -> None:
        for client in list(self._subscriptions):
            task = asyncio.ensure_future(client.close())
            task.add_done_callback(lambda done: done.exception())

    async def _tick(self) -> None:
        while True:
            await asyncio.sleep(0.05)
            now = time.monotonic()
            dt = (now - self._last) * self.time_scale
            self._last = now
            self.theta += self.angular * dt
            self.x += self.linear * math.cos(self.theta) * dt
            self.y += self.linear * math.sin(self.theta) * dt
            for client, topics in list(self._subscriptions.items()):
                for topic in sorted(topics & {"/battery_state", "/odom", "/temperature", "/lamp_state", "/mode"}):
                    await self._send(client, {"op": "publish", "topic": topic, "msg": self.message(topic)})
            for goal in list(self.goals.values()):
                remaining = max(0.0, (goal.ends - time.monotonic()) * self.time_scale)
                if remaining > 0:
                    await self._send(
                        goal.client,
                        {
                            "op": "action_feedback",
                            "id": goal.id,
                            "action": "/navigate",
                            "values": {"seconds_remaining": remaining},
                        },
                    )
                    continue
                self.x, self.y = goal.target
                del self.goals[goal.id]
                await self._send(
                    goal.client,
                    {
                        "op": "action_result",
                        "id": goal.id,
                        "action": "/navigate",
                        "values": {"success": True},
                        "status": 4,
                        "result": True,
                    },
                )

    async def _client(self, client: Any) -> None:
        self._subscriptions[client] = set()
        self._advertised[client] = set()
        try:
            async for raw in client:
                message = json.loads(raw)
                self.received.append(message)
                await self._handle(client, message)
        except Exception:  # noqa: BLE001, S110
            pass
        finally:
            self._subscriptions.pop(client, None)
            self._advertised.pop(client, None)
            for goal in [goal for goal in self.goals.values() if goal.client is client]:
                del self.goals[goal.id]

    async def _error(self, client: Any, ident: Any, text: str) -> None:
        await self._send(client, {"op": "status", "level": "error", "msg": text, "id": ident})

    async def _handle(self, client: Any, message: dict[str, Any]) -> None:
        op, ident = message.get("op"), message.get("id")
        topic = message.get("topic")
        if op in ("subscribe", "advertise"):
            kind = message.get("type")
            if topic in TOPICS and kind and kind != TOPICS[topic]:
                await self._error(client, ident, f"{op}: {topic} already has type {TOPICS[topic]}, not {kind}")
                return
            (self._subscriptions if op == "subscribe" else self._advertised)[client].add(str(topic))
            if op == "subscribe" and topic in TOPICS:
                await self._send(client, {"op": "publish", "topic": topic, "msg": self.message(topic)})
        elif op == "publish":
            await self._publish(client, ident, topic, message.get("msg"))
        elif op == "call_service":
            await self._service(client, ident, message.get("service"), message.get("args") or {})
        elif op == "send_action_goal":
            args = message.get("args") or {}
            if message.get("action") not in ACTIONS:
                await self._error(client, ident, f"send_action_goal: no action server {message.get('action')}")
                return
            try:
                target = (float(args["x"]), float(args["y"]))
            except (KeyError, TypeError, ValueError):
                await self._send(
                    client,
                    {
                        "op": "action_result",
                        "id": ident,
                        "action": "/navigate",
                        "values": {"success": False},
                        "status": 6,
                        "result": False,
                    },
                )
                return
            self.goals[str(ident)] = SimGoal(
                str(ident), client, target, time.monotonic() + self.navigate_s / self.time_scale
            )
        elif op == "cancel_action_goal":
            goal = self.goals.pop(str(ident), None)
            if goal is not None:
                await self._send(
                    client,
                    {
                        "op": "action_result",
                        "id": goal.id,
                        "action": "/navigate",
                        "values": {"success": False},
                        "status": 5,
                        "result": False,
                    },
                )

    async def _publish(self, client: Any, ident: Any, topic: Any, msg: Any) -> None:
        if topic not in self._advertised.get(client, set()):
            await self._error(client, ident, f"publish: {topic} is not advertised")
            return
        if topic == "/cmd_vel":
            try:
                linear, angular = msg["linear"], msg["angular"]
                values = [float(linear[axis]) for axis in "xyz"] + [float(angular[axis]) for axis in "xyz"]
            except (KeyError, TypeError, ValueError):
                await self._error(client, ident, "publish: /cmd_vel needs linear and angular with x, y and z")
                return
            self.linear, self.angular = values[0], values[5]
        elif topic == "/lamp":
            if not isinstance(msg, dict) or not isinstance(msg.get("data"), bool):
                await self._error(client, ident, "publish: /lamp needs data as a bool")
                return
            self.lamp = msg["data"]

    async def _service(self, client: Any, ident: Any, service: Any, args: dict[str, Any]) -> None:
        async def reply(values: Any, ok: bool = True) -> None:
            await self._send(
                client, {"op": "service_response", "id": ident, "service": service, "values": values, "result": ok}
            )

        if service == "/rosapi/topics":
            await reply({"topics": list(TOPICS), "types": list(TOPICS.values())})
        elif service == "/rosapi/services":
            await reply({"services": list(SERVICES)})
        elif service == "/rosapi/action_servers":
            await reply({"action_servers": list(ACTIONS)})
        elif service == "/rosapi/service_type":
            await reply({"type": SERVICES.get(str(args.get("service")), "")})
        elif service == "/rosapi/nodes":
            await reply({"nodes": ["/turtle", "/rosbridge_websocket", "/rosapi"]})
        elif service == "/rosapi/get_ros_version":
            await reply({"version": 2, "distro": "jazzy"})
        elif service == "/reset_odometry":
            self.x = self.y = self.theta = 0.0
            await reply({"success": True, "message": "odometry reset"})
        elif service == "/set_lamp":
            if not isinstance(args.get("data"), bool):
                await reply("SetBool data must be a bool", ok=False)
                return
            self.lamp = args["data"]
            await reply({"success": True, "message": ""})
        else:
            await reply(f"Service {service} does not exist", ok=False)

    async def stop(self) -> None:
        if self._ticker is not None:
            self._ticker.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._ticker
        if self._server is not None:
            self._server.close()
            with contextlib.suppress(Exception):
                await asyncio.wait_for(self._server.wait_closed(), 2.0)


class ServerThread:
    """Runs the simulator on its own event loop in a daemon thread, for synchronous setup."""

    def __init__(self, sim: RosbridgeSim) -> None:
        self.sim = sim
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> int:
        ready = threading.Event()
        port: list[int] = []

        def run() -> None:
            loop = asyncio.new_event_loop()
            self._loop = loop
            port.append(loop.run_until_complete(self.sim.start()))
            ready.set()
            loop.run_forever()
            loop.run_until_complete(self.sim.stop())
            loop.close()

        self._thread = threading.Thread(target=run, name="openhal-rosbridge-sim", daemon=True)
        self._thread.start()
        if not ready.wait(5):
            raise RuntimeError("the rosbridge simulator didn't start")
        return port[0]

    def call(self, function: Any) -> None:
        if self._loop is not None:
            self._loop.call_soon_threadsafe(function)

    def stop(self) -> None:
        if self._loop is not None:
            self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread is not None:
            self._thread.join(5)
