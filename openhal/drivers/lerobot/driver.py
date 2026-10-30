"""Hugging Face LeRobot arms, such as the SO-100, SO-101 and Koch followers.

Protocol (the `lerobot.robots.Robot` interface of LeRobot 0.6). LeRobot pulls in PyTorch, so it is
imported only when a device connects, and the tests use the fake in `simulator.py`, whose
docstring lists every assumption it makes about LeRobot.

- One device file is one LeRobot robot, named by its LeRobot type (`so101_follower`) with its
  serial port and the id its calibration was saved under.
- connect() calls `connect(calibrate=False)`. Calibration moves the arm by hand and prompts at
  the keyboard, so the driver never runs it. An uncalibrated arm fails to connect with a pointer
  to `lerobot-calibrate`. Connecting turns torque on, so the arm holds where it is.
- Joint positions are reads, `<joint>.pos` from `get_observation()`. Goal positions are changes
  through `send_action()`, one joint per channel, with the device file's per-joint limits and
  `max_change_per_s`. A goal reads back as the value LeRobot actually wrote, after its own
  `max_relative_target` clipping.
- Body joints are in degrees with `use_degrees: true` (LeRobot's default) and from -100 to 100
  otherwise. Grippers are 0 to 100 percent open.
- A goal channel reads the joint's present position until a goal is sent, because the servo
  holds where it is. Rate limits are then measured from where the joint really is.
- The torque_on action first writes every present position as the goal, so no joint jumps to
  an old goal when torque comes back.
- Every LeRobot call blocks on the serial bus, so it runs in a worker thread with a deadline.

Safe state. Native. Torque off on every motor (`bus.disable_torque()`). The arm goes limp and
falls under gravity, so rest it over something soft or park it before stopping.
"""

from __future__ import annotations

import asyncio
import contextlib
import threading
import time
from collections.abc import Callable
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from openhal.drivers.base import Discovered, Driver, DriverError, DriverInfo, Health, Reading
from openhal.drivers.serial import mapping
from openhal.drivers.serial.link import list_serial_ports, port_identifiers
from openhal.spec.models import DeviceFile
from openhal.spec.units import Quantity, UnitError, convert, parse_unit

POLL_S = 0.05
CONNECT_BUDGET_S = 9.0
RobotFactory = Callable[[str, dict[str, Any]], Any]


def lerobot_factory(robot_type: str, settings: dict[str, Any]) -> Any:
    """Build a LeRobot robot from its registered type name, importing LeRobot only now."""
    try:
        from lerobot.robots import RobotConfig, make_robot_from_config  # type: ignore[import-not-found]
    except ImportError as exc:
        raise DriverError(
            f"LeRobot isn't installed ({exc.name}). Install it with pip install 'lerobot[feetech]' "
            "or the extra for your motors. See docs/drivers/lerobot.md."
        ) from exc
    try:
        config_class = RobotConfig.get_choice_class(robot_type)
    except (KeyError, ValueError) as exc:
        raise DriverError(f"LeRobot has no robot type {robot_type!r} ({exc}).") from exc
    return make_robot_from_config(config_class(**settings))


ANGLES = frozenset({"deg", "degree", "degrees", "rad", "radian", "radians", "arcmin", "arcsec", "turn", "revolution"})


def _compatible(source: str, target: str) -> bool:
    """Whether a value converts. Angles and plain numbers are both dimensionless to pint, but never mix here."""
    if (source in ANGLES) != (target in ANGLES):
        return False
    try:
        convert(Quantity(1.0, parse_unit(source)), target)
    except UnitError:
        return False
    return True


class LeRobotParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    robot: str = Field(pattern=r"^[a-z][a-z0-9_]{1,63}$")
    port: str = Field(min_length=1, max_length=300)
    robot_id: str = Field(min_length=1, max_length=120, pattern=r"^[A-Za-z0-9_.\-]+$")
    use_degrees: bool = True
    max_relative_target: float | None = Field(default=None, gt=0, le=180)
    torque_off_on_close: bool = True
    timeout: float = 2.0
    action_wait: float = 8.0
    observation_age: float = 0.05
    tolerance: float = Field(default=2.0, gt=0, le=20)

    @field_validator("timeout", "action_wait", "observation_age", mode="before")
    @classmethod
    def _duration(cls, value: Any) -> float:
        return mapping.duration(value)

    @model_validator(mode="after")
    def _ranges(self) -> LeRobotParams:
        checks = (("timeout", 0.1, 9), ("action_wait", 0.1, 9), ("observation_age", 0, 1))
        for name, low, high in checks:
            if not low <= getattr(self, name) <= high:
                raise ValueError(f"{name} must be between {low:g} s and {high:g} s.")
        return self


class JointMap(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    joint: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_]{0,63}$")
    torque: bool = False
    unit: str | None = None

    @model_validator(mode="after")
    def _one(self) -> JointMap:
        if (self.joint is None) == (not self.torque):
            raise ValueError("give a joint, or torque: true.")
        return self


class ActionMap(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    command: str = Field(pattern=r"^(torque_off|torque_on|move)$")
    joints: dict[str, str] = {}


def _validate(model: type[BaseModel], raw: dict[str, Any] | None, default: dict[str, Any] | None, where: str) -> Any:
    data = raw if raw is not None else default
    if data is None:
        raise DriverError(f"{where} needs a map. See docs/drivers/lerobot.md.")
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        problems = "; ".join(f"{'.'.join(str(p) for p in e['loc']) or 'map'}: {e['msg']}" for e in exc.errors())
        raise DriverError(f"{where}.map is not valid for the LeRobot driver ({problems}).") from exc


class LeRobotDriver(Driver):
    """LeRobot follower arms. Joint positions, goal positions with limits, torque off as the safe state."""

    info: ClassVar[DriverInfo] = DriverInfo(
        name="lerobot",
        protocols=("Hugging Face LeRobot Robot API",),
        hazard_default="high",
        summary="LeRobot arms such as SO-101 and Koch. Joint positions, limited goals, torque off on stop.",
        safe_state_support="native",
        conformance="full",
    )
    params_model: ClassVar[type[Any] | None] = LeRobotParams

    def __init__(self, device: DeviceFile, *, robot_factory: RobotFactory | None = None) -> None:
        super().__init__(device)
        self.settings = LeRobotParams.model_validate(device.connect.params)
        self._factory = robot_factory or lerobot_factory
        self.robot: Any = None
        self.reads: dict[str, JointMap] = {}
        self.writes: dict[str, JointMap] = {}
        self.actions: dict[str, ActionMap] = {}
        self.sent: dict[str, Reading] = {}
        self._observation: tuple[dict[str, Any], float] | None = None
        self._bus_lock = threading.Lock()
        self._lost: str | None = None
        for name, spec in device.read.items():
            default = {"torque": True} if name == "torque" else {"joint": name.removesuffix("_pos")}
            joint_map = _validate(JointMap, spec.map, default, f"read.{name}")
            if joint_map.torque and spec.type != "bool":
                raise DriverError(f"read.{name}: torque reads as true or false.")
            if joint_map.joint and spec.type != "number":
                raise DriverError(f"read.{name}: a joint position is a number.")
            self.reads[name] = joint_map
        for name, write_spec in device.write.items():
            joint_map = _validate(JointMap, write_spec.map, {"joint": name.removesuffix("_goal")}, f"write.{name}")
            if joint_map.torque or write_spec.type != "number":
                raise DriverError(f"write.{name}: goal positions are numbers on one joint. Use the torque_off action.")
            self.writes[name] = joint_map
        for name, action in device.actions.items():
            known = {"command": name} if name in ("torque_off", "torque_on") else None
            action_map = _validate(ActionMap, action.map, known, f"actions.{name}")
            if action_map.command == "move":
                if set(action_map.joints) != set(action.args) or not action.args:
                    raise DriverError(f"actions.{name}: map.joints must name a joint for each argument.")
            elif action.args:
                raise DriverError(f"actions.{name}: {action_map.command} takes no arguments.")
            self.actions[name] = action_map

    def _unit(self, joint: str, override: str | None) -> str:
        if override:
            return override
        if joint == "gripper":
            return "percent"
        return "deg" if self.settings.use_degrees else "dimensionless"

    @classmethod
    async def discover(cls) -> list[Discovered]:
        ports = await asyncio.to_thread(list_serial_ports)
        return [
            Discovered(driver="lerobot", address=str(info.device), identifiers=port_identifiers(info))
            for info in ports
            if getattr(info, "vid", None) is not None
        ]

    async def _call(self, function: Callable[..., Any], *args: Any, what: str, budget: float | None = None) -> Any:
        """Run one blocking LeRobot call in a thread, one at a time, with a deadline."""

        def locked() -> Any:
            with self._bus_lock:
                return function(*args)

        wait = budget or self.settings.timeout
        try:
            return await asyncio.wait_for(asyncio.to_thread(locked), wait)
        except TimeoutError:
            raise TimeoutError(
                f"The arm sent no reply to {what} within {wait:g} s. Check the bus and its power."
            ) from None
        except DriverError:
            raise
        except (ConnectionError, OSError) as exc:
            self._lost = f"{what} failed ({exc})"
            raise DriverError(
                f"The arm's bus failed during {what} ({exc}). Check the cable and power, then reconnect."
            ) from exc
        except Exception as exc:
            raise DriverError(f"LeRobot returned an error for {what} ({type(exc).__name__}, {exc}).") from exc

    def _robot(self) -> Any:
        if self.robot is None:
            raise DriverError(f"{self.device.device_id} is not connected. Connect it first.")
        return self.robot

    async def identify(self) -> dict[str, str]:
        identity = {"robot": self.settings.robot, "port": self.settings.port, "robot_id": self.settings.robot_id}
        if self.robot is not None:
            identity["joints"] = ", ".join(key.removesuffix(".pos") for key in self.robot.action_features)
            identity["calibrated"] = str(bool(self.robot.is_calibrated)).lower()
        return identity

    async def connect(self) -> None:
        await self.close()
        settings = {
            "port": self.settings.port,
            "id": self.settings.robot_id,
            "use_degrees": self.settings.use_degrees,
            "max_relative_target": self.settings.max_relative_target,
            "disable_torque_on_disconnect": self.settings.torque_off_on_close,
            "cameras": {},
        }
        robot = await self._call(
            self._factory, self.settings.robot, settings, what="building the robot", budget=CONNECT_BUDGET_S
        )
        if not robot.is_calibrated:
            raise DriverError(
                f"{self.settings.robot} {self.settings.robot_id} isn't calibrated. Run lerobot-calibrate "
                f"--robot.type={self.settings.robot} --robot.port={self.settings.port} "
                f"--robot.id={self.settings.robot_id} first."
            )
        self._lost = None
        self._observation = None
        await self._call(robot.connect, False, what="connect", budget=CONNECT_BUDGET_S)
        self.robot = robot
        self.sent.clear()
        joints = {key.removesuffix(".pos") for key in robot.action_features if key.endswith(".pos")}
        observed = {key.removesuffix(".pos") for key in robot.observation_features if key.endswith(".pos")}
        try:
            self._check_joints(joints, observed)
        except DriverError:
            await self.close()
            raise

    def _check_joints(self, joints: set[str], observed: set[str]) -> None:
        def check(where: str, joint: str, known: set[str], unit: str | None, override: str | None) -> None:
            if joint not in known:
                raise DriverError(
                    f"{where}: {self.settings.robot} has no joint {joint!r}. It has {', '.join(sorted(known))}."
                )
            source = self._unit(joint, override)
            if not _compatible(source, unit or source):
                raise DriverError(f"{where}: {joint} is in {source}, which doesn't convert to the file's {unit}.")

        for name, read_map in self.reads.items():
            if read_map.joint:
                check(f"read.{name}", read_map.joint, observed, self.device.channel_unit(name), read_map.unit)
        for name, write_map in self.writes.items():
            assert write_map.joint is not None
            check(f"write.{name}", write_map.joint, joints, self.device.channel_unit(name), write_map.unit)
        for name, action in self.actions.items():
            for arg, joint in action.joints.items():
                check(f"actions.{name}.{arg}", joint, joints, self.device.actions[name].args[arg].unit, None)

    async def _positions(self, max_age: float | None = None) -> dict[str, Any]:
        age = self.settings.observation_age if max_age is None else max_age
        if self._observation is not None and time.monotonic() - self._observation[1] <= age:
            return self._observation[0]
        observation = await self._call(self._robot().get_observation, what="reading the joints")
        self._observation = (observation, time.monotonic())
        return dict(observation)

    async def read(self, channel: str) -> Reading:
        robot = self._robot()
        unit = self.device.channel_unit(channel)
        if channel in self.writes:
            sent = self.sent.get(channel)
            if sent is not None:
                return sent
            write_map = self.writes[channel]
            assert write_map.joint is not None
            return await self._joint(channel, write_map.joint, write_map.unit, unit)
        read_map = self.reads.get(channel)
        if read_map is None:
            raise DriverError(f"{self.device.device_id} has no channel {channel!r}.")
        if read_map.torque:
            states = await self._call(robot.bus.sync_read, "Torque_Enable", what="reading torque")
            return Reading(channel, all(int(value) == 1 for value in states.values()), None)
        assert read_map.joint is not None
        reading = await self._joint(channel, read_map.joint, read_map.unit, unit)
        span = self.device.read[channel].range
        value = reading.value
        if span is not None and isinstance(value, float) and not span[0] <= value <= span[1]:
            return Reading(channel, value, unit, at=reading.at, suspect=True)
        return reading

    async def _joint(self, channel: str, joint: str, override: str | None, unit: str | None) -> Reading:
        """A joint's present position. A goal channel reads it too until a goal is sent, since the servo holds there."""
        observation = await self._positions()
        raw = observation.get(f"{joint}.pos")
        if isinstance(raw, bool) or not isinstance(raw, int | float):
            raise DriverError(f"{channel}: LeRobot reported {raw!r} for {joint}.pos, not a number.")
        value = convert(Quantity(float(raw), parse_unit(self._unit(joint, override))), unit or "deg")
        return Reading(channel, value, unit)

    def _to_robot(self, joint: str, value: float, unit: str | None, override: str | None) -> float:
        target = self._unit(joint, override)
        return convert(Quantity(value, parse_unit(unit or target)), target)

    async def _write(self, channel: str, value: float | bool | str) -> Reading | None:
        write_map = self.writes.get(channel)
        if write_map is None or write_map.joint is None:
            raise DriverError(f"{self.device.device_id} has no write channel {channel!r}.")
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise DriverError(f"{channel} needs a number.")
        unit = self.device.channel_unit(channel)
        goal = self._to_robot(write_map.joint, float(value), unit, write_map.unit)
        self.sent.pop(channel, None)
        written = await self._call(
            self._robot().send_action, {f"{write_map.joint}.pos": goal}, what=f"the goal for {write_map.joint}"
        )
        self._observation = None
        actual = float(written.get(f"{write_map.joint}.pos", goal))
        reading = Reading(
            channel,
            convert(Quantity(actual, parse_unit(self._unit(write_map.joint, write_map.unit))), unit or "deg"),
            unit,
        )
        self.sent[channel] = reading
        return reading

    async def _action(self, name: str, args: dict[str, Any]) -> Any:
        action = self.actions.get(name)
        if action is None:
            raise DriverError(f"{self.device.device_id} has no action {name!r}.")
        robot = self._robot()
        if action.command == "torque_off":
            await self._torque_off(robot)
            return {"sent": "disable_torque"}
        if action.command == "torque_on":
            observation = await self._positions(0)
            hold = {key: value for key, value in observation.items() if key in robot.action_features}
            await self._call(robot.send_action, hold, what="holding the present position")
            await self._call(robot.bus.enable_torque, what="torque on")
            self.sent.clear()
            return {"sent": "enable_torque", "held": hold}
        specs = self.device.actions[name].args
        goals = {
            f"{joint}.pos": self._to_robot(joint, float(args[arg]), specs[arg].unit, None)
            for arg, joint in action.joints.items()
        }
        written = await self._call(robot.send_action, goals, what="the move")
        self._observation = None
        return {"sent": written, "status": await self._settle(written)}

    async def _settle(self, goals: dict[str, Any]) -> str:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self.settings.action_wait
        while loop.time() < deadline:
            observation = await self._positions(0)
            if all(
                abs(float(observation.get(key, value)) - float(value)) <= self.settings.tolerance
                for key, value in goals.items()
            ):
                return "done"
            await asyncio.sleep(POLL_S)
        return "started"

    async def _torque_off(self, robot: Any) -> None:
        bus = getattr(robot, "bus", None)
        if bus is None or not hasattr(bus, "disable_torque"):
            raise DriverError(f"{self.settings.robot} has no motor bus to turn torque off. Use the robot's own stop.")
        await self._call(bus.disable_torque, what="torque off")
        self.sent.clear()

    async def _safe_state(self) -> None:
        await self._torque_off(self._robot())

    async def describe(self) -> dict[str, Any] | None:
        if self.robot is None:
            return None
        joints = [key.removesuffix(".pos") for key in self.robot.action_features if key.endswith(".pos")]
        observation = await self._positions(0)
        read: dict[str, Any] = {"torque": {"type": "bool"}}
        write: dict[str, Any] = {}
        for joint in joints:
            unit = self._unit(joint, None)
            here = float(observation.get(f"{joint}.pos", 0.0))
            read[joint] = {"unit": unit}
            floor, ceiling = {"percent": (0.0, 100.0), "dimensionless": (-100.0, 100.0)}.get(unit, (-180.0, 180.0))
            write[f"{joint}_goal"] = {
                "unit": unit,
                "min": max(floor, round(here - 10, 1)),
                "max": min(ceiling, round(here + 10, 1)),
                "max_change_per_s": 20,
                "confirm": "confirm-each-time",
                "suggested": True,
            }
        return {
            "device": {"name": f"{self.settings.robot} {self.settings.robot_id}"},
            "read": read,
            "write": write,
            "actions": {
                "torque_off": {"suggested": True},
                "torque_on": {"confirm": "confirm-each-time", "suggested": True},
            },
            "notes": (
                "Proposed from the arm's joints. Goal limits start 10 degrees either side of where each joint is now. "
                "Widen them only after checking the arm's real range of motion, one joint at a time."
            ),
        }

    async def health(self) -> Health:
        if self.robot is None:
            return Health(connected=False, detail="not connected")
        if self._lost:
            return Health(connected=False, detail=self._lost)
        try:
            await self._positions(0)
        except (DriverError, TimeoutError) as exc:
            return Health(connected=False, detail=str(exc))
        return Health(connected=True, detail=f"{self.settings.robot} {self.settings.robot_id} on {self.settings.port}")

    async def close(self) -> None:
        robot, self.robot = self.robot, None
        self._observation = None
        if robot is not None and getattr(robot, "is_connected", False):
            with contextlib.suppress(Exception):
                await self._call(robot.disconnect, what="disconnect")
