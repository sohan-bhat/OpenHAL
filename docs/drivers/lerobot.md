# lerobot driver

The `lerobot` driver controls LeRobot arms such as the SO-100, SO-101 and Koch followers through LeRobot 0.6.1. Install LeRobot separately, such as `pip install 'lerobot[feetech]'`, since LeRobot pulls in PyTorch, which lacks wheels for some machines such as Intel Macs.

## Supports

| Channel name | Kind | LeRobot call |
|---|---|---|
| `<joint>` such as `shoulder_pan` | read, deg or -100 to 100, gripper in percent | `get_observation()["<joint>.pos"]` |
| `torque` | read, bool | `bus.sync_read("Torque_Enable")` on every motor |
| `<joint>_goal` such as `elbow_flex_goal` | set, same unit as the joint | `send_action({"<joint>.pos": goal})` |
| `torque_off`, `torque_on` | action | `bus.disable_torque()`, `bus.enable_torque()` |
| `move` with one argument per joint | action | one `send_action()` for several joints |

| Map | Meaning |
|---|---|
| `{ joint: wrist_flex }` | A joint under another channel name |
| `{ joint: x, unit: m/s }` | The unit LeRobot uses for that key, for robots that aren't arms |
| `{ torque: true }` | The torque state |
| `{ command: move, joints: { pan: shoulder_pan, lift: shoulder_lift } }` | A move action, each argument naming a joint |

Body joints read in degrees, or -100 to 100 with `use_degrees: false`. Grippers read 0 to 100 percent open.

## Behavior

- The driver never calibrates. An uncalibrated arm fails to connect with the `lerobot-calibrate` command to run.
- Connecting turns torque on, so the arm holds position.
- A goal channel reads the present position until a goal is sent, so `max_change_per_s` counts from the real position. Read-back shows the goal after `max_relative_target` clipping.
- `torque_on` first sets every goal to the present position, so no joint jumps.

## Safe state

A stop turns torque off, so the arm goes limp and falls. Rest the arm over something soft while testing. `close()` also turns torque off unless `torque_off_on_close: false`.

## Setup

1. Install LeRobot with the motor extra in the hub's environment.
2. Calibrate once with `lerobot-calibrate --robot.type=so101_follower --robot.port=<port> --robot.id=<id>`.
3. Start from `openhal/drivers/lerobot/examples/so101-follower.hal.yaml` and keep goal limits narrow.

| Key | Default | Meaning |
|---|---|---|
| `robot` | required | LeRobot type such as `so101_follower` or `koch_follower` |
| `port` | required | Motor bus serial port |
| `robot_id` | required | Calibration id |
| `use_degrees` | true | Degrees for body joints, or -100 to 100 |
| `max_relative_target` | none | LeRobot's clip on one goal's distance from the present position, in degrees |
| `torque_off_on_close` | true | Torque off when the hub closes the device |
| `timeout` | `2 s` | Per call |
| `action_wait` | `8 s` | Time `move` allows for arrival before returning `started` |
| `observation_age` | `50 ms` | Observation reuse window |
| `tolerance` | 2 | Arrival tolerance for `move`, in the joint's unit |

## Known limitations

- No camera reads, kinematics or Cartesian moves.
- `move` uses the action's limits, so match the action limits to the goal channels.
- Tests use the fake in `simulator.py`, and the hardware test plan checks the fake's assumptions.

## Hazard defaults

`high`, so the hub holds every change and action until a person approves the request.

## Sources

- LeRobot repository, robot interface in src/lerobot/robots/robot.py and so_follower, https://github.com/huggingface/lerobot
- SO-101 guide, https://huggingface.co/docs/lerobot/so101
- Bring your own hardware, https://huggingface.co/docs/lerobot/integrate_hardware
