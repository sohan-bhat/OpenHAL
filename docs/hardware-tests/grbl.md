# Hardware test plan for the grbl driver

This plan checks the GRBL driver on a real machine. The plan starts with read-only checks and ends with the smallest safe moves. Stay at the machine for every step that changes something with a hand on the physical emergency stop. Stop at the first step that fails and send what [If something fails](#if-something-fails) lists. [README.md](README.md) has the setup and rules every plan shares.

## What you need

- A CNC router or laser on a GRBL 1.1 or grblHAL board with USB, and its cable. Note the version from the controller's `$I` in your usual sender.
- No bit in the spindle and no material on the bed. For a laser, the laser cap or a scrap of aluminium under the head and the safety glasses for its wavelength.
- No other program connected to the controller (UGS, Candle, LightBurn, bCNC).
- A checkout of this repository with the grbl extra, `uv sync --extra grbl`.

## The read-only probe

Save this as `probe.py`. The probe connects, identifies the firmware and reads every channel. The probe holds no kernel grant, so the probe can't change anything.

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
            try:
                reading = await driver.read(name)
                print("read", name, reading.value, reading.unit or "")
            except Exception as exc:
                print("read", name, "ERROR", type(exc).__name__, exc)
        print("describe", json.dumps(await driver.describe())[:400])
    finally:
        await driver.close()

asyncio.run(main(sys.argv[1]))
```

Connecting sends `$I`, `$$` and the `?` status byte. Reads may also send `$G` and `$#`. None of these change the machine. Opening the port resets most Arduino boards, which is normal and turns the spindle off.

## Step 1. The port is listed (read-only)

```
uv run python -m serial.tools.list_ports -v
```

Expected. A port with a USB id such as `1a86:7523` (CH340) or `2341:0043` (Arduino Uno). Note the path and the id.

## Step 2. Validate the device file (read-only)

```
cp openhal/drivers/grbl/examples/3018-router.hal.yaml ./router.hal.yaml
uv run openhal file validate ./router.hal.yaml
```

Edit `match.usb` or replace `grbl: auto` with the port path. Set `spindle_speed.max` to your spindle's maximum and no higher than `$30`. On a laser, add `laser_power: { unit: percent, min: 0, max: 1, confirm: confirm-each-time, map: { laser: constant } }` under `write` and `laser_power: 0` to the safe state, and turn on laser mode (`$32=1`) in your sender. Expected. `valid ./router.hal.yaml (router, high hazard, read-only)`.

## Step 3. Identify and read (read-only)

```
uv run python probe.py ./router.hal.yaml
```

Expected.

```
identify {"port": "...", "banner": "Grbl 1.1h", "version": "1.1h", "build": "20190830", "options": "V,15,128"}
health Grbl 1.1h, idle
read state idle
read alarm 0.0 dimensionless
read position_x 0.0 mm
read position_y 0.0 mm
read position_z 0.0 mm
read feed_rate 0.0 mm/min
read max_spindle 10000.0 rpm
read spindle_speed 0.0 rpm
describe {"device": {"name": "GRBL 1.1h controller"}, ...
```

If homing is enabled the state is `alarm` after power-up, which is correct. `max_spindle` matches `$30` in your sender. Positions match your sender's machine coordinates. Paste the full output into the report.

## Step 4. Status during a manual jog (read-only for OpenHAL)

Run the probe in a loop, and jog the machine a few millimeters with the controller's own buttons or pendant if it has one. Skip this step if it has none.

```
while true; do uv run python probe.py ./router.hal.yaml | grep position_x; sleep 1; done
```

Expected. `position_x` follows the machine. Stop with Ctrl-C.

## Step 5. Unplug during reads (read-only)

Run the loop from step 4, unplug the USB cable for five seconds, then plug it back in. Expected. Runs during the outage fail with `Could not open` or `disconnected`. Later runs succeed. Stop with Ctrl-C.

## Step 6. Start the hub

Read every limit in the file, then confirm them yourself. The confirm lists each limit and prompts you to type `confirm`. Then the file goes into a fresh test home and hub.

```
export OPENHAL_HOME="$PWD/openhal-test"
uv run openhal init --yes --no-sample --no-discover --no-service
uv run openhal file confirm ./router.hal.yaml
cp ./router.hal.yaml "$OPENHAL_HOME/devices/"
bash docs/hardware-tests/hub.sh start
uv run openhal devices
uv run openhal read router.state
```

Expected. `router` is connected, high hazard and writable. If the state is `alarm`, run `uv run openhal action router.home` (with limit switches) or `uv run openhal action router.clear_alarm`, and read the state again until it is `idle`.

## Step 7. Hold and resume without motion

```
uv run openhal action router.hold
uv run openhal read router.state
uv run openhal action router.resume
uv run openhal read router.state
```

Expected. `hold` returns `done` and the state reads `hold`, because GRBL 1.1 enters Hold:0 even when nothing moves. `resume` returns `done` and the state is `idle` again. If the state stays `idle` after the hold, `resume` is blocked with `interlock`, because `resume` needs `state == hold`. Either outcome is safe, but write down which one you saw, since the simulator models the state as staying `idle`.

## Step 8. The smallest move, a 1 mm jog with Z clear

Raise Z by hand or in your sender first, so the tool is well clear of the bed.

```
uv run openhal action router.jog x="1 mm" y="0 mm" z="0 mm" feed="100 mm/min"
uv run openhal read router.position_x
uv run openhal action router.jog x="-1 mm" y="0 mm" z="0 mm" feed="100 mm/min"
```

Expected. The X axis moves 1 mm and back. The action returns `done`. `position_x` changes by 1.0 mm.

## Step 9. A blocked jog never reaches the machine

```
uv run openhal action router.jog x="50 mm" y="0 mm" z="0 mm" feed="100 mm/min"
```

Expected. Blocked with code `above_max`. The machine doesn't move.

## Step 10. The spindle at low speed, then stop

Use about a fifth of the `max_spindle` value from step 3. The commands show `2000 rpm` for a `$30` of 10000. The driver blocks a speed above `$30` with `failed driver_error` and sends nothing, and many 3018 boards ship with `$30=1000`. On a laser, put the cap on and run `uv run openhal write router.laser_power "1 %"` instead of the first two commands.

```
uv run openhal write router.spindle_speed "2000 rpm"
uv run openhal read router.spindle_speed
uv run openhal stop
uv run openhal read router.spindle_speed
uv run openhal read router.state
uv run openhal unlock
```

Expected. The spindle spins up and the read shows the speed you requested. After `openhal stop` it spins down and the read shows `0 rpm`. The state is `idle`, because nothing was moving. `openhal unlock` prompts you to type `unlock`.

## Step 11. Stop during a jog

Open a second terminal in the checkout and run `export OPENHAL_HOME="$PWD/openhal-test"` there, so the stop can go in while the machine moves.

In the first terminal, start a 20 mm jog. The jog takes 12 s at 100 mm/min.

```
uv run openhal action router.jog x="20 mm" y="0 mm" z="0 mm" feed="100 mm/min"
```

In the second terminal, within a few seconds, stop it.

```
uv run openhal stop
uv run openhal read router.state router.alarm router.position_x
uv run openhal unlock
```

Expected. The stop reports `router  safe` and the axis decelerates and stops well before 20 mm. The driver holds the feed, waits up to 2 s for the axis to stop, then soft resets GRBL. A hold during a jog cancels the jog, so the state is usually `idle` with alarm `0`. If the reset came while the axis still moved, the state is `alarm` with alarm `3`. Then run `uv run openhal action router.clear_alarm` and read the state until it is `idle`. Write down which one you saw. Stop the hub with `bash docs/hardware-tests/hub.sh stop` when done.

## If something fails

Send what [README.md](README.md#if-a-step-fails) lists, plus the `$I` and `$$` replies from your usual sender, the machine and board, and whether homing and limit switches are on. If a blocked command reached the device, stop the hub, power the device off and report it privately as [SECURITY.md](../../SECURITY.md) describes.

## Report template

```
Plan: docs/hardware-tests/grbl.md
Tested by and date:
OpenHAL: (uv run openhal --version, and git rev-parse --short HEAD)
Device file: (path, and the sha256 in its confirmed line)
Machine and controller: (model, board, GRBL version from $I)
Host OS and port path:
Step 1 port listed:              pass / fail
Step 2 file valid:               pass / fail
Step 3 probe output:             pass / fail   (paste it)
Step 4 status during manual jog: pass / fail / skipped
Step 5 unplug and replug:        pass / fail
Step 6 hub lists the device:     pass / fail
Step 7 hold and resume:          pass / fail
Step 8 1 mm jog:                 pass / fail
Step 9 blocked jog:              pass / fail
Step 10 spindle and stop:        pass / fail
Step 11 stop during a jog:       pass / fail   (state and alarm after the stop)
Audit chain: (the line uv run openhal log --verify prints)
Anything unexpected (paste exact output):
Result: verified-on-hardware / tested-reads / failed at step N
```

Save the filled-in report as `docs/hardware-tests/reports/<device id>-<date>.md`. [README.md](README.md#reports) lists when a report marks the device file `verified-on-hardware`.
