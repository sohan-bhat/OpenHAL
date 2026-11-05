# grbl driver

The `grbl` driver controls CNC routers, laser engravers and plotters running GRBL 1.1 or grblHAL over USB serial. `describe()` builds channels from `$$`.

## Supports

| Channel name | Kind | GRBL source |
|---|---|---|
| `state` | read, enum `idle run hold jog alarm door check home sleep` | status report `?` |
| `alarm` | read, dimensionless | the last `ALARM:N`, 0 when not in alarm |
| `position_x`, `position_y`, `position_z`, `position_a` | read, length | machine position, `MPos` |
| `work_x`, `work_y`, `work_z`, `work_a` | read, length | work position, `WPos` |
| `feed_rate` | read, mm/min or any speed unit | `FS` or `F` |
| `pins` | read, string | `Pn`, such as `XP` |
| `spindle_speed` | set, rpm | `M3 S<rpm>`, `M5` at 0 |
| `laser_power` | set, percent | `M4 S<percent x $30 / 100>`, `M5` at 0 |
| `flood`, `mist` | set, bool | `M8`, `M7`, `M9` |
| `home` | action | `$H` |
| `jog` with `x`, `y`, `z`, `a`, `feed` | action | `$J=G21 G91 ...` |
| `move` with `x`, `y`, `z`, `a`, `feed` | action | `G21 G90 G1 ...` |
| `set_work_zero` with `axes` | action | `G10 L20 P0 X0 ...` |
| `cancel_jog`, `hold`, `resume`, `reset` | action | realtime 0x85, `!`, `~`, 0x18 |
| `clear_alarm` | action | `$X` |

Other names need a `map`.

| Map | Meaning |
|---|---|
| `{ status: x, frame: work }` | One status field, `state`, `alarm`, `x`, `y`, `z`, `a`, `feed`, `spindle` or `pins` |
| `{ setting: 130 }` | Any numeric `$` setting, read-only, in the setting's unit |
| `{ spindle: ccw }` | Spindle with `M4` instead of `M3` |
| `{ laser: constant }` | Laser with `M3` instead of `M4` |
| `{ coolant: mist }` | Coolant output `flood` or `mist` |
| `{ command: move, distance: relative, frame: machine, rapid: true }` | An action under another name. `move` defaults to absolute work coordinates and `G1` |

Lengths go out in mm with `G21` on every line, and inch reports convert back. No raw G-code action exists, since a raw line would bypass the file's limits.

## How the protocol is handled

- Each line goes out after the previous `ok` or `error:N`, and error numbers become sentences.
- Reads within `status_age` share one `?` status report.
- `jog`, `move` and `home` return `done` once the machine is idle, or `started` after `action_wait`.
- `ALARM:N` fails the command in flight, and after a limit alarm only a reset goes through. A `Grbl 1.1h` banner means the board reset and fails commands in flight.

## Safe state

A stop sends feed hold, allows 2 s, then sends a Ctrl-X soft reset that turns off the spindle, laser and coolant. A machine stopped mid-move comes back in `ALARM:3`, so home or clear the alarm before the next job. The file's safe state steps run afterwards, and an output already off in `$G` counts as done.

## Setup

Install with `uv tool install --compile-bytecode "halkit[grbl] @ git+https://github.com/sohan-bhat/OpenHAL"`, close any sender holding the port such as UGS, Candle, LightBurn or bCNC, and start from `openhal/drivers/grbl/examples/3018-router.hal.yaml`.

| Key | Default | Meaning |
|---|---|---|
| `port` | required | Device path, pyserial URL or `auto` with `match.usb` |
| `baud` | 115200 | Baud rate |
| `timeout` | `5 s` | Deadline for `ok` or a status report |
| `settle` | `2 s` | Longest banner delay after opening |
| `action_wait` | `8 s` | Time before motion actions return `started`, at most 9 s |
| `status_age` | `200 ms` | Status report reuse window |

## Known limitations

- No G-code streaming. Run jobs from a sender and use the driver to watch, hold and stop.
- No overrides yet, and only the active work coordinate system.
- In laser mode `M4` fires only while moving. `{ laser: constant }` uses `M3`, which stays on.
- Spindle speeds outside `$31` to `$30` are blocked, since GRBL would clamp the speed silently.

## Hazard defaults

`high`, so the hub holds every change and action until a person approves the request. Keep a physical e-stop that cuts motor and spindle power.

## Sources

- Grbl v1.1 Interface for status reports, `ok`, `error:N`, `ALARM:N`, realtime bytes and streaming, https://github.com/gnea/grbl/blob/master/doc/markdown/interface.md
- Grbl v1.1 Commands for `$$`, `$#`, `$G`, `$I`, `$X`, `$H` and `$J=`, https://github.com/gnea/grbl/blob/master/doc/markdown/commands.md
- Grbl v1.1 Jogging and Laser Mode, https://github.com/gnea/grbl/blob/master/doc/markdown/jogging.md and laser_mode.md
- Error and alarm code tables, with messages paraphrased since GRBL is GPL-3.0 and no code was copied, https://github.com/gnea/grbl/tree/master/doc/csv
