"""A rosbridge v2 client on the `websockets` package.

Written from the rosbridge v2 protocol specification (RobotWebTools/rosbridge_suite,
ROSBRIDGE_PROTOCOL.md) for the ROS 2 branch.

- Every message is a JSON object with an `op`. The client sends `subscribe`, `advertise`,
  `publish`, `call_service`, `send_action_goal` and `cancel_action_goal`.
- The server sends `publish` for subscribed topics, `service_response` with `values` and a
  `result` flag, and `action_feedback` and `action_result` for goals, all matched by `id`.
- Failures can also arrive as `{"op": "status", "level": "error", "msg": ..., "id": ...}`.
- Action results carry `status` from action_msgs/msg/GoalStatus, 4 succeeded, 5 canceled and
  6 aborted.

The client never reconnects on its own. After a failure every call raises DriverError until the
driver connects again.
"""

from __future__ import annotations

import asyncio
import contextlib
import itertools
import json
import time
from dataclasses import dataclass, field
from typing import Any, Final

from openhal.drivers.base import DriverError

SUCCEEDED: Final = 4
CANCELED: Final = 5
ABORTED: Final = 6
GOAL_STATUS: Final = {
    0: "unknown",
    1: "accepted",
    2: "executing",
    3: "canceling",
    4: "succeeded",
    5: "canceled",
    6: "aborted",
}
MAX_MESSAGE: Final = 4 * 1024 * 1024


@dataclass
class Goal:
    """One action goal sent by this client."""

    id: str
    action: str
    result: asyncio.Future[dict[str, Any]]
    feedback: dict[str, Any] = field(default_factory=dict)


class Rosbridge:
    """One WebSocket connection to rosbridge_server."""

    def __init__(self, url: str, *, timeout: float) -> None:
        self.url = url
        self.timeout = timeout
        self.latest: dict[str, tuple[dict[str, Any], float]] = {}
        self.goals: dict[str, Goal] = {}
        self.lost: str | None = None
        self._ws: Any = None
        self._task: asyncio.Task[None] | None = None
        self.refused: dict[str, str] = {}
        self.last_error = ""
        self._pending: dict[str, asyncio.Future[Any]] = {}
        self._topics: dict[str, str] = {}
        self._ids = itertools.count(1)

    async def open(self) -> None:
        from websockets.asyncio.client import connect

        try:
            self._ws = await connect(self.url, open_timeout=self.timeout, max_size=MAX_MESSAGE, proxy=None)
        except (OSError, TimeoutError) as exc:
            raise DriverError(
                f"Could not reach rosbridge at {self.url} ({exc or 'timed out'}). "
                "Check that rosbridge_server is running, for example "
                "ros2 launch rosbridge_server rosbridge_websocket_launch.xml."
            ) from exc
        except Exception as exc:
            raise DriverError(f"rosbridge at {self.url} refused the WebSocket ({exc}).") from exc
        self.lost = None
        self._task = asyncio.create_task(self._read_forever(self._ws))

    @property
    def connected(self) -> bool:
        return self._ws is not None and self.lost is None and self._task is not None and not self._task.done()

    def require(self) -> None:
        if self.lost is not None:
            raise DriverError(f"The rosbridge connection was lost ({self.lost}). Reconnect it.")
        if not self.connected:
            raise DriverError(f"rosbridge at {self.url} is not connected. Connect it first.")

    def _id(self, kind: str) -> str:
        return f"openhal-{kind}-{next(self._ids)}"

    async def _read_forever(self, ws: Any) -> None:
        try:
            async for raw in ws:
                self._handle(raw)
            self.lost = "rosbridge closed the connection"
        except ValueError:
            self.lost = "rosbridge sent a message that is not JSON"
        except Exception as exc:  # noqa: BLE001
            self.lost = f"the WebSocket failed ({exc})"
        error = DriverError(f"The rosbridge connection was lost ({self.lost}). Reconnect it.")
        for future in [*self._pending.values(), *(goal.result for goal in self.goals.values())]:
            if not future.done():
                future.set_exception(error)
                future.exception()
        self._pending.clear()

    def _handle(self, raw: str | bytes) -> None:
        message = json.loads(raw)
        if not isinstance(message, dict):
            return
        op = message.get("op")
        ident = message.get("id")
        if op == "publish" and isinstance(message.get("topic"), str) and isinstance(message.get("msg"), dict):
            self.latest[message["topic"]] = (message["msg"], time.time())
        elif op == "service_response" and isinstance(ident, str):
            future = self._pending.pop(ident, None)
            if future is not None and not future.done():
                future.set_result(message)
        elif op == "action_feedback" and ident in self.goals:
            values = message.get("values")
            self.goals[ident].feedback = values if isinstance(values, dict) else {"values": values}
        elif op == "action_result" and ident in self.goals:
            goal = self.goals.pop(ident)
            if not goal.result.done():
                goal.result.set_result(message)
        elif op == "status" and message.get("level") == "error" and isinstance(ident, str):
            text = str(message.get("msg", ""))[:300]
            self.last_error = text
            if ident in self._topics:
                self.refused[self._topics[ident]] = text
            error = DriverError(f"rosbridge refused the request ({text}).")
            for future in (self._pending.pop(ident, None), getattr(self.goals.pop(ident, None), "result", None)):
                if future is not None and not future.done():
                    future.set_exception(error)
                    future.exception()

    async def send(self, message: dict[str, Any]) -> None:
        self.require()
        try:
            await asyncio.wait_for(self._ws.send(json.dumps(message, allow_nan=False)), self.timeout)
        except ValueError as exc:
            raise DriverError(f"The message can't be sent as JSON ({exc}).") from exc
        except Exception as exc:
            self.lost = f"sending failed ({exc})"
            raise DriverError(f"Sending to rosbridge failed ({exc}). Reconnect it.") from exc

    async def call(
        self, service: str, args: dict[str, Any] | None = None, *, kind: str | None = None
    ) -> dict[str, Any]:
        """Call a service and return its `values`. A false `result` raises DriverError."""
        ident = self._id("call")
        future: asyncio.Future[Any] = asyncio.get_running_loop().create_future()
        self._pending[ident] = future
        message: dict[str, Any] = {"op": "call_service", "id": ident, "service": service, "args": args or {}}
        if kind:
            message["type"] = kind
        try:
            await self.send(message)
            reply = await asyncio.wait_for(future, self.timeout)
        except TimeoutError:
            raise TimeoutError(f"{service} didn't answer within {self.timeout:g} s.") from None
        finally:
            self._pending.pop(ident, None)
        values = reply.get("values")
        if reply.get("result") is False:
            raise DriverError(f"{service} failed ({str(values)[:300]}).")
        return values if isinstance(values, dict) else {}

    async def subscribe(self, topic: str, kind: str | None, *, throttle_ms: int = 0) -> None:
        """Subscribe. A refusal arrives later as a status line and lands in `refused`."""
        ident = self._id("sub")
        self._topics[ident] = topic
        message: dict[str, Any] = {"op": "subscribe", "id": ident, "topic": topic, "throttle_rate": throttle_ms}
        if kind:
            message["type"] = kind
        await self.send(message)

    async def advertise(self, topic: str, kind: str) -> None:
        ident = self._id("adv")
        self._topics[ident] = topic
        await self.send({"op": "advertise", "id": ident, "topic": topic, "type": kind})

    async def publish(self, topic: str, msg: dict[str, Any]) -> None:
        await self.send({"op": "publish", "id": self._id("pub"), "topic": topic, "msg": msg})

    async def send_goal(self, action: str, kind: str, args: dict[str, Any]) -> Goal:
        ident = self._id("goal")
        goal = Goal(ident, action, asyncio.get_running_loop().create_future())
        self.goals[ident] = goal
        message = {
            "op": "send_action_goal",
            "id": ident,
            "action": action,
            "action_type": kind,
            "args": args,
            "feedback": True,
        }
        try:
            await self.send(message)
        except DriverError:
            self.goals.pop(ident, None)
            raise
        return goal

    async def cancel(self, goal: Goal) -> None:
        await self.send({"op": "cancel_action_goal", "id": goal.id, "action": goal.action})

    async def ping(self) -> float:
        self.require()
        started = time.monotonic()
        waiter = await self._ws.ping()
        await asyncio.wait_for(waiter, self.timeout)
        return (time.monotonic() - started) * 1000

    async def close(self) -> None:
        ws, task = self._ws, self._task
        self._ws, self._task = None, None
        if ws is not None:
            with contextlib.suppress(Exception):
                await asyncio.wait_for(ws.close(), 1.0)
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
        if self.lost is None:
            self.lost = "closed"
