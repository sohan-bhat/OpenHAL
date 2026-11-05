# rpi-camera driver

The rpi-camera driver captures JPEG frames from Raspberry Pi CSI camera modules through picamera2 and libcamera, and reads per-frame metadata such as light level and exposure time. The driver is read-only and never changes camera controls.

The driver is tested only against a fake Picamera2 class, since picamera2 installs only on Raspberry Pi OS. docs/hardware-tests/rpi-camera.md lists the checks for a real Pi.

## Supports

- `image` reads, one JPEG frame each.
- Number reads from the libcamera metadata fields `Lux`, `ExposureTime`, `AnalogueGain`, `DigitalGain`, `ColourTemperature`, `SensorTemperature`, `FrameDuration`, `FocusFoM` and `LensPosition`.
- `discover()` and `identify()` list attached modules without opening any.

## Setup

picamera2 needs the system libcamera bindings, so picamera2 comes from apt on Raspberry Pi OS Bookworm or later and there is no `rpi-camera` pip extra.

```sh
sudo apt install -y python3-picamera2
uv venv --system-site-packages
uv pip install -e .
rpicam-hello --list-cameras
```

If `rpicam-hello --list-cameras` doesn't list the module, check the ribbon cable and, on older images, `camera_auto_detect=1` in `/boot/firmware/config.txt`.

| Parameter | Default | Meaning |
|---|---|---|
| `camera` | `0` | Number from `rpicam-hello --list-cameras`, or `auto` for the first. `rpi-camera: 0` is shorthand |
| `configuration` | `still` | `still` is full resolution and slow, `video` smaller and faster |
| `width`, `height` | from the configuration | Main stream size, both or neither |
| `jpeg_quality` | `85` | 1 to 100 |
| `warmup` | `1 s` | Settle time for autoexposure and white balance |
| `timeout` | `10 s` | Camera start and capture deadline |

## Channels

```yaml
read:
  frame: { type: image }
  light: { unit: lux, map: { metadata: Lux } }
  exposure: { unit: ms, map: { metadata: ExposureTime } }
```

Metadata reads arrive in libcamera's units, `lux`, `us` for times, `K`, `degC` and `dimensionless` for gains and figures of merit. The kernel converts to the channel unit, so `exposure` above reads in ms.

## Behavior

The camera starts once on connect and keeps running, so each capture takes one frame time. One process can hold a camera, so a second hub or a running `rpicam-*` app fails the connect with "Device or resource busy". A failed capture marks the camera failed, and the hub reopens the camera after the next heartbeat.

## Example

`openhal/drivers/rpi_camera/examples/camera-module-3.hal.yaml` captures 1920x1080 frames from a Camera Module 3 and reads light level, exposure and sensor temperature.

## Errors

- Missing picamera2 raises `DriverError` with the apt command.
- A missing camera number, no module, a busy camera, a failed capture and non-JPEG bytes raise `DriverError`. No frame within `timeout` raises `TimeoutError`.
- A metadata field the sensor lacks raises `DriverError` listing the available fields.

## Limitations

- No camera controls such as exposure, gain, focus or white balance, and no video recording.
- One capture at a time per camera.

## Hazard default and safe state

Low with no write channels, so `safe_state_support` is `none`. Frames can show people and private spaces, so point cameras with care.

## Sources

- The Picamera2 Library manual, Raspberry Pi Ltd, https://datasheets.raspberrypi.com/camera/picamera2-manual.pdf
- Raspberry Pi camera software documentation, https://www.raspberrypi.com/documentation/computers/camera_software.html
- Raspberry Pi camera hardware documentation, https://www.raspberrypi.com/documentation/accessories/camera.html
- libcamera control and metadata definitions in control_ids_core.yaml, https://libcamera.org/api-html/namespacelibcamera_1_1controls.html
