# Hardware test plan, ble driver

This plan checks the ble driver against real Bluetooth Low Energy peripherals. The read-only part uses a sensor with the standard Environmental Sensing service. The write part uses a board with an LED on a writable characteristic, because a light that changes is the smallest write that proves the path works.

Run every step from the repository checkout. [README.md](README.md) has the setup and rules every plan shares. Close any phone app connected to the peripheral first, since most peripherals accept only one central.

## What you need

- A computer with Bluetooth LE (Linux with BlueZ 5.55 or newer, macOS, or Windows 10 or newer).
- A sensor with the Environmental Sensing service, for example an nRF52 or ESP32 board running the Zephyr or ArduinoBLE environmental sensing sample.
- For the write steps, a board with an LED brightness characteristic. The ArduinoBLE `LED` example on an Arduino Nano 33 BLE works, with characteristic `19b10001-e8f2-537e-4f6c-d104768a1214` (one byte, 0 is off).
- A second, independent BLE tool to cross-check, such as nRF Connect for Mobile, or `bluetoothctl` on Linux.
- The repository with the ble extra, `uv sync --extra ble`.
- A copy of the example file, `cp openhal/drivers/ble/examples/environment-sensor.hal.yaml my-sensor.hal.yaml`, with `match.ble_name` set to your sensor's advertised name.

## The test script

Save this as `hwtest.py` in the repository root. The script drives the device only through the safety kernel, as the hub does.

```python
"""Usage: uv run python hwtest.py FILE identify|describe|read|write CHANNEL VALUE|stop"""

import asyncio
import json
import sys

from openhal.drivers import registry
from openhal.kernel import Kernel
from openhal.kernel.commands import Write
from openhal.kernel.principals import human
from openhal.spec import load


async def main(path: str, command: str, *rest: str) -> None:
    file = load(path)
    driver = registry.load(file.connect.driver)(file)
    if command == "identify":
        print(json.dumps(await driver.identify(), indent=2))
        return
    kernel = Kernel()
    kernel.register(file, driver)
    await kernel.connect(file.device_id)
    me = human("hardware-tester")
    try:
        if command == "describe":
            print(json.dumps(await driver.describe(), indent=2, default=str))
        elif command == "read":
            for channel in [*file.read, *file.write]:
                reading = await kernel.read(file.device_id, channel, me)
                value = f"<{len(reading.value)} bytes>" if isinstance(reading.value, bytes) else reading.value
                print(f"{channel} = {value} {reading.unit or ''}{' (suspect)' if reading.suspect else ''}")
        elif command == "write":
            channel, value = rest
            parsed = {"true": True, "false": False}.get(value, value)
            decision = await kernel.execute(Write(device=file.device_id, channel=channel, value=parsed), me)
            print(decision.status, decision.code or "", decision.message)
        elif command == "stop":
            report = await kernel.stop_all(me, "hardware test")
            for result in report.devices:
                print(result.device, result.status, result.detail)
        print("health", await driver.health())
    finally:
        await driver.close()


asyncio.run(main(*sys.argv[1:]))
```

## Read-only steps

### 1. Find the peripheral

```sh
uv run python -c "import asyncio; from openhal.drivers.ble.driver import BleDriver; print(*asyncio.run(BleDriver.discover()), sep='\n')"
```

Expected. One line per advertising peripheral, with its address (a UUID on macOS) and `ble_name`. Your sensor is in the list, with `181a` in `ble_services` if the sensor advertises the service. The scan only listens and never connects.

### 2. The device file validates

```sh
uv run openhal file validate my-sensor.hal.yaml
```

Expected. `valid  my-sensor.hal.yaml  (room-climate, low hazard, read-only)`.

### 3. Identify and describe

```sh
uv run python hwtest.py my-sensor.hal.yaml describe
```

Expected. `match.ble_services` with `181a`, read channels such as `temperature` and `humidity` with `stream: true` if the sensor notifies, `device` from the Device Information service if it has one, and notes listing any vendor characteristics. Compare the service list with nRF Connect.

### 4. Read every channel

```sh
uv run python hwtest.py my-sensor.hal.yaml read
```

Expected. A `temperature` and `humidity` close to a reference thermometer, `pressure` near your local air pressure in hPa, `battery` in percent, and `health Health(connected=True, ...)`. A channel that only notifies and has not sent anything yet shows `None`. Run it again after a minute and it should show values.

### 5. Out of range

Start step 4 and, while it runs, carry the sensor out of range or remove its battery. Then run step 4 again.

Expected. A `DriverError` saying the device could not be connected (or that the read failed), and `health` reports the link dropped. Bring the sensor back and run step 4. The device reads normally.

## Write steps

These steps use the LED board. Save this as `my-led.hal.yaml`, with `address` set from step 1.

```yaml
device: LED board
id: led-board
connect: { ble: "<address from step 1>" }
write:
  led: { type: bool, map: { characteristic: 19b10001-e8f2-537e-4f6c-d104768a1214, on: 1, off: 0 } }
safe_state: { led: false }
hazard: low
```

Run `uv run python hwtest.py my-led.hal.yaml read` first. The script should print `led = False` (or `True`).

### 6. Confirm the limits

Read the file and decide the limits and the safe state are right. Then confirm them yourself.

```sh
uv run openhal file confirm my-led.hal.yaml
```

`openhal file confirm` lists each limit, asks you to type `confirm`, and adds a `confirmed` line with your name, the date and the `sha256` of the limits. `uv run openhal file validate my-led.hal.yaml` then says `writable`.

### 7. The smallest safe write

```sh
uv run python hwtest.py my-led.hal.yaml write led true
uv run python hwtest.py my-led.hal.yaml read
uv run python hwtest.py my-led.hal.yaml write led false
```

Expected. `done` for each write, the LED turns on and off, and the read in between shows `led = True`. Reading the characteristic in nRF Connect shows `0x01` while it is on.

### 8. Stop

Turn the LED on with the first command of the previous step, then run

```sh
uv run python hwtest.py my-led.hal.yaml stop
```

Expected. `led-board safe`, and the LED turns off.

## If something fails

Send what [README.md](README.md#if-a-step-fails) lists, plus the operating system and Bluetooth adapter, the `discover` output from step 1, a screenshot or export of the peripheral's GATT table from nRF Connect, and your device file. On Linux, add the output of `bluetoothctl --version` and `journalctl -u bluetooth --since "10 min ago"`.

## Report template

Save the filled-in report as `docs/hardware-tests/reports/<device id>-<date>.md`. [README.md](README.md#reports) says when it marks the device file `verified-on-hardware`.

```markdown
# Hardware report, ble driver

- Plan: docs/hardware-tests/ble.md
- Device: <manufacturer, model>
- Peripheral firmware: <version>
- Host: <computer, operating system, Bluetooth adapter>
- OpenHAL: <uv run openhal --version>, commit <git rev-parse --short HEAD>
- Device files: my-sensor.hal.yaml (read-only), and my-led.hal.yaml, sha256 <from its confirmed line>
- Tested by: <name>, <date>

| Step | Result | Notes |
|---|---|---|
| 1 find the peripheral | pass / fail | |
| 2 the device file validates | pass / fail | |
| 3 identify and describe | pass / fail | |
| 4 read every channel | pass / fail | |
| 5 out of range | pass / fail | |
| 6 confirm limits | done | |
| 7 the smallest safe write | pass / fail | |
| 8 stop | pass / fail | |

Anything unexpected:

Result: verified-on-hardware / tested-reads / failed at step N
```
