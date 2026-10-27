# Hardware test plan for the marlin driver

This plan checks the Marlin driver on a real printer. The plan starts with read-only checks and ends with the smallest safe writes. Stay next to the printer for every write step. Stop at the first step that fails and send what [If something fails](#if-something-fails) lists. [README.md](README.md) has the setup and rules every plan shares.

## What you need

- A printer running Marlin 2.x with USB, and its cable. Note the firmware version from the printer's About screen.
- No filament loaded in the hotend for steps 6 and 7, or at least nothing that minds 40 degC.
- No other program connected to the printer (OctoPrint, Pronterface, a slicer).
- A checkout of this repository with the marlin extra, `uv sync --extra marlin`.

## The read-only probe

Save this as `probe.py`. The probe connects, identifies the firmware and reads every channel. The probe holds no kernel grant, so the probe can't write anything.

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
uv run python -m serial.tools.list_ports -v
```

Expected. A port with a USB id such as `1a86:7523` (CH340) or `0483:5740` (STM32). Note the path and the id.

## Step 2. Validate the device file (read-only)

```
cp openhal/drivers/marlin/examples/ender-3-v2.hal.yaml ./printer.hal.yaml
uv run openhal file validate ./printer.hal.yaml
```

Edit `match.usb` or replace `marlin: auto` with the port path, and lower the limits if your printer needs it. Expected. `valid ./printer.hal.yaml (ender, medium hazard, read-only)`.

## Step 3. Identify and read (read-only)

```
uv run python probe.py ./printer.hal.yaml
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
while true; do uv run python probe.py ./printer.hal.yaml; sleep 2; done
```

Unplug the USB cable for five seconds, then plug it back in. Expected. Runs during the outage fail with `Could not open` or `disconnected`. Later runs succeed. Stop with Ctrl-C.

## Step 5. Start the hub

Read every limit in the file, then confirm them yourself. The confirm lists each limit and asks you to type `confirm`. Then the file goes into a fresh test home and hub.

```
export OPENHAL_HOME="$PWD/openhal-test"
uv run openhal init --yes --no-sample --no-discover --no-service
uv run openhal file confirm ./printer.hal.yaml
cp ./printer.hal.yaml "$OPENHAL_HOME/devices/"
bash docs/hardware-tests/hub.sh start
uv run openhal devices
uv run openhal read ender.extruder_temp
```

Expected. `ender` is connected and writable. The read matches the display.

## Step 6. The smallest safe write, the part fan

```
uv run openhal write ender.fan_speed "20 %"
uv run openhal read ender.fan_speed
uv run openhal write ender.fan_speed "0 %"
```

Expected. The part fan spins slowly, then stops. The read says `20 %`.

## Step 7. A low heater target and the safe state

```
uv run openhal write ender.bed_target "35 degC"
uv run openhal read ender.bed_target
uv run openhal read ender.bed_temp
uv run openhal stop
uv run openhal read ender.bed_target
uv run openhal unlock
```

Expected. The display shows a bed target of 35. After `openhal stop` the target is 0 on the display and in the read. The printer does not halt and needs no reset. `openhal unlock` asks you to type `unlock`.

## Step 8. A blocked write never reaches the printer

```
uv run openhal write ender.bed_target "150 degC"
```

Expected. Blocked with code `above_max`. The display target doesn't change.

## Step 9. Homing (optional, needs a clear bed)

```
uv run openhal action ender.home axes=all
uv run openhal read ender.position_z
```

Expected. The printer homes. The action answers `done`, or `started` if homing takes longer than 8 s. After homing the Z position is 0 or your Z offset. Stop the hub with `bash docs/hardware-tests/hub.sh stop` when done.

## If something fails

Send what [README.md](README.md#if-a-step-fails) lists, plus the firmware line from the printer's About screen, the output of `uv run python -m serial.tools.list_ports -v`, and whether another program had the port open. If a blocked command reached the device, stop the hub, power the device off and report it privately as [SECURITY.md](../../SECURITY.md) says.

## Report template

```
Plan: docs/hardware-tests/marlin.md
Tested by and date:
OpenHAL: (uv run openhal --version, and git rev-parse --short HEAD)
Device file: (path, and the sha256 in its confirmed line)
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
Audit chain: (the line uv run openhal log --verify prints)
Anything unexpected (paste exact output):
Result: verified-on-hardware / tested-reads / failed at step N
```

Save the filled-in report as `docs/hardware-tests/reports/<device id>-<date>.md`. [README.md](README.md#reports) says when it marks the device file `verified-on-hardware`.
