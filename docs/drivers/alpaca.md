# alpaca driver

The `alpaca` driver controls ASCOM Alpaca astronomy devices through httpx. One device file is one device, picked by `device_type` and `device_number`.

## Supports

| Type | Read | Set | Actions |
|---|---|---|---|
| telescope | `right_ascension`, `declination`, `altitude`, `azimuth`, `sidereal_time`, `slewing`, `at_park`, `at_home`, `tracking` | `tracking` | `abort_slew`, `park`, `unpark`, `find_home`, `slew_to_coordinates` with `right_ascension` and `declination`, `slew_to_alt_az` with `azimuth` and `altitude` |
| focuser | `is_moving`, `temperature`, `max_step` | `position` in steps | `halt` |
| camera | `ccd_temperature`, `camera_state`, `image_ready`, `percent_completed`, `cooler_power` | `cooler`, `target_temperature`, `gain` | `start_exposure` with `duration` and `light`, `abort_exposure`, `stop_exposure` |
| switch | `switch_0`, `switch_1`, ... | `switch_0`, `switch_1`, ... | |
| dome | `azimuth`, `altitude`, `shutter`, `slewing`, `at_park`, `at_home` | | `abort_slew`, `park`, `find_home`, `open_shutter`, `close_shutter`, `slew_to_azimuth` with `azimuth` |

Right ascension and sidereal time read in degrees, hours times 15, so `90 deg` slews to 6 h. A switch channel is a bool or a number by channel type. Other members need a `map`.

| Map | Meaning |
|---|---|
| `{ property: coolerpower, unit: percent }` | Any property, with the protocol `unit` and an optional `scale` |
| `{ property: shutterstatus, states: [open, closed, opening, closing, error] }` | Integer state as an enum |
| `{ switch: 3 }` | Switch 3 |
| `{ property: tracking, param: Tracking }` | Set a property with PUT |
| `{ method: move, param: Position, integer: true, readback: position }` | Set through a method, read back from a property |
| `{ method: slewtoazimuth, wait: slewing, params: { azimuth: { name: Azimuth, unit: deg } } }` | Action. `wait` names a property that stays true while the action runs |
| `{ device: dome, number: 0, ... }` | Any of these on another device of the same server |

## Behavior

- `connect()` checks for API version 1 and every device the file uses, then sets `Connected` on each. `close()` leaves `Connected` set unless `disconnect_on_close: true`.
- A non-zero ASCOM `ErrorNumber` fails the command with the error named, such as `0x408 not allowed while parked`.
- A `wait` action polls until the member is false and returns `done`, or returns `started` after `action_wait`.
- A fractional value for an integer member such as focuser position is blocked.
- A stop sends AbortSlew to telescopes and domes, Halt to focusers and AbortExposure to cameras. InvalidWhileParked from a parked mount counts as safe. `park_on_stop: true` also parks. Switches and tracking change only through the file's `safe_state`.
- `openhal discover` broadcasts on UDP port 32227 and lists each server's devices read-only.

## Setup

Install with `uv tool install --compile-bytecode "halkit[alpaca] @ git+https://github.com/sohan-bhat/OpenHAL"` and start ASCOM Remote or the device's own Alpaca server.

| Key | Default | Meaning |
|---|---|---|
| `host` | required | Server host |
| `port` | 11111 | HTTP port |
| `scheme` | `http` | `http` or `https` |
| `device_type` | `telescope` | Any Alpaca type |
| `device_number` | 0 | Device number on the server |
| `timeout` | `5 s` | Per request |
| `action_wait` | `8 s` | Poll time for `wait` actions, at most 9 s |
| `park_on_stop` | false | Park telescopes and domes on a stop |
| `disconnect_on_close` | false | Clear `Connected` on close |

## Example device file

`openhal/drivers/alpaca/examples/eq-mount.hal.yaml` drives a mount. Set the host and site limits. Slews need `confirm-each-time` and an unparked, tracking, still mount.

## Known limitations

- No camera image download, since `imagearray` can be tens of megabytes.
- Absolute focusers only.
- No MoveAxis or pulse guiding.
- OpenHAL checks only the file's declination and altitude limits, so keep the mount's own horizon limits set.

## Hazard defaults

`medium`. A slewing mount can hit the pier, a tripod leg or a person, and a dome rotates with force.

## Sources

- ASCOM Alpaca API reference with the device API, management API and error numbers, https://ascom-standards.org/api/
- ASCOM Alpaca discovery protocol, https://github.com/ASCOMInitiative/ASCOMRemote/blob/main/Documentation/ASCOM%20Alpaca%20API%20Reference.pdf
- ASCOM interface definitions ITelescopeV3, IFocuserV3, ICameraV3, ISwitchV2 and IDomeV2, https://ascom-standards.org/Help/Developer/html/N_ASCOM_DeviceInterface.htm
