# alpaca driver

The `alpaca` driver talks to astronomy devices through ASCOM Alpaca, the REST form of ASCOM. It covers telescope mounts, focusers, cameras, switches and power boxes, and domes, and finds Alpaca servers with the Alpaca UDP discovery broadcast.

| | |
|---|---|
| Driver name | `alpaca` |
| Library | httpx 0.28.1 (BSD-3-Clause), already a hub dependency |
| Extra | `uv pip install 'openhal-hub[alpaca]'` |
| Hazard default | medium |
| Conformance | full |
| Safe state | native. AbortSlew, Halt or AbortExposure by device type |
| Self-describe | yes, from the device's `can` properties |

## What it supports

One device file is one Alpaca device, chosen with `device_type` and `device_number`. Channel names follow these conventions for each type. A map can reach another device on the same server, for example the dome next to its mount.

| Type | Read | Set | Actions |
|---|---|---|---|
| telescope | `right_ascension`, `declination`, `altitude`, `azimuth`, `sidereal_time`, `slewing`, `at_park`, `at_home`, `tracking` | `tracking` | `abort_slew`, `park`, `unpark`, `find_home`, `slew_to_coordinates` (args `right_ascension`, `declination`), `slew_to_alt_az` (args `azimuth`, `altitude`) |
| focuser | `is_moving`, `temperature`, `max_step` | `position` (steps, through Move) | `halt` |
| camera | `ccd_temperature`, `camera_state`, `image_ready`, `percent_completed`, `cooler_power` | `cooler`, `target_temperature`, `gain` | `start_exposure` (args `duration`, `light`), `abort_exposure`, `stop_exposure` |
| switch | `switch_0`, `switch_1`, ... | `switch_0`, `switch_1`, ... | |
| dome | `azimuth`, `altitude`, `shutter`, `slewing`, `at_park`, `at_home` | | `abort_slew`, `park`, `find_home`, `open_shutter`, `close_shutter`, `slew_to_azimuth` (arg `azimuth`) |

Right ascension and sidereal time come from Alpaca in hours and are reported in degrees, hours times 15, because the unit registry has no hour angle. Send `90 deg` to slew to 6 h.

A switch channel is a bool through GetSwitch and SetSwitch, or a number through GetSwitchValue and SetSwitchValue, depending on the channel type.

Other members need a `map`.

| Map | Meaning |
|---|---|
| `{ property: coolerpower, unit: percent }` | Read any property. `unit` is the protocol unit, `scale` multiplies the protocol value |
| `{ property: shutterstatus, states: [open, closed, opening, closing, error] }` | Read an integer state as an enum |
| `{ switch: 3 }` | Switch number 3 |
| `{ property: tracking, param: Tracking }` | Set a property with PUT |
| `{ method: move, param: Position, integer: true, readback: position }` | Set through a method and read the value back from a property |
| `{ method: slewtoazimuth, wait: slewing, params: { azimuth: { name: Azimuth, unit: deg } } }` | An action. `wait` names a property that is true while it runs |
| `{ device: dome, number: 0, ... }` | Any of the above on another device of the same server |

## How the protocol is handled

- connect() checks `/management/apiversions` for version 1 and that every device the file uses is configured, then sets `Connected` on each.
- close() leaves `Connected` alone, because an imaging program may share the device. Set `disconnect_on_close: true` to clear it.
- Every request carries `ClientID` and `ClientTransactionID`. PUT parameter names are spelled exactly as the reference spells them.
- An ASCOM error comes back as HTTP 200 with a non-zero `ErrorNumber`. The driver names it, for example `0x408 not allowed while parked`, and fails the command.
- Actions with `wait` poll it until it is false and answer `done`, or answer `started` after `action_wait`.
- Integer members such as the focuser position refuse a value that isn't whole. Nothing is sent.

## Safe state

Telescopes and domes get AbortSlew, focusers Halt and cameras AbortExposure, on every device the file uses. A parked mount refuses AbortSlew as InvalidWhileParked, which counts as safe since it isn't moving. `park_on_stop: true` also parks telescopes and domes after the abort. Switches have no native safe state, so the file's own `safe_state` values set them. A stop doesn't turn tracking off unless the file says so.

## Discovery

`openhal discover` broadcasts `alpacadiscovery1` to UDP port 32227 and waits one second. Each answering server is asked for its configured devices with read-only GET requests. Nothing is connected and nothing changes.

## Setup

1. Install the extra with `uv pip install 'openhal-hub[alpaca]'`.
2. Start the Alpaca server. That is ASCOM Remote for ASCOM drivers on Windows, or the device's own server.
3. Start from `openhal/drivers/alpaca/examples/eq-mount.hal.yaml`, set the host, port and device number, and set limits for your site.
4. Run `openhal file validate`, then confirm the limits by hand.

## Parameters

| Key | Default | Meaning |
|---|---|---|
| `host` | required | Alpaca server host name or address |
| `port` | 11111 | Alpaca HTTP port |
| `scheme` | `http` | `http` or `https` |
| `device_type` | `telescope` | `telescope`, `focuser`, `camera`, `switch`, `dome` and the other Alpaca types |
| `device_number` | 0 | Device number on the server |
| `timeout` | `5 s` | Per request |
| `action_wait` | `8 s` | How long a waiting action polls before answering `started`. At most 9 s |
| `park_on_stop` | false | Park telescopes and domes during a stop |
| `disconnect_on_close` | false | Set `Connected` to false when the hub closes the device |

## Example device file

```yaml
device: Equatorial mount
id: mount
connect: { alpaca: observatory.local, device_type: telescope, device_number: 0 }
read:
  declination: { unit: deg }
  slewing: { type: bool }
  at_park: { type: bool }
write:
  tracking: { type: bool }
actions:
  abort_slew: {}
  park: { confirm: confirm }
  slew_to_coordinates:
    args:
      right_ascension: { unit: deg, min: 0, max: 359.99 }
      declination: { unit: deg, min: -20, max: 89 }
    require: ["at_park == false", "tracking == true"]
    confirm: confirm-each-time
safe_state:
  - { tracking: false }
hazard: medium
```

## Known limitations

- Camera images are not downloaded. `imagearray` can be tens of megabytes, and the hub has no image path for Alpaca yet.
- Relative focusers are not written. The `position` convention needs an absolute focuser.
- MoveAxis and pulse guiding are not exposed. Use slews, which the device bounds itself.
- The declination and altitude limits in the file are the only horizon limits OpenHAL knows. The mount's own limits still matter.

## Hazard defaults

`medium`. A slewing mount can hit the pier, a tripod leg or a person, and a dome rotates with force. Keep `confirm-each-time` on slews and add `require` conditions on park state and tracking.

## Sources

- ASCOM Alpaca API reference, https://ascom-standards.org/api/ (device API, management API, error numbers)
- ASCOM Alpaca discovery protocol, https://github.com/ASCOMInitiative/ASCOMRemote/blob/main/Documentation/ASCOM%20Alpaca%20API%20Reference.pdf
- ASCOM interface definitions, ITelescopeV3, IFocuserV3, ICameraV3, ISwitchV2 and IDomeV2, https://ascom-standards.org/Help/Developer/html/N_ASCOM_DeviceInterface.htm
