# Hardware test plan for the ros2 driver

This plan checks the ROS 2 driver on a real robot. The plan starts with read-only checks and ends with the smallest safe motion. Lift the wheels off the floor, or clear a 2 by 2 m space, before any step that moves the robot, and keep its physical stop within reach. Stop at the first step that fails and send what [If something fails](#if-something-fails) lists. [README.md](README.md) has the setup and rules every plan shares.

## What you need

- A ROS 2 robot with rosbridge running, for example `ros2 launch rosbridge_server rosbridge_websocket_launch.xml`. Note the ROS distribution.
- The names and types of a battery topic, an odometry topic and the velocity command topic, from `ros2 topic list -t`.
- A checkout of this repository with the ros2 extra, `uv sync --extra ros2`, on a machine that can reach the robot on port 9090.

## The read-only probe

Save this as `probe.py`. The probe connects, identifies the graph and reads every channel. The probe holds no kernel grant, so the probe can't change anything.

```python
import asyncio, json, sys
from openhal.drivers import registry
from openhal.spec import load

async def main(path):
    file = load(path)
    driver = registry.load(file.connect.driver)(file)
    await driver.connect()
    try:
        await asyncio.sleep(2)
        print("identify", json.dumps(await driver.identify()))
        print("health", (await driver.health()).detail)
        for name in [*file.read, *file.write]:
            try:
                reading = await driver.read(name)
                print("read", name, reading.value, reading.unit or "")
            except Exception as exc:
                print("read", name, "ERROR", type(exc).__name__, exc)
        print("describe", json.dumps(await driver.describe())[:600])
    finally:
        await driver.close()

asyncio.run(main(sys.argv[1]))
```

Connecting subscribes to the read topics and advertises the publish topics. Advertising alone sends nothing to the robot.

## Step 1. rosbridge answers (read-only)

```
uv run python -m websockets ws://<robot>:9090
```

Expected. `Connected to ws://<robot>:9090.` Close it with Ctrl-D. If it fails, check that rosbridge is running and the port is open.

## Step 2. Validate the device file (read-only)

```
cp openhal/drivers/ros2/examples/turtlebot4.hal.yaml ./robot.hal.yaml
uv run openhal file validate ./robot.hal.yaml
```

Set the host, and change the topics and types to your robot's. Keep the velocity limits at 0.1 m/s. Expected. `valid ./robot.hal.yaml (turtlebot, high hazard, read-only)`.

## Step 3. Identify and read (read-only)

```
uv run python probe.py ./robot.hal.yaml
```

Expected.

```
identify {"rosbridge": "ws://...:9090", "nodes": "24", "distro": "jazzy"}
health rosbridge at ws://...:9090
read battery 86.0 percent
read odom_x 0.0 m
read odom_y 0.0 m
read cmd_vel_linear None m/s
describe {"device": {"name": "ROS 2 robot"}, "read": {...
```

`battery` matches `ros2 topic echo /battery_state --once` times 100. `cmd_vel_linear` is `None` because nothing has been sent yet. Paste the full output into the report.

## Step 4. Network loss during reads (read-only)

```
while true; do uv run python probe.py ./robot.hal.yaml | grep battery; sleep 2; done
```

Stop rosbridge for ten seconds, then start it again. Expected. Runs during the outage fail with `Could not reach rosbridge`. Later runs succeed. Stop with Ctrl-C.

## Step 5. Start the hub

Read every limit in the file, then confirm them yourself. The confirm lists each limit and asks you to type `confirm`. Then the file goes into a fresh test home and hub.

```
export OPENHAL_HOME="$PWD/openhal-test"
uv run openhal init --yes --no-sample --no-discover --no-service
uv run openhal file confirm ./robot.hal.yaml
cp ./robot.hal.yaml "$OPENHAL_HOME/devices/"
bash docs/hardware-tests/hub.sh start
uv run openhal devices
uv run openhal read turtlebot.battery
```

Expected. `turtlebot` is connected, high hazard and its limits are confirmed.

## Step 6. A blocked velocity never reaches the robot

```
ros2 topic echo /cmd_vel &
uv run openhal write turtlebot.cmd_vel_linear "0.5 m/s"
```

Expected. Blocked with code `above_max`. `ros2 topic echo` prints nothing.

## Step 7. The smallest motion, then stop

With the wheels lifted or the space clear.

```
uv run openhal write turtlebot.cmd_vel_linear "0.05 m/s"
uv run openhal stop
uv run openhal read turtlebot.cmd_vel_linear
uv run openhal unlock
```

Expected. `ros2 topic echo` prints one Twist with `linear.x: 0.05`, then one with `linear.x: 0.0` after the stop. The wheels turn slowly, then stop. Some bases stop by themselves within a second because `cmd_vel` went quiet. Note whether yours does. `openhal unlock` asks you to type `unlock`.

## Step 8. An action goal and a stop that cancels it (optional)

Use an action the robot offers, such as `undock` on a TurtleBot 4 sitting on its dock. Open a second terminal in the checkout and run `export OPENHAL_HOME="$PWD/openhal-test"` there, so the stop can go in while the robot moves. In the first terminal, send the goal.

```
uv run openhal action turtlebot.undock
```

In the second terminal, while the robot is still moving, stop it.

```
uv run openhal stop
ros2 action list -t
uv run openhal unlock
```

Expected. The action answers `started`, the stop cancels the goal and the robot halts. Stop the hub with `bash docs/hardware-tests/hub.sh stop` and the echo with `kill %1` when done.

## If something fails

Send what [README.md](README.md#if-a-step-fails) lists, plus the output of `ros2 topic list -t`, the `ros2 topic echo` output from the same minutes, the rosbridge launch output, and the ROS distribution. If a blocked command reached the device, stop the hub, power the device off and report it privately as [SECURITY.md](../../SECURITY.md) says.

## Report template

```
Plan: docs/hardware-tests/ros2.md
Tested by and date:
OpenHAL: (uv run openhal --version, and git rev-parse --short HEAD)
Device file: (path, and the sha256 in its confirmed line)
Robot, ROS 2 distribution and rosbridge version:
Host OS and network:
Step 1 rosbridge answers:         pass / fail
Step 2 file valid:                pass / fail
Step 3 probe output:              pass / fail   (paste it)
Step 4 network loss:              pass / fail
Step 5 hub lists the device:      pass / fail
Step 6 blocked velocity:          pass / fail
Step 7 smallest motion and stop:  pass / fail   (does the base stop on its own when cmd_vel goes quiet)
Step 8 goal and cancel:           pass / fail / skipped
Audit chain: (the line uv run openhal log --verify prints)
Anything unexpected (paste exact output):
Result: verified-on-hardware / tested-reads / failed at step N
```

Save the filled-in report as `docs/hardware-tests/reports/<device id>-<date>.md`. [README.md](README.md#reports) says when it marks the device file `verified-on-hardware`.
