# Hardware test plan, can driver

This plan checks the can driver against a real CAN bus. It was made for a Linux computer (a Raspberry Pi works) with a USB CAN adapter and a VESC motor controller, using the example file. Any node described in a device file works the same way.

Run every step from the repository checkout. Take the load off the motor, or remove the motor, before the steps that change anything.

## What you need

- A USB CAN adapter that Linux sees as a SocketCAN interface, such as a CANable with candleLight firmware.
- A VESC with controller id 1, CAN status messages 1, 4 and 5 enabled at 50 Hz in VESC Tool, and a command timeout set in its app settings.
- Both ends of the bus terminated with 120 ohm, and a common ground.
- can-utils for an independent view of the bus, `sudo apt install can-utils`.
- The repository with the can extra, `uv sync --extra can`.
- A copy of the example file, `cp openhal/drivers/can/examples/vesc-motor-controller.hal.yaml my-vesc.hal.yaml`. Change the ids if your controller id isn't 1.

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

### 1. The interface is up

```sh
sudo ip link set can0 up type can bitrate 500000
ip -details link show can0
```

Expected. `state UP` on the first line, and `can state ERROR-ACTIVE` with `bitrate 500000` further down.

### 2. The bus carries the node's frames

```sh
candump -tz can0
```

Expected. With the VESC powered, frames with ids `00000901`, `00001001` and `00001B01` repeat about every 20 ms. Stop it with Ctrl-C.

### 3. The device file validates

```sh
uv run openhal file validate my-vesc.hal.yaml
```

Expected. `valid  my-vesc.hal.yaml  (bench-vesc, medium hazard, read-only)`.

### 4. Identify and discover

```sh
uv run python hwtest.py my-vesc.hal.yaml identify
uv run python -c "import asyncio; from openhal.drivers.can.driver import CanDriver; print(asyncio.run(CanDriver.discover()))"
```

Expected. The first prints `socketcan`, `can0` and the bitrate. The second lists `socketcan:can0`.

### 5. Read every channel

```sh
uv run python hwtest.py my-vesc.hal.yaml read
```

Expected. `erpm = 0.0 rpm`, `motor_current` close to `0.0 A`, the two temperatures close to room temperature, and `input_voltage` matching the supply. `erpm_target = None`, because nothing was sent yet. Compare the values with VESC Tool's realtime data page. A value that is off by a factor of ten or reads as a huge number means a wrong scale, length or byte order in the map.

### 6. Describe

```sh
uv run python hwtest.py my-vesc.hal.yaml describe
```

Expected. Proposed read channels `frame_901`, `frame_1001` and `frame_1b01`, each the first bytes of that frame as one number.

### 7. Bus loss

Run `sudo ip link set can0 down`, then run step 5 again.

Expected. The connect fails with `DriverError` and a hint to bring the interface up, or the reads fail with `DriverError` saying the bus failed. Bring the interface up again with step 1 and run step 5. It reads normally.

## Steps that change the device

Keep `candump -tz can0` from step 2 running in another terminal while you do these, so you can see every frame the driver sends.

### 8. Confirm the limits

Read the file, decide the limits and the safe state are right for your motor, and add this line yourself.

```yaml
confirmed: { by: <your name>, at: <today's date> }
```

`uv run openhal file validate my-vesc.hal.yaml` should now say `writable`.

### 9. The smallest safe frame

```sh
uv run python hwtest.py my-vesc.hal.yaml action coast
```

Expected. `done`, and candump shows `00000101   [4]  00 00 00 00`. A stopped motor stays stopped.

### 10. A small change

With the motor unloaded and clamped, run

```sh
uv run python hwtest.py my-vesc.hal.yaml set erpm_target "300 rpm"
uv run python hwtest.py my-vesc.hal.yaml read
uv run python hwtest.py my-vesc.hal.yaml action coast
```

Expected. `done`, candump shows `00000301   [4]  00 00 01 2C`, the motor turns slowly, and the read shows `erpm` close to `300 rpm`. The VESC command timeout stops it shortly after the script exits even without the coast action.

### 11. Stop

Run the first command of step 10 again, then run

```sh
uv run python hwtest.py my-vesc.hal.yaml stop
```

Expected. `bench-vesc safe`, candump shows the coast frame `00000101   [4]  00 00 00 00`, and the motor coasts to a stop.

## If something fails

Send the full output of the failing step, the candump output covering the same time, `ip -details -statistics link show can0`, the adapter model and firmware, the node's firmware version, and your device file.

## Report template

Save the filled-in report as `reports/<device-id>-<date>.md` and set `provenance.verification` in the device file to `{ status: verified-on-hardware, report: reports/<device-id>-<date>.md }`.

```markdown
# Hardware report, can driver

- Device: <manufacturer, model, controller id>
- Firmware: <version>
- Adapter: <model, firmware, interface>
- Host: <computer, operating system, kernel>
- OpenHAL commit: <git rev-parse --short HEAD>
- Tested by: <name>, <date>

| Step | Result | Notes |
|---|---|---|
| 1 the interface is up | pass / fail | |
| 2 the bus carries the node's frames | pass / fail | |
| 3 the device file validates | pass / fail | |
| 4 identify and discover | pass / fail | |
| 5 read every channel | pass / fail | |
| 6 describe | pass / fail | |
| 7 bus loss | pass / fail | |
| 8 confirm limits | done | |
| 9 the smallest safe frame | pass / fail | |
| 10 a small change | pass / fail | |
| 11 stop | pass / fail | |

Anything unexpected:
```
