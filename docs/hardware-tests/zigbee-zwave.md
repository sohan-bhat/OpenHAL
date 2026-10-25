# Hardware test plan, zigbee-zwave driver

This plan checks the zigbee-zwave driver against a real Zigbee2MQTT install and a real zwave-js-server, using the two example files. It was made for an IKEA TRADFRI bulb on Zigbee2MQTT and a Zooz ZEN04 plug on Z-Wave JS UI. Run the Zigbee steps, the Z-Wave steps or both.

Run every step from the repository checkout. [README.md](README.md) has the setup and rules every plan shares. Plug nothing into the Z-Wave plug.

## What you need

- Zigbee2MQTT with the bulb paired as `desk_lamp`, publishing to a Mosquitto broker at, for example, `192.168.1.10`, with availability turned on.
- Z-Wave JS UI (or zwave-js-server) with its WebSocket server on port 3000 and the plug included as node 2.
- The Mosquitto command line clients, to watch the broker independently.
- The repository with the extra, `uv sync --extra zigbee-zwave`.
- Copies of the examples, `cp openhal/drivers/zigbee_zwave/examples/ikea-bulb-zigbee2mqtt.hal.yaml my-bulb.hal.yaml` and `cp openhal/drivers/zigbee_zwave/examples/zooz-plug-zwave.hal.yaml my-plug.hal.yaml`, with your addresses, friendly name and node id.
- The broker password in the environment, `export MQTT_PASSWORD=...`.

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

### 1. Zigbee2MQTT knows the bulb

```sh
mosquitto_sub -h 192.168.1.10 -u openhal -P "$MQTT_PASSWORD" -t zigbee2mqtt/bridge/devices -C 1 | grep -o '"friendly_name":"desk_lamp"'
```

Expected. `"friendly_name":"desk_lamp"`. Then keep a watcher running in another terminal.

```sh
mosquitto_sub -h 192.168.1.10 -u openhal -P "$MQTT_PASSWORD" -v -t 'zigbee2mqtt/desk_lamp' -t 'zigbee2mqtt/desk_lamp/#'
```

### 2. The device files validate

```sh
uv run openhal file validate my-bulb.hal.yaml my-plug.hal.yaml
```

Expected. Both `valid`, the bulb `low hazard, read-only` and the plug `medium hazard, read-only`.

### 3. Read the bulb

```sh
uv run python hwtest.py my-bulb.hal.yaml read
```

Expected. `state`, `brightness` and `color_temp` match the Zigbee2MQTT frontend, with brightness in percent. The watcher shows a `zigbee2mqtt/desk_lamp/get` request and the bulb's answer.

### 4. Describe the bulb

```sh
uv run python hwtest.py my-bulb.hal.yaml describe
```

Expected. `state`, `brightness`, `color_temp` and `power_on_behavior` under `write` marked suggested, with Zigbee2MQTT's own limits, and `linkquality` under `read`.

### 5. Read the plug

```sh
uv run python hwtest.py my-plug.hal.yaml read
```

Expected. `power` close to `0.0 W`, `energy` matching Z-Wave JS UI's meter value, and `relay` matching the plug's LED. The health line ends with `alive`.

### 6. Bridge loss

Stop the broker (`sudo systemctl stop mosquitto`) and run step 3, then stop Z-Wave JS UI's server and run step 5.

Expected. Each fails with `DriverError` saying the broker or zwave-js-server could not be reached. Start them again and run steps 3 and 5. They read normally.

### 7. An offline bulb

Switch the bulb off at the wall and wait until the Zigbee2MQTT frontend shows it offline (its availability timeout, 10 minutes by default for mains devices). Run step 3.

Expected. The values read as before, from the last report, and the health line says the bulb is offline in Zigbee2MQTT. Switch it on again.

## Steps that change the device

### 8. Confirm the limits

Read both files and decide the limits and safe states are right. Then confirm each one yourself.

```sh
uv run openhal file confirm my-bulb.hal.yaml
uv run openhal file confirm my-plug.hal.yaml
```

Each lists the file's limits, asks you to type `confirm`, and adds a `confirmed` line with your name, the date and the `sha256` of the limits. `uv run openhal file validate my-bulb.hal.yaml my-plug.hal.yaml` then says `writable` for both.

### 9. The smallest safe change on Zigbee

```sh
uv run python hwtest.py my-bulb.hal.yaml set state true
uv run python hwtest.py my-bulb.hal.yaml set brightness "20 percent"
uv run python hwtest.py my-bulb.hal.yaml read
uv run python hwtest.py my-bulb.hal.yaml set state false
```

Expected. `done` for each command. The bulb turns on, dims, then turns off. The watcher shows `zigbee2mqtt/desk_lamp/set {"state": "ON"}`, then `{"brightness": 51}`, then `{"state": "OFF"}`, each followed by the bulb's new state. The read shows `brightness` close to `20 percent`.

### 10. The smallest safe change on Z-Wave

```sh
uv run python hwtest.py my-plug.hal.yaml set relay true
uv run python hwtest.py my-plug.hal.yaml read
uv run python hwtest.py my-plug.hal.yaml set relay false
```

Expected. `done` for each command, the plug clicks on and off, Z-Wave JS UI shows the Binary Switch current value change, and the read shows `relay = True`.

### 11. Stop

Turn both on again with the first command of steps 9 and 10, then run

```sh
uv run python hwtest.py my-bulb.hal.yaml stop
uv run python hwtest.py my-plug.hal.yaml stop
```

Expected. `desk-lamp safe` and `solder-plug safe`, and both turn off.

## If something fails

Send what [README.md](README.md#if-a-step-fails) lists, plus the watcher output for the same time, the Zigbee2MQTT or Z-Wave JS UI version and its log lines for the device, the device's model and firmware, and your device file without passwords.

## Report template

Save the filled-in report as `docs/hardware-tests/reports/<device id>-<date>.md`. [README.md](README.md#reports) says when it marks the device file `verified-on-hardware`.

```markdown
# Hardware report, zigbee-zwave driver

- Plan: docs/hardware-tests/zigbee-zwave.md
- Devices: <bulb model and firmware, plug model and firmware>
- Bridges: <Zigbee2MQTT version and adapter, Z-Wave JS UI or zwave-js-server version and stick>
- Host: <computer, operating system, broker and version>
- OpenHAL: <uv run openhal --version>, commit <git rev-parse --short HEAD>
- Device files: my-bulb.hal.yaml and my-plug.hal.yaml, with the sha256 from each confirmed line
- Tested by: <name>, <date>

| Step | Result | Notes |
|---|---|---|
| 1 Zigbee2MQTT knows the bulb | pass / fail / skipped | |
| 2 the device files validate | pass / fail | |
| 3 read the bulb | pass / fail / skipped | |
| 4 describe the bulb | pass / fail / skipped | |
| 5 read the plug | pass / fail / skipped | |
| 6 bridge loss | pass / fail | |
| 7 an offline bulb | pass / fail / skipped | |
| 8 confirm limits | done | |
| 9 the smallest safe change on Zigbee | pass / fail / skipped | |
| 10 the smallest safe change on Z-Wave | pass / fail / skipped | |
| 11 stop | pass / fail | |

Anything unexpected:

Result: verified-on-hardware / tested-reads / failed at step N
```
