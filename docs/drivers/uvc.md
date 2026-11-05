# uvc driver

The uvc driver captures JPEG frames from USB webcams and other cameras the operating system can open, through OpenCV `opencv-python-headless` on V4L2, AVFoundation, Media Foundation or DirectShow. The driver is read-only and never changes exposure, focus or any other camera control.

## Supports

- `image` reads, one fresh JPEG frame each.
- Number reads of the capture properties `width`, `height`, `fps`, `brightness`, `contrast`, `saturation`, `hue`, `gain`, `exposure` and `focus`, as the camera reports them.
- A requested resolution and frame rate on open.
- `discover()` on Linux lists capture devices from sysfs without opening any.

## Setup

```sh
uv tool install --compile-bytecode "halkit[uvc] @ git+https://github.com/sohan-bhat/OpenHAL"
```

The 35 MB wheel bundles OpenCV and codecs. On Linux, join the `video` group. On macOS, grant camera permission the first time the app running the hub opens a camera.

| Parameter | Default | Meaning |
|---|---|---|
| `name` | `auto` | `auto` for the first camera, an index such as `1`, or a path such as `/dev/video2`. `uvc: auto` is shorthand |
| `width`, `height` | the camera's default | Requested frame size |
| `fps` | the camera's default | Requested frame rate |
| `jpeg_quality` | `85` | 1 to 100 |
| `backend` | `any` | `any`, `v4l2`, `avfoundation`, `dshow`, `msmf` or `gstreamer` |
| `flush_frames` | `1` | Frames dropped before each capture, so reads never return an old buffer |
| `timeout` | `5 s` | Open and capture deadline |

Cameras use the nearest supported mode, which the `width`, `height` and `fps` properties report.

## Channels

```yaml
read:
  frame: { type: image }
  frame_width: { unit: dimensionless, map: { property: width } }
  fps: { unit: Hz, map: { property: fps } }
```

Number channels need `map: { property: <name> }`. The hub skips image channels in the connect snapshot, so frames are captured only on request.

## Example

`openhal/drivers/uvc/examples/bench-webcam.hal.yaml` captures 1280x720 frames from the first webcam.

## Errors and health

- A camera that won't open, because the camera is missing, busy or lacks permission, raises `DriverError`.
- A capture with no frame raises `DriverError` and marks the camera failed, so the hub reopens the camera after the next heartbeat.
- No frame within `timeout` raises `TimeoutError`.
- `health()` grabs one frame and reports disconnected without one.

## Limitations

- No camera controls such as exposure, focus, zoom or pan.
- Single frames on request only, with no video streams or recording.
- `discover()` works only on Linux. Elsewhere cameras open by index.
- Indexes can change with plug order, but `/dev/v4l/by-id/...` paths on Linux are stable.

## Hazard default and safe state

Low with no write channels, so `safe_state_support` is `none`. Frames can show people and private spaces, so point cameras with care and tell people the cameras are there.

## Sources

- USB Video Class 1.5 document set, USB-IF, https://www.usb.org/document-library/video-class-v15-document-set
- Linux UVC driver and supported devices, https://www.ideasonboard.org/uvc/
- OpenCV VideoCapture reference, https://docs.opencv.org/4.x/d8/dfe/classcv_1_1VideoCapture.html
- V4L2 userspace API, https://www.kernel.org/doc/html/latest/userspace-api/media/v4l/v4l2.html
