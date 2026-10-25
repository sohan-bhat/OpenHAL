# Hardware test plan, matter driver

This plan checks the matter driver against a real Matter Server and a real Matter device. It was made for an Eve Energy plug with the example file, on the Home Assistant Matter Server add-on. matterjs-server and a standalone python-matter-server work the same way.

Run every step from the repository checkout. Plug nothing into the plug.

## What you need

- A Matter Server reachable from this computer, for example the Home Assistant add-on with its WebSocket port 5580 exposed.
- The plug commissioned into that server, and its node id from the server's frontend.
- The repository with the extra, `uv sync --extra matter`.
- A copy of the example, `cp openhal/drivers/matter/examples/eve-energy-plug.hal.yaml my-plug.hal.yaml`, with your server URL and node id.

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

### 1. The server answers

```sh
uv run python -c "import asyncio, json; from websockets.asyncio.client import connect
async def main():
    async with connect('ws://192.168.1.10:5580/ws') as ws: print(json.loads(await ws.recv()))
asyncio.run(main())"
```

Expected. The server info, with `schema_version`, `sdk_version` and `fabric_id`.

### 2. The device file validates

```sh
uv run openhal file validate my-plug.hal.yaml
```

Expected. `valid  my-plug.hal.yaml  (enclosure-plug, low hazard, read-only)`.

### 3. Describe

```sh
uv run python hwtest.py my-plug.hal.yaml describe
```

Expected. `power` under `write` with `on_command: On`, and `active_power` under `read`. Note the endpoints it shows. If they differ from the example, change the paths in your copy.

### 4. Identify and read

```sh
uv run python hwtest.py my-plug.hal.yaml identify
uv run python hwtest.py my-plug.hal.yaml read
```

Expected. The first prints the server URL and node. The read shows `active_power` close to `0.0 W` and `power` matching the plug's LED, and the health line names the node.

### 5. An unavailable node

Unplug the plug from the wall, wait until the server's frontend shows it unavailable, and run the read again.

Expected. The connect works, then the reads fail with `DriverError` saying the node is unavailable. Plug it back in, wait until it shows available, and read again. It reads normally.

### 6. Server loss

Stop the Matter Server and run the read.

Expected. `DriverError` saying the Matter Server could not be opened. Start it again.

## Steps that change the device

### 7. Confirm the limits

Read the file, decide the limits and the safe state are right, and add this line yourself.

```yaml
confirmed: { by: <your name>, at: <today's date> }
```

`uv run openhal file validate my-plug.hal.yaml` should now say `writable`.

### 8. The smallest safe action

```sh
uv run python hwtest.py my-plug.hal.yaml action identify seconds="5 s"
```

Expected. `done`, and the plug's LED blinks for about five seconds.

### 9. The smallest safe change

```sh
uv run python hwtest.py my-plug.hal.yaml set power true
uv run python hwtest.py my-plug.hal.yaml read
uv run python hwtest.py my-plug.hal.yaml set power false
```

Expected. `done` for each command, the relay clicks on and off, the server's frontend shows the change, and the read in between shows `power = True`.

### 10. Stop

Turn the plug on again with the first command of step 9, then run

```sh
uv run python hwtest.py my-plug.hal.yaml stop
```

Expected. `enclosure-plug safe`, and the plug turns off.

## If something fails

Send the full output of the failing step, the server's name and version and its log lines for the node, the device's vendor, product and software version from step 4, and your device file.

## Report template

Save the filled-in report as `reports/<device-id>-<date>.md` and set `provenance.verification` in the device file to `{ status: verified-on-hardware, report: reports/<device-id>-<date>.md }`.

```markdown
# Hardware report, matter driver

- Device: <vendor, product, software version, node id>
- Server: <python-matter-server, matterjs-server or the Home Assistant add-on, and version>
- Host: <computer, operating system>
- OpenHAL commit: <git rev-parse --short HEAD>
- Tested by: <name>, <date>

| Step | Result | Notes |
|---|---|---|
| 1 the server answers | pass / fail | |
| 2 the device file validates | pass / fail | |
| 3 describe | pass / fail | |
| 4 identify and read | pass / fail | |
| 5 an unavailable node | pass / fail | |
| 6 server loss | pass / fail | |
| 7 confirm limits | done | |
| 8 the smallest safe action | pass / fail | |
| 9 the smallest safe change | pass / fail | |
| 10 stop | pass / fail | |

Anything unexpected:
```
