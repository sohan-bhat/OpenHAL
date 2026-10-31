"""A faithful fake of a LeRobot follower arm, for tests and the conformance case.

LeRobot pulls in PyTorch and does not install everywhere, so the driver is tested against this
fake of the `lerobot.robots.Robot` interface, modelled on LeRobot 0.6's SOFollower (SO-100 and
SO-101 arms on a Feetech bus). The driver never imports it outside tests and the conformance
case. Every assumption below has a step in docs/hardware-tests/lerobot.md that checks it on a
real arm.

1. `connect(calibrate=False)` opens the bus, never prompts and never moves the arm. It turns
   torque on, so the arm holds where it is.
2. `is_calibrated` is true once `lerobot-calibrate` has run for the same robot id.
3. `get_observation()` returns `<joint>.pos` floats, in degrees for body joints when
   `use_degrees` is true, and 0 to 100 for the gripper. Camera frames use other keys.
4. `send_action()` takes any subset of `<joint>.pos` keys and writes only those goals.
5. `send_action()` returns the goals it actually wrote, after clipping each one to within
   `max_relative_target` of the present position.
6. `bus.disable_torque()` and `bus.enable_torque()` switch torque on every motor, and
   `bus.sync_read("Torque_Enable")` reports it per motor as 0 or 1.
7. `disconnect()` turns torque off when `disable_torque_on_disconnect` is true.
8. A lost bus raises ConnectionError from every call, as LeRobot's motor buses do.
9. A motor whose torque comes back on drives to its Goal_Position register, and `send_action()`
   still writes that register while torque is off. So the driver writes the present positions
   as goals before it turns torque back on.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any

JOINTS = ("shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll", "gripper")


@dataclass
class FakeConfig:
    """The fields of LeRobot's SOFollowerRobotConfig the driver passes."""

    port: str
    id: str | None = None
    use_degrees: bool = True
    max_relative_target: float | dict[str, float] | None = None
    disable_torque_on_disconnect: bool = True
    cameras: dict[str, Any] = field(default_factory=dict)


class FakeBus:
    """The part of LeRobot's FeetechMotorsBus the driver touches."""

    def __init__(self, arm: FakeFollower) -> None:
        self.arm = arm
        self.torque = False

    def disable_torque(self, motors: Any = None, num_retry: int = 0) -> None:
        self.arm.check()
        self.arm.calls.append(("disable_torque", {}))
        self.torque = False

    def enable_torque(self, motors: Any = None, num_retry: int = 0) -> None:
        self.arm.check()
        self.arm.calls.append(("enable_torque", {}))
        self.torque = True

    def sync_read(self, data_name: str, motors: Any = None) -> dict[str, Any]:
        self.arm.check()
        if data_name == "Torque_Enable":
            return dict.fromkeys(JOINTS, 1 if self.torque else 0)
        if data_name == "Present_Position":
            return self.arm.positions()
        raise ValueError(f"the fake bus doesn't support {data_name}")


class FakeFollower:
    """A six joint follower arm that moves toward its goals at `speed` degrees per second."""

    name = "so101_follower"

    def __init__(self, config: FakeConfig, *, calibrated: bool = True) -> None:
        self.config = config
        self.id = config.id
        self.calibrated = calibrated
        self.connected = False
        self.bus = FakeBus(self)
        self.speed = 90.0
        self.lost = False
        self.latency_s = 0.0
        self.fail_next = 0
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.present = {
            "shoulder_pan": 0.0,
            "shoulder_lift": -90.0,
            "elbow_flex": 90.0,
            "wrist_flex": 0.0,
            "wrist_roll": 0.0,
            "gripper": 10.0,
        }
        self.goal = dict(self.present)
        self._moved_at = time.monotonic()
        self._lock = threading.Lock()

    @property
    def observation_features(self) -> dict[str, Any]:
        return {f"{joint}.pos": float for joint in JOINTS}

    @property
    def action_features(self) -> dict[str, Any]:
        return {f"{joint}.pos": float for joint in JOINTS}

    @property
    def is_connected(self) -> bool:
        return self.connected and not self.lost

    @property
    def is_calibrated(self) -> bool:
        return self.calibrated

    def check(self) -> None:
        if self.latency_s:
            time.sleep(self.latency_s)
        if self.lost:
            raise ConnectionError("Failed to sync read 'Present_Position' on ids=[1, 2, 3, 4, 5, 6] after 2 tries.")
        if not self.connected:
            raise ConnectionError(f"{self.id} SOFollower is not connected.")
        if self.fail_next > 0:
            self.fail_next -= 1
            raise ConnectionError("[TxRxResult] There is no status packet.")

    def connect(self, calibrate: bool = True) -> None:
        if self.lost:
            raise ConnectionError(f"Could not connect on port '{self.config.port}'.")
        if calibrate and not self.calibrated:
            raise RuntimeError("calibration would prompt for input, which the driver must never do")
        self.calls.append(("connect", {"calibrate": calibrate}))
        self.connected = True
        self.configure()

    def calibrate(self) -> None:
        raise RuntimeError("calibration moves the arm by hand and prompts, the driver never calls it")

    def configure(self) -> None:
        self.bus.torque = True

    def _step(self) -> None:
        now = time.monotonic()
        travel = (now - self._moved_at) * self.speed
        self._moved_at = now
        if not self.bus.torque:
            return
        for joint in JOINTS:
            gap = self.goal[joint] - self.present[joint]
            self.present[joint] += max(-travel, min(travel, gap))

    def positions(self) -> dict[str, float]:
        with self._lock:
            self._step()
            return dict(self.present)

    def get_observation(self) -> dict[str, Any]:
        self.check()
        observation: dict[str, Any] = {f"{joint}.pos": value for joint, value in self.positions().items()}
        observation["front"] = b"\x00" * 16
        return observation

    def send_action(self, action: dict[str, Any]) -> dict[str, Any]:
        self.check()
        goals = {key.removesuffix(".pos"): float(value) for key, value in action.items() if key.endswith(".pos")}
        unknown = set(goals) - set(JOINTS)
        if unknown:
            raise KeyError(f"unknown motors {sorted(unknown)}")
        with self._lock:
            self._step()
            limit = self.config.max_relative_target
            if limit is not None:
                for joint, goal in goals.items():
                    cap = limit[joint] if isinstance(limit, dict) else limit
                    present = self.present[joint]
                    goals[joint] = max(present - cap, min(present + cap, goal))
            self.goal.update(goals)
        self.calls.append(("send_action", dict(goals)))
        return {f"{joint}.pos": value for joint, value in goals.items()}

    def disconnect(self) -> None:
        if not self.connected:
            raise ConnectionError(f"{self.id} SOFollower is not connected.")
        if self.config.disable_torque_on_disconnect and not self.lost:
            self.bus.torque = False
        self.calls.append(("disconnect", {}))
        self.connected = False


class FakeFactory:
    """Builds one FakeFollower per connect, like a fresh LeRobot robot object, and keeps the last."""

    def __init__(self, *, calibrated: bool = True) -> None:
        self.calibrated = calibrated
        self.arm: FakeFollower | None = None
        self.configs: list[FakeConfig] = []
        self.lost = False

    def __call__(self, robot_type: str, settings: dict[str, Any]) -> FakeFollower:
        config = FakeConfig(**settings)
        self.configs.append(config)
        arm = FakeFollower(config, calibrated=self.calibrated)
        arm.lost = self.lost
        if self.arm is not None:
            arm.present = dict(self.arm.present)
            arm.goal = dict(self.arm.present)
        self.arm = arm
        return arm
