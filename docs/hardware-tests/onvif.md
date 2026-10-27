# Hardware test plan, onvif driver

This plan checks the onvif driver against a real ONVIF PTZ camera. The plan was made for a Hikvision PTZ camera with the example file. Any ONVIF Profile S camera works the same way, and the PTZ steps need a PTZ camera.

Run every step from the repository checkout, on a computer on the same network as the camera. [README.md](README.md) has the setup and rules every plan shares. Keep people and objects out of the camera's swing.

## What you need

- An ONVIF camera at, for example, `192.168.1.40`, with ONVIF on, an ONVIF user `openhal` and NTP set.
- Presets 1 and 2 saved in the camera's web interface.
- ffprobe (part of FFmpeg) to check the stream URI independently.
- The repository with the extra, `uv sync --extra onvif`.
- A copy of the example, `cp openhal/drivers/onvif/examples/ptz-camera.hal.yaml my-camera.hal.yaml`, with your address and profile name.
- The password in the environment, `export CAMERA_PASSWORD=...`.

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
uv run python -c "import asyncio; from openhal.drivers.onvif.driver import OnvifDriver; print(*asyncio.run(OnvifDriver.discover()), sep='\n')"
```

Expected. An entry with the camera's address, its name and hardware model from its scopes.

### 2. The device file validates

```sh
uv run openhal file validate my-camera.hal.yaml
```

Expected. `valid  my-camera.hal.yaml  (workshop-ptz, low hazard, read-only)`.

### 3. Read every channel

```sh
uv run python hwtest.py my-camera.hal.yaml read
```

Expected. `model` and `firmware` as the web interface shows them, an `rtsp://` `stream_uri`, an `http://` `snapshot_uri`, `moving = False`, and `pan`, `tilt` and `zoom` within their ranges.

### 4. The stream URI works

```sh
ffprobe -v error -show_entries stream=codec_name,width,height "<stream_uri from step 3 with openhal:password@ after rtsp://>"
```

Expected. The video codec and the profile's resolution.

### 5. Describe and identify

```sh
uv run python hwtest.py my-camera.hal.yaml describe
uv run python hwtest.py my-camera.hal.yaml identify
```

Expected. The proposal lists pan, tilt, zoom, move, stop, home and goto_preset with the presets 1 and 2. Identify prints the host.

### 6. Wrong credentials and camera loss

Run step 3 with a wrong password (`CAMERA_PASSWORD=wrong uv run python hwtest.py my-camera.hal.yaml read`), then unplug the camera's network cable and run it again.

Expected. The first fails with `DriverError` saying the camera refused the credentials. The second fails with `DriverError` saying the camera could not be reached, or `TimeoutError`. Plug it back in and run step 3. The device reads normally.

## Steps that change the device

### 7. Confirm the limits

Read the file and decide the limits are right for where the camera hangs. Then confirm them yourself.

```sh
uv run openhal file confirm my-camera.hal.yaml
```

`openhal file confirm` lists each limit, asks you to type `confirm`, and adds a `confirmed` line with your name, the date and the `sha256` of the limits. `uv run openhal file validate my-camera.hal.yaml` then says `writable`.

### 8. The smallest safe action

```sh
uv run python hwtest.py my-camera.hal.yaml action stop
```

Expected. `done`, and nothing moves.

### 9. A small move

```sh
uv run python hwtest.py my-camera.hal.yaml action move pan="0.2 dimensionless" tilt="0 dimensionless" duration="0.5 s"
uv run python hwtest.py my-camera.hal.yaml read
```

Expected. `done`, the camera turns a little for half a second and stops on its own, and the read shows a changed `pan`.

### 10. Positions and presets

```sh
uv run python hwtest.py my-camera.hal.yaml set pan "30 degree"
uv run python hwtest.py my-camera.hal.yaml action goto_preset preset=1
uv run python hwtest.py my-camera.hal.yaml set pan "120 degree"
uv run python hwtest.py my-camera.hal.yaml action home
```

Expected. The first turns the camera to about 30 degrees with tilt unchanged. The second goes to preset 1. The third is `blocked above_max` and nothing moves. The last returns to the home position.

### 11. Stop

Start a longer move with `duration="2 s"` from step 9, then within the two seconds run

```sh
uv run python hwtest.py my-camera.hal.yaml stop
```

Expected. `workshop-ptz safe`, and the camera stops before the two seconds are up.

## If something fails

Send what [README.md](README.md#if-a-step-fails) lists, plus the camera's model and firmware, its ONVIF version from the web interface, and your device file without the password.

## Report template

Save the filled-in report as `docs/hardware-tests/reports/<device id>-<date>.md`. [README.md](README.md#reports) says when it marks the device file `verified-on-hardware`.

```markdown
# Hardware report, onvif driver

- Plan: docs/hardware-tests/onvif.md
- Device: <manufacturer, model, firmware>
- Host: <computer, operating system>
- OpenHAL: <uv run openhal --version>, commit <git rev-parse --short HEAD>
- Device file: <path>, sha256 <from its confirmed line>
- Tested by: <name>, <date>

| Step | Result | Notes |
|---|---|---|
| 1 discover | pass / fail | |
| 2 the device file validates | pass / fail | |
| 3 read every channel | pass / fail | |
| 4 the stream URI works | pass / fail | |
| 5 describe and identify | pass / fail | |
| 6 wrong credentials and camera loss | pass / fail | |
| 7 confirm limits | done | |
| 8 the smallest safe action | pass / fail | |
| 9 a small move | pass / fail | |
| 10 positions and presets | pass / fail | |
| 11 stop | pass / fail | |

Anything unexpected:

Result: verified-on-hardware / tested-reads / failed at step N
```
