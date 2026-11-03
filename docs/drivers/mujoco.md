# mujoco driver

The `mujoco` driver runs any MuJoCo model in real time as a device. Joints are reads, actuators are goal channels with limits and speeds, `move_to` puts a site at a point, and a stop holds every joint where it stands. The driver never reaches hardware and reports itself as simulated.

| | |
|---|---|
| Driver name | `mujoco` |
| Library | MuJoCo 3.3 or later (Apache-2.0), 3.10 on Intel Macs |
| Extra | `uv tool install --compile-bytecode "ohal[mujoco] @ git+https://github.com/sohan-bhat/OpenHAL"` |
| Hazard default | medium |
| Conformance | full |
| Safe state | native. Every move ends and every setpoint holds |
| Self-describe | yes, from the model's joints and actuators |

MuJoCo has no wheels for Intel Macs after 3.10, so the extra pins 3.10 there.

## What it supports

| Map | Kind | MuJoCo |
|---|---|---|
| `{ joint: shoulder_pan }`, or a channel named like the joint | read | the joint's position |
| `{ site: tip, axis: z }`, `{ body: cube, axis: x }` | read | a site's or a body's world position on one axis |
| `{ actuator: gripper }`, or a channel named `<actuator>_goal` | set | the actuator's control value |
| `{ command: move_to, site: tip }` | action | inverse kinematics on the site's Jacobian, then a move |
| `{ command: hold }`, or an action named `hold` | action | every setpoint stays where it is |

Hinge joints and their actuators are in radians and slides in metres, so any angle or length unit converts. A channel in percent spans the joint's range, or the actuator's `ctrlrange`, from its low end at 0 to its high end at 100. An actuator that doesn't drive a joint takes its unit from `map.unit`.

### move_to

| Key | Meaning |
|---|---|
| `site` | The site that moves |
| `axes` | Which axis each argument sets. Arguments named `x`, `y` and `z` set their own axis |
| `at` | Fixed coordinates for the axes no argument sets, such as `{ x: 120 mm }` |
| `aim` | `{ axis: [1, 0, 0], toward: [0, 0, -1] }` points the site's own x axis straight down |
| `joints` | The joints the move may turn. The default is every actuated joint in the site's chain |
| `then` | Goal channels to set once the site arrives, such as `{ gripper_goal: 60 }` |

The action's arguments are the coordinates in a length unit, and their limits are the workspace box the kernel checks. The driver solves joint positions inside both the model's ranges and the file's own goal limits, and a point out of reach fails with the closest miss. Every joint moves at most at its goal channel's `max_change_per_s`, and all of them arrive together. Every goal channel the move changes, `then` included, must be in the action's `effects`, so the kernel reads it back after the move.

## How it works

- connect() loads the model from the path in the environment variable `model_env` names, resets it to `keyframe` when one is set, checks every map against the model and starts stepping in real time on its own thread.
- A goal moves along a minimum-jerk path whose peak speed is the channel's `max_change_per_s`, and a goal channel reads back where the actuator is headed. A channel with no speed jumps in one step.
- A new goal takes over only the actuators it names, and a move already going keeps the others.
- `move_to` waits up to `action_wait` for the move and returns `done`, or `started` when the move is still going.

## Safe state

A stop ends every move and freezes every setpoint, so position servos hold the joints where they stand and a closed gripper keeps its grip. A device file can add steps after that. A real arm on the lerobot driver goes limp on a stop instead, so a file for a real arm keeps that arm's own safe state.

## Parameters

| Key | Default | Meaning |
|---|---|---|
| `model_env` | required | Name of the environment variable that holds the MJCF file's path |
| `keyframe` | none | The model keyframe to start from |
| `timestep` | the model's | Physics step, such as `4 ms` |
| `action_wait` | `8 s` | How long `move_to` waits before returning `started` |
| `tolerance` | `1 mm` | How close the site must get for a point to count as reached |
| `aim_tolerance` | `3 deg` | How close the aim must get |

## Example device file

```yaml
device: Bench arm (simulated)
id: bench-arm
connect: { mujoco: OPENHAL_BENCH_ARM, keyframe: rest }
read:
  pan: { unit: deg, every: 500 ms }
  block_x: { unit: mm, map: { body: block, axis: x } }
write:
  pan_goal: { unit: deg, min: -90, max: 90, max_change_per_s: 60 }
  lift_goal: { unit: deg, min: -85, max: 85, max_change_per_s: 60 }
  elbow_goal: { unit: deg, min: -140, max: 140, max_change_per_s: 60 }
  wrist_goal: { unit: deg, min: -110, max: 110, max_change_per_s: 90 }
actions:
  move_to:
    args:
      x: { unit: mm, min: 140, max: 200 }
      y: { unit: mm, min: -60, max: 60 }
      z: { unit: mm, min: 30, max: 90 }
    map: { command: move_to, site: tip, aim: { axis: [1, 0, 0], toward: [0, 0, -1] } }
    effects: [pan_goal, lift_goal, elbow_goal, wrist_goal]
  hold: {}
safe_state: { action: hold }
hazard: medium
```

The bench arm's model is `BENCH_ARM` in `openhal/drivers/mujoco/conformance.py`. The film's SO-101 file is `video/hub/so101-sim.hal.yaml`.

## Known limitations

- `move_to` follows a straight line in joint space, not in space, so a long move can bow. Short moves near the work stay close to straight.
- A stop freezes setpoints, and a joint that lagged behind its setpoint settles onto it within a few hundredths of a second.
- The physics thread shares the Python interpreter with the hub, so a busy hub can leave simulated time a little behind the clock. The health detail shows how far.

## Hazard defaults

The default hazard is `medium`. A simulation can't hurt anyone, but a file written for a simulated machine is often the draft of one for the real machine, which may need `high`.

## Sources

- MuJoCo Python bindings, https://mujoco.readthedocs.io/en/stable/python.html
- MuJoCo API reference for `mj_jacSite`, https://mujoco.readthedocs.io/en/stable/APIreference/APIfunctions.html
- MuJoCo Menagerie, https://github.com/google-deepmind/mujoco_menagerie
