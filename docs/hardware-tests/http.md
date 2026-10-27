# Hardware test plan, http driver

This plan checks the http driver against a real device with a local HTTP API. The plan starts with read-only checks and ends with the smallest safe write. The plan was written for a Shelly Plus Plug S with nothing plugged into it, and works the same way for any device you describe in a device file.

Never plug a load into the device while you run the write steps. Run every step from the repository checkout. [README.md](README.md) has the setup and rules every plan shares.

## What you need

- A device with a local HTTP API on your network. These steps use a Shelly Plus Plug S at `192.168.1.50`. Change the address to yours.
- `curl`.
- The repository with the http extra, `uv sync --extra http`.
- A copy of the example file, `cp openhal/drivers/http/examples/smart-plug.hal.yaml my-plug.hal.yaml`, with `base_url` set to your device.

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

### 1. The device answers

```sh
curl -s http://192.168.1.50/rpc/Shelly.GetDeviceInfo
```

Expected. A JSON object with `id`, `model` and `fw_id`. If this fails, fix the network before going on.

### 2. The device file validates

```sh
uv run openhal file validate my-plug.hal.yaml
```

Expected. `valid  my-plug.hal.yaml  (bench-plug, medium hazard, read-only)`.

### 3. Identify

```sh
uv run python hwtest.py my-plug.hal.yaml identify
```

Expected. `base_url`, plus `model`, `gen`, `fw_id` and `ver` from the device.

### 4. Read every channel

```sh
uv run python hwtest.py my-plug.hal.yaml read
```

Expected. `power = 0.0 W`, a `voltage` close to your mains voltage, a `plug_temperature` in degC, `output = False` (or `True` if it was on), then `health Health(connected=True, ...)`. Compare each value with the device's own web page.

### 5. Disconnect handling

Unplug the device from the wall, then run step 4 again.

Expected. `DriverError` that names the URL and says the device is not reachable, within about 3 seconds (the `timeout`). Plug the device back in, wait for the device to rejoin the network and run step 4 again. The device should read normally.

### 6. Describe (only if your device serves an OpenAPI document)

Add `openapi: /openapi.json` (or your device's path) to `connect`, then run

```sh
uv run python hwtest.py my-plug.hal.yaml describe
```

Expected. Proposed `read`, `write` and `actions` sections. Every write and action has `suggested: true`.

## Write steps

Only do these with nothing plugged into the device.

### 7. Confirm the limits

Read the file and decide the limits and the safe state are right. Then confirm them yourself.

```sh
uv run openhal file confirm my-plug.hal.yaml
```

`openhal file confirm` lists each limit, asks you to type `confirm`, and adds a `confirmed` line with your name, the date and the `sha256` of the limits. `uv run openhal file validate my-plug.hal.yaml` then says `writable`.

### 8. The smallest safe write

```sh
uv run python hwtest.py my-plug.hal.yaml write output true
uv run python hwtest.py my-plug.hal.yaml read
uv run python hwtest.py my-plug.hal.yaml write output false
```

Expected. `done` for each write, the relay clicks, and the read in between shows `output = True`.

### 9. Stop

Turn the output on again with step 8's first command, then run

```sh
uv run python hwtest.py my-plug.hal.yaml stop
```

Expected. `bench-plug safe`, and the relay switches off.

## If something fails

Send what [README.md](README.md#if-a-step-fails) lists, plus the device model and firmware version from step 3, your device file with addresses changed if you prefer, and the output of the matching `curl` request for the failing channel.

## Report template

Save the filled-in report as `docs/hardware-tests/reports/<device id>-<date>.md`. [README.md](README.md#reports) says when it marks the device file `verified-on-hardware`.

```markdown
# Hardware report, http driver

- Plan: docs/hardware-tests/http.md
- Device: <manufacturer, model>
- Firmware: <from step 3>
- OpenHAL: <uv run openhal --version>, commit <git rev-parse --short HEAD>
- Device file: <path>, sha256 <from its confirmed line>
- Tested by: <name>, <date>

| Step | Result | Notes |
|---|---|---|
| 1 device answers | pass / fail | |
| 2 file validates | pass / fail | |
| 3 identify | pass / fail | |
| 4 read every channel | pass / fail | values matched the device's own page: yes / no |
| 5 disconnect handling | pass / fail | |
| 6 describe | pass / fail / not applicable | |
| 7 confirm limits | done | |
| 8 smallest safe write | pass / fail | |
| 9 stop | pass / fail | |

Anything unexpected:

Result: verified-on-hardware / tested-reads / failed at step N
```
