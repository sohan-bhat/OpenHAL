# Hardware test plan, upnp driver

This plan checks the upnp driver against a real UPnP media renderer. The plan was made for a Sonos speaker with the example file. Any device whose actions a device file maps works the same way.

Run every step from the repository checkout, on a computer on the same network as the speaker. [README.md](README.md) has the setup and rules every plan shares. Keep the speaker's volume low.

## What you need

- A UPnP media renderer, such as a Sonos speaker at `192.168.1.30`, with something in its queue.
- curl, to fetch the description independently.
- The repository with the extra, `uv sync --extra upnp`.
- A copy of the example, `cp openhal/drivers/upnp/examples/sonos-speaker.hal.yaml my-speaker.hal.yaml`, with your speaker's address.

## The test script

Save this as `hwtest.py` in the repository root. The script drives the device only through the safety kernel, as the hub does. `set` waits one second first, because the kernel measures the first change's rate from the moment the device connected.

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

### 1. Discover

```sh
uv run python -c "import asyncio; from openhal.drivers.upnp.driver import UpnpDriver; print(*asyncio.run(UpnpDriver.discover()), sep='\n')"
```

Expected. An entry whose address is the speaker's description URL, among other UPnP devices on the network.

### 2. The description

```sh
curl -s http://192.168.1.30:1400/xml/device_description.xml | grep -o '<serviceId>[^<]*</serviceId>'
```

Expected. Service ids that include `RenderingControl` and `AVTransport`. On Sonos they sit in an embedded MediaRenderer device, which the driver searches too.

### 3. The device file validates

```sh
uv run openhal file validate my-speaker.hal.yaml
```

Expected. `valid  my-speaker.hal.yaml  (workshop-speaker, low hazard, read-only)`.

### 4. Read and describe

```sh
uv run python hwtest.py my-speaker.hal.yaml read
uv run python hwtest.py my-speaker.hal.yaml describe
```

Expected. The read shows `transport_state`, `volume` matching the Sonos app and `mute`. The proposal lists channels such as `current_volume` and actions such as `play` and `stop`.

### 5. Device loss

Unplug the speaker and run the read.

Expected. `DriverError` or `TimeoutError` saying the description could not be fetched. Plug the speaker in, wait until the app sees the speaker, and read again. The device reads normally.

## Steps that change the device

### 6. Confirm the limits

Read the file and decide the limits and the safe state are right. Then confirm them yourself.

```sh
uv run openhal file confirm my-speaker.hal.yaml
```

`openhal file confirm` lists each limit, asks you to type `confirm`, and adds a `confirmed` line with your name, the date and the `sha256` of the limits. `uv run openhal file validate my-speaker.hal.yaml` then says `writable`.

### 7. The smallest safe change

```sh
uv run python hwtest.py my-speaker.hal.yaml set mute true
uv run python hwtest.py my-speaker.hal.yaml read
uv run python hwtest.py my-speaker.hal.yaml set mute false
```

Expected. `done` for each command, the app shows the speaker muted and unmuted, and the read shows `mute = True`.

### 8. Volume and its limit

```sh
uv run python hwtest.py my-speaker.hal.yaml set volume "12 percent"
uv run python hwtest.py my-speaker.hal.yaml set volume "80 percent"
```

Expected. The first is `done` and the app shows 12. The second is `blocked above_max`, and the volume stays at 12.

### 9. Actions

```sh
uv run python hwtest.py my-speaker.hal.yaml action play
uv run python hwtest.py my-speaker.hal.yaml read
uv run python hwtest.py my-speaker.hal.yaml action pause
```

Expected. `done` for each, the queue plays then pauses, and the read shows `transport_state = PLAYING`.

### 10. Stop

Run the play action again, then run

```sh
uv run python hwtest.py my-speaker.hal.yaml stop
```

Expected. `workshop-speaker safe`, playback stops and the volume goes to 10. With an empty queue some firmware answers Stop with UPnP error 701, and the result is `partial`.

## If something fails

Send what [README.md](README.md#if-a-step-fails) lists, plus the description from step 2, the device's model and firmware, and your device file.

## Report template

Save the filled-in report as `docs/hardware-tests/reports/<device id>-<date>.md`. [README.md](README.md#reports) says when it marks the device file `verified-on-hardware`.

```markdown
# Hardware report, upnp driver

- Plan: docs/hardware-tests/upnp.md
- Device: <manufacturer, model, firmware>
- Host: <computer, operating system>
- OpenHAL: <uv run openhal --version>, commit <git rev-parse --short HEAD>
- Device file: <path>, sha256 <from its confirmed line>
- Tested by: <name>, <date>

| Step | Result | Notes |
|---|---|---|
| 1 discover | pass / fail | |
| 2 the description | pass / fail | |
| 3 the device file validates | pass / fail | |
| 4 read and describe | pass / fail | |
| 5 device loss | pass / fail | |
| 6 confirm limits | done | |
| 7 the smallest safe change | pass / fail | |
| 8 volume and its limit | pass / fail | |
| 9 actions | pass / fail | |
| 10 stop | pass / fail | |

Anything unexpected:

Result: verified-on-hardware / tested-reads / failed at step N
```
