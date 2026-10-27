# onvif driver

The onvif driver reads an ONVIF camera's identity and stream addresses and moves PTZ cameras through the safety kernel. The driver speaks the ONVIF device, media and PTZ services itself, with a small SOAP 1.2 client and WS-Security digest authentication, so it works with the Profile S and T cameras most brands sell.

## What it supports

- Device information (manufacturer, model, firmware, serial number, hardware id) and the chosen profile's name, RTSP stream URI and snapshot URI, as text channels read on connect.
- Pan, tilt and zoom positions as number channels, and `moving` as a bool. As control channels, pan, tilt and zoom move the camera to the given position with AbsoluteMove.
- Actions for ContinuousMove (`move`), RelativeMove (`step`), AbsoluteMove (`go_to`), presets (`goto_preset`), the home position (`home`) and `stop`.
- A native safe state that stops pan, tilt and zoom.
- `discover()` sends one WS-Discovery Probe for network video transmitters.
- `describe()` proposes the identity and URI channels, the PTZ channels and actions, and the camera's presets.

## Setup

```sh
uv tool install --compile-bytecode "openhal-hub[onvif] @ git+https://github.com/sohan-bhat/OpenHAL"
```

Turn ONVIF on in the camera's web interface and create an ONVIF user. Put the user's password in an environment variable, `export CAMERA_PASSWORD=...`. Keep the camera's clock on NTP, because the driver corrects for clock drift but some cameras log every request with a wrong time.

## Parameters

| Parameter | Default | Meaning |
|---|---|---|
| `host` | required | The camera's address. The shorthand `onvif: 192.168.1.40` sets it |
| `port`, `scheme` | `80`, `http` | Where the device service listens |
| `username`, `token_env` | none | The ONVIF user, and the variable that holds its password |
| `profile` | the first profile | A profile token or name, such as `MainStream` |
| `device_path` | `/onvif/device_service` | The device service path |
| `move_timeout` | `1 s` | How long `move` runs when it has no `duration` |
| `timeout` | `5 s` | How long one SOAP call may take |

## Channels and actions

Channels are named after what they read, or map to it with `map: { field: pan }`. Pan, tilt and zoom are in ONVIF's generic spaces, where pan and tilt run from -1 to 1 and zoom from 0 to 1, and `scale`, `offset` and `unit` turn them into degrees or another unit.

```yaml
read:
  stream_uri: { type: string }
  moving: { type: bool }
write:
  pan: { unit: degree, min: -90, max: 90, map: { field: pan, scale: 180 } }
  zoom: { unit: dimensionless, min: 0, max: 1 }
actions:
  move:
    args:
      pan: { unit: dimensionless, min: -0.5, max: 0.5 }
      duration: { unit: s, min: 0.1, max: 2 }
  goto_preset: { args: { preset: { type: enum, values: ["1", "2"] } } }
  stop: {}
```

| Action | ONVIF operation | Arguments |
|---|---|---|
| `move` | ContinuousMove | `pan`, `tilt`, `zoom` speeds, `duration` |
| `step` | RelativeMove | `pan`, `tilt`, `zoom` distances |
| `go_to` | AbsoluteMove | `pan`, `tilt`, `zoom` positions, missing axes stay put |
| `goto_preset` | GotoPreset | `preset`, a preset token |
| `home` | GotoHomePosition | none |
| `stop` | Stop | none |

An action named otherwise picks its operation with `map: { operation: move }`.

## How reads and commands behave

- Identity and URIs are read once on connect, and the driver only reports the URIs and never opens them.
- Position reads call GetStatus, and changing one axis reads the other axes first, so the other axes stay where they are.
- The kernel checks every argument against the device file, but because the kernel checks speeds and distances rather than end positions, `move` and `step` can still carry the camera past a position limit. Keep `duration` short, and set the camera's own PTZ limits as well.
- Faults from the camera become `DriverError` with the ONVIF subcode and reason, such as `ter:NoToken` for a missing preset.

## Why the driver has its own SOAP client

onvif-zeep-async (MIT, maintained) was checked first. Importing onvif-zeep-async configures the root logger, creating a camera removes `http_proxy` and `https_proxy` from the process environment, and the library turns TLS certificate checks off for every camera. Those side effects are wrong inside a long-running hub, so the driver uses about 250 lines of its own SOAP, WS-Security and WS-Discovery code on httpx and defusedxml.

## Example

`openhal/drivers/onvif/examples/ptz-camera.hal.yaml` reads a Hikvision PTZ camera's stream URIs and moves the camera within limits, with two presets.

## Errors

- A camera that can't be reached, refused credentials, a missing password variable and a missing profile raise `DriverError` that says what to check. A file that uses PTZ with a profile that has no PTZ fails the connect.
- A reply that isn't SOAP raises `DriverError`, and a camera that doesn't respond raises `TimeoutError`.

## Limitations

- The driver doesn't support events, imaging settings, recording or audio, and because the driver has no Media2 (ver20 media) service, Profile T cameras are used through their Media1 service.
- The driver supports only WS-Security UsernameToken, which ONVIF requires, and no HTTP digest authentication.
- `https` uses normal certificate checks, so cameras with self-signed certificates need plain `http` on a trusted network.

## Hazard default and safe state

The default hazard is low, because a camera's motors are small. `safe_state_support` is `native`, so a hub stop sends Stop for pan, tilt and zoom on the profile in use, and the camera holds its position.

## Sources

- ONVIF Core Specification, https://www.onvif.org/specs/core/ONVIF-Core-Specification.pdf
- ONVIF Media Service Specification, https://www.onvif.org/specs/srv/media/ONVIF-Media-Service-Spec.pdf
- ONVIF PTZ Service Specification, https://www.onvif.org/specs/srv/ptz/ONVIF-PTZ-Service-Spec.pdf
- ONVIF Application Programmer's Guide (digest example), https://www.onvif.org/wp-content/uploads/2016/12/ONVIF_WG-APG-Application_Programmers_Guide-1.pdf
- OASIS Web Services Security UsernameToken Profile 1.0, https://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-username-token-profile-1.0.pdf
- OASIS WS-Discovery 1.1, https://docs.oasis-open.org/ws-dd/discovery/1.1/os/wsdd-discovery-1.1-spec-os.html
