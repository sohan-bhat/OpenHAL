# Hardware test plan, knx driver

This plan checks the knx driver against a real KNX installation through a KNXnet/IP interface. It was made for the example file, a room with a dimmer actuator, a thermostat and a window contact. Change the group addresses to the ones in your ETS project.

Run every step from the repository checkout, on a computer on the same network as the interface. [README.md](README.md) has the setup and rules every plan shares. Ask the installation's owner before you change anything on the bus.

## What you need

- A KNXnet/IP interface or router with a free tunnel, at for example `192.168.1.20`.
- The ETS group address list with each address's DPT.
- The repository with the extra, `uv sync --extra knx`.
- A copy of the example, `cp openhal/drivers/knx/examples/living-room.hal.yaml my-room.hal.yaml`, with your addresses.

## The test script

Save this as `hwtest.py` in the repository root. It drives the device only through the safety kernel, as the hub does. `set` waits one second first, because the kernel measures the first change's rate from the moment the device connected.

```python
"""Usage: uv run python hwtest.py FILE identify|describe|read|set CHANNEL VALUE|action NAME [ARG=VALUE ...]|stop"""

import asyncio
import json
import sys

from openhal.drivers import registry
from openhal.kernel import Kernel
from openhal.kernel.commands import Action, Write
from openhal.kernel.principals import human
from openhal.spec import load


def parse(text: str) -> object:
    return {"true": True, "false": False}.get(text, text)


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
        elif command == "set":
            channel, value = rest
            await asyncio.sleep(1.0)
            decision = await kernel.execute(Write(device=file.device_id, channel=channel, value=parse(value)), me)
            print(decision.status, decision.code or "", decision.message)
        elif command == "action":
            name, *pairs = rest
            args = {key: parse(value) for key, value in (pair.split("=", 1) for pair in pairs)}
            decision = await kernel.execute(Action(device=file.device_id, action=name, args=args), me)
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

### 1. The interface answers

```sh
uv run python -c "import asyncio; from openhal.drivers.knx.driver import KnxDriver; print(asyncio.run(KnxDriver.discover()))"
```

Expected. Your interface with its address, port and name. Routers on another subnet may not answer a search, which is fine if the next steps work.

### 2. The device file validates

```sh
uv run openhal file validate my-room.hal.yaml
```

Expected. `valid  my-room.hal.yaml  (living-room-knx, low hazard, read-only)`.

### 3. Identify and read

```sh
uv run python hwtest.py my-room.hal.yaml identify
uv run python hwtest.py my-room.hal.yaml read
```

Expected. The first prints the gateway and `tunneling`. The read shows `temperature` within 1 degC of the room thermostat's display, `ceiling_light` and `ceiling_dimmer` as the light is, and `heating_setpoint` and `hvac_mode` as the thermostat shows. A value of `None` means the address doesn't answer reads. Check its read flag in ETS.

### 4. Bus changes reach the driver

Run the read again while someone switches the light at the wall.

Expected. `ceiling_light` follows the switch.

### 5. Interface loss

Unplug the interface's network cable and run step 3.

Expected. `DriverError` or `TimeoutError` saying the interface did not accept a connection. Plug it back in, wait a few seconds, and run step 3. It reads normally.

## Steps that change the device

### 6. Confirm the limits

Read the file and decide the limits, the interlock and the safe state are right. Then confirm them yourself.

```sh
uv run openhal file confirm my-room.hal.yaml
```

It lists each limit, asks you to type `confirm`, and adds a `confirmed` line with your name, the date and the `sha256` of the limits. `uv run openhal file validate my-room.hal.yaml` then says `writable`.

### 7. The smallest safe change

```sh
uv run python hwtest.py my-room.hal.yaml set ceiling_light true
uv run python hwtest.py my-room.hal.yaml read
uv run python hwtest.py my-room.hal.yaml set ceiling_light false
```

Expected. `done` for each command, the light turns on and off, and the read shows `ceiling_light = True` from the status address.

### 8. A dimmed value

```sh
uv run python hwtest.py my-room.hal.yaml set ceiling_dimmer "30 percent"
uv run python hwtest.py my-room.hal.yaml read
```

Expected. `done`, the light dims to about 30 %, and the read shows `ceiling_dimmer` close to `30.0 percent` as the actuator reports it.

### 9. The interlock

Open the window, then run

```sh
uv run python hwtest.py my-room.hal.yaml set heating_setpoint "22 degC"
```

Expected. `blocked interlock` with the message to close the window, and nothing is sent. Close the window and run it again. `done`, and the thermostat shows 22 degC.

### 10. Stop

Turn the light on with the first command of step 7, then run

```sh
uv run python hwtest.py my-room.hal.yaml stop
```

Expected. `living-room-knx safe`, and the light turns off.

## If something fails

Send what [README.md](README.md#if-a-step-fails) lists, plus the interface's make, model and firmware, the group addresses and DPTs from ETS for the channels involved, and your device file.

## Report template

Save the filled-in report as `docs/hardware-tests/reports/<device id>-<date>.md`. [README.md](README.md#reports) says when it marks the device file `verified-on-hardware`.

```markdown
# Hardware report, knx driver

- Plan: docs/hardware-tests/knx.md
- Installation: <actuator and sensor makes and models>
- Interface: <make, model, firmware, tunneling or routing>
- Host: <computer, operating system>
- OpenHAL: <uv run openhal --version>, commit <git rev-parse --short HEAD>
- Device file: <path>, sha256 <from its confirmed line>
- Tested by: <name>, <date>

| Step | Result | Notes |
|---|---|---|
| 1 the interface answers | pass / fail | |
| 2 the device file validates | pass / fail | |
| 3 identify and read | pass / fail | |
| 4 bus changes reach the driver | pass / fail | |
| 5 interface loss | pass / fail | |
| 6 confirm limits | done | |
| 7 the smallest safe change | pass / fail | |
| 8 a dimmed value | pass / fail | |
| 9 the interlock | pass / fail | |
| 10 stop | pass / fail | |

Anything unexpected:

Result: verified-on-hardware / tested-reads / failed at step N
```
