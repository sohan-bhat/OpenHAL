"""Any MuJoCo model, simulated in real time, as a device (ADR 0020).

Protocol (the official mujoco Python bindings, 3.3 or later). One device file is one MJCF model,
stepped in real time by `simulator.World`. The model's path comes from the environment variable
that `model_env` names, because a device file never names a file the hub opens (THREAT_MODEL T16).
The driver never reaches hardware, so it reports itself as simulated.

- Read channels are joint positions, `{ joint: shoulder_pan }`, or world positions of a site or a
  body along one axis, `{ body: cube, axis: z }`. A channel named like a joint reads that joint.
- Write channels are actuator goals, `{ actuator: gripper }`. A channel named `<actuator>_goal`
  sets that actuator. A goal moves along a minimum-jerk path whose peak speed is the channel's
  `max_change_per_s`, and reads back as where the actuator is headed.
- Hinge joints and their actuators are in radians and slides in metres, so any angle or length
  unit converts. A channel in percent maps 0 to 100 onto the joint's range or the actuator's
  ctrlrange, low end first.
- `{ command: move_to, site: tip }` moves a site to a point, with the point's axes from the
  action's length arguments or from `at`. MuJoCo's site Jacobian solves the joint positions, only
  for actuated joints in the site's chain, and only inside both the model's ranges and the file's
  own goal limits. `joints` narrows that to the joints it names, so the others keep their goals.
  Every joint moves at most at its channel's `max_change_per_s`, and all of them arrive
  together. `aim` points one of the site's axes along a world direction, and `then` sets
  goal channels once the site has arrived. Every goal channel a move changes must be in the
  action's `effects`, so the kernel reads them back.
- `{ command: hold }`, or an action named hold, ends every move and holds each actuator where it is.

Safe state. Native. Every move ends and every setpoint stays where it is, so position servos
hold the joints in place and a closed gripper keeps its grip. A device file can add steps after.
"""

from __future__ import annotations

import asyncio
import math
from typing import Any, ClassVar

import mujoco

from openhal.drivers.base import Driver, DriverError, DriverInfo, Health, Reading
from openhal.drivers.mujoco.maps import (
    AXES,
    ActionMap,
    ModelLoader,
    MujocoParams,
    Plan,
    Reader,
    ReadMap,
    WriteMap,
    Writer,
    axes_of,
    default_loader,
    is_length,
    scale,
    validate,
)
from openhal.drivers.mujoco.simulator import Aim, Motion, World
from openhal.spec.models import DeviceFile
from openhal.spec.units import Quantity, convert, parse_unit

POLL_S = 0.02


class MujocoDriver(Driver):
    """Any MJCF model. Joint and body reads, actuator goals with speed limits, move_to and hold."""

    info: ClassVar[DriverInfo] = DriverInfo(
        name="mujoco",
        protocols=("MuJoCo physics simulation",),
        hazard_default="medium",
        summary="Any MuJoCo model in real time. Joint reads, actuator goals, move_to by inverse kinematics, hold.",
        safe_state_support="native",
        conformance="full",
    )
    params_model: ClassVar[type[Any] | None] = MujocoParams

    def __init__(self, device: DeviceFile, *, loader: ModelLoader | None = None) -> None:
        super().__init__(device)
        self.settings = MujocoParams.model_validate(device.connect.params)
        self._loader = loader or default_loader(self.settings.model_env)
        self.world: World | None = None
        self.read_maps: dict[str, ReadMap] = {}
        self.write_maps: dict[str, WriteMap] = {}
        self.action_maps: dict[str, ActionMap] = {}
        self.readers: dict[str, Reader] = {}
        self.writers: dict[str, Writer] = {}
        self.plans: dict[str, Plan] = {}
        for name, spec in device.read.items():
            if spec.type != "number":
                raise DriverError(f"read.{name}: positions are numbers.")
            self.read_maps[name] = validate(ReadMap, spec.map or {"joint": name}, f"read.{name}")
        for name, write in device.write.items():
            if write.type != "number":
                raise DriverError(f"write.{name}: actuator goals are numbers.")
            raw = write.map or {"actuator": name.removesuffix("_goal")}
            self.write_maps[name] = validate(WriteMap, raw, f"write.{name}")
        for name, action in device.actions.items():
            given = action.map if action.map is not None else ({"command": "hold"} if name == "hold" else None)
            if given is None:
                raise DriverError(f"actions.{name} needs a map, such as {{ command: move_to, site: tip }}.")
            action_map = validate(ActionMap, given, f"actions.{name}")
            self._check_action(name, action_map)
            self.action_maps[name] = action_map

    def _check_action(self, name: str, action_map: ActionMap) -> None:
        spec = self.device.actions[name]
        if action_map.command == "hold":
            if spec.args:
                raise DriverError(f"actions.{name}: hold takes no arguments.")
            return
        axes = axes_of(action_map, spec)
        unknown = sorted(set(axes) - set(spec.args))
        if unknown:
            raise DriverError(f"actions.{name}: map.axes names {', '.join(unknown)}, which aren't arguments.")
        for arg, arg_spec in spec.args.items():
            if arg not in axes:
                raise DriverError(f"actions.{name}: map.axes must name an axis for {arg}.")
            if arg_spec.type != "number" or arg_spec.unit is None or not is_length(arg_spec):
                raise DriverError(f"actions.{name}.args.{arg} is a coordinate, so it needs a length unit such as mm.")
        named = [axes[arg] for arg in spec.args]
        if sorted(named + list(action_map.at)) != list(AXES):
            raise DriverError(f"actions.{name}: x, y and z each come from one argument or from map.at.")
        for channel, value in action_map.then.items():
            target = self.device.write.get(channel)
            if target is None:
                raise DriverError(f"actions.{name}.map.then names {channel}, which is not a write channel.")
            assert target.min is not None
            assert target.max is not None
            if not target.min <= value <= target.max:
                raise DriverError(
                    f"actions.{name}.map.then sets {channel} to {value:g}, outside its limits "
                    f"{target.min:g} to {target.max:g} {target.unit}."
                )
            if channel not in spec.effects:
                raise DriverError(f"actions.{name} changes {channel}, so list it in effects.")

    @property
    def simulated(self) -> bool:
        return True

    def _world(self) -> World:
        if self.world is None:
            raise DriverError(f"{self.device.device_id} is not connected. Connect it first.")
        return self.world

    async def connect(self) -> None:
        await self.close()
        model = await asyncio.to_thread(self._loader)
        if self.settings.timestep is not None:
            model.opt.timestep = self.settings.timestep
        try:
            world = World(model, keyframe=self.settings.keyframe)
        except KeyError:
            raise DriverError(f"The model has no keyframe named {self.settings.keyframe!r}.") from None
        self._bind(model)
        world.start()
        self.world = world

    def _id(self, model: Any, kind: Any, name: str, where: str, what: str) -> int:
        index = int(mujoco.mj_name2id(model, kind, name))
        if index < 0:
            raise DriverError(f"{where}: the model has no {what} named {name!r}.")
        return index

    def _bind(self, model: Any) -> None:
        """Resolve every map against the model, or raise DriverError naming the first mismatch."""
        self.readers = {name: self._reader(model, name, item) for name, item in self.read_maps.items()}
        self.writers = {name: self._writer(model, name, item) for name, item in self.write_maps.items()}
        self.plans = {
            name: self._plan(model, name, item) for name, item in self.action_maps.items() if item.command == "move_to"
        }

    def _reader(self, model: Any, name: str, item: ReadMap) -> Reader:
        where, unit = f"read.{name}", self.device.channel_unit(name)
        if item.joint is not None:
            joint = self._id(model, mujoco.mjtObj.mjOBJ_JOINT, item.joint, where, "joint")
            return Reader("joint", joint, 0, scale(unit, *_joint_unit(model, joint, where), where))
        axis = AXES.index(item.axis or "x")
        if item.site is not None:
            site = self._id(model, mujoco.mjtObj.mjOBJ_SITE, item.site, where, "site")
            return Reader("site", site, axis, scale(unit, "m", None, where))
        assert item.body is not None
        body = self._id(model, mujoco.mjtObj.mjOBJ_BODY, item.body, where, "body")
        return Reader("body", body, axis, scale(unit, "m", None, where))

    def _writer(self, model: Any, name: str, item: WriteMap) -> Writer:
        where = f"write.{name}"
        actuator = self._id(model, mujoco.mjtObj.mjOBJ_ACTUATOR, item.actuator, where, "actuator")
        span: tuple[float, float] | None = None
        if model.actuator_ctrllimited[actuator]:
            span = float(model.actuator_ctrlrange[actuator][0]), float(model.actuator_ctrlrange[actuator][1])
        if item.unit is not None:
            native = item.unit
        elif model.actuator_trntype[actuator] == mujoco.mjtTrn.mjTRN_JOINT:
            native = _joint_unit(model, int(model.actuator_trnid[actuator][0]), where)[0]
        else:
            raise DriverError(f"{where}: {item.actuator} doesn't drive a joint, so give its unit in map.unit.")
        units = scale(self.device.channel_unit(name), native, span, where)
        spec = self.device.write[name]
        assert spec.min is not None
        assert spec.max is not None
        low, high = sorted((units.native(spec.min), units.native(spec.max)))
        speed = abs(units.factor) * spec.max_change_per_s if spec.max_change_per_s else None
        return Writer(actuator, units, speed, low, high)

    def _plan(self, model: Any, name: str, item: ActionMap) -> Plan:
        where = f"actions.{name}"
        assert item.site is not None
        site = self._id(model, mujoco.mjtObj.mjOBJ_SITE, item.site, where, "site")
        chain = self._chain(model, int(model.site_bodyid[site]))
        if not chain:
            raise DriverError(f"{where}: no write channel drives a joint that moves {item.site}.")
        if item.joints:
            named = {self._id(model, mujoco.mjtObj.mjOBJ_JOINT, joint, where, "joint") for joint in item.joints}
            outside = sorted(_name(model, mujoco.mjtObj.mjOBJ_JOINT, joint) for joint in named - set(chain))
            if outside:
                raise DriverError(
                    f"{where}: map.joints names {', '.join(outside)}, which no goal moves for {item.site}."
                )
            chain = {joint: channel for joint, channel in chain.items() if joint in named}
        effects = set(self.device.actions[name].effects)
        missing = sorted(channel for channel in chain.values() if channel not in effects)
        if missing:
            raise DriverError(f"{where} moves {', '.join(missing)}, so list them in effects.")
        spec = self.device.actions[name]
        axes = axes_of(item, spec)
        aim = Aim(item.aim.axis, item.aim.toward) if item.aim else None
        at = {AXES.index(axis): value for axis, value in item.at.items()}
        arguments = {arg: AXES.index(axis) for arg, axis in axes.items()}
        return Plan(site, arguments, at, aim, chain, dict(item.then))

    def _chain(self, model: Any, body: int) -> dict[int, str]:
        """Joints that move `body`, driven by one of the file's write channels, by joint id."""
        above = {body}
        while body > 0:
            body = int(model.body_parentid[body])
            above.add(body)
        chain: dict[int, str] = {}
        for channel, writer in self.writers.items():
            if model.actuator_trntype[writer.actuator] != mujoco.mjtTrn.mjTRN_JOINT:
                continue
            joint = int(model.actuator_trnid[writer.actuator][0])
            if int(model.jnt_bodyid[joint]) in above:
                chain[joint] = channel
        return chain

    async def identify(self) -> dict[str, str]:
        identity = {"model_env": self.settings.model_env, "mujoco": mujoco.__version__, "simulated": "true"}
        if self.world is not None:
            model = self.world.model
            identity["model"] = _model_name(model)
            identity["joints"] = ", ".join(_name(model, mujoco.mjtObj.mjOBJ_JOINT, i) for i in range(model.njnt))
            identity["actuators"] = ", ".join(_name(model, mujoco.mjtObj.mjOBJ_ACTUATOR, i) for i in range(model.nu))
            identity["timestep"] = f"{self.world.timestep:g} s"
        return identity

    async def read(self, channel: str) -> Reading:
        world = self._world()
        unit = self.device.channel_unit(channel)
        writer = self.writers.get(channel)
        if writer is not None:
            return Reading(channel, writer.scale.channel(world.goal(writer.actuator)), unit)
        reader = self.readers.get(channel)
        if reader is None:
            raise DriverError(f"{self.device.device_id} has no channel {channel!r}.")
        if reader.kind == "joint":
            native = world.qpos(reader.index)
        elif reader.kind == "site":
            native = world.site_position(reader.index)[reader.axis]
        else:
            native = world.body_position(reader.index)[reader.axis]
        value = reader.scale.channel(native)
        span = self.device.read[channel].range
        suspect = span is not None and not span[0] <= value <= span[1]
        return Reading(channel, value, unit, suspect=suspect)

    async def _write(self, channel: str, value: float | bool | str) -> Reading | None:
        writer = self.writers.get(channel)
        if writer is None:
            raise DriverError(f"{self.device.device_id} has no write channel {channel!r}.")
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise DriverError(f"{channel} needs a number.")
        self._world().move([({writer.actuator: writer.scale.native(float(value))}, {writer.actuator: writer.speed})])
        return Reading(channel, float(value), self.device.channel_unit(channel))

    async def _action(self, name: str, args: dict[str, Any]) -> Any:
        action = self.action_maps.get(name)
        if action is None:
            raise DriverError(f"{self.device.device_id} has no action {name!r}.")
        world = self._world()
        if action.command == "hold":
            world.hold()
            return {"held": True}
        return await self._move_to(name, self.plans[name], args, world)

    async def _move_to(self, name: str, plan: Plan, args: dict[str, Any], world: World) -> dict[str, Any]:
        point = [0.0, 0.0, 0.0]
        for axis, value in plan.at.items():
            point[axis] = value
        specs = self.device.actions[name].args
        for arg, axis in plan.axes.items():
            unit = specs[arg].unit
            assert unit is not None
            point[axis] = convert(Quantity(float(args[arg]), parse_unit(unit)), "m")
        writers = {joint: self.writers[channel] for joint, channel in plan.chain.items()}
        model = world.model
        gears = {joint: float(model.actuator_gear[writer.actuator][0]) for joint, writer in writers.items()}
        limits = {joint: _joint_limits(model, joint, writer, gears[joint]) for joint, writer in writers.items()}
        speeds = {
            joint: (writer.speed / abs(gears[joint]) if writer.speed else None) for joint, writer in writers.items()
        }
        x, y, z = point
        solution = await asyncio.to_thread(
            world.solve,
            plan.site,
            (x, y, z),
            limits,
            aim=plan.aim,
            speeds=speeds,
            tolerance=self.settings.tolerance,
            aim_tolerance=self.settings.aim_tolerance,
        )
        shown = ", ".join(f"{value * 1000:.1f}" for value in point)
        if not solution.reached:
            raise DriverError(
                f"{name} can't reach {shown} mm{' with that aim' if plan.aim else ''} inside the joint limits. "
                f"The closest pose ends {solution.error_m * 1000:.1f} mm and "
                f"{math.degrees(solution.aim_error_rad):.1f} deg away, so pick a point inside the reach."
            )
        reach = {writers[joint].actuator: gears[joint] * value for joint, value in solution.joints.items()}
        reach_speeds = {writer.actuator: writer.speed for writer in writers.values()}
        phases = [(reach, reach_speeds)]
        if plan.then:
            then = {
                self.writers[channel].actuator: self.writers[channel].scale.native(v)
                for channel, v in plan.then.items()
            }
            phases.append(
                (then, {self.writers[channel].actuator: self.writers[channel].speed for channel in plan.then})
            )
        motion = world.move(phases)
        status = await self._wait(motion)
        goals = {
            plan.chain[joint]: round(writers[joint].scale.channel(gears[joint] * value), 3)
            for joint, value in solution.joints.items()
        }
        return {"status": status, "to_mm": shown, "goals": goals, "error_mm": round(solution.error_m * 1000, 3)}

    async def _wait(self, motion: Motion) -> str:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self.settings.action_wait
        while not motion.over:
            if loop.time() >= deadline:
                return "started"
            await asyncio.sleep(POLL_S)
        return "held" if motion.held else "done"

    async def _safe_state(self) -> None:
        if self.world is not None:
            self.world.hold()

    async def describe(self) -> dict[str, Any] | None:
        if self.world is None:
            return None
        model = self.world.model
        read: dict[str, Any] = {}
        write: dict[str, Any] = {}
        for joint in range(model.njnt):
            name = _slug(_name(model, mujoco.mjtObj.mjOBJ_JOINT, joint))
            if name and _scalar(model, joint):
                read[name] = {"unit": "deg" if model.jnt_type[joint] == mujoco.mjtJoint.mjJNT_HINGE else "mm"}
        for actuator in range(model.nu):
            name = _slug(_name(model, mujoco.mjtObj.mjOBJ_ACTUATOR, actuator))
            joint = int(model.actuator_trnid[actuator][0])
            if not name or model.actuator_trntype[actuator] != mujoco.mjtTrn.mjTRN_JOINT or not _scalar(model, joint):
                continue
            unit, factor = ("deg", math.degrees(1.0)) if _native_unit(model, joint) == "rad" else ("mm", 1000.0)
            entry: dict[str, Any] = {"unit": unit, "suggested": True}
            span = _span(model, actuator, joint)
            if span is not None:
                entry |= {"min": round(span[0] * factor, 1), "max": round(span[1] * factor, 1)}
            write[f"{name[:42]}_goal"] = entry
        return {
            "device": {"name": f"{_model_name(model) or 'MuJoCo model'} (simulated)"},
            "read": read,
            "write": write,
            "actions": {"hold": {"description": "Hold every actuator where it is.", "suggested": True}},
            "safe_state": [{"action": "hold"}],
            "notes": (
                "Proposed from the MuJoCo model. Goal limits are the model's full ranges and no speed is set, "
                "so set max_change_per_s on each goal and narrow the limits before confirming."
            ),
        }

    async def health(self) -> Health:
        if self.world is None:
            return Health(connected=False, detail="not connected")
        if self.world.failure is not None:
            return Health(connected=False, detail=self.world.failure)
        if not self.world.running:
            return Health(connected=False, detail="the simulation is not running")
        detail = f"{self.world.time:.1f} s simulated, {max(0.0, self.world.lag_s) * 1000:.0f} ms behind the clock"
        return Health(connected=True, detail=detail)

    async def close(self) -> None:
        world, self.world = self.world, None
        if world is not None:
            await asyncio.to_thread(world.close)


def _scalar(model: Any, joint: int) -> bool:
    """Whether a joint has one position, a hinge or a slide."""
    return bool(model.jnt_type[joint] in (mujoco.mjtJoint.mjJNT_HINGE, mujoco.mjtJoint.mjJNT_SLIDE))


def _native_unit(model: Any, joint: int) -> str:
    return "rad" if model.jnt_type[joint] == mujoco.mjtJoint.mjJNT_HINGE else "m"


def _joint_unit(model: Any, joint: int, where: str) -> tuple[str, tuple[float, float] | None]:
    """A joint's own unit, rad for a hinge and m for a slide, and its range when it has one."""
    if not _scalar(model, joint):
        raise DriverError(
            f"{where}: {_name(model, mujoco.mjtObj.mjOBJ_JOINT, joint)} is a free or ball joint. Read a body."
        )
    span = (float(model.jnt_range[joint][0]), float(model.jnt_range[joint][1])) if model.jnt_limited[joint] else None
    return _native_unit(model, joint), span


def _span(model: Any, actuator: int, joint: int) -> tuple[float, float] | None:
    """An actuator's control range, or its joint's range, or None when neither is limited."""
    if model.actuator_ctrllimited[actuator]:
        return float(model.actuator_ctrlrange[actuator][0]), float(model.actuator_ctrlrange[actuator][1])
    if model.jnt_limited[joint]:
        return float(model.jnt_range[joint][0]), float(model.jnt_range[joint][1])
    return None


def _joint_limits(model: Any, joint: int, writer: Writer, gear: float) -> tuple[float, float]:
    """Where inverse kinematics may put a joint, inside the model's range and the file's goal limits."""
    low, high = sorted((writer.low / gear, writer.high / gear))
    if model.jnt_limited[joint]:
        low = max(low, float(model.jnt_range[joint][0]))
        high = min(high, float(model.jnt_range[joint][1]))
    return low, high


def _name(model: Any, kind: Any, index: int) -> str:
    return str(mujoco.mj_id2name(model, kind, index) or "")


def _model_name(model: Any) -> str:
    """The model's own name, the first entry in MuJoCo's names buffer."""
    return bytes(model.names).split(b"\0", 1)[0].decode("utf-8", errors="replace")


def _slug(name: str) -> str:
    text = "".join(char if char.isalnum() or char == "_" else "_" for char in name.lower()).strip("_")
    if not text or not text[0].isalpha():
        return ""
    return text[:48]
