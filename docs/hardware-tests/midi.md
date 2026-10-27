# Hardware test plan, midi driver

This plan checks the midi driver against a real USB MIDI controller. The plan was written for an Akai LPD8, and any class-compliant controller with knobs, pads and pad LEDs works the same way. MIDI writes only change LEDs and parameters on the controller, so the write steps are safe on any controller that isn't wired to something physical.

Run every step from the repository checkout. [README.md](README.md) has the setup and rules every plan shares. Close any music software that has the controller open, since some systems give a port to one program at a time.

## What you need

- A USB MIDI controller plugged into the computer.
- An independent MIDI monitor to cross-check, such as `aseqdump` on Linux (`aseqdump -l` then `aseqdump -p <port>`), MIDI Monitor on macOS, or MIDI-OX on Windows.
- The repository with the midi extra, `uv sync --extra midi`.
- A copy of the example file, `cp openhal/drivers/midi/examples/lpd8-pads.hal.yaml my-pads.hal.yaml`, with `name` set to part of your controller's port name and the CC and note numbers set from its MIDI implementation chart.

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

### 1. The controller is listed

```sh
uv run python -c "import asyncio; from openhal.drivers.midi.driver import MidiDriver; print(*asyncio.run(MidiDriver.discover()), sep='\n')"
```

Expected. One line per MIDI port, including your controller with `(input and output)`. Listing doesn't open any port.

### 2. The device file validates

```sh
uv run openhal file validate my-pads.hal.yaml
```

Expected. `valid  my-pads.hal.yaml  (pad-controller, low hazard, read-only)`.

### 3. Describe while moving controls

```sh
uv run python hwtest.py my-pads.hal.yaml describe
```

Within three seconds of starting it, turn knob 1 and hit pad 1. Expected. Proposed read channels such as `cc_1` and `note_36`, matching what the MIDI monitor shows for the same controls.

### 4. Read every channel

The test script reads right after connecting, before any control has moved, so this step uses a small loop instead. Save it as `midiread.py`.

```python
import asyncio

from openhal.drivers import registry
from openhal.spec import load


async def main() -> None:
    file = load("my-pads.hal.yaml")
    driver = registry.load("midi")(file)
    await driver.connect()
    for _ in range(10):
        await asyncio.sleep(1)
        print({name: (await driver.read(name)).value for name in file.read})
    await driver.close()


asyncio.run(main())
```

Run `uv run python midiread.py` and turn knob 1 slowly from left to right, then press pad 1. Expected. `knob_1` is `None` until you touch it, then rises from 0 to 100, and `pad_1` is `True` while the pad is held. The values match the MIDI monitor.

### 5. Unplug handling

Run `uv run python hwtest.py my-pads.hal.yaml read`, which ends with a health line, then unplug the controller and run it again.

Expected. The first run ends with `health Health(connected=True, ...)`. The second run fails with a `DriverError` saying no MIDI input port matches and listing the ports there are. Plug it back in and the first command works again.

## Write steps

Watch the controller's pads during these steps. Some controllers don't light their pads from incoming notes. On those, check the messages in a MIDI monitor that can watch what is sent to the controller.

### 6. Confirm the limits

Read the file and decide the limits and the safe state are right. Then confirm them yourself.

```sh
uv run openhal file confirm my-pads.hal.yaml
```

`openhal file confirm` lists each limit, asks you to type `confirm`, and adds a `confirmed` line with your name, the date and the `sha256` of the limits. `uv run openhal file validate my-pads.hal.yaml` then says `writable`.

### 7. The smallest safe write

```sh
uv run python hwtest.py my-pads.hal.yaml write pad_1_led true
uv run python hwtest.py my-pads.hal.yaml write pad_1_led false
```

Expected. `done` for each write, and pad 1 lights and goes dark. A monitor on the controller's port shows `Note On 36 velocity 127` then `Note Off 36`.

### 8. Stop

Light pad 1 with the first command of the previous step, then run

```sh
uv run python hwtest.py my-pads.hal.yaml stop
```

Expected. `pad-controller safe`, and both pad LEDs go dark.

## If something fails

Send what [README.md](README.md#if-a-step-fails) lists, plus the port list from step 1, what the MIDI monitor showed at the same time, the controller model and firmware version, the operating system, and your device file.

## Report template

Save the filled-in report as `docs/hardware-tests/reports/<device id>-<date>.md`. [README.md](README.md#reports) says when it marks the device file `verified-on-hardware`.

```markdown
# Hardware report, midi driver

- Plan: docs/hardware-tests/midi.md
- Device: <manufacturer, model>
- Firmware: <version>
- Host: <computer, operating system, Python version>
- OpenHAL: <uv run openhal --version>, commit <git rev-parse --short HEAD>
- Device file: <path>, sha256 <from its confirmed line>
- Tested by: <name>, <date>

| Step | Result | Notes |
|---|---|---|
| 1 the controller is listed | pass / fail | |
| 2 the device file validates | pass / fail | |
| 3 describe while moving controls | pass / fail | |
| 4 read every channel | pass / fail | |
| 5 unplug handling | pass / fail | |
| 6 confirm limits | done | |
| 7 the smallest safe write | pass / fail | |
| 8 stop | pass / fail | |

Anything unexpected:

Result: verified-on-hardware / tested-reads / failed at step N
```
