# uvc driver

The uvc driver captures frames from USB webcams and other cameras the operating system can open, and returns them as JPEG bytes. The driver uses OpenCV (`opencv-python-headless`), which uses V4L2 on Linux, AVFoundation on macOS and Media Foundation or DirectShow on Windows. The driver is read-only and never changes exposure, focus or any other camera control.

## What it supports

- `image` read channels, returning one fresh JPEG frame per read.
- Number read channels for capture properties (`width`, `height`, `fps`, `brightness`, `contrast`, `saturation`, `hue`, `gain`, `exposure`, `focus`), as the camera reports them.
- A requested resolution and frame rate when the camera opens.
- `discover()` on Linux, which lists capture devices from sysfs without opening them.

## Setup

```sh
uv tool install --compile-bytecode "openhal-hub[uvc] @ git+https://github.com/sohan-bhat/OpenHAL"
```

The wheel is about 35 MB and bundles OpenCV and its codecs. On Linux, your user needs to be in the `video` group to open `/dev/video*`. On macOS, macOS prompts for camera permission the first time the terminal or app running the hub opens a camera.

## Parameters

| Parameter | Default | Meaning |
|---|---|---|
| `name` | `auto` | `auto` (the first camera), a camera index such as `1`, or a device path such as `/dev/video2`. The shorthand `uvc: auto` sets it |
| `width`, `height` | the camera's default | Requested frame size |
| `fps` | the camera's default | Requested frame rate |
| `jpeg_quality` | `85` | JPEG quality, 1 to 100 |
| `backend` | `any` | `any`, `v4l2`, `avfoundation`, `dshow`, `msmf` or `gstreamer` |
| `flush_frames` | `1` | Frames grabbed and dropped before each capture, so a read never returns an old buffered frame |
| `timeout` | `5 s` | Deadline for opening and for each capture |

The requested size and rate are only requests, because cameras use the nearest mode they support, and the `width`, `height` and `fps` properties report the mode the camera uses.

## Channels

```yaml
read:
  frame: { type: image }
  frame_width: { unit: dimensionless, map: { property: width } }
  fps: { unit: Hz, map: { property: fps } }
```

Image channels need no map, but number channels need `map: { property: <name> }`. The hub doesn't poll image channels during the snapshot it takes on connect, so a frame is only captured when a client requests one.

## Example

`openhal/drivers/uvc/examples/bench-webcam.hal.yaml` captures 1280x720 frames from the first webcam.

## Errors and health

- A camera that won't open (missing, busy in another app, no permission) raises `DriverError`.
- A capture that returns no frame raises `DriverError` and marks the camera as failed, which the next heartbeat reports, so the hub reopens the camera.
- No frame within `timeout` raises `TimeoutError`.
- `health()` grabs one frame and reports the camera as disconnected if no frame arrives.

## Limitations

- The driver has no camera controls, so exposure, focus, zoom and pan stay as the camera sets them.
- The driver captures only single frames on request, with no video streams or recording.
- `discover()` only works on Linux, so on macOS and Windows cameras are opened by index.
- Camera indexes can change when cameras are plugged in a different order, but on Linux a `/dev/v4l/by-id/...` path is stable.

## Hazard default and safe state

The default hazard is low and the driver has no write channels, so `safe_state_support` is `none` and there is nothing to put in a safe state. Frames can show people and private spaces, so point cameras with care and tell people the cameras are there.

## Sources

- USB Video Class 1.5 document set, USB-IF, https://www.usb.org/document-library/video-class-v15-document-set
- Linux UVC driver and supported devices, https://www.ideasonboard.org/uvc/
- OpenCV VideoCapture reference, https://docs.opencv.org/4.x/d8/dfe/classcv_1_1VideoCapture.html
- V4L2 userspace API, https://www.kernel.org/doc/html/latest/userspace-api/media/v4l/v4l2.html
