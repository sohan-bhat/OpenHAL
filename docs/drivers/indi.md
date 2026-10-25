# indi driver

The `indi` driver talks to telescope mounts, focusers and cameras on an INDI server (`indiserver`, TCP port 7624) with its own client for the INDI XML protocol. Number, switch, text and light properties become channels, and abort is the native safe state.

| | |
|---|---|
| Driver name | `indi` |
| Library | none, the Python standard library only |
| Extra | none needed |
| Hazard default | medium |
| Conformance | full |
| Safe state | native. TELESCOPE_ABORT_MOTION, FOCUS_ABORT_MOTION or CCD_ABORT_EXPOSURE by kind |
| Self-describe | yes, from the properties the server defines |

## What it supports

One device file is one INDI device, named in `device` exactly as the INDI control panel shows it. `kind` picks the conventions below. A map can reach any property of any device on the same server.

| Kind | Read | Set | Actions |
|---|---|---|---|
| telescope | `right_ascension`, `declination`, `altitude`, `azimuth`, `slewing`, `parked`, `tracking` | `tracking` | `abort`, `park`, `unpark`, `slew_to_coordinates` (args `right_ascension`, `declination`) |
| focuser | `position`, `moving`, `temperature` | `position` | `abort` |
| camera | `ccd_temperature`, `cooler`, `exposure_left`, `exposing` | `cooler`, `target_temperature` | `start_exposure` (arg `duration`), `abort_exposure` |
| generic | anything through a map | anything through a map | anything through a map |

Right ascension comes from INDI in hours and is reported in degrees, hours times 15, because the unit registry has no hour angle. `slewing`, `moving` and `exposing` are true while their property is Busy.

| Map | Meaning |
|---|---|
| `{ property: EQUATORIAL_EOD_COORD, element: DEC, unit: deg }` | One number member. `unit` is the protocol unit and `scale` multiplies the protocol value |
| `{ property: TELESCOPE_TRACK_STATE, element: TRACK_ON }` | One switch member as a bool |
| `{ property: TELESCOPE_TRACK_STATE, element: TRACK_ON, off: TRACK_OFF }` | A bool that turns `off` on for false, for one of many switches |
| `{ property: ON_COORD_SET }` | The member that is on, as an enum of lower case member names |
| `{ property: EQUATORIAL_EOD_COORD, state: true }` | The property state as an enum `idle ok busy alert`, or a bool that is true while Busy |
| `{ property: TELESCOPE_PARK, element: PARK, wait: true }` | An action that turns one switch member on, and follows the Busy state |
| `{ property: EQUATORIAL_EOD_COORD, args: { ra: { element: RA, unit: deg, scale: 15 } }, before: [{ property: ON_COORD_SET, element: TRACK }] }` | An action that sends number or text members, after setting other switches first |
| `{ device: Focuser Simulator, ... }` | Any of the above on another device of the same server |

## How the protocol is handled

- connect() sends `getProperties` for each device the file uses, turns the device's CONNECTION switch on, and waits up to `define_wait` until every property the file names is defined. Many drivers define their properties only after they connect.
- close() leaves the device connected, because KStars, Ekos or a guider may share it.
- The server pushes updates. Reads come from a cache it keeps current, so a read costs no round trip.
- A change sends `new*Vector` with only the members that change and waits for the server's answer. An answer in the Alert state fails the command with the driver's own message, such as `Mount is parked`.
- Actions with `wait` follow the property while it is Busy and answer `done`, or `started` after `action_wait`.
- Numbers may arrive in sexagesimal form (`5:30:00`) and are read as decimal.
- Document type declarations and entities are refused, and the connection is dropped. INDI never uses them. BLOBs are never requested, so no image arrives.

## Safe state

A stop turns on TELESCOPE_ABORT_MOTION for a telescope, FOCUS_ABORT_MOTION for a focuser and CCD_ABORT_EXPOSURE for a camera, then runs the file's own steps. A `generic` device has no native step. Other devices reached through maps are not aborted by the native step, so give them their own device file or file steps. A stop doesn't park the mount or turn tracking off unless the file says so.

## Discovery

`openhal discover` asks the INDI server on `127.0.0.1:7624` for its properties and lists every device with its driver name. It never sends a change and never connects a device.

## Setup

1. Start `indiserver` with your drivers, for example `indiserver indi_eqmod_telescope indi_asi_focuser`.
2. Note each device name from the INDI control panel, such as `EQMod Mount`.
3. Start from `openhal/drivers/indi/examples/eq6-mount.hal.yaml`, set the host and device name, and set limits for your site.
4. Run `openhal file validate`, then confirm the limits by hand.

## Parameters

| Key | Default | Meaning |
|---|---|---|
| `host` | required | INDI server host name or address |
| `port` | 7624 | INDI server port |
| `device` | required | INDI device name |
| `kind` | `telescope` | `telescope`, `focuser`, `camera` or `generic` |
| `timeout` | `5 s` | How long to wait for an answer |
| `action_wait` | `8 s` | How long a waiting action follows Busy before answering `started`. At most 9 s |
| `define_wait` | `5 s` | How long connect waits for the file's properties |
| `connect_device` | true | Turn the device's CONNECTION switch on during connect |

## Example device file

```yaml
device: EQ6-R mount
id: eq6
connect: { indi: astro-pi.local, device: EQMod Mount, kind: telescope }
read:
  declination: { unit: deg }
  slewing: { type: bool }
  parked: { type: bool }
write:
  tracking: { type: bool }
actions:
  abort: {}
  park: { confirm: confirm }
  slew_to_coordinates:
    args:
      right_ascension: { unit: deg, min: 0, max: 359.99 }
      declination: { unit: deg, min: -20, max: 89 }
    require: ["parked == false", "slewing == false"]
    confirm: confirm-each-time
safe_state:
  - { tracking: false }
hazard: medium
```

## Known limitations

- Images (BLOBs) are not downloaded.
- Manual motion (TELESCOPE_MOTION_NS and WE) is not a convention. Map it as a generic switch only with tight interlocks.
- A property the server deletes after connect fails its reads until the server defines it again.
- Discovery only checks the local server. Name remote servers in a device file.

## Hazard defaults

`medium`. A slewing mount can hit the pier or a person, and a focuser can drive past its mechanical end. Keep `confirm-each-time` on slews and use `require` conditions on the park state.

## Sources

- INDI protocol 1.7, Elwood Downey, https://github.com/indilib/indi/blob/master/doc/INDI.pdf
- INDI standard properties, https://www.indilib.org/develop/developer-manual/101-standard-properties.html
- INDI device list, https://www.indilib.org/devices.html (used only for the device estimate)
