# ros2 driver

The `ros2` driver reaches ROS 2 robots through rosbridge, with a built-in rosbridge v2 client on websockets 17. Topic fields become reads, publishing or calling a service sets a channel, and services, topics and action goals become actions. Only the topics, services and actions the device file names are touched. `describe` drafts a file from rosapi.

## Supports

Every channel and action names a ROS endpoint in a `map`.

| Map | Meaning |
|---|---|
| `{ topic: /battery_state, type: sensor_msgs/msg/BatteryState, field: percentage, unit: dimensionless }` | Read one field of the newest message on a topic |
| `{ topic: /cmd_vel, type: geometry_msgs/msg/Twist, field: linear.x, unit: m/s, base: { ... } }` | Set a channel by publishing `base` with one field set |
| `{ service: /set_lamp, type: std_srvs/srv/SetBool, field: data }` | Set a channel by calling a service with one field set |
| `{ service: /reset_odometry, type: std_srvs/srv/Trigger }` | An action that calls a service. A `success: false` reply fails the action |
| `{ action: /navigate, type: nav2_msgs/action/NavigateToPose, args: { x: pose.pose.position.x } }` | An action that sends a goal, each argument naming a goal field |
| `{ topic: /goal_point, type: geometry_msgs/msg/Point, args: { x: x, y: y } }` | An action that publishes one message |

`field` is a dotted path with numbers for list items, such as `ranges.0`. `unit` is the ROS unit, SI under REP 103, such as `m/s`, `rad`, `degC` and fractions from 0 to 1 for percentages. `scale` multiplies the ROS value, and `integer: true` sends whole numbers to int fields. An argument is a field path or `{ field, unit, scale, integer }`.

## How the protocol is handled

- Connect subscribes to each read topic and advertises each publish topic once, so the first message survives DDS matching.
- Reads return the newest message on the topic, unknown until the first message.
- A failed subscription or advertisement fails reads and changes on that topic with rosbridge's reason, and health shows the last failure.
- Publishing has no reply, so a set channel reads back the last value sent.
- A goal returns `done` within `action_wait`, or `started` while still running. Aborted and canceled goals fail with their status.

## Safe state

A stop cancels every running goal this driver started, allowing up to 2 s each. ROS has no general stop, so put the robot's own stop in `safe_state`, such as a `cmd_vel` channel set to 0, which the kernel publishes right after the cancel. Only some bases stop when `cmd_vel` messages stop, so check the base and keep a physical stop within reach.

## Setup

1. On the robot, run `ros2 launch rosbridge_server rosbridge_websocket_launch.xml`, which starts rosapi too.
2. List topics and types with `ros2 topic list -t`.
3. Start from `openhal/drivers/ros2/examples/turtlebot4.hal.yaml` or `describe`.

| Key | Default | Meaning |
|---|---|---|
| `host` | required | rosbridge host |
| `port` | 9090 | rosbridge port |
| `scheme` | `ws` | `ws` or `wss` |
| `path` | empty | URL path, for rosbridge behind a proxy |
| `timeout` | `5 s` | Service reply deadline |
| `action_wait` | `8 s` | Time before a goal returns `started`, at most 9 s |
| `throttle` | `0 s` | Smallest gap between messages per topic |

## Known limitations

- No images or point clouds, and a message above 4 MB closes the rosbridge connection.
- Velocity commands go out once per change, so robots that need a steady `cmd_vel` stream stop after their own timeout.
- No rosauth, so keep rosbridge on a trusted network.
- QoS uses rosbridge defaults.

## Hazard defaults

`high`, so the hub holds every change and action until a person approves the request. Give velocity channels small limits and a `max_change_per_s`.

## Sources

- rosbridge v2 protocol, https://github.com/RobotWebTools/rosbridge_suite/blob/ros2/ROSBRIDGE_PROTOCOL.md
- rosapi services, https://github.com/RobotWebTools/rosbridge_suite/tree/ros2/rosapi
- REP 103, standard units of measure, https://www.ros.org/reps/rep-0103.html
- action_msgs/msg/GoalStatus, https://docs.ros2.org/latest/api/action_msgs/msg/GoalStatus.html
