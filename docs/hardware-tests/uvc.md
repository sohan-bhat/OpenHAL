# Hardware test plan, uvc driver

This plan checks the uvc driver against a real USB webcam. The driver is read-only, so every step is read-only. Point the camera at something that is fine to photograph.

Run every step from the repository checkout. Close video call apps first, since some systems give a camera to one app at a time.

## What you need

- A USB webcam, plugged in.
- On Linux, `v4l2-ctl` (from `v4l-utils`) to cross-check, and your user in the `video` group.
- The repository with the uvc extra, `uv sync --extra uvc`.
- A copy of the example file, `cp openhal/drivers/uvc/examples/bench-webcam.hal.yaml my-camera.hal.yaml`.

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

### 1. The camera is listed

On Linux:

```sh
uv run python -c "import asyncio; from openhal.drivers.uvc.driver import UvcDriver; print(*asyncio.run(UvcDriver.discover()), sep='\n')"
v4l2-ctl --list-devices
```

Expected. The driver lists `/dev/video0` (or another number) with the camera's name, and only the capture nodes that `v4l2-ctl` shows first under the camera. On macOS and Windows, skip this step and use `name: 0` or `name: 1`.

### 2. The device file validates

```sh
uv run openhal file validate my-camera.hal.yaml
```

Expected. `valid  my-camera.hal.yaml  (bench-camera, low hazard, read-only)`.

### 3. Identify and describe

```sh
uv run python hwtest.py my-camera.hal.yaml identify
uv run python hwtest.py my-camera.hal.yaml describe
```

Expected. `identify` prints the source and backend. `describe` opens the camera, and its notes give the size and frame rate the camera chose for the requested 1280x720. On macOS, allow camera access when asked, then run it again.

### 4. Capture a frame

Save this as `snap.py` and run `uv run python snap.py`.

```python
import asyncio

from openhal.drivers import registry
from openhal.spec import load


async def main() -> None:
    file = load("my-camera.hal.yaml")
    driver = registry.load("uvc")(file)
    await driver.connect()
    frame = await driver.read("frame")
    with open("frame.jpg", "wb") as out:
        out.write(frame.value)
    print(len(frame.value), "bytes", (await driver.read("frame_width")).value, (await driver.read("frame_height")).value)
    await driver.close()


asyncio.run(main())
```

Expected. A line such as `142311 bytes 1280.0 720.0`, and `frame.jpg` shows what the camera sees right now, not an older frame. Run it twice while moving something in view to check.

### 5. Unplug handling

Run `uv run python hwtest.py my-camera.hal.yaml read` to see `health Health(connected=True, ...)`. Then unplug the camera and run it again.

Expected. A `DriverError` saying the camera could not be opened. Plug it back in and the command works again. If the camera came back under a different index or device number, use a `/dev/v4l/by-id/` path on Linux.

## If something fails

Send the full output of the failing step, the camera model and USB id (`lsusb` on Linux, System Information on macOS), `v4l2-ctl --list-formats-ext -d /dev/video0` on Linux, the operating system, and your device file. Don't send frames that show people or private spaces.

## Report template

Save the filled-in report as `reports/<device-id>-<date>.md` and set `provenance.verification` in the device file to `{ status: verified-on-hardware, report: reports/<device-id>-<date>.md }`.

```markdown
# Hardware report, uvc driver

- Device: <manufacturer, model>
- Camera model and USB id: <version>
- Host: <computer, operating system>
- OpenHAL commit: <git rev-parse --short HEAD>
- Tested by: <name>, <date>

| Step | Result | Notes |
|---|---|---|
| 1 the camera is listed | pass / fail | |
| 2 the device file validates | pass / fail | |
| 3 identify and describe | pass / fail | |
| 4 capture a frame | pass / fail | |
| 5 unplug handling | pass / fail | |

Anything unexpected:
```
