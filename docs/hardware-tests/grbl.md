# Hardware test plan for the grbl driver

This plan checks the GRBL driver on a real machine. It starts with read-only checks and ends with the smallest safe moves. Stay at the machine for every step that changes something with a hand on the physical emergency stop. Stop at the first step that fails and send back the report below.

## What you need

- A CNC router or laser on a GRBL 1.1 or grblHAL board with USB, and its cable. Note the version from the controller's `$I` in your usual sender.
- No bit in the spindle and no material on the bed. For a laser, the laser cap or a scrap of aluminium under the head and the safety glasses for its wavelength.
- No other program connected to the controller (UGS, Candle, LightBurn, bCNC).
- OpenHAL installed with `uv pip install 'openhal-hub[grbl]'`.

## The read-only probe

Save this as `probe.py`. It connects, identifies the firmware and reads every channel. It holds no kernel grant, so it can't change anything.

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
python -m serial.tools.list_ports -v
```

Expected. A port with a USB id such as `1a86:7523` (CH340) or `2341:0043` (Arduino Uno). Note the path and the id.

## Step 2. Validate the device file (read-only)

```
cp openhal/drivers/grbl/examples/3018-router.hal.yaml ./router.hal.yaml
openhal file validate ./router.hal.yaml
```

Edit `match.usb` or replace `grbl: auto` with the port path. Set `spindle_speed.max` to your spindle's maximum and no higher than `$30`. Expected. `valid ./router.hal.yaml (router, high hazard, read-only)`.

## Step 3. Identify and read (read-only)

```
python probe.py ./router.hal.yaml
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

If homing is enabled the state is `alarm` after power-up. That is correct. `max_spindle` matches `$30` in your sender. Positions match your sender's machine coordinates. Paste the full output into the report.

## Step 4. Status during a manual jog (read-only for OpenHAL)

Run the probe in a loop, and jog the machine a few millimeters with the controller's own buttons or pendant if it has one. Skip this step if it has none.

```
while true; do python probe.py ./router.hal.yaml | grep position_x; sleep 1; done
```

Expected. `position_x` follows the machine. Stop with Ctrl-C.

## Step 5. Unplug during reads (read-only)

Run the loop from step 4, unplug the USB cable for five seconds, then plug it back in. Expected. Runs during the outage fail with `Could not open` or `disconnected`. Later runs succeed. Stop with Ctrl-C.

## Step 6. Start the hub

Confirm the limits by adding `confirmed: { by: <your name>, at: <today> }`, then load the file into a fresh hub.

```
export OPENHAL_HOME="$PWD/openhal-test"
openhal init
cp ./router.hal.yaml "$OPENHAL_HOME/devices/"
openhald &
openhal devices
openhal read router.state
```

Expected. `router` is connected, high hazard and writable. If the state is `alarm`, run `openhal action router.home` (with limit switches) or `openhal action router.clear_alarm`, and read the state again until it is `idle`.

## Step 7. Hold and resume without motion

```
openhal action router.hold
openhal read router.state
openhal action router.resume
openhal read router.state
```

Expected. Both actions answer done. The state stays `idle`, because a feed hold with no motion does nothing.

## Step 8. The smallest move, a 1 mm jog with Z clear

Raise Z by hand or in your sender first, so the tool is well clear of the bed.

```
openhal action router.jog x="1 mm" y="0 mm" z="0 mm" feed="100 mm/min"
openhal read router.position_x
openhal action router.jog x="-1 mm" y="0 mm" z="0 mm" feed="100 mm/min"
```

Expected. The X axis moves 1 mm and back. The action answers `done`. `position_x` changes by 1.0 mm.

## Step 9. A blocked jog never reaches the machine

```
openhal action router.jog x="50 mm" y="0 mm" z="0 mm" feed="100 mm/min"
```

Expected. Blocked with code `above_max`. The machine doesn't move.

## Step 10. The spindle at low speed, then stop

Skip the spindle part on a laser and use `laser_power` at `1 %` with the laser cap on instead.

```
openhal write router.spindle_speed "2000 rpm"
openhal read router.spindle_speed
openhal stop
openhal read router.spindle_speed
openhal read router.state
openhal unlock
```

Expected. The spindle spins up and the read says `2000 rpm`. After `openhal stop` it spins down and the read says `0 rpm`. The state is `idle`, because nothing was moving. `openhal unlock` asks you to type `unlock`.

## Step 11. Stop during a jog

```
openhal action router.jog x="20 mm" y="0 mm" z="0 mm" feed="100 mm/min"
openhal stop
openhal read router.state
openhal read router.alarm
openhal unlock
openhal action router.clear_alarm
```

Run `openhal stop` within a few seconds of the jog. Expected. The axis decelerates and stops before it reaches 20 mm. The state is `alarm` and the alarm is `3`, which GRBL raises after a reset during motion. `clear_alarm` brings the state back to `idle`. Stop the hub with `kill %1` when done.

## Report template

```
Driver: grbl
OpenHAL version:
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
Anything unexpected (paste exact output):
Result: verified-on-hardware / failed at step N
```

A passing report lets the device file set `provenance.verification.status: verified-on-hardware` with `report:` pointing at the saved report.
