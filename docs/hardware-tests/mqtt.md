# Hardware test plan, mqtt driver

This plan checks the mqtt driver against a real broker and a real device. It was written for a Tasmota smart plug with nothing plugged into it and a Mosquitto broker on the local network. Any device described in a device file works the same way.

Run every step from the repository checkout. Never plug a load into the device while you run the write steps.

## What you need

- A Mosquitto broker at, for example, `192.168.1.10`, with a user `openhal`.
- A Tasmota plug connected to that broker, with its Topic set to `bench_plug` and `PowerRetain 1` set in its console.
- The Mosquitto command line clients (`mosquitto_sub`), to watch the broker independently.
- The repository with the mqtt extra, `uv sync --extra mqtt`.
- A copy of the example file, `cp openhal/drivers/mqtt/examples/tasmota-plug.hal.yaml my-plug.hal.yaml`, with the broker address and topics set to yours.
- The broker password in the environment, `export MQTT_PASSWORD=...`.

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

### 1. The broker carries the device's messages

```sh
mosquitto_sub -h 192.168.1.10 -u openhal -P "$MQTT_PASSWORD" -v -t 'stat/bench_plug/#' -t 'tele/bench_plug/#' -W 330
```

Expected. A retained `stat/bench_plug/POWER OFF` (or `ON`) at once, and a `tele/bench_plug/SENSOR` JSON message within the telemetry period (300 s by default, `TelePeriod 10` makes it faster). Stop it with Ctrl-C.

### 2. The device file validates

```sh
uv run openhal file validate my-plug.hal.yaml
```

Expected. `valid  my-plug.hal.yaml  (bench-mqtt-plug, medium hazard, read-only)`.

### 3. Identify

```sh
uv run python hwtest.py my-plug.hal.yaml identify
```

Expected. The `broker` address and the `client_id` the driver will use.

### 4. Read every channel

```sh
uv run python hwtest.py my-plug.hal.yaml read
```

Expected. `relay = False` (or `True`) from the retained state. `power`, `voltage` and `energy_today` show values if a SENSOR message was retained or arrived within half a second, and `None` otherwise, which is correct for a topic with nothing retained. Set `TelePeriod 10` and run it again a few times. The values should match the plug's web page.

### 5. Broker loss

Stop the broker (`sudo systemctl stop mosquitto`), then run step 4 again.

Expected. `DriverError` saying the broker could not be reached. Start the broker again and run step 4. It reads normally.

### 6. Describe

Set `discover_topic: "+/bench_plug/#"` under `connect`, then run

```sh
uv run python hwtest.py my-plug.hal.yaml describe
```

Expected. Proposed read channels such as `stat_bench_plug_power` (bool) and, if a SENSOR message arrived while it listened, `tele_bench_plug_sensor_time`. Nested JSON objects such as `ENERGY` are not expanded. Remove `discover_topic` afterwards.

## Write steps

Keep `mosquitto_sub` from step 1 running in another terminal while you do these, so you can see every command the driver publishes.

### 7. Confirm the limits

Read the file, decide the limits and the safe state are right, and add this line yourself.

```yaml
confirmed: { by: <your name>, at: <today's date> }
```

`uv run openhal file validate my-plug.hal.yaml` should now say `writable`.

### 8. The smallest safe write

```sh
uv run python hwtest.py my-plug.hal.yaml write relay true
uv run python hwtest.py my-plug.hal.yaml read
uv run python hwtest.py my-plug.hal.yaml write relay false
```

Expected. `done` for each write, the relay clicks, and `mosquitto_sub` shows `stat/bench_plug/POWER ON` then `OFF`. The read in between shows `relay = True`. To see the command topic itself, subscribe to `cmnd/bench_plug/#` as well and look for `cmnd/bench_plug/POWER ON`.

### 9. Stop

Turn the relay on again with the first command of the previous step, then run

```sh
uv run python hwtest.py my-plug.hal.yaml stop
```

Expected. `bench-mqtt-plug safe`, the relay clicks off and `mosquitto_sub` shows `stat/bench_plug/POWER OFF`.

## If something fails

Send the full output of the failing step, the `mosquitto_sub -v` output covering the same time, the broker version and its log lines for the OpenHAL client id, the device firmware version, and your device file.

## Report template

Save the filled-in report as `reports/<device-id>-<date>.md` and set `provenance.verification` in the device file to `{ status: verified-on-hardware, report: reports/<device-id>-<date>.md }`.

```markdown
# Hardware report, mqtt driver

- Device: <manufacturer, model>
- Firmware: <version>
- Host: <computer, operating system, broker and version>
- OpenHAL commit: <git rev-parse --short HEAD>
- Tested by: <name>, <date>

| Step | Result | Notes |
|---|---|---|
| 1 the broker carries the device's messages | pass / fail | |
| 2 the device file validates | pass / fail | |
| 3 identify | pass / fail | |
| 4 read every channel | pass / fail | |
| 5 broker loss | pass / fail | |
| 6 describe | pass / fail | |
| 7 confirm limits | done | |
| 8 the smallest safe write | pass / fail | |
| 9 stop | pass / fail | |

Anything unexpected:
```
