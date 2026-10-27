# rpi-camera driver

The rpi-camera driver captures JPEG frames from Raspberry Pi camera modules on the CSI connector, through picamera2 and libcamera, and reads the per-frame metadata libcamera reports, such as light level and exposure time. The driver is read-only and never changes camera controls.

This driver has only been tested against a fake Picamera2 class, because picamera2 installs only on Raspberry Pi OS. docs/hardware-tests/rpi-camera.md lists what a person has to check on a real Pi.

## What it supports

- `image` read channels, one JPEG frame per read.
- Number read channels from libcamera metadata. `Lux`, `ExposureTime`, `AnalogueGain`, `DigitalGain`, `ColourTemperature`, `SensorTemperature`, `FrameDuration`, `FocusFoM` and `LensPosition`.
- Still or video configurations, with an optional frame size.
- `discover()` and `identify()` list attached modules without opening them.

## Setup

picamera2 comes from apt on Raspberry Pi OS Bookworm or later, not from pip, because it needs the system libcamera bindings. There is no `rpi-camera` pip extra for that reason.

```sh
sudo apt install -y python3-picamera2
uv venv --system-site-packages
uv pip install -e .
rpicam-hello --list-cameras
```

`rpicam-hello --list-cameras` should list your module. If it doesn't, check the ribbon cable and, on older OS images, the `camera_auto_detect=1` line in `/boot/firmware/config.txt`.

## Parameters

| Parameter | Default | Meaning |
|---|---|---|
| `camera` | `0` | Camera number from `rpicam-hello --list-cameras`, or `auto` for the first one. The shorthand `rpi-camera: 0` sets it |
| `configuration` | `still` | `still` uses the full sensor resolution and captures slowly. `video` is smaller and faster |
| `width`, `height` | from the configuration | Main stream size. Give both or neither |
| `jpeg_quality` | `85` | JPEG quality, 1 to 100 |
| `warmup` | `1 s` | Wait after starting the camera, so autoexposure and white balance settle |
| `timeout` | `10 s` | Deadline for starting the camera and for each capture |

## Channels

```yaml
read:
  frame: { type: image }
  light: { unit: lux, map: { metadata: Lux } }
  exposure: { unit: ms, map: { metadata: ExposureTime } }
```

Metadata channels report the unit libcamera uses (`lux`, `us` for times, `K`, `degC`, `dimensionless` for gains and figures of merit). The kernel converts a reading into the channel's unit when they differ, so `exposure` above reads in milliseconds.

## How it works

The driver opens and starts the camera once on connect and keeps it running, so each capture takes one frame time rather than a full camera start. Only one process can hold a camera, so a second hub or a `rpicam-*` app running at the same time makes connect fail with "Device or resource busy". A capture or metadata request that fails marks the camera as failed, the next heartbeat reports it, and the hub reopens it.

## Example

`openhal/drivers/rpi_camera/examples/camera-module-3.hal.yaml` captures 1920x1080 frames from a Camera Module 3 and reads light level, exposure and sensor temperature.

## Errors

- picamera2 missing raises `DriverError` with the apt command above.
- A missing camera number, no attached module, or a busy camera raises `DriverError`.
- A capture that fails, or bytes that aren't a JPEG, raise `DriverError`. No frame within `timeout` raises `TimeoutError`.
- A metadata field the sensor doesn't report raises `DriverError` listing the fields it does report.

## Limitations

- No camera controls (exposure, gain, focus, white balance) and no video recording.
- One capture at a time per camera.
- Only tested against the fake until the hardware test plan has been run.

## Hazard default and safe state

The default hazard is low and the driver has no write channels, so `safe_state_support` is `none`. Frames can show people and private spaces, so point cameras with care.

## Sources

- The Picamera2 Library manual, Raspberry Pi Ltd, https://datasheets.raspberrypi.com/camera/picamera2-manual.pdf
- Raspberry Pi camera software documentation, https://www.raspberrypi.com/documentation/computers/camera_software.html
- Raspberry Pi camera hardware documentation, https://www.raspberrypi.com/documentation/accessories/camera.html
- libcamera control and metadata definitions (control_ids_core.yaml), https://libcamera.org/api-html/namespacelibcamera_1_1controls.html
