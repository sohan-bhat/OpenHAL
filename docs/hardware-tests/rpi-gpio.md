# Hardware test plan, rpi-gpio driver

This plan checks the rpi-gpio driver on a real Raspberry Pi with an LED and a push button on a breadboard. Nothing in it switches a mains load. An LED that lights is the smallest write that proves the path works.

Run every step on the Pi, from the repository checkout. [README.md](README.md) has the setup and rules every plan shares.

## What you need

- A Raspberry Pi with Raspberry Pi OS Trixie or later, and your user in the `gpio` group. Bookworm's Python 3.11 is older than the 3.12 OpenHAL needs.
- An LED with a 330 ohm resistor from GPIO 17 (header pin 11) to ground, and a push button from GPIO 27 (header pin 13) to ground.
- `pinctrl` (part of Raspberry Pi OS) to check pin levels independently.
- The repository set up as [README.md](README.md#on-a-raspberry-pi) says, with the rpi-gpio extra. The last command there prints the lgpio module's path.
- This device file, saved as `my-gpio.hal.yaml`.

```yaml
device: Breadboard
id: breadboard
connect: { rpi-gpio: { led: 17, button: 27 } }
read:
  button: { type: bool }
write:
  led: { type: bool }
safe_state: { led: false }
hazard: low
```

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

### 1. The board is detected

```sh
uv run python -c "import asyncio; from openhal.drivers.rpi_gpio.driver import RpiGpioDriver; print(asyncio.run(RpiGpioDriver.discover()))"
```

Expected. One `Discovered` entry whose label is your Pi model, the same as `cat /proc/device-tree/model`.

### 2. The device file validates

```sh
uv run openhal file validate my-gpio.hal.yaml
```

Expected. `valid  my-gpio.hal.yaml  (breadboard, low hazard, read-only)`.

### 3. Identify

```sh
uv run python hwtest.py my-gpio.hal.yaml identify
```

Expected. `board` is your Pi model and `pin_factory` is `auto` (connecting picks lgpio).

### 4. Read the button

```sh
uv run python hwtest.py my-gpio.hal.yaml read
```

Run the command once with the button released and once while holding the button. Expected. `button = False`, then `button = True`, and `led = False` both times, because connecting starts the LED output inactive. `pinctrl get 27` shows `hi` released and `lo` pressed.

### 5. The stop button helper

Save this as `stopbutton.py` and run `uv run python stopbutton.py`, then press the button a few times within ten seconds.

```python
import asyncio

from openhal.drivers.rpi_gpio import watch_stop_button


async def main() -> None:
    presses = []
    button = watch_stop_button(27, lambda: presses.append("stop"), loop=asyncio.get_running_loop())
    await asyncio.sleep(10)
    button.close()
    print(len(presses), "presses")


asyncio.run(main())
```

Expected. The count matches the number of presses, with no extra counts from contact bounce.

## Write steps



### 6. Confirm the limits

Read the file and decide the limits and the safe state are right. Then confirm them yourself.

```sh
uv run openhal file confirm my-gpio.hal.yaml
```

`openhal file confirm` lists each limit, asks you to type `confirm`, and adds a `confirmed` line with your name, the date and the `sha256` of the limits. `uv run openhal file validate my-gpio.hal.yaml` then says `writable`.

### 7. The smallest safe write

```sh
uv run python hwtest.py my-gpio.hal.yaml write led true
pinctrl get 17
uv run python hwtest.py my-gpio.hal.yaml write led false
```

Expected. `done` for each write. The LED lights while the first command runs and goes dark when it ends, because the script releases the pins when it exits. Note what `pinctrl get 17` shows after the first command (usually `ip`, an input, once the pin is released), since that is what a relay sees when the hub stops.

### 8. Stop

Save this as `gpiostop.py` and run `uv run python gpiostop.py`.

```python
import asyncio

from openhal.drivers import registry
from openhal.kernel import Kernel
from openhal.kernel.commands import Write
from openhal.kernel.principals import human
from openhal.spec import load


async def main() -> None:
    file = load("my-gpio.hal.yaml")
    driver = registry.load("rpi-gpio")(file)
    kernel = Kernel()
    kernel.register(file, driver)
    await kernel.connect(file.device_id)
    me = human("hardware-tester")
    print((await kernel.execute(Write(device=file.device_id, channel="led", value=True), me)).status)
    await asyncio.sleep(2)
    report = await kernel.stop_all(me, "hardware test")
    print([(result.device, result.status) for result in report.devices])
    await asyncio.sleep(2)
    await driver.close()


asyncio.run(main())
```

Expected. `done`, the LED lights for two seconds, then `[('breadboard', 'safe')]` and the LED goes dark while the script is still running.

## If something fails

Send what [README.md](README.md#if-a-step-fails) lists, plus `pinctrl get 17,27` before and after, the Pi model, `cat /etc/os-release`, the gpiozero version (`uv run python -c "from importlib.metadata import version; print(version('gpiozero'))"`), the lgpio package version (`apt policy python3-lgpio`), and a photo of the wiring.

## Report template

Save the filled-in report as `docs/hardware-tests/reports/<device id>-<date>.md`. [README.md](README.md#reports) says when it marks the device file `verified-on-hardware`.

```markdown
# Hardware report, rpi-gpio driver

- Plan: docs/hardware-tests/rpi-gpio.md
- Device: <manufacturer, model>
- gpiozero and lgpio versions: <version>
- Host: <Raspberry Pi model, Raspberry Pi OS version>
- OpenHAL: <uv run openhal --version>, commit <git rev-parse --short HEAD>
- Device file: my-gpio.hal.yaml, sha256 <from its confirmed line>
- Tested by: <name>, <date>

| Step | Result | Notes |
|---|---|---|
| 1 the board is detected | pass / fail | |
| 2 the device file validates | pass / fail | |
| 3 identify | pass / fail | |
| 4 read the button | pass / fail | |
| 5 the stop button helper | pass / fail | |
| 6 confirm limits | done | |
| 7 the smallest safe write | pass / fail | |
| 8 stop | pass / fail | |

Anything unexpected:

Result: verified-on-hardware / tested-reads / failed at step N
```
