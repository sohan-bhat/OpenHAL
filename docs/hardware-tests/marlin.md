# Hardware test plan for the marlin driver

This plan checks the Marlin driver on a real printer. It starts with read-only checks and ends with the smallest safe writes. Stay next to the printer for every write step. Stop at the first step that fails and send back the report below.

## What you need

- A printer running Marlin 2.x with USB, and its cable. Note the firmware version from the printer's About screen.
- No filament loaded in the hotend for steps 6 and 7, or at least nothing that minds 40 degC.
- No other program connected to the printer (OctoPrint, Pronterface, a slicer).
- OpenHAL installed with `uv pip install 'openhal-hub[marlin]'`.

## The read-only probe

Save this as `probe.py`. It connects, identifies the firmware and reads every channel. It holds no kernel grant, so it can't write anything.

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
        for name in [*file.read, *file.write]:
            try:
                reading = await driver.read(name)
                print("read", name, reading.value, reading.unit or "")
            except Exception as exc:
                print("read", name, "ERROR", type(exc).__name__, exc)
    finally:
        await driver.close()

asyncio.run(main(sys.argv[1]))
```

Connecting sends `M110 N0`, `M115` and, when the firmware supports it, `M155 S2`. None of these change the machine. Opening the port resets most boards, which is normal.

## Step 1. The port is listed (read-only)

```
python -m serial.tools.list_ports -v
```

Expected. A port with a USB id such as `1a86:7523` (CH340) or `0483:5740` (STM32). Note the path and the id.

## Step 2. Validate the device file (read-only)

```
cp openhal/drivers/marlin/examples/ender-3-v2.hal.yaml ./printer.hal.yaml
openhal file validate ./printer.hal.yaml
```

Edit `match.usb` or replace `marlin: auto` with the port path, and lower the limits if your printer needs it. Expected. `valid ./printer.hal.yaml (ender, medium hazard, read-only)`.

## Step 3. Identify and read (read-only)

```
python probe.py ./printer.hal.yaml
```

Expected.

```
identify {"port": "...", "firmware_name": "Marlin 2.1.2.4 (...)", "machine_type": "...", "cap.autoreport_temp": "1", ...}
read extruder_temp 24.1 degC
read bed_temp 23.8 degC
read position_z 0.0 mm
read sd_printing False
read sd_progress 0.0 percent
read extruder_target 0.0 degC
read bed_target 0.0 degC
read fan_speed None percent
```

Temperatures match the printer's display within a degree. `fan_speed` is `None` because Marlin can't report it. Paste the full output into the report.

## Step 4. Unplug during reads (read-only)

```
while true; do python probe.py ./printer.hal.yaml; sleep 2; done
```

Unplug the USB cable for five seconds, then plug it back in. Expected. Runs during the outage fail with `Could not open` or `disconnected`. Later runs succeed. Stop with Ctrl-C.

## Step 5. Start the hub

Confirm the limits by adding `confirmed: { by: <your name>, at: <today> }`, then load the file into a fresh hub.

```
export OPENHAL_HOME="$PWD/openhal-test"
openhal init
cp ./printer.hal.yaml "$OPENHAL_HOME/devices/"
openhald &
openhal devices
openhal read ender.extruder_temp
```

Expected. `ender` is connected and writable. The read matches the display.

## Step 6. The smallest safe write, the part fan

```
openhal write ender.fan_speed "20 %"
openhal read ender.fan_speed
openhal write ender.fan_speed "0 %"
```

Expected. The part fan spins slowly, then stops. The read says `20 %`.

## Step 7. A low heater target and the safe state

```
openhal write ender.bed_target "35 degC"
openhal read ender.bed_target
openhal read ender.bed_temp
openhal stop
openhal read ender.bed_target
openhal unlock
```

Expected. The display shows a bed target of 35. After `openhal stop` the target is 0 on the display and in the read. The printer does not halt and needs no reset. `openhal unlock` asks you to type `unlock`.

## Step 8. A blocked write never reaches the printer

```
openhal write ender.bed_target "150 degC"
```

Expected. Blocked with code `above_max`. The display target doesn't change.

## Step 9. Homing (optional, needs a clear bed)

```
openhal action ender.home axes=all
openhal read ender.position_z
```

Expected. The printer homes. The action answers `done`, or `started` if homing takes longer than 8 s. After homing the Z position is 0 or your Z offset. Stop the hub with `kill %1` when done.

## Report template

```
Driver: marlin
OpenHAL version:
Printer and firmware: (model, Marlin version from the About screen)
Host OS and port path:
Step 1 port listed:             pass / fail
Step 2 file valid:              pass / fail
Step 3 probe output:            pass / fail   (paste it)
Step 4 unplug and replug:       pass / fail
Step 5 hub lists the device:    pass / fail
Step 6 fan write:               pass / fail
Step 7 heater target and stop:  pass / fail
Step 8 blocked write:           pass / fail
Step 9 homing:                  pass / fail / skipped   (done or started)
Anything unexpected (paste exact output):
Result: verified-on-hardware / failed at step N
```

A passing report lets the device file set `provenance.verification.status: verified-on-hardware` with `report:` pointing at the saved report.
