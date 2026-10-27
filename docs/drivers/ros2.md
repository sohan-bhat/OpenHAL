# ros2 driver

The `ros2` driver reaches ROS 2 robots through rosbridge. Topic fields become read channels, publishing to a topic or calling a service sets a channel, and services, topics and action goals become actions. The driver is a bridge, so only the topics, services and actions the device file names are touched.

| | |
|---|---|
| Driver name | `ros2` |
| Library | websockets 17 (BSD-3-Clause), already a hub dependency. The rosbridge v2 client is the driver's own |
| Extra | `uv tool install --compile-bytecode "openhal-hub[ros2] @ git+https://github.com/sohan-bhat/OpenHAL"` |
| Hazard default | high |
| Conformance | full |
| Safe state | native. Cancels every action goal this driver started |
| Self-describe | yes, from rosapi |

## What it supports

Every channel and action names its ROS endpoint in a `map`.

| Map | Meaning |
|---|---|
| `{ topic: /battery_state, type: sensor_msgs/msg/BatteryState, field: percentage, unit: dimensionless }` | Read one field of the newest message on a topic |
| `{ topic: /cmd_vel, type: geometry_msgs/msg/Twist, field: linear.x, unit: m/s, base: { ... } }` | Set a channel by publishing `base` with one field set |
| `{ service: /set_lamp, type: std_srvs/srv/SetBool, field: data }` | Set a channel by calling a service with one field set |
| `{ service: /reset_odometry, type: std_srvs/srv/Trigger }` | An action that calls a service. A reply with `success: false` fails it |
| `{ action: /navigate, type: nav2_msgs/action/NavigateToPose, args: { x: pose.pose.position.x } }` | An action that sends a goal. Each argument names the field it fills |
| `{ topic: /goal_point, type: geometry_msgs/msg/Point, args: { x: x, y: y } }` | An action that publishes one message |

`field` is a dotted path, with numbers for list items (`ranges.0`). `unit` is the unit ROS uses for the field, which REP 103 makes SI, such as `m/s`, `rad`, `degC` and fractions from 0 to 1 for percentages. `scale` multiplies the ROS value, and `integer: true` sends whole numbers to int fields. An argument can be a plain field path or `{ field, unit, scale, integer }`.

## How the protocol is handled

- connect() opens the WebSocket, subscribes to each read topic once and advertises each topic the file publishes to, so the first message isn't lost while DDS matches publishers and subscribers.
- Reads come from the newest message on each topic, with its arrival time, and a channel is unknown until its first message arrives.
- rosbridge reports a refused subscription or advertisement in a status line, and reads and changes on that topic then fail with the reported reason, while health shows the last refusal.
- Because publishing has no reply in rosbridge, a set channel reads back as the last value the driver sent.
- A goal waits up to `action_wait` for its result and returns `done`, or returns `started` and keeps running. Aborted and canceled goals fail with their status.

## Safe state

A stop cancels every goal this driver started that is still running and waits up to 2 s for each goal to end. ROS has no general stop command, so put the robot's own stop in the device file, for example a `cmd_vel` channel set to 0 in `safe_state`. The kernel publishes that stop right after the cancel.

Many bases stop on their own when `cmd_vel` messages stop arriving, and many do not, so check your robot's base and keep a physical stop within reach.

## Setup

1. On the robot, run rosbridge, for example `ros2 launch rosbridge_server rosbridge_websocket_launch.xml`. The default launch file starts rosapi too.
2. Run `ros2 topic list -t` to see the topics and their types.
3. Start from `openhal/drivers/ros2/examples/turtlebot4.hal.yaml`, or call `describe` for a proposal, and keep only what you need.
4. Run `openhal file validate`, then confirm the limits by hand.

## Parameters

| Key | Default | Meaning |
|---|---|---|
| `host` | required | rosbridge host name or address |
| `port` | 9090 | rosbridge port |
| `scheme` | `ws` | `ws` or `wss` |
| `path` | empty | URL path, for a rosbridge behind a proxy |
| `timeout` | `5 s` | How long to wait for a service reply |
| `action_wait` | `8 s` | How long a goal waits for its result before answering `started`. At most 9 s |
| `throttle` | `0 s` | Smallest gap between messages rosbridge sends per topic |

## Example device file

```yaml
device: TurtleBot 4
id: turtlebot
connect: { ros2: turtlebot4.local, port: 9090 }
read:
  battery:
    unit: percent
    map: { topic: /battery_state, type: sensor_msgs/msg/BatteryState, field: percentage, unit: dimensionless }
write:
  cmd_vel_linear:
    unit: m/s
    min: -0.1
    max: 0.1
    max_change_per_s: 0.2
    confirm: confirm-each-time
    map:
      topic: /cmd_vel
      type: geometry_msgs/msg/Twist
      field: linear.x
      base: { linear: { x: 0, y: 0, z: 0 }, angular: { x: 0, y: 0, z: 0 } }
actions:
  dock: { confirm: confirm-each-time, map: { action: /dock, type: irobot_create_msgs/action/Dock } }
safe_state:
  - { cmd_vel_linear: 0 }
hazard: high
```

## Known limitations

- Images and point clouds are not read, and messages above 4 MB are refused.
- Velocity commands are published once per change, so robots that need a steady stream of `cmd_vel` stop after their own timeout.
- Because rosauth is not supported, keep rosbridge on a trusted network.
- QoS settings use rosbridge's defaults.

## Hazard defaults

The default hazard is `high`, because mobile robots and arms can injure. Every change and action waits for a person's approval, and velocity channels need small limits and a `max_change_per_s`.

## Sources

- rosbridge v2 protocol, https://github.com/RobotWebTools/rosbridge_suite/blob/ros2/ROSBRIDGE_PROTOCOL.md
- rosapi services, https://github.com/RobotWebTools/rosbridge_suite/tree/ros2/rosapi
- REP 103, standard units of measure, https://www.ros.org/reps/rep-0103.html
- action_msgs/msg/GoalStatus, https://docs.ros2.org/latest/api/action_msgs/msg/GoalStatus.html
