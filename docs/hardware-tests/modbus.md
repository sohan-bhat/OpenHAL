# Hardware test plan, modbus driver

This plan checks the modbus driver against real Modbus devices. The read-only part uses an energy meter such as the Eastron SDM120. The write part uses a Modbus RTU relay module with nothing wired to its contacts, because a relay that clicks is the smallest write that proves the path works without moving anything.

Run every step from the repository checkout. [README.md](README.md) has the setup and rules every plan shares. Never run the write steps on a drive, heater or valve.

## What you need

- A USB to RS-485 adapter, and an SDM120 (or any meter with a published register map) wired A to A and B to B.
- For the write steps, a Modbus RTU relay module with nothing connected to its relay contacts.
- `mbpoll`, an independent command line Modbus master, to cross-check values (`brew install mbpoll` or `sudo apt install mbpoll`).
- The repository with the modbus extra, `uv sync --extra modbus`.
- A copy of the example file, `cp openhal/drivers/modbus/examples/sdm120-energy-meter.hal.yaml my-meter.hal.yaml`, with `port`, `baud` and `unit` set to match your meter.

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

### 1. The bus answers

Find the adapter (`ls /dev/ttyUSB*` on Linux, `ls /dev/cu.usbserial*` on macOS), then read the voltage register with mbpoll, which uses function 4, a read.

```sh
mbpoll -m rtu -b 2400 -P none -a 1 -t 3:float -0 -r 0 -c 1 -1 /dev/ttyUSB0
```

Expected. One line such as `[0]: 231.4`. If it times out, check the wiring, baud rate, parity and unit id before going on.

### 2. The device file validates

```sh
uv run openhal file validate my-meter.hal.yaml
```

Expected. `valid  my-meter.hal.yaml  (workshop-meter, low hazard, read-only)`.

### 3. Identify

```sh
uv run python hwtest.py my-meter.hal.yaml identify
```

Expected. `transport`, `unit` and `address`. Meters that support Read Device Identification add `vendor`, `product_code` and `revision`. Most meters don't, and that is fine.

### 4. Read every channel

```sh
uv run python hwtest.py my-meter.hal.yaml read
```

Expected. `voltage` matching mbpoll from step 1 and the meter's display, a `frequency` of 50 or 60 Hz, `power` near 0 W with no load, and `health Health(connected=True, ...)`. A value marked `(suspect)` is outside the channel's range and usually means the wrong register, word order or format.

### 5. Disconnect handling

Unplug the A and B wires from the meter, then run step 4 again.

Expected. A `TimeoutError` that says the device didn't answer and suggests checking the unit id, wiring, baud rate and parity, after about 2 seconds. Reconnect the wires and run step 4 again. The device reads normally.

## Write steps

These steps use the relay module. Copy this file to `my-relay.hal.yaml`, with `port`, `baud`, `unit` and the coil address set from the module's manual (many modules use coil 0 for relay 1, at 9600 baud).

```yaml
device: Relay module
id: relay-module
connect: { modbus: rtu, port: /dev/ttyUSB0, baud: 9600, unit: 1 }
write:
  relay_1: { type: bool, map: { register: 0, kind: coil } }
safe_state: { relay_1: false }
hazard: low
```

Run step 4 with `my-relay.hal.yaml` first. The script should print `relay_1 = False` (or `True` if the relay was on).

### 6. Confirm the limits

Read the file and decide the limits and the safe state are right. Then confirm them yourself.

```sh
uv run openhal file confirm my-relay.hal.yaml
```

`openhal file confirm` lists each limit, asks you to type `confirm`, and adds a `confirmed` line with your name, the date and the `sha256` of the limits. `uv run openhal file validate my-relay.hal.yaml` then says `writable`.

### 7. The smallest safe write

```sh
uv run python hwtest.py my-relay.hal.yaml write relay_1 true
uv run python hwtest.py my-relay.hal.yaml read
uv run python hwtest.py my-relay.hal.yaml write relay_1 false
```

Expected. `done` for each write, the relay clicks on and off, and the read in between shows `relay_1 = True`. Cross-check with `mbpoll -m rtu -b 9600 -P none -a 1 -t 0 -0 -r 0 -c 1 -1 /dev/ttyUSB0`, which reads the coil without writing.

### 8. Stop

Turn the relay on with the first command of the previous step, then run

```sh
uv run python hwtest.py my-relay.hal.yaml stop
```

Expected. `relay-module safe`, and the relay clicks off.

## If something fails

Send what [README.md](README.md#if-a-step-fails) lists, plus the matching mbpoll output, the device model and the register map page from its manual, your device file, and the adapter model. For wrong values, say what the device's own display showed at the same time.

## Report template

Save the filled-in report as `docs/hardware-tests/reports/<device id>-<date>.md`. [README.md](README.md#reports) says when it marks the device file `verified-on-hardware`.

```markdown
# Hardware report, modbus driver

- Plan: docs/hardware-tests/modbus.md
- Device: <manufacturer, model>
- Firmware: <version>
- Host: <computer, operating system, RS-485 adapter model>
- OpenHAL: <uv run openhal --version>, commit <git rev-parse --short HEAD>
- Device files: my-meter.hal.yaml (read-only), and my-relay.hal.yaml, sha256 <from its confirmed line>
- Tested by: <name>, <date>

| Step | Result | Notes |
|---|---|---|
| 1 the bus answers | pass / fail | |
| 2 the device file validates | pass / fail | |
| 3 identify | pass / fail | |
| 4 read every channel | pass / fail | |
| 5 disconnect handling | pass / fail | |
| 6 confirm limits | done | |
| 7 the smallest safe write | pass / fail | |
| 8 stop | pass / fail | |

Anything unexpected:

Result: verified-on-hardware / tested-reads / failed at step N
```
