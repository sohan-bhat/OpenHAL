# Hardware test plan for the lerobot driver

This plan checks the LeRobot driver on a real arm, and checks every assumption the test fake makes about LeRobot. It starts with read-only steps and ends with the smallest safe moves. Clamp the arm's base to the table, clear its reach, rest it over something soft, and keep a hand on its power switch. Stop at the first step that fails and send back the report below.

## What you need

- An SO-100 or SO-101 follower arm, calibrated with `lerobot-calibrate`, and the id you used. Other LeRobot arms work too, with their own type and joint names.
- LeRobot installed in the hub's environment, for example `pip install 'lerobot[feetech]'`, and OpenHAL with `uv pip install openhal-hub`.
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
openhal file validate ./arm.hal.yaml
```

Set `port` and `robot_id`. Expected. `valid ./arm.hal.yaml (so101, high hazard, read-only)`.

## Step 2. Connect without calibrating, and hold (assumptions 1, 2)

```
python probe.py ./arm.hal.yaml
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
while true; do python probe.py ./arm.hal.yaml | grep torque; sleep 2; done
```

Expected. `read torque True` while connected. Runs during the outage fail with a bus or connection error, not a hang. Later runs succeed. Stop with Ctrl-C.

## Step 5. Start the hub

Confirm the limits by adding `confirmed: { by: <your name>, at: <today> }`, then load the file into a fresh hub.

```
export OPENHAL_HOME="$PWD/openhal-test"
openhal init
cp ./arm.hal.yaml "$OPENHAL_HOME/devices/"
openhald &
openhal devices
openhal read so101.shoulder_pan
```

Expected. `so101` is connected, high hazard, and the arm holds its pose.

## Step 6. A blocked goal never reaches the arm

```
openhal write so101.shoulder_pan_goal "90 deg"
```

Expected. Blocked with `above_max`. Nothing moves.

## Step 7. One joint, 5 degrees (assumptions 4, 5)

Read `shoulder_pan`, then add 5 degrees. Wait a second between steps so the rate limit allows them.

```
openhal read so101.shoulder_pan
openhal write so101.shoulder_pan_goal "<current + 5> deg"
openhal read so101.shoulder_pan
openhal read so101.elbow_flex
```

Expected. Only the shoulder pan turns, by about 5 degrees. The other joints hold. That checks that a goal for one joint leaves the others alone. Then set `max_relative_target: 2` in the file, restart the hub, and send a goal 5 degrees away. Expected. The goal reads back about 2 degrees from where the joint was, because LeRobot clipped it. Set it back to 10.

## Step 8. Stop, torque off and torque back on (assumptions 6, 9)

```
openhal stop
openhal read so101.torque
openhal unlock
```

Move the shoulder pan a little by hand while torque is off, then turn torque back on.

```
openhal action so101.torque_on
openhal read so101.torque
```

Expected. After the stop the arm goes limp and `torque` reads `false`. When torque comes back the arm stiffens where you left it and does not jump back to the old goal. `openhal unlock` asks you to type `unlock`.

## Step 9. Close turns torque off (assumption 7)

Stop the hub with `kill %1`. Expected. The arm goes limp as the hub closes the device.

## Report template

```
Driver: lerobot
OpenHAL version:
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
Assumptions that didn't hold (number and what you saw):
Result: verified-on-hardware / failed at step N
```

A passing report lets the device file set `provenance.verification.status: verified-on-hardware` with `report:` pointing at the saved report. Send any assumption that didn't hold, since the fake has to change with it.
