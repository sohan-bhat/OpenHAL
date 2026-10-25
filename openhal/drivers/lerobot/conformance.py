"""The LeRobot driver's conformance case, against the fake SO-101 follower."""

from __future__ import annotations

from openhal.conformance import ConformanceCase
from openhal.drivers.base import Driver
from openhal.drivers.lerobot.driver import LeRobotDriver
from openhal.drivers.lerobot.simulator import FakeFactory
from openhal.spec import loads
from openhal.spec.models import DeviceFile

FILE = loads(
    """
device: Fake SO-101 follower
id: lerobot-sim
connect: { lerobot: so101_follower, port: /dev/fake, robot_id: conformance, timeout: 500 ms, observation_age: 0 s }
read:
  shoulder_pan: { unit: deg }
  gripper: { unit: percent }
  torque: { type: bool }
write:
  shoulder_pan_goal: { unit: deg, min: 0, max: 30, max_change_per_s: 30, confirm: confirm-each-time }
actions:
  torque_off: {}
safe_state: { shoulder_pan_goal: 0 }
hazard: high
confirmed: { by: conformance, at: 2026-10-24 }
"""
)


def case() -> ConformanceCase:
    factory = FakeFactory()

    def make(file: DeviceFile) -> Driver:
        return LeRobotDriver(file, robot_factory=factory)

    async def broken(driver: Driver) -> None:
        assert factory.arm is not None
        factory.arm.lost = True

    async def slow(driver: Driver) -> None:
        assert factory.arm is not None
        factory.arm.latency_s = 3.0

    async def cleanup() -> None:
        if factory.arm is not None:
            factory.arm.latency_s = 0.0

    return ConformanceCase(
        name="lerobot", file=FILE, make=make, break_connection=broken, make_slow=slow, cleanup=cleanup
    )
