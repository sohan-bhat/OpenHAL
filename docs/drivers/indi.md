# indi driver

The `indi` driver connects to mounts, focusers and cameras on an INDI server, `indiserver` on TCP port 7624. Number, switch, text and light properties become channels. One device file is one INDI device, named in `device` as the INDI control panel shows, and `kind` picks these conventions.

## Supports

| Kind | Read | Set | Actions |
|---|---|---|---|
| telescope | `right_ascension`, `declination`, `altitude`, `azimuth`, `slewing`, `parked`, `tracking` | `tracking` | `abort`, `park`, `unpark`, `slew_to_coordinates` with `right_ascension` and `declination` |
| focuser | `position`, `moving`, `temperature` | `position` | `abort` |
| camera | `ccd_temperature`, `cooler`, `exposure_left`, `exposing` | `cooler`, `target_temperature` | `start_exposure` with `duration`, `abort_exposure` |
| generic | anything through a map | anything through a map | anything through a map |

Right ascension reads in degrees, hours times 15. `slewing`, `moving` and `exposing` are true while their property is Busy.

| Map | Meaning |
|---|---|
| `{ property: EQUATORIAL_EOD_COORD, element: DEC, unit: deg }` | One number member in the protocol `unit`, with an optional `scale` |
| `{ property: TELESCOPE_TRACK_STATE, element: TRACK_ON }` | One switch member as a bool |
| `{ property: TELESCOPE_TRACK_STATE, element: TRACK_ON, off: TRACK_OFF }` | A bool that turns `off` on for false |
| `{ property: ON_COORD_SET }` | The member that is on, as an enum of lower case names |
| `{ property: EQUATORIAL_EOD_COORD, state: true }` | Property state as an enum `idle ok busy alert`, or a bool true while Busy |
| `{ property: TELESCOPE_PARK, element: PARK, wait: true }` | Action that turns one switch on and follows Busy |
| `{ property: EQUATORIAL_EOD_COORD, args: { ra: { element: RA, unit: deg, scale: 15 } }, before: [{ property: ON_COORD_SET, element: TRACK }] }` | Action that sends number or text members after setting other switches |
| `{ device: Focuser Simulator, ... }` | Any of these on another device of the same server |

## How the protocol is handled

- `connect()` turns CONNECTION on and allows `define_wait` for the named properties to appear. `close()` leaves the device connected for KStars, Ekos or a guider.
- Reads come from a cache of the server's pushed updates.
- An Alert reply fails the command with the INDI driver's message, such as `Mount is parked`.
- `wait` actions follow Busy and return `done`, or `started` after `action_wait`.
- BLOBs are never requested, and an XML document type declaration drops the connection.

## Safe state

A stop turns on TELESCOPE_ABORT_MOTION, FOCUS_ABORT_MOTION or CCD_ABORT_EXPOSURE by kind, then runs the file's steps. `generic` devices and devices reached through maps get no native abort. Parking and tracking off happen only through the file's safe state.

## Discovery

`openhal discover` lists the devices on the INDI server at `127.0.0.1:7624` without connecting any.

## Setup

Start `indiserver` with your drivers, such as `indiserver indi_eqmod_telescope indi_asi_focuser`, then set the host, device name and site limits in `openhal/drivers/indi/examples/eq6-mount.hal.yaml`.

| Key | Default | Meaning |
|---|---|---|
| `host` | required | Server host |
| `port` | 7624 | Server port |
| `device` | required | INDI device name |
| `kind` | `telescope` | `telescope`, `focuser`, `camera` or `generic` |
| `timeout` | `5 s` | Response deadline |
| `action_wait` | `8 s` | Time a `wait` action follows Busy before returning `started`, at most 9 s |
| `define_wait` | `5 s` | Time connect allows for the file's properties |
| `connect_device` | true | Turn CONNECTION on during connect |

## Known limitations

- No image download.
- No manual motion convention. Map TELESCOPE_MOTION_NS and WE as generic switches only with tight interlocks.
- A property deleted after connect fails reads until defined again.

## Hazard defaults

`medium`. A slewing mount can hit the pier or a person, and a focuser can drive past the mechanical end.

## Sources

- INDI protocol 1.7, Elwood Downey, https://github.com/indilib/indi/blob/master/doc/INDI.pdf
- INDI standard properties, https://www.indilib.org/develop/developer-manual/101-standard-properties.html
- INDI device list, used only for the device estimate, https://www.indilib.org/devices.html
