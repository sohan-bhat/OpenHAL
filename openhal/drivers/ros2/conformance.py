"""The ROS 2 driver's conformance case, against the simulated rosbridge in its own thread."""

from __future__ import annotations

import asyncio

from openhal.conformance import ConformanceCase
from openhal.drivers.base import Driver
from openhal.drivers.ros2.driver import Ros2Driver
from openhal.drivers.ros2.simulator import RosbridgeSim, ServerThread
from openhal.spec import loads
from openhal.spec.models import DeviceFile

FILE = """
device: Simulated ROS 2 robot
id: ros2-sim
connect: {{ ros2: 127.0.0.1, port: {port}, timeout: 500 ms, action_wait: 1 s }}
read:
  battery:
    unit: percent
    map: {{ topic: /battery_state, type: sensor_msgs/msg/BatteryState, field: percentage, unit: dimensionless }}
  odom_x: {{ unit: m, map: {{ topic: /odom, type: nav_msgs/msg/Odometry, field: pose.pose.position.x, unit: m }} }}
write:
  drive:
    unit: m/s
    min: -0.2
    max: 0.2
    confirm: confirm-each-time
    map:
      topic: /cmd_vel
      type: geometry_msgs/msg/Twist
      field: linear.x
      base: {{ linear: {{ x: 0, y: 0, z: 0 }}, angular: {{ x: 0, y: 0, z: 0 }} }}
actions:
  reset_odometry: {{ confirm: confirm-each-time, map: {{ service: /reset_odometry, type: std_srvs/srv/Trigger }} }}
safe_state: {{ drive: 0 }}
hazard: high
confirmed: {{ by: conformance, at: 2026-10-24 }}
"""


def case() -> ConformanceCase:
    sim = RosbridgeSim()
    sim.time_scale = 10
    thread = ServerThread(sim)
    port = thread.start()

    def make(file: DeviceFile) -> Driver:
        return Ros2Driver(file)

    async def broken(driver: Driver) -> None:
        thread.call(sim.drop_clients)
        for _ in range(200):
            if not (await driver.health()).connected:
                return
            await asyncio.sleep(0.01)

    async def slow(driver: Driver) -> None:
        sim.silent = True

    async def cleanup() -> None:
        sim.silent = False
        thread.stop()

    return ConformanceCase(
        name="ros2",
        file=loads(FILE.format(port=port)),
        make=make,
        break_connection=broken,
        make_slow=slow,
        cleanup=cleanup,
    )
