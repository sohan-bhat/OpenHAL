# Hardware test plan for the firmata driver

This plan checks the Firmata driver on a real board. It starts with read-only checks and ends with the smallest safe writes. Stop at the first step that fails and send what [If something fails](#if-something-fails) lists. [README.md](README.md) has the setup and rules every plan shares.

## What you need

- An Arduino Uno (or another board StandardFirmata supports) and its USB cable.
- StandardFirmata uploaded from the Arduino IDE (File, Examples, Firmata, StandardFirmata).
- Optional parts for the example file. A light sensor or potentiometer on A0, a push button from pin 2 to ground, a small fan through a MOSFET on pin 9 and a hobby servo on pin 6 with its own 5 V supply. The onboard LED on pin 13 is enough for the write steps.
- A checkout of this repository with the firmata extra, `uv sync --extra firmata`.

## The read-only probe

Save this as `probe.py`. It connects, identifies the firmware, prints the driver's proposal for the board and reads every channel. It holds no kernel grant, so it can't write anything. Connecting does set the read pins to input mode and turns on reporting, which drives nothing.

```python
import asyncio, json, sys
from openhal.drivers import registry
from openhal.spec import load

async def main(path):
    file = load(path)
    driver = registry.load(file.connect.driver)(file)
    await driver.connect()
    await asyncio.sleep(0.5)
    try:
        print("identify", json.dumps(await driver.identify()))
        print("describe", json.dumps(await driver.describe(), indent=2, default=str))
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

## Step 1. The port is listed (read-only)

```
uv run python -m serial.tools.list_ports -v
```

Expected. A port with a USB id such as `2341:0043`. Note the path and the id.

## Step 2. Validate the device file (read-only)

```
cp openhal/drivers/firmata/examples/uno-desk-kit.hal.yaml ./desk-kit.hal.yaml
uv run openhal file validate ./desk-kit.hal.yaml
```

Remove the channels for parts you don't have, and their entries in `safe_state`. Expected. `valid ./desk-kit.hal.yaml (desk-kit, low hazard, read-only)`.

## Step 3. Identify, describe and read (read-only)

```
uv run python probe.py ./desk-kit.hal.yaml
```

Expected.

```
identify {"port": "auto", "firmware": "StandardFirmata.ino", "firmware_version": "2.5", "protocol": "2.5"}
describe { "device": {"name": "StandardFirmata"}, "read": {"a0": ...}, "write": {"pwm_3": ...}, ... }
read light 2.4 V
read button False
read led False
read fan 0.0 percent
read pointer None degree
```

`light` follows the sensor between 0 V and 5 V. `button` is `True` while the button is held, so run the probe twice to see both. `pointer` is `None` until the first servo write. Paste the full output into the report.

## Step 4. Unplug during reads (read-only)

```
while true; do uv run python probe.py ./desk-kit.hal.yaml; sleep 1; done
```

Unplug the USB cable for five seconds, then plug it back in. Expected. Runs fail while unplugged and work again afterwards. Stop with Ctrl-C.

## Step 5. Start the hub

Read every limit in the file. Then confirm them yourself with `uv run openhal file confirm ./desk-kit.hal.yaml`. It lists each limit and asks you to type `confirm`. Then load the file into a fresh hub.

```
export OPENHAL_HOME="$PWD/openhal-test"
uv run openhal init --no-sample
cp ./desk-kit.hal.yaml "$OPENHAL_HOME/devices/"
uv run openhald --verbose > "$OPENHAL_HOME/hub.log" 2>&1 &
uv run openhal devices
uv run openhal read desk-kit.light
```

Expected. `desk-kit` is connected and writable.

## Step 6. The smallest safe write, the LED

```
uv run openhal write desk-kit.led true
uv run openhal read desk-kit.led
uv run openhal write desk-kit.led false
```

Expected. The onboard LED turns on, the read says `true`, then the LED turns off.

## Step 7. PWM, servo and the safe state

```
uv run openhal write desk-kit.fan "20 %"
uv run openhal read desk-kit.fan
uv run openhal write desk-kit.pointer "90 degree"
uv run openhal stop
uv run openhal read desk-kit.fan
uv run openhal unlock
```

Expected. The fan runs slowly and reads about `20 %` (PWM value 51). The servo moves to the middle. After `openhal stop` the fan reads `0 %` and the LED is off. The servo stays where it is, as the file's `safe_state_note` says.

## Step 8. A blocked write never reaches the board

```
uv run openhal write desk-kit.fan "95 %"
```

Expected. Blocked with code `above_max` (the example limits the fan to 80 %). The fan doesn't change. Stop the hub with `kill %1` when done.

## If something fails

Send what [README.md](README.md#if-a-step-fails) lists, plus the output of `uv run python -m serial.tools.list_ports -v`, the identify line from step 3, the board model, and which optional parts are wired. If a blocked command reached the device, stop the hub, power the device off and report it privately as [SECURITY.md](../../SECURITY.md) says.

## Report template

```
Plan: docs/hardware-tests/firmata.md
Tested by and date:
OpenHAL: (uv run openhal --version, and git rev-parse --short HEAD)
Device file: (path, and the sha256 in its confirmed line)
Board and firmware: (board, StandardFirmata version from identify)
Host OS and port path:
Parts connected:
Step 1 port listed:             pass / fail
Step 2 file valid:              pass / fail
Step 3 probe output:            pass / fail   (paste it)
Step 4 unplug and replug:       pass / fail
Step 5 hub lists the device:    pass / fail
Step 6 LED write:               pass / fail
Step 7 PWM, servo and stop:     pass / fail
Step 8 blocked write:           pass / fail
Audit chain: (the line uv run openhal log --verify prints)
Anything unexpected (paste exact output):
Result: verified-on-hardware / tested-reads / failed at step N
```

Save the filled-in report as `docs/hardware-tests/reports/<device id>-<date>.md`. [README.md](README.md#reports) says when it marks the device file `verified-on-hardware`.
