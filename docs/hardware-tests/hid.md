# Hardware test plan, hid driver

This plan checks the hid driver against a real USB HID device. It was written for a homemade macropad with key LEDs (any board running a TinyUSB or Arduino HID sketch whose reports you know), and works the same way for any HID device described in a device file. Writing an LED report is the smallest write that proves the path works.

Run every step from the repository checkout. Don't use a keyboard or mouse you rely on, since some systems release it from the desktop while the driver holds it.

## What you need

- The HID device, plugged in.
- Its report layout, from its firmware or documentation.
- An independent HID tool to cross-check, such as `hidapitester` (https://github.com/todbot/hidapitester), or `usbhid-dump` on Linux.
- On Linux, a udev rule that lets your user open the device (see docs/drivers/hid.md).
- The repository with the hid extra, `uv sync --extra hid`.
- A copy of the example file, `cp openhal/drivers/hid/examples/diy-macropad.hal.yaml my-pad.hal.yaml`, with `match.usb` and the maps set for your device.

## The test script

Save this as `hwtest.py` in the repository root. It drives the device only through the safety kernel, as the hub does.

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

### 1. The device is listed

```sh
uv run python -c "import asyncio; from openhal.drivers.hid.driver import HidDriver; print(*asyncio.run(HidDriver.discover()), sep='\n')"
```

Expected. One line per HID interface, including yours with its `usb` id and product name. Composite devices show several interfaces. Note the one with your reports, and set `usage_page` or `interface` in the file if more than one matches. Listing doesn't open anything.

### 2. The device file validates

```sh
uv run openhal file validate my-pad.hal.yaml
```

Expected. `valid  my-pad.hal.yaml  (desk-macropad, low hazard, read-only)`.

### 3. Identify and describe

```sh
uv run python hwtest.py my-pad.hal.yaml identify
uv run python hwtest.py my-pad.hal.yaml describe
```

Expected. `identify` before connecting prints the `usb` id. `describe` prints proposed channels from the report descriptor, with buttons and LEDs named, which should match your firmware's layout. Compare with `hidapitester --vidpid 1209:0001 --open --get-report-descriptor` if you have it.

### 4. Read every channel

Hold key 1 down and run

```sh
uv run python hwtest.py my-pad.hal.yaml read
```

Expected. `key_1 = True` if the device sent a report since the driver connected, otherwise `None`, which is correct for a device that only reports changes. Turn the knob while running it again and `knob` shows a value between 0 and 100. The LED channels show `None` because nothing has been written yet.

### 5. Unplug handling

Run step 4, unplug the device, and run it again.

Expected. The second run fails with `DriverError` saying no HID interfaces match. Plug it back in and step 4 works again.

## Write steps



### 6. Confirm the limits

Read the file, decide the limits and the safe state are right, and add this line yourself.

```yaml
confirmed: { by: <your name>, at: <today's date> }
```

`uv run openhal file validate my-pad.hal.yaml` should now say `writable`.

### 7. The smallest safe write

```sh
uv run python hwtest.py my-pad.hal.yaml write key_1_led true
uv run python hwtest.py my-pad.hal.yaml write key_1_led false
```

Expected. `done` for each write, and the key 1 LED lights and goes dark. The first write sends output report 2 as `02 01 00`, which you can compare with `hidapitester --vidpid 1209:0001 --open --send-output 2,1,0`.

The driver keeps each output report's buffer for as long as the driver object lives, and every run of `hwtest.py` is a new one, so fields not written in a run go out as zero. In the hub the buffer lasts for the whole session.

### 8. Stop

Light the LED with the first command of the previous step, then run

```sh
uv run python hwtest.py my-pad.hal.yaml stop
```

Expected. `desk-macropad safe`, and every key LED goes dark.

## If something fails

Send the full output of the failing step, the `discover` line for your device, the report descriptor (`hidapitester ... --get-report-descriptor` or `usbhid-dump -e descriptor`), a capture of a few input reports from the same tool, the firmware's report layout, the operating system and your device file.

## Report template

Save the filled-in report as `reports/<device-id>-<date>.md` and set `provenance.verification` in the device file to `{ status: verified-on-hardware, report: reports/<device-id>-<date>.md }`.

```markdown
# Hardware report, hid driver

- Device: <manufacturer, model>
- Firmware: <version>
- Host: <computer, operating system>
- OpenHAL commit: <git rev-parse --short HEAD>
- Tested by: <name>, <date>

| Step | Result | Notes |
|---|---|---|
| 1 the device is listed | pass / fail | |
| 2 the device file validates | pass / fail | |
| 3 identify and describe | pass / fail | |
| 4 read every channel | pass / fail | |
| 5 unplug handling | pass / fail | |
| 6 confirm limits | done | |
| 7 the smallest safe write | pass / fail | |
| 8 stop | pass / fail | |

Anything unexpected:
```
