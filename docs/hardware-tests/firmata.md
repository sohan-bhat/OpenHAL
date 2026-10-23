# Hardware test plan for the firmata driver

This plan checks the Firmata driver on a real board. It starts with read-only checks and ends with the smallest safe writes. Stop at the first step that fails and send back the report below.

## What you need

- An Arduino Uno (or another board StandardFirmata supports) and its USB cable.
- StandardFirmata uploaded from the Arduino IDE (File, Examples, Firmata, StandardFirmata).
- Optional parts for the example file. A light sensor or potentiometer on A0, a push button from pin 2 to ground, a small fan through a MOSFET on pin 9 and a hobby servo on pin 6 with its own 5 V supply. The onboard LED on pin 13 is enough for the write steps.
- OpenHAL installed with `uv pip install 'openhal-hub[firmata]'`.

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
python -m serial.tools.list_ports -v
```

Expected. A port with a USB id such as `2341:0043`. Note the path and the id.

## Step 2. Validate the device file (read-only)

```
cp openhal/drivers/firmata/examples/uno-desk-kit.hal.yaml ./desk-kit.hal.yaml
openhal file validate ./desk-kit.hal.yaml
```

Remove the channels for parts you don't have. Expected. `valid ./desk-kit.hal.yaml (desk-kit, low hazard, read-only)`.

## Step 3. Identify, describe and read (read-only)

```
python probe.py ./desk-kit.hal.yaml
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
while true; do python probe.py ./desk-kit.hal.yaml; sleep 1; done
```

Unplug the USB cable for five seconds, then plug it back in. Expected. Runs fail while unplugged and work again afterwards. Stop with Ctrl-C.

## Step 5. Start the hub

Confirm the limits by adding `confirmed: { by: <your name>, at: <today> }`, then load the file into a fresh hub.

```
export OPENHAL_HOME="$PWD/openhal-test"
openhal init
cp ./desk-kit.hal.yaml "$OPENHAL_HOME/devices/"
openhald &
openhal devices
openhal read desk-kit.light
```

Expected. `desk-kit` is connected and writable.

## Step 6. The smallest safe write, the LED

```
openhal write desk-kit.led true
openhal read desk-kit.led
openhal write desk-kit.led false
```

Expected. The onboard LED turns on, the read says `true`, then the LED turns off.

## Step 7. PWM, servo and the safe state

```
openhal write desk-kit.fan "20 %"
openhal read desk-kit.fan
openhal write desk-kit.pointer "90 degree"
openhal stop
openhal read desk-kit.fan
openhal unlock
```

Expected. The fan runs slowly and reads about `20 %` (PWM value 51). The servo moves to the middle. After `openhal stop` the fan reads `0 %` and the LED is off. The servo stays where it is, as the file's `safe_state_note` says.

## Step 8. A blocked write never reaches the board

```
openhal write desk-kit.fan "95 %"
```

Expected. Blocked with code `above_max` (the example limits the fan to 80 %). The fan doesn't change. Stop the hub with `kill %1` when done.

## Report template

```
Driver: firmata
OpenHAL version:
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
Anything unexpected (paste exact output):
Result: verified-on-hardware / failed at step N
```

A passing report lets the device file set `provenance.verification.status: verified-on-hardware` with `report:` pointing at the saved report.
