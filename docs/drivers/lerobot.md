# lerobot driver

The `lerobot` driver controls Hugging Face LeRobot arms, such as the SO-100, SO-101 and Koch followers. Joint positions are reads, goal positions are channels with per-joint limits and rates, and torque off is the native safe state.

| | |
|---|---|
| Driver name | `lerobot` |
| Library | LeRobot 0.6.1 (Apache-2.0), installed separately |
| Extra | none. Install LeRobot with `pip install 'lerobot[feetech]'`, or the extra for your motors |
| Hazard default | high |
| Conformance | full |
| Safe state | native. Torque off on every motor |
| Self-describe | yes, from the arm's joints and where they are now |

LeRobot pulls in PyTorch, which is several gigabytes and has no wheels for some machines, such as Intel Macs. So it is not an OpenHAL extra. The driver imports it only when a device connects and explains how to install it when it is missing.

## What it supports

| Channel name | Kind | LeRobot call |
|---|---|---|
| `<joint>`, for example `shoulder_pan` | read, deg (or -100 to 100), gripper in percent | `get_observation()["<joint>.pos"]` |
| `torque` | read, bool | `bus.sync_read("Torque_Enable")` on every motor |
| `<joint>_goal`, for example `elbow_flex_goal` | set, same unit as the joint | `send_action({"<joint>.pos": goal})` |
| `torque_off`, `torque_on` | action | `bus.disable_torque()`, `bus.enable_torque()` |
| `move` (one argument per joint) | action | one `send_action()` for several joints |

| Map | Meaning |
|---|---|
| `{ joint: wrist_flex }` | A joint under another channel name |
| `{ joint: x, unit: m/s }` | The unit LeRobot uses for that key, for robots that aren't arms |
| `{ torque: true }` | The torque state |
| `{ command: move, joints: { pan: shoulder_pan, lift: shoulder_lift } }` | A move action, each argument naming its joint |

Body joints are in degrees with `use_degrees: true`, LeRobot's default, and from -100 to 100 otherwise. Grippers are 0 to 100 percent open. Angles and plain numbers are never mixed, even though both count as dimensionless to the unit library.

## How it works

- connect() builds the robot from its LeRobot type and calls `connect(calibrate=False)`. Calibration moves the arm by hand and asks questions at the keyboard, so the driver never runs it. An uncalibrated arm is refused with the exact `lerobot-calibrate` command to run.
- Connecting turns torque on, so the arm holds where it is. Nothing moves.
- A goal channel reads the joint's present position until a goal is sent, because the servo holds there. The kernel's `max_change_per_s` is then measured from where the joint really is.
- A goal reads back as the value LeRobot actually wrote, after its own `max_relative_target` clipping.
- `torque_on` sends every present position as the goal first, so no joint jumps to an old goal.
- Every LeRobot call blocks on the serial bus, so it runs in a worker thread with a deadline.

## Safe state

A stop turns torque off on every motor. The arm goes limp and falls under gravity. Rest it over something soft while testing, and keep the power switch within reach. The device file's own safe state steps run afterwards, and with torque off they only set registers.

close() turns torque off too, LeRobot's `disable_torque_on_disconnect`, unless `torque_off_on_close: false`.

## Setup

1. Install LeRobot and its motor extra, for example `pip install 'lerobot[feetech]'` in the hub's environment.
2. Calibrate the arm once with `lerobot-calibrate --robot.type=so101_follower --robot.port=<port> --robot.id=<id>`.
3. Start from `openhal/drivers/lerobot/examples/so101-follower.hal.yaml`. Set the port and the id you calibrated with, and keep the goal limits narrow.
4. Run `openhal file validate`, then confirm the limits by hand.

## Parameters

| Key | Default | Meaning |
|---|---|---|
| `robot` | required | LeRobot robot type, for example `so101_follower` or `koch_follower` |
| `port` | required | Serial port of the motor bus |
| `robot_id` | required | The id the arm was calibrated under |
| `use_degrees` | true | Degrees for body joints, or -100 to 100 |
| `max_relative_target` | none | LeRobot's own clip on how far one goal may move from the present position, in degrees |
| `torque_off_on_close` | true | Turn torque off when the hub closes the device |
| `timeout` | `2 s` | Per call |
| `action_wait` | `8 s` | How long `move` waits for the joints to arrive before answering `started` |
| `observation_age` | `50 ms` | Reuse one observation across reads this close together |
| `tolerance` | 2 | How close, in the joint's unit, counts as arrived for `move` |

## Example device file

```yaml
device: SO-101 follower arm
id: so101
connect: { lerobot: so101_follower, port: /dev/ttyACM0, robot_id: my_follower, max_relative_target: 10 }
read:
  shoulder_pan: { unit: deg }
  torque: { type: bool }
write:
  shoulder_pan_goal: { unit: deg, min: -30, max: 30, max_change_per_s: 20, confirm: confirm-each-time }
actions:
  torque_off: {}
hazard: high
```

## Known limitations

- Cameras in the observation are ignored.
- The fake in `simulator.py` stands in for LeRobot in tests. The assumptions it makes are listed in its docstring and checked step by step in the hardware test plan.
- Kinematics and Cartesian moves are not exposed. Goals are per joint.
- `move` arguments get their limits from the action, not from the goal channels, so keep both the same.

## Hazard defaults

`high`. Arms can pinch and strike, and they fall when torque goes off. The kernel asks a person for every change and action.

## Sources

- LeRobot repository and robot interface, https://github.com/huggingface/lerobot (src/lerobot/robots/robot.py, so_follower)
- SO-101 guide, https://huggingface.co/docs/lerobot/so101
- Bring your own hardware, https://huggingface.co/docs/lerobot/integrate_hardware
