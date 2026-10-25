# Hardware test plan for the lerobot driver

This plan checks the LeRobot driver on a real arm, and checks every assumption the test fake makes about LeRobot. It starts with read-only steps and ends with the smallest safe moves. Clamp the arm's base to the table, clear its reach, rest it over something soft, and keep a hand on its power switch. Stop at the first step that fails and send what [If something fails](#if-something-fails) lists. [README.md](README.md) has the setup and rules every plan shares.

## What you need

- An SO-100 or SO-101 follower arm, calibrated with `lerobot-calibrate`, and the id you used. Other LeRobot arms work too, with their own type and joint names.
- A checkout of this repository, `uv sync`, with LeRobot added to its environment, `uv pip install 'lerobot[feetech]'`. The lerobot driver has no extra, and a later `uv sync` removes LeRobot again.
- No other program holding the arm's port, such as a teleoperation script.

The fake in `openhal/drivers/lerobot/simulator.py` makes nine numbered assumptions. Each step below names the ones it checks.

## The probe

Save this as `probe.py`. It connects, identifies the arm and reads every channel. It holds no kernel grant, so it can't change anything.

```python
import asyncio, json, sys
from openhal.drivers import registry
from openhal.spec import load

async def main(path):
    file = load(path)
    driver = registry.load(file.connect.driver)(file)
    await driver.connect()
    try:
        print("identify", json.dumps(await driver.identify()))
        print("health", (await driver.health()).detail)
        for name in [*file.read, *file.write]:
            reading = await driver.read(name)
            print("read", name, reading.value, reading.unit or "")
        print("describe", json.dumps(await driver.describe())[:600])
    finally:
        await driver.close()

asyncio.run(main(sys.argv[1]))
```

## Step 1. Validate the device file (read-only)

```
cp openhal/drivers/lerobot/examples/so101-follower.hal.yaml ./arm.hal.yaml
uv run openhal file validate ./arm.hal.yaml
```

Set `port` and `robot_id`. Expected. `valid ./arm.hal.yaml (so101, high hazard, read-only)`.

## Step 2. Connect without calibrating, and hold (assumptions 1, 2)

```
uv run python probe.py ./arm.hal.yaml
```

Expected. No calibration prompt appears and the arm doesn't move. While the probe runs the arm holds its pose, because torque is on. When it ends the arm goes limp, because close() turns torque off. Then change `robot_id` to a name you never calibrated and run it again. Expected. `... isn't calibrated. Run lerobot-calibrate --robot.type=so101_follower ...`. Put the id back.

## Step 3. Joint readings (assumption 3)

From the step 2 output.

```
identify {"robot": "so101_follower", "port": "/dev/ttyACM0", "robot_id": "my_follower", "joints": "shoulder_pan, shoulder_lift, elbow_flex, wrist_flex, wrist_roll, gripper", "calibrated": "true"}
read shoulder_pan 1.2 deg
read shoulder_lift -97.8 deg
read elbow_flex 95.1 deg
read gripper 2.4 percent
read torque True
read shoulder_pan_goal 1.2 deg
```

Expected. Body joints are in degrees and match the arm's pose roughly. The gripper is between 0 and 100. The goal reads the same as the present position. Paste the full output into the report.

## Step 4. Torque state and the bus (assumptions 6, 8)

Run the probe in a loop and unplug the arm's USB cable for five seconds, then plug it back in.

```
while true; do uv run python probe.py ./arm.hal.yaml | grep torque; sleep 2; done
```

Expected. `read torque True` while connected. Runs during the outage fail with a bus or connection error, not a hang. Later runs succeed. Stop with Ctrl-C.

## Step 5. Start the hub

Read every limit in the file. Then confirm them yourself with `uv run openhal file confirm ./arm.hal.yaml`. It lists each limit and asks you to type `confirm`. Then load the file into a fresh hub.

```
export OPENHAL_HOME="$PWD/openhal-test"
uv run openhal init --no-sample
cp ./arm.hal.yaml "$OPENHAL_HOME/devices/"
uv run openhald --verbose > "$OPENHAL_HOME/hub.log" 2>&1 &
uv run openhal devices
uv run openhal read so101.shoulder_pan
```

Expected. `so101` is connected, high hazard, and the arm holds its pose.

## Step 6. A blocked goal never reaches the arm

```
uv run openhal write so101.shoulder_pan_goal "90 deg"
```

Expected. Blocked with `above_max`. Nothing moves.

## Step 7. One joint, 5 degrees (assumptions 4, 5)

Read `shoulder_pan`, then add 5 degrees. Wait a second between steps so the rate limit allows them.

```
uv run openhal read so101.shoulder_pan
uv run openhal write so101.shoulder_pan_goal "<current + 5> deg"
uv run openhal read so101.shoulder_pan
uv run openhal read so101.elbow_flex
```

Expected. Only the shoulder pan turns, by about 5 degrees. The other joints hold. That checks that a goal for one joint leaves the others alone.

Then check LeRobot's own clipping. A change to `connect` changes the limits, so the file needs your confirmation again. Stop the hub, set `max_relative_target: 2` in `$OPENHAL_HOME/devices/arm.hal.yaml`, then confirm and restart.

```
kill %1
uv run openhal file confirm "$OPENHAL_HOME/devices/arm.hal.yaml"
uv run openhald --verbose > "$OPENHAL_HOME/hub.log" 2>&1 &
uv run openhal read so101.shoulder_pan
uv run openhal write so101.shoulder_pan_goal "<current + 5> deg"
uv run openhal read so101.shoulder_pan_goal
```

Expected. The goal reads back about 2 degrees from where the joint was, because LeRobot clipped it. Set `max_relative_target` back to 10 the same way, by stopping the hub, editing the file, confirming it and starting the hub.

## Step 8. Stop, torque off and torque back on (assumptions 6, 9)

```
uv run openhal stop
uv run openhal read so101.torque
uv run openhal unlock
```

Move the shoulder pan a little by hand while torque is off, then turn torque back on.

```
uv run openhal action so101.torque_on
uv run openhal read so101.torque
```

Expected. After the stop the arm goes limp and `torque` reads `false`. When torque comes back the arm stiffens where you left it and does not jump back to the old goal. `openhal unlock` asks you to type `unlock`.

## Step 9. Close turns torque off (assumption 7)

Stop the hub with `kill %1`. Expected. The arm goes limp as the hub closes the device.

## If something fails

Send what [README.md](README.md#if-a-step-fails) lists, plus the LeRobot version (`uv run python -c "from importlib.metadata import version; print(version('lerobot'))"`), the robot type and id, the numbers of the assumptions that didn't hold, and any motor bus errors. If a blocked command reached the device, stop the hub, power the device off and report it privately as [SECURITY.md](../../SECURITY.md) says.

## Report template

```
Plan: docs/hardware-tests/lerobot.md
Tested by and date:
OpenHAL: (uv run openhal --version, and git rev-parse --short HEAD)
Device file: (path, and the sha256 in its confirmed line)
Arm, motors and LeRobot version:
Host OS and port:
Step 1 file valid:                        pass / fail
Step 2 connect without calibrating:       pass / fail   (assumptions 1, 2)
Step 3 joint readings:                    pass / fail   (assumption 3, paste the output)
Step 4 torque state and unplugging:       pass / fail   (assumptions 6, 8)
Step 5 hub lists the device:              pass / fail
Step 6 blocked goal:                      pass / fail
Step 7 one joint and LeRobot's clipping:  pass / fail   (assumptions 4, 5)
Step 8 stop and torque back on:           pass / fail   (assumptions 6, 9)
Step 9 close turns torque off:            pass / fail   (assumption 7)
Audit chain: (the line uv run openhal log --verify prints)
Assumptions that didn't hold (number and what you saw):
Result: verified-on-hardware / tested-reads / failed at step N
```

A passing report lets the device file set `provenance.verification.status: verified-on-hardware` with `report:` pointing at the saved report. Send any assumption that didn't hold, since the fake has to change with it.
