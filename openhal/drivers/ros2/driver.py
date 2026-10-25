"""ROS 2 robots through rosbridge, with this driver's own rosbridge v2 client.

Protocol (rosbridge v2 protocol, rosbridge_suite ROS 2 branch). The client is in `bridge.py`,
the maps in `channels.py` and the describe() proposal in `describe.py`.

- The driver connects to rosbridge_server over a WebSocket (default port 9090). It is a bridge,
  so only the topics, services and actions the device file names are touched.
- Read channels are topic fields. connect() subscribes to each topic once and keeps the newest
  message, so a read costs no round trip and returns unknown until a message has arrived.
- Changes publish a whole message (the map's `base` with one field set) or call a service.
  Topics the file publishes to are advertised during connect, so the first message isn't lost
  while DDS matches publishers and subscribers.
- Actions call a service, publish a message, or send an action goal. A goal waits up to
  `action_wait` for its result, then answers `started` and keeps running.

Safe state. Native. Every action goal this driver started and that is still running is
canceled. ROS has no general stop, so put the robot's own stop (a zero velocity on cmd_vel, a
brake service) in the device file's safe state as well.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Iterable
from typing import Any, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from openhal.drivers.base import Driver, DriverError, DriverInfo, Health, Reading
from openhal.drivers.ros2 import channels
from openhal.drivers.ros2.bridge import GOAL_STATUS, SUCCEEDED, Rosbridge
from openhal.drivers.ros2.channels import ActionMap, ReadMap, WriteMap
from openhal.drivers.serial import mapping
from openhal.spec.models import DeviceFile
from openhal.spec.units import Quantity, UnitError, convert, parse_unit

CANCEL_WAIT_S = 2.0


class Ros2Params(BaseModel):
    model_config = ConfigDict(extra="forbid")

    host: str = Field(min_length=1, max_length=253)
    port: int = Field(default=9090, ge=1, le=65535)
    scheme: Literal["ws", "wss"] = "ws"
    path: str = Field(default="", max_length=200, pattern=r"^(/[A-Za-z0-9_\-./]*)?$")
    timeout: float = 5.0
    action_wait: float = 8.0
    throttle: float = 0.0

    @field_validator("timeout", "action_wait", "throttle", mode="before")
    @classmethod
    def _duration(cls, value: Any) -> float:
        return mapping.duration(value)

    @model_validator(mode="after")
    def _ranges(self) -> Ros2Params:
        checks = (("timeout", 0.1, 30), ("action_wait", 0.1, 9), ("throttle", 0, 60))
        for name, low, high in checks:
            if not low <= getattr(self, name) <= high:
                raise ValueError(f"{name} must be between {low:g} s and {high:g} s.")
        return self


def _convert(value: float, source: str | None, target: str | None, where: str) -> float:
    if not source or not target or source == target:
        return value
    try:
        return convert(Quantity(value, parse_unit(source)), target)
    except UnitError as exc:
        raise DriverError(f"{where}: {exc}") from exc


def _types(items: Iterable[ReadMap | WriteMap | ActionMap]) -> dict[str, str | None]:
    """Each topic once, with the message type any of its maps names."""
    found: dict[str, str | None] = {}
    for item in items:
        if item.topic is not None and found.get(item.topic) is None:
            found[item.topic] = item.type
    return found


class Ros2Driver(Driver):
    """ROS 2 topics, services and actions through rosbridge."""

    info: ClassVar[DriverInfo] = DriverInfo(
        name="ros2",
        protocols=("rosbridge v2 over WebSocket",),
        hazard_default="high",
        summary="ROS 2 robots through rosbridge. Topic fields as channels, publishing, services and actions.",
        safe_state_support="native",
        conformance="full",
    )
    params_model: ClassVar[type[Any] | None] = Ros2Params

    def __init__(self, device: DeviceFile) -> None:
        super().__init__(device)
        self.settings = Ros2Params.model_validate(device.connect.params)
        self.bridge: Rosbridge | None = None
        self.reads: dict[str, ReadMap] = {}
        self.writes: dict[str, WriteMap] = {}
        self.actions: dict[str, ActionMap] = {}
        self.sent: dict[str, Reading] = {}
        for name, spec in device.read.items():
            if spec.type == "image":
                raise DriverError(f"read.{name}: the ROS 2 driver doesn't read images.")
            self.reads[name] = channels.validate(ReadMap, spec.map, f"read.{name}")
        for name, write_spec in device.write.items():
            self.writes[name] = channels.validate(WriteMap, write_spec.map, f"write.{name}")
        for name, action in device.actions.items():
            action_map = channels.validate(ActionMap, action.map, f"actions.{name}")
            if set(action.args) != set(action_map.args):
                raise DriverError(
                    f"actions.{name}: the arguments {sorted(action.args)} must match "
                    f"map.args {sorted(action_map.args)}."
                )
            self.actions[name] = action_map

    @property
    def url(self) -> str:
        return f"{self.settings.scheme}://{self.settings.host}:{self.settings.port}{self.settings.path}"

    def _bridge(self) -> Rosbridge:
        if self.bridge is None:
            raise DriverError(f"{self.device.device_id} is not connected. Connect it first.")
        self.bridge.require()
        return self.bridge

    async def identify(self) -> dict[str, str]:
        identity = {"rosbridge": self.url}
        if self.bridge is None or not self.bridge.connected:
            return identity
        with contextlib.suppress(DriverError, TimeoutError):
            nodes = await self.bridge.call("/rosapi/nodes")
            identity["nodes"] = str(len(nodes.get("nodes", [])))
        with contextlib.suppress(DriverError, TimeoutError):
            distro = await self.bridge.call("/rosapi/get_ros_version")
            identity.update({key: str(value) for key, value in distro.items() if key in ("version", "distro")})
        return identity

    async def connect(self) -> None:
        await self.close()
        bridge = Rosbridge(self.url, timeout=self.settings.timeout)
        await bridge.open()
        self.bridge = bridge
        self.sent.clear()
        throttle = round(self.settings.throttle * 1000)
        for topic, kind in sorted(_types(self.reads.values()).items()):
            await bridge.subscribe(topic, kind, throttle_ms=throttle)
        for topic, kind in sorted(_types([*self.writes.values(), *self.actions.values()]).items()):
            assert kind is not None
            await bridge.advertise(topic, kind)

    async def read(self, channel: str) -> Reading:
        if channel in self.writes:
            sent = self.sent.get(channel)
            return sent if sent is not None else Reading(channel, None, self.device.channel_unit(channel))
        read_map = self.reads.get(channel)
        if read_map is None:
            raise DriverError(f"{self.device.device_id} has no channel {channel!r}.")
        assert read_map.topic is not None
        bridge = self._bridge()
        if read_map.topic in bridge.refused:
            raise DriverError(
                f"rosbridge refused the subscription to {read_map.topic} ({bridge.refused[read_map.topic]})."
            )
        latest = bridge.latest.get(read_map.topic)
        unit = self.device.channel_unit(channel)
        if latest is None:
            return Reading(channel, None, unit)
        message, at = latest
        try:
            raw = channels.get_field(message, read_map.field)
        except KeyError:
            raise DriverError(
                f"{read_map.topic} has no field {read_map.field}. Check the map against the message type."
            ) from None
        spec = self.device.read[channel]
        if spec.type == "number":
            value = _convert(channels.finite(raw, channel) * read_map.scale, read_map.unit, unit, channel)
            span = spec.range
            return Reading(channel, value, unit, at=at, suspect=span is not None and not span[0] <= value <= span[1])
        if spec.type == "bool":
            if not isinstance(raw, bool):
                raise DriverError(f"{channel}: {read_map.field} is not a bool ({raw!r}).")
            return Reading(channel, raw, None, at=at)
        text = str(raw)
        if spec.type == "enum" and text not in spec.values:
            raise DriverError(f"{channel}: {read_map.field} is {text!r}, not one of {', '.join(spec.values)}.")
        return Reading(channel, text, None, at=at)

    @staticmethod
    def _encode(value: Any, unit: str | None, ros_unit: str | None, scale: float, integer: bool, where: str) -> Any:
        if isinstance(value, bool) or not isinstance(value, int | float):
            return value
        number = _convert(float(value), unit, ros_unit, where) / scale
        if not integer:
            return number
        if abs(number - round(number)) > 1e-6:
            raise DriverError(
                f"{where}: {number:g} is not a whole number, and the field is an integer. Nothing was sent."
            )
        return round(number)

    async def _write(self, channel: str, value: float | bool | str) -> Reading | None:
        write_map = self.writes.get(channel)
        if write_map is None:
            raise DriverError(f"{self.device.device_id} has no write channel {channel!r}.")
        spec = self.device.write[channel]
        encoded = self._encode(value, spec.unit, write_map.unit, write_map.scale, write_map.integer, channel)
        message = channels.with_field(write_map.base, write_map.field, encoded)
        bridge = self._bridge()
        self.sent.pop(channel, None)
        if write_map.topic is not None:
            if write_map.topic in bridge.refused:
                raise DriverError(
                    f"rosbridge refused to advertise {write_map.topic} ({bridge.refused[write_map.topic]})."
                )
            await bridge.publish(write_map.topic, message)
        else:
            assert write_map.service is not None
            await bridge.call(write_map.service, message, kind=write_map.type)
        reading = Reading(channel, value, spec.unit)
        self.sent[channel] = reading
        return reading

    def _message(self, name: str, action_map: ActionMap, args: dict[str, Any]) -> dict[str, Any]:
        specs = self.device.actions[name].args
        message = dict(action_map.base)
        for key in action_map.args:
            arg = action_map.arg(key)
            encoded = self._encode(args[key], specs[key].unit, arg.unit, arg.scale, arg.integer, f"{name}.{key}")
            message = channels.with_field(message, arg.field, encoded)
        return message

    async def _action(self, name: str, args: dict[str, Any]) -> Any:
        action_map = self.actions.get(name)
        if action_map is None:
            raise DriverError(f"{self.device.device_id} has no action {name!r}.")
        bridge = self._bridge()
        message = self._message(name, action_map, args)
        if action_map.topic is not None:
            await bridge.publish(action_map.topic, message)
            return {"sent": action_map.topic}
        if action_map.service is not None:
            values = await bridge.call(action_map.service, message, kind=action_map.type)
            if values.get("success") is False:
                raise DriverError(
                    f"{action_map.service} answered success false ({str(values.get('message', ''))[:200]})."
                )
            return {"sent": action_map.service, "values": values}
        assert action_map.action is not None
        assert action_map.type is not None
        goal = await bridge.send_goal(action_map.action, action_map.type, message)
        try:
            result = await asyncio.wait_for(asyncio.shield(goal.result), self.settings.action_wait)
        except TimeoutError:
            return {"sent": action_map.action, "goal": goal.id, "status": "started"}
        status = result.get("status")
        if status != SUCCEEDED or result.get("result") is False:
            word = GOAL_STATUS.get(status, str(status)) if isinstance(status, int) else "failed"
            raise DriverError(f"{action_map.action} {word} ({str(result.get('values', ''))[:200]}).")
        return {"sent": action_map.action, "goal": goal.id, "status": "done", "values": result.get("values")}

    async def _safe_state(self) -> None:
        bridge = self._bridge()
        goals = list(bridge.goals.values())
        problems: list[str] = []
        for goal in goals:
            try:
                await bridge.cancel(goal)
            except DriverError as exc:
                problems.append(f"{goal.action}: {exc}")
        for goal in goals:
            with contextlib.suppress(DriverError, TimeoutError):
                await asyncio.wait_for(asyncio.shield(goal.result), CANCEL_WAIT_S)
        if problems:
            raise DriverError("; ".join(problems))

    async def describe(self) -> dict[str, Any] | None:
        if self.bridge is None or not self.bridge.connected:
            return None
        from openhal.drivers.ros2.describe import proposal

        return await proposal(self.bridge)

    async def health(self) -> Health:
        if self.bridge is None:
            return Health(connected=False, detail="not connected")
        try:
            latency = await self.bridge.ping()
        except (DriverError, TimeoutError) as exc:
            return Health(connected=False, detail=str(exc) or "rosbridge didn't answer a ping")
        except Exception as exc:  # noqa: BLE001
            return Health(connected=False, detail=f"rosbridge connection failed ({exc})")
        running = len(self.bridge.goals)
        detail = f"rosbridge at {self.url}" + (f", {running} goals running" if running else "")
        if self.bridge.last_error:
            detail += f", last rosbridge error: {self.bridge.last_error}"
        return Health(connected=True, detail=detail, latency_ms=latency)

    async def close(self) -> None:
        bridge, self.bridge = self.bridge, None
        if bridge is not None:
            await bridge.close()
