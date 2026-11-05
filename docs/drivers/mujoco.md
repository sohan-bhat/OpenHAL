# mujoco driver

The `mujoco` driver runs any MuJoCo model in real time as a simulated device, on MuJoCo 3.3 or later, or 3.10 on Intel Macs. Joints are reads, actuators are goal channels, `move_to` puts a site at a point, and a stop holds every joint. `describe()` builds channels from the model.

## Supports

| Map | Kind | MuJoCo |
|---|---|---|
| `{ joint: shoulder_pan }`, or a channel named like the joint | read | the joint's position |
| `{ site: tip, axis: z }`, `{ body: cube, axis: x }` | read | a site's or a body's world position on one axis |
| `{ camera: overhead, width: 640, height: 480 }` on a `type: image` channel | read | a PNG frame from a camera the model names |
| `{ actuator: gripper }`, or a channel named `<actuator>_goal` | set | the actuator's control value |
| `{ command: move_to, site: tip }` | action | inverse kinematics on the site's Jacobian, then a move |
| `{ command: hold }`, or an action named `hold` | action | every setpoint holds |

Hinges are in radians and slides in metres, so any angle or length unit converts. A percent channel spans the joint's range or the actuator's `ctrlrange`, with 0 at the low end. An actuator without a joint takes `map.unit`.

### move_to

| Key | Meaning |
|---|---|
| `site` | The site that moves |
| `axes` | The axis each argument sets. Arguments named `x`, `y` and `z` set their own axis |
| `at` | Fixed coordinates for axes no argument sets, such as `{ x: 120 mm }` |
| `aim` | `{ axis: [1, 0, 0], toward: [0, 0, -1] }` points the site's x axis straight down |
| `joints` | Joints the move may turn, by default every actuated joint in the site's chain |
| `then` | Goal channels to set once the site arrives, such as `{ gripper_goal: 60 }` |
| `speed` | The argument that sets the move's speed, angular for hinges and linear for slides |

The arguments are coordinates whose limits are the workspace box the kernel checks. Solutions stay inside the model's ranges and the goal limits, and an unreachable point fails with the closest miss. Joints arrive together, each within the goal channel's `max_change_per_s`. With `speed`, the argument's `max` is a speed limit the kernel checks, blocking faster requests with LIMIT_EXCEEDED, and `min` must be above zero. Every goal channel the move changes, `then` included, must be in `effects`.

### Cameras

A camera in the MJCF model, fixed or on a moving body, becomes an image channel returning a PNG, 640 by 480 by default and at most 2048 a side.

```yaml
read:
  overhead: { type: image, map: { camera: overhead, width: 640, height: 480 } }
```

Rendering needs OpenGL, so without a display set `MUJOCO_GL` to `egl` or `osmesa` before the hub starts. The first frame of a size takes a few tenths of a second, and later frames about 10 ms.

## Behavior

- `connect()` loads the model from the path in the `model_env` variable, resets to `keyframe` if set, checks every map and steps in real time on a separate thread.
- A goal follows a minimum-jerk path peaking at the channel's `max_change_per_s` and reads back the target. A channel with no speed jumps in one step.
- A new goal takes over only the actuators the goal names, and a running move keeps the rest.
- `move_to` returns `done`, or `started` after `action_wait`.
- Each change records its actuator targets in the audit entry's `native` field.

## Safe state

A stop ends every move and freezes every setpoint, so servos hold the joints. A real arm on the lerobot driver goes limp instead, so a real arm's file keeps that arm's own safe state.

## Parameters

| Key | Default | Meaning |
|---|---|---|
| `model_env` | required | Variable holding the MJCF file's path |
| `keyframe` | none | Starting keyframe |
| `timestep` | the model's | Physics step, such as `4 ms` |
| `action_wait` | `8 s` | Time before `move_to` returns `started` |
| `tolerance` | `1 mm` | Distance that counts as reached |
| `aim_tolerance` | `3 deg` | Aim error that counts as reached |

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

The bench arm's model is `BENCH_ARM` in `openhal/drivers/mujoco/conformance.py`.

## Known limitations

- `move_to` moves in a straight line in joint space, so long moves can bow.
- A busy hub can leave simulated time a little behind the clock, as the health detail shows.
- Camera frames have no lens distortion or noise.

## Hazard defaults

`medium`, since a file for a simulated machine is often the draft for a real one, which may need `high`.

## Sources

- MuJoCo Python bindings, https://mujoco.readthedocs.io/en/stable/python.html
- MuJoCo API reference for `mj_jacSite`, https://mujoco.readthedocs.io/en/stable/APIreference/APIfunctions.html
- MuJoCo Python rendering, `mujoco.Renderer` and `MUJOCO_GL`, https://mujoco.readthedocs.io/en/stable/python.html#rendering
- MuJoCo Menagerie, https://github.com/google-deepmind/mujoco_menagerie
