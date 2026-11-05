# onvif driver

The onvif driver reads an ONVIF camera's identity and stream addresses and moves PTZ cameras under the safety kernel, for the Profile S and T cameras most brands sell. The driver uses a small built-in SOAP 1.2 client on httpx and defusedxml with WS-Security digest authentication, since onvif-zeep-async reconfigures the root logger, clears the proxy variables and turns TLS checks off for every camera.

## Supports

- Identity and the chosen profile's name, RTSP stream URI and snapshot URI as text reads, read once on connect and never opened.
- Pan, tilt and zoom positions as numbers and `moving` as a bool. Setting pan, tilt or zoom sends AbsoluteMove.
- `move`, `step`, `go_to`, `goto_preset`, `home` and `stop` actions.
- `discover()` sends one WS-Discovery Probe. `describe()` returns the identity, URI and PTZ channels, actions and presets.

## Setup

```sh
uv tool install --compile-bytecode "halkit[onvif] @ git+https://github.com/sohan-bhat/OpenHAL"
```

Turn ONVIF on in the camera's web interface, create an ONVIF user, and `export CAMERA_PASSWORD=...`. Keep the camera clock on NTP.

| Parameter | Default | Meaning |
|---|---|---|
| `host` | required | Camera address. `onvif: 192.168.1.40` is shorthand |
| `port`, `scheme` | `80`, `http` | Device service location |
| `username`, `token_env` | none | ONVIF user and the variable holding the password |
| `profile` | the first profile | Profile token or name, such as `MainStream` |
| `device_path` | `/onvif/device_service` | Device service path |
| `move_timeout` | `1 s` | `move` run time without `duration` |
| `timeout` | `5 s` | Per SOAP call |

## Channels and actions

Channels are named after the field, or map with `map: { field: pan }`. Pan and tilt run from -1 to 1 and zoom from 0 to 1 in ONVIF's generic spaces, and `scale`, `offset` and `unit` convert to degrees or another unit.

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

`map: { operation: move }` picks the operation for another action name.

## Behavior

- Position reads call GetStatus. Changing one axis reads the others first, so the other axes stay put.
- The kernel checks `move` and `step` speeds and distances, not end positions, so those actions can pass a position limit. Keep `duration` short and set the camera's own PTZ limits.
- Camera faults become `DriverError` with the ONVIF subcode and reason, such as `ter:NoToken` for a missing preset.
- Connect failures, a PTZ file on a profile without PTZ and non-SOAP replies raise `DriverError`, and a silent camera `TimeoutError`.

## Example

`openhal/drivers/onvif/examples/ptz-camera.hal.yaml` reads a Hikvision PTZ camera's stream URIs and moves the camera within limits, with two presets.

## Limitations

- No events, imaging settings, recording, audio or Media2, so Profile T cameras use Media1.
- WS-Security UsernameToken only, with no HTTP digest.
- `https` checks certificates, so self-signed cameras need `http` on a trusted network.

## Hazard default and safe state

Low. `safe_state_support` is `native`, so a hub stop sends Stop for pan, tilt and zoom and the camera holds position.

## Sources

- ONVIF Core Specification, https://www.onvif.org/specs/core/ONVIF-Core-Specification.pdf
- ONVIF Media Service Specification, https://www.onvif.org/specs/srv/media/ONVIF-Media-Service-Spec.pdf
- ONVIF PTZ Service Specification, https://www.onvif.org/specs/srv/ptz/ONVIF-PTZ-Service-Spec.pdf
- ONVIF Application Programmer's Guide with the digest example, https://www.onvif.org/wp-content/uploads/2016/12/ONVIF_WG-APG-Application_Programmers_Guide-1.pdf
- OASIS Web Services Security UsernameToken Profile 1.0, https://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-username-token-profile-1.0.pdf
- OASIS WS-Discovery 1.1, https://docs.oasis-open.org/ws-dd/discovery/1.1/os/wsdd-discovery-1.1-spec-os.html
