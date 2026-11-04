# 0021 A general mujoco driver for simulated machines

## Context

The launch film shows an agent driving an SO-101 arm through the hub. The owner's rule is that the motion in the film comes from OpenHAL itself, so the blocks, the hold for approval and the STOP in the film are what the hub really does. That needs an arm in a physics simulator that the hub drives like any device, with limits, a move to a point, a gripper, an action held for a person and a safe state.

The owner's standing rule is no hardcoding, so the simulator has to take any MuJoCo model, not only the SO-101.

Simulators in the repository today sit behind a driver's own protocol, such as the firmware boards behind `port: sim:<name>` and the fake LeRobot follower behind the lerobot driver's robot factory. The driver is the real one and only the far end is simulated.

## Options considered

1. A MuJoCo backend for the lerobot driver, in place of the fake follower. The driver would be the one that runs real arms. But the kernel always runs a driver's native safe state first, and the lerobot driver's is torque off, so a simulated arm would fall on every stop. LeRobot's robot interface has joint goals only, so a move to a point would add Cartesian moves to a driver whose real arms can't do them. And it would cover LeRobot arms only.
2. A small general `mujoco` driver. One device file is one MJCF model. Joints become read channels, actuators become goal channels, and a `move_to` action solves the joint positions with MuJoCo's own site Jacobian.

## Decision

Option 2, the `mujoco` driver, an optional extra on the official `mujoco` package.

- The model's path comes from the environment variable that `model_env` names, as `deck_env` and `ca_env` do, because a device file never names a file the hub opens.
- `simulator.World` steps one model in real time on its own thread, as the other simulators run beside their drivers. The driver calls the world and never steps MuJoCo itself, and it reports itself as simulated.
- A goal moves along a minimum-jerk path whose peak speed is the channel's `max_change_per_s`. `move_to` moves only actuated joints in the site's chain, or the ones its map names, keeps them inside both the model's ranges and the file's goal limits, and moves each at most at its channel's speed. A point out of reach fails in the driver with the closest miss.
- Every goal channel a move changes must be in the action's `effects`, so the kernel reads it back. A file that leaves one out doesn't connect.
- The native safe state ends every move and holds every setpoint, so a stop freezes a simulated arm where it stands and a closed gripper keeps its grip. A file can add its own steps after that.
- The catalog lists the driver as tier 0, beside the mock driver, because it drives no hardware. The README's device count stays unchanged.
- The conformance case and the tests use a small built-in arm and skip when the extra isn't installed. A conformance case now skips any driver whose optional dependency is missing, with the registry's install hint as the reason.
- MuJoCo stopped shipping Intel Mac wheels after 3.10, so the extra pins `mujoco<3.11` there and takes any version from 3.3 elsewhere.

## Consequences

- Any MJCF model, such as a MuJoCo Menagerie robot, runs as a device with a device file and no new code.
- The kernel checks a `move_to` point against the action's argument limits, the workspace box. It doesn't see the joint angles the driver solves, so the driver keeps them inside the goal limits a person confirmed and moves them no faster than those channels allow.
- A simulated device can be medium hazard where the real machine is high, because a simulation can't hurt anyone. Its file says so in its notes.

## Cameras, added 2026-11-04

The owner asked how the hub and the model know what to avoid. A camera the MJCF model names now becomes an image channel, `{ camera: name, width, height }` on a `type: image` read.

- A read renders the camera offscreen with `mujoco.Renderer` and returns a PNG, encoded with the standard library, so the extra needs no imaging package and an agent gets the frame like a uvc or rpi_camera frame.
- The frame comes from one whole physics step, read under the world's lock, and the renders run on one thread the driver owns, because an OpenGL context belongs to its thread.
- Rendering needs OpenGL. Without it only the image channel fails, with advice to set `MUJOCO_GL` to `egl` or `osmesa`. The tests that render skip where no OpenGL context can be made, and the rest of the camera code runs everywhere against a stand-in renderer.
- A camera reads and never moves anything, so it adds no write channel, no action and no risk to the device.
