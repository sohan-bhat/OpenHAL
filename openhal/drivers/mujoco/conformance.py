"""The mujoco driver's conformance case, on a small bench arm that tests and the docs use too."""

from __future__ import annotations

import mujoco

from openhal.conformance import ConformanceCase
from openhal.drivers.base import Driver
from openhal.drivers.mujoco.driver import MujocoDriver
from openhal.spec import loads
from openhal.spec.models import DeviceFile

BENCH_ARM = """
<mujoco model="bench arm">
  <compiler angle="radian" autolimits="true"/>
  <option timestep="0.002" integrator="implicitfast"/>
  <default>
    <joint damping="0.5" armature="0.01"/>
    <position kp="100" kv="2"/>
    <geom contype="0" conaffinity="0" rgba="0.8 0.8 0.8 1"/>
  </default>
  <worldbody>
    <geom name="floor" type="plane" size="1 1 0.1" contype="1" conaffinity="1"/>
    <body name="base">
      <geom type="cylinder" size="0.03 0.05" pos="0 0 0.05" mass="1"/>
      <body name="turret" pos="0 0 0.1">
        <joint name="pan" axis="0 0 1" range="-2 2"/>
        <geom type="sphere" size="0.02" mass="0.1"/>
        <body name="upper">
          <joint name="lift" axis="0 1 0" range="-1.5 1.5"/>
          <geom type="capsule" fromto="0 0 0 0.12 0 0" size="0.012" mass="0.1"/>
          <body name="fore" pos="0.12 0 0">
            <joint name="elbow" axis="0 1 0" range="-2.5 2.5"/>
            <geom type="capsule" fromto="0 0 0 0.12 0 0" size="0.01" mass="0.08"/>
            <body name="hand" pos="0.12 0 0">
              <joint name="wrist" axis="0 1 0" range="-2 2"/>
              <geom type="box" size="0.02 0.01 0.01" pos="0.02 0 0" mass="0.05"/>
              <site name="tip" pos="0.05 0 0"/>
              <body name="finger" pos="0.03 0 0">
                <joint name="finger" type="slide" axis="0 1 0" range="0 0.03"/>
                <geom type="box" size="0.005 0.005 0.01" mass="0.01"/>
              </body>
            </body>
          </body>
        </body>
      </body>
    </body>
    <body name="block" pos="0.3 0.1 0.02">
      <freejoint name="block"/>
      <geom type="box" size="0.02 0.02 0.02" mass="0.05" contype="1" conaffinity="1"/>
    </body>
  </worldbody>
  <actuator>
    <position name="pan" joint="pan" ctrlrange="-2 2"/>
    <position name="lift" joint="lift" ctrlrange="-1.5 1.5"/>
    <position name="elbow" joint="elbow" ctrlrange="-2.5 2.5"/>
    <position name="wrist" joint="wrist" ctrlrange="-2 2"/>
    <position name="finger" joint="finger" ctrlrange="0 0.03" kp="200"/>
  </actuator>
  <keyframe>
    <key name="rest" qpos="0 -0.9 1.9 0.6 0.01 0.3 0.1 0.02 1 0 0 0" ctrl="0 -0.9 1.9 0.6 0.01"/>
  </keyframe>
</mujoco>
"""
"""A small four joint arm with a sliding finger and a loose block, for tests, the conformance case and the docs."""

FILE = loads(
    """
device: Simulated bench arm
id: mujoco-sim
connect: { mujoco: OPENHAL_BENCH_ARM, keyframe: rest, action_wait: 2 s }
read:
  pan: { unit: deg }
  finger: { unit: percent }
  tip_z: { unit: mm, map: { site: tip, axis: z } }
  block_x: { unit: mm, map: { body: block, axis: x } }
write:
  pan_goal: { unit: deg, min: 0, max: 90, max_change_per_s: 90 }
  lift_goal: { unit: deg, min: -85, max: 85, max_change_per_s: 90 }
  elbow_goal: { unit: deg, min: -140, max: 140, max_change_per_s: 90 }
  wrist_goal: { unit: deg, min: -110, max: 110, max_change_per_s: 90 }
  finger_goal: { unit: percent, min: 0, max: 100, max_change_per_s: 200 }
actions:
  move_to:
    args:
      x: { unit: mm, min: 140, max: 200 }
      y: { unit: mm, min: 0, max: 60 }
      z: { unit: mm, min: 30, max: 90 }
    map: { command: move_to, site: tip, aim: { axis: [1, 0, 0], toward: [0, 0, -1] } }
    effects: [pan_goal, lift_goal, elbow_goal, wrist_goal]
  hold: {}
safe_state: { action: hold }
hazard: medium
confirmed: { by: conformance, at: 2026-11-02 }
"""
)


def case() -> ConformanceCase:
    def make(file: DeviceFile) -> Driver:
        return MujocoDriver(file, loader=lambda: mujoco.MjModel.from_xml_string(BENCH_ARM))

    async def broken(driver: Driver) -> None:
        assert isinstance(driver, MujocoDriver)
        assert driver.world is not None
        driver.world.close()

    return ConformanceCase(name="mujoco", file=FILE, make=make, break_connection=broken)
