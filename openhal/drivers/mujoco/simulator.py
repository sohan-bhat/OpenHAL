"""A MuJoCo world that steps in real time, behind the mujoco driver.

The driver never steps MuJoCo itself. It calls a `World`, where other drivers have a protocol
and a simulator behind it. A world is one compiled MJCF model and its state, stepped on its own
thread so that simulated time keeps pace with the hub's clock.

- Position goals move every actuator along a minimum-jerk path. A path is as slow as it needs to
  be for no actuator to pass its speed, so the peak speed equals the limit and never exceeds it.
- One move may have several phases, such as a reach and then a gripper opening. A new move takes
  over the actuators it names, and an older move keeps going on the others.
- `hold()` ends every move at once and freezes every setpoint where it is, so position servos
  hold the joints there and a closed gripper keeps its grip.
- `solve()` finds joint positions that put a site at a point, optionally with one of the site's
  axes along a world direction, by damped least squares on MuJoCo's site Jacobian. It starts
  from the present pose, then the model's keyframes, then a fixed spread of poses inside the
  limits, and keeps the reachable solution that moves for the shortest time. Nothing in it is random.
- `watch()` calls a function every few physics steps with the live data, for recordings.
"""

from __future__ import annotations

import math
import threading
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any

import mujoco
import numpy as np

PEAK: float = 1.875
"""The peak speed of a minimum-jerk path over its average speed."""
MAX_BURST_S: float = 0.25
"""The most simulated time one pass of the loop catches up before the thread gives up the lock."""
SEEDS: int = 12
"""How many fixed spread poses `solve()` starts from after the present pose and the keyframes."""
ITERATIONS: int = 100
"""Damped least squares iterations per starting pose."""
DAMPING: float = 1e-4
AIM_WEIGHT: float = 0.2
"""How much an aim error in radians counts against a position error in metres."""

Watcher = Callable[[float, Any], None]


def minimum_jerk(tau: float) -> float:
    """How far along a minimum-jerk path is at the fraction `tau` of its duration."""
    tau = min(1.0, max(0.0, tau))
    return tau**3 * (10.0 - 15.0 * tau + 6.0 * tau**2)


def halton(index: int, base: int) -> float:
    """One term of the Halton sequence, for a fixed spread of starting poses."""
    fraction, result = 1.0, 0.0
    while index > 0:
        fraction /= base
        result += fraction * (index % base)
        index //= base
    return result


PRIMES = (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37)


@dataclass
class Phase:
    """Actuators moving together to their goals, each at most at its speed in native units per second."""

    goals: dict[int, float]
    speeds: dict[int, float | None]
    start: float | None = None
    duration: float = 0.0
    origins: dict[int, float] = field(default_factory=dict)

    def begin(self, now: float, ctrl: Any) -> None:
        self.start = now
        self.origins = {actuator: float(ctrl[actuator]) for actuator in self.goals}
        times = [
            PEAK * abs(goal - self.origins[actuator]) / speed
            for actuator, goal in self.goals.items()
            if (speed := self.speeds.get(actuator))
        ]
        self.duration = max(times, default=0.0)

    def apply(self, now: float, ctrl: Any) -> bool:
        """Set every setpoint for the step at `now`. True once the phase has reached its goals."""
        assert self.start is not None
        tau = 1.0 if self.duration <= 0 else (now - self.start) / self.duration
        share = minimum_jerk(tau)
        for actuator, goal in self.goals.items():
            origin = self.origins[actuator]
            ctrl[actuator] = origin + (goal - origin) * share
        return tau >= 1.0


class Motion:
    """One move, a list of phases run one after another. `ended` says why it stopped early, if it did."""

    def __init__(self, phases: list[Phase]) -> None:
        self.phases = [phase for phase in phases if phase.goals]
        self.ended: str | None = None

    @property
    def over(self) -> bool:
        return not self.phases

    def actuators(self) -> set[int]:
        return {actuator for phase in self.phases for actuator in phase.goals}

    def release(self, actuators: set[int]) -> None:
        """Hand these actuators to a newer move. Phases left with nothing to move are dropped."""
        if actuators & self.actuators():
            self.ended = "taken over"
        for phase in self.phases:
            for actuator in actuators & set(phase.goals):
                phase.goals.pop(actuator)
                phase.origins.pop(actuator, None)
        self.phases = [phase for phase in self.phases if phase.goals]

    def step(self, now: float, ctrl: Any) -> None:
        while self.phases:
            phase = self.phases[0]
            if phase.start is None:
                phase.begin(now, ctrl)
            if not phase.apply(now, ctrl):
                return
            self.phases.pop(0)


@dataclass(frozen=True)
class Aim:
    """Point the site's own `axis` along the world direction `toward`."""

    axis: tuple[float, float, float]
    toward: tuple[float, float, float]


@dataclass(frozen=True)
class Solution:
    """Joint positions by joint id, and how far the site ends from the point and from the aim."""

    joints: dict[int, float]
    error_m: float
    aim_error_rad: float
    reached: bool


class World:
    """One MuJoCo model and its state, stepped in real time on a thread once started."""

    def __init__(self, model: Any, *, keyframe: str | None = None, clock: Callable[[], float] = time.monotonic) -> None:
        self.model = model
        self.data = mujoco.MjData(model)
        self.clock = clock
        if keyframe is not None:
            key = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_KEY, keyframe)
            if key < 0:
                raise KeyError(keyframe)
            mujoco.mj_resetDataKeyframe(model, self.data, key)
        mujoco.mj_forward(model, self.data)
        self.goals = np.array(self.data.ctrl, dtype=float)
        self.motions: list[Motion] = []
        self.failure: str | None = None
        self.steps = 0
        self.origin = clock() - float(self.data.time)
        self._watchers: list[tuple[int, Watcher]] = []
        self._lock = threading.Lock()
        self._solve_lock = threading.Lock()
        self._scratch = mujoco.MjData(model)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def timestep(self) -> float:
        return float(self.model.opt.timestep)

    @property
    def time(self) -> float:
        """Simulated seconds since the world began."""
        return float(self.data.time)

    @property
    def lag_s(self) -> float:
        """How far simulated time is behind the clock right now."""
        return self.clock() - self.origin - self.time

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive() and self.failure is None

    def start(self) -> None:
        """Start stepping in real time from now."""
        if self._thread is not None:
            return
        self.origin = self.clock() - self.time
        self._thread = threading.Thread(target=self._loop, name="openhal-mujoco", daemon=True)
        self._thread.start()

    def close(self) -> None:
        self._stop.set()
        thread, self._thread = self._thread, None
        if thread is not None:
            thread.join(timeout=2.0)

    def _loop(self) -> None:
        burst = max(1, int(MAX_BURST_S / self.timestep))
        try:
            while not self._stop.is_set():
                for _ in range(burst):
                    if self.lag_s < self.timestep:
                        break
                    self.advance()
                    if self.failure is not None:
                        return
                self._stop.wait(max(0.0, self.timestep - self.lag_s))
        except Exception as exc:  # noqa: BLE001 (the driver's health check reports it)
            self.failure = f"the physics thread stopped ({type(exc).__name__}: {exc})"

    def advance(self, steps: int = 1) -> None:
        """Take physics steps now, whatever the clock says. The thread calls this, and so can tests."""
        for _ in range(steps):
            with self._lock:
                now = self.time
                for motion in list(self.motions):
                    motion.step(now, self.data.ctrl)
                    if motion.over:
                        self.motions.remove(motion)
                mujoco.mj_step(self.model, self.data)
                self.steps += 1
                for every, watcher in list(self._watchers):
                    if self.steps % every == 0:
                        watcher(self.time, self.data)
                if self.data.warning[mujoco.mjtWarning.mjWARN_BADQACC].number:
                    self.failure = "the simulation became unstable and MuJoCo reset it"
                    return

    def watch(self, every: int, watcher: Watcher) -> Callable[[], None]:
        """Call `watcher(time, data)` after every `every` physics steps, on the physics thread.

        The watcher holds the world's lock while it runs, so it must copy what it needs and return.
        """
        entry = (max(1, every), watcher)
        with self._lock:
            self._watchers.append(entry)

        def remove() -> None:
            with self._lock:
                if entry in self._watchers:
                    self._watchers.remove(entry)

        return remove

    def qpos(self, joint: int) -> float:
        with self._lock:
            return float(self.data.qpos[self.model.jnt_qposadr[joint]])

    def body_position(self, body: int) -> tuple[float, float, float]:
        with self._lock:
            x, y, z = (float(value) for value in self.data.xpos[body])
            return x, y, z

    def site_position(self, site: int) -> tuple[float, float, float]:
        with self._lock:
            x, y, z = (float(value) for value in self.data.site_xpos[site])
            return x, y, z

    def goal(self, actuator: int) -> float:
        """Where the actuator is headed, the setpoint itself once it got there."""
        with self._lock:
            return float(self.goals[actuator])

    def move(self, phases: Iterable[tuple[dict[int, float], dict[int, float | None]]]) -> Motion:
        """Start a move now. Each phase is goals and speeds by actuator id, in native units."""
        motion = Motion([Phase(dict(goals), dict(speeds)) for goals, speeds in phases])
        with self._lock:
            taken = motion.actuators()
            for older in self.motions:
                older.release(taken)
            self.motions = [older for older in self.motions if not older.over]
            self.motions.append(motion)
            for phase in motion.phases:
                for actuator, goal in phase.goals.items():
                    self.goals[actuator] = goal
        return motion

    def hold(self) -> None:
        """End every move now and keep every setpoint where it is."""
        with self._lock:
            for motion in self.motions:
                motion.ended = "held"
                motion.phases.clear()
            self.motions.clear()
            self.goals[:] = self.data.ctrl

    def solve(
        self,
        site: int,
        target: tuple[float, float, float],
        joints: dict[int, tuple[float, float]],
        *,
        aim: Aim | None = None,
        speeds: dict[int, float | None] | None = None,
        tolerance: float = 1e-3,
        aim_tolerance: float = math.radians(3),
    ) -> Solution:
        """Joint positions within `joints` (id to low and high, in native units) that put `site` at `target`.

        Only the listed joints move. The solution that is reached and takes the least time at
        `speeds` wins, and when nothing reaches, the closest miss comes back with `reached` false.
        """
        with self._lock:
            qpos = np.array(self.data.qpos, dtype=float)
        ids = list(joints)
        low = np.array([joints[joint][0] for joint in ids])
        high = np.array([joints[joint][1] for joint in ids])
        address = np.array([self.model.jnt_qposadr[joint] for joint in ids])
        columns = np.array([self.model.jnt_dofadr[joint] for joint in ids])
        rates = np.array([((speeds or {}).get(joint) or 1.0) for joint in ids])
        start = np.clip(qpos[address], low, high)
        goal = np.array(target, dtype=float)
        best: tuple[bool, float, Any, float, float] | None = None
        with self._solve_lock:
            for seed in self._seeds(start, low, high, address):
                q, error, aim_error = self._descend(qpos, seed, address, columns, low, high, site, goal, aim)
                reached = error <= tolerance and aim_error <= aim_tolerance
                score = float(np.max(np.abs(q - start) / rates)) if reached else error + aim_error * AIM_WEIGHT
                candidate = (not reached, score, q, error, aim_error)
                if best is None or candidate[:2] < best[:2]:
                    best = candidate
                if reached and seed is start:
                    break
        assert best is not None
        missed, _score, q, error, aim_error = best
        return Solution(
            {joint: float(value) for joint, value in zip(ids, q, strict=True)}, error, aim_error, not missed
        )

    def _seeds(self, start: Any, low: Any, high: Any, address: Any) -> Iterable[Any]:
        yield start
        for key in range(self.model.nkey):
            yield np.clip(np.array(self.model.key_qpos[key], dtype=float)[address], low, high)
        for index in range(1, SEEDS + 1):
            spread = np.array([halton(index, PRIMES[i % len(PRIMES)]) for i in range(len(low))])
            yield low + (high - low) * spread

    def _descend(
        self,
        qpos: Any,
        seed: Any,
        address: Any,
        columns: Any,
        low: Any,
        high: Any,
        site: int,
        goal: Any,
        aim: Aim | None,
    ) -> tuple[Any, float, float]:
        data = self._scratch
        data.qpos[:] = qpos
        q = np.array(seed, dtype=float)
        jacp = np.zeros((3, self.model.nv))
        jacr = np.zeros((3, self.model.nv))
        rows = 6 if aim else 3
        jacobian = np.zeros((rows, len(columns)))
        residual = np.zeros(rows)
        solved = np.zeros(rows)
        damping = DAMPING * np.eye(rows)
        gx, gy, gz = (float(value) for value in goal)
        best = math.inf
        stalled = 0
        for iteration in range(ITERATIONS + 1):
            data.qpos[address] = q
            mujoco.mj_kinematics(self.model, data)
            mujoco.mj_comPos(self.model, data)
            sx, sy, sz = data.site_xpos[site].tolist()
            residual[:3] = (gx - sx, gy - sy, gz - sz)
            error = math.sqrt((gx - sx) ** 2 + (gy - sy) ** 2 + (gz - sz) ** 2)
            aim_error = 0.0
            if aim is not None:
                turn, aim_error = _turn(data.site_xmat[site].tolist(), aim)
                residual[3:] = [AIM_WEIGHT * part for part in turn]
            score = error + AIM_WEIGHT * aim_error
            stalled = stalled + 1 if score > best - 1e-7 else 0
            best = min(best, score)
            if (error < 2e-4 and aim_error < 2e-3) or iteration == ITERATIONS or stalled >= 10:
                break
            mujoco.mj_jacSite(self.model, data, jacp, jacr, site)
            jacobian[:3] = jacp[:, columns]
            if aim is not None:
                jacobian[3:] = AIM_WEIGHT * jacr[:, columns]
            factor = jacobian @ jacobian.T + damping
            mujoco.mju_cholFactor(factor, 0.0)
            mujoco.mju_cholSolve(solved, factor, residual)
            np.clip(q + jacobian.T @ solved, low, high, out=q)
        return q, error, aim_error


def _turn(xmat: list[float], aim: Aim) -> tuple[tuple[float, float, float], float]:
    """The rotation that brings the site's aim axis onto its world direction, and the angle between them."""
    ax, ay, az = aim.axis
    px = xmat[0] * ax + xmat[1] * ay + xmat[2] * az
    py = xmat[3] * ax + xmat[4] * ay + xmat[5] * az
    pz = xmat[6] * ax + xmat[7] * ay + xmat[8] * az
    tx, ty, tz = aim.toward
    turn = (py * tz - pz * ty, pz * tx - px * tz, px * ty - py * tx)
    size = math.sqrt(turn[0] ** 2 + turn[1] ** 2 + turn[2] ** 2)
    return turn, math.atan2(size, px * tx + py * ty + pz * tz)
