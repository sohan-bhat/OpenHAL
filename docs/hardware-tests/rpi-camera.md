# Hardware test plan, rpi-camera driver

This plan checks the rpi-camera driver on a real Raspberry Pi. The driver has only run against a fake Picamera2 class so far, so this plan is how the driver's calls get proved on hardware. Every step in the plan is read-only. Point the camera at something that is fine to photograph.

The list below names what the fake can't prove, and the step that checks each item.

| Assumption in the fake | Checked in step |
|---|---|
| `Picamera2.global_camera_info()` lists modules with `Num`, `Model` and `Id` | 1, 3 |
| `create_still_configuration(main={"size": ...})` and `create_video_configuration` accept those arguments | 4, 6 |
| `options["quality"]` sets the JPEG quality used by `capture_file(..., format="jpeg")` | 6 |
| `capture_file` into a `BytesIO` writes a complete JPEG | 4 |
| `capture_metadata()` has `Lux`, `ExposureTime`, `AnalogueGain`, `ColourTemperature` and `SensorTemperature` | 5 |
| Opening a camera another process holds raises `RuntimeError` | 7 |
| Capture timing with `warmup` and the default `timeout` | 4, 6 |

Run every step on the Pi, from the repository checkout. [README.md](README.md) has the setup and rules every plan shares.

## What you need

- A Raspberry Pi 4 or 5 with Raspberry Pi OS Trixie or later, and a camera module on the CSI connector. Bookworm's Python 3.11 is older than the 3.12 OpenHAL needs, and picamera2's libcamera bindings load only in the system Python.
- picamera2 from apt and a virtual environment on the system Python that can import it, set up as [README.md](README.md#on-a-raspberry-pi) describes. The driver needs no extra. Check it with `uv run python -c "import picamera2"`.
- A copy of the example file, `cp openhal/drivers/rpi_camera/examples/camera-module-3.hal.yaml my-picam.hal.yaml`.

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

### 1. The camera is attached

```sh
rpicam-hello --list-cameras
uv run python -c "import asyncio; from openhal.drivers.rpi_camera.driver import RpiCameraDriver; print(*asyncio.run(RpiCameraDriver.discover()), sep='\n')"
```

Expected. `rpicam-hello` lists camera 0 with its sensor (for example `imx708`), and the driver prints one `Discovered` line per camera with the same number and model. If the driver prints nothing, check that `uv run python -c "import picamera2"` works.

### 2. The device file validates

```sh
uv run openhal file validate my-picam.hal.yaml
```

Expected. `valid  my-picam.hal.yaml  (plant-camera, low hazard, read-only)`.

### 3. Identify

```sh
uv run python hwtest.py my-picam.hal.yaml identify
```

Expected. `camera`, `model` and `id` matching step 1.

### 4. Capture a frame

Save this as `picsnap.py` and run `time uv run python picsnap.py`.

```python
import asyncio
import time

from openhal.drivers import registry
from openhal.spec import load


async def main() -> None:
    file = load("my-picam.hal.yaml")
    driver = registry.load("rpi-camera")(file)
    started = time.monotonic()
    await driver.connect()
    print(f"connect {time.monotonic() - started:.1f} s")
    for index in range(3):
        started = time.monotonic()
        frame = await driver.read("frame")
        print(f"frame {index} {len(frame.value)} bytes in {time.monotonic() - started:.2f} s")
        with open(f"pi-frame-{index}.jpg", "wb") as out:
            out.write(frame.value)
    await driver.close()


asyncio.run(main())
```

Expected. `connect` takes about 2 to 3 seconds (camera start plus the 2 s warmup), each frame takes well under a second, and `pi-frame-0.jpg` to `pi-frame-2.jpg` open as 1920x1080 images that are correctly exposed. Check the size with `file pi-frame-0.jpg`.

### 5. Read the metadata

```sh
uv run python hwtest.py my-picam.hal.yaml read
uv run python hwtest.py my-picam.hal.yaml describe
```

Expected. `read` prints a `light` value in lux that rises when you shine a light at the lens, an `exposure` in ms, a `sensor_temperature` in degC (some sensors don't report it, and then the read fails with a list of the fields the sensor does report, which is useful to send back), and `health Health(connected=True, ...)`. `describe` lists every numeric metadata field this sensor reports.

### 6. Still configuration and quality

Change `connect` to `{ rpi-camera: 0, configuration: still, jpeg_quality: 30, warmup: 2 s }` and run step 4 again.

Expected. Frames at the full sensor resolution (4608x2592 for a Camera Module 3), noticeably smaller files than at quality 85 for the same scene, and slower captures than in video mode. Put the file back the way it was afterwards.

### 7. A busy camera

Start `rpicam-hello -t 0` in another terminal, then run step 5's `read` command.

Expected. A `DriverError` stating that camera 0 could not be opened and that another program may be using it. Stop `rpicam-hello` with Ctrl-C and the command works again.

## If something fails

Send what [README.md](README.md#if-a-step-fails) lists, plus `rpicam-hello --list-cameras`, the output of `apt policy python3-picamera2`, the Pi model (`cat /proc/device-tree/model`), the OS version (`cat /etc/os-release`), and your device file. Don't send frames that show people or private spaces.

## Report template

Save the filled-in report as `docs/hardware-tests/reports/<device id>-<date>.md`. [README.md](README.md#reports) lists when a report marks the device file `verified-on-hardware`.

```markdown
# Hardware report, rpi-camera driver

- Plan: docs/hardware-tests/rpi-camera.md
- Device: <manufacturer, model>
- Camera module and sensor: <version>
- Host: <Raspberry Pi model, Raspberry Pi OS version, picamera2 version from apt>
- OpenHAL: <uv run openhal --version>, commit <git rev-parse --short HEAD>
- Device file: my-picam.hal.yaml (read-only, so it has no confirmed line)
- Tested by: <name>, <date>

| Step | Result | Notes |
|---|---|---|
| 1 the camera is attached | pass / fail | |
| 2 the device file validates | pass / fail | |
| 3 identify | pass / fail | |
| 4 capture a frame | pass / fail | |
| 5 read the metadata | pass / fail | |
| 6 still configuration and quality | pass / fail | |
| 7 a busy camera | pass / fail | |

Anything unexpected:

Result: verified-on-hardware / tested-reads / failed at step N
```
