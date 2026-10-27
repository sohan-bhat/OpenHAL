# grbl driver

The `grbl` driver talks to CNC routers, laser engravers and plotters running GRBL 1.1 over USB serial. The driver reads the machine state, positions and settings, sets the spindle, laser power and coolant, and runs homing, jogs and moves. grblHAL controllers speak the same protocol and work too.

| | |
|---|---|
| Driver name | `grbl` |
| Library | pyserial 3.5 (BSD-3-Clause), through the shared serial link |
| Extra | `uv tool install --compile-bytecode "openhal-hub[grbl] @ git+https://github.com/sohan-bhat/OpenHAL"` |
| Hazard default | high |
| Conformance | full |
| Safe state | native. Feed hold, then soft reset |
| Self-describe | yes, from `$$` |

## What it supports

| Channel name | Kind | GRBL source |
|---|---|---|
| `state` | read, enum `idle run hold jog alarm door check home sleep` | status report `?` |
| `alarm` | read, dimensionless | the last `ALARM:N`, 0 when not in alarm |
| `position_x`, `position_y`, `position_z`, `position_a` | read, length | machine position, `MPos` |
| `work_x`, `work_y`, `work_z`, `work_a` | read, length | work position, `WPos` |
| `feed_rate` | read, mm/min or any speed unit | `FS` or `F` |
| `pins` | read, string | `Pn`, for example `XP` |
| `spindle_speed` | set, rpm | `M3 S<rpm>`, `M5` at 0 |
| `laser_power` | set, percent | `M4 S<percent x $30 / 100>`, `M5` at 0 |
| `flood`, `mist` | set, bool | `M8`, `M7`, `M9` |
| `home` | action | `$H` |
| `jog` (args `x`, `y`, `z`, `a`, `feed`) | action | `$J=G21 G91 ...` |
| `move` (args `x`, `y`, `z`, `a`, `feed`) | action | `G21 G90 G1 ...` |
| `set_work_zero` (arg `axes`) | action | `G10 L20 P0 X0 ...` |
| `cancel_jog`, `hold`, `resume`, `reset` | action | realtime 0x85, `!`, `~`, 0x18 |
| `clear_alarm` | action | `$X` |

Other names need a `map`.

| Map | Meaning |
|---|---|
| `{ status: x, frame: work }` | One field of the status report. `state`, `alarm`, `x`, `y`, `z`, `a`, `feed`, `spindle` or `pins` |
| `{ setting: 130 }` | Any numeric `$` setting, read-only. The unit comes from the setting, for example mm for `$130` |
| `{ spindle: ccw }` | Spindle with `M4` instead of `M3` |
| `{ laser: constant }` | Laser with `M3` instead of `M4` |
| `{ coolant: mist }` | Coolant output `flood` or `mist` |
| `{ command: move, distance: relative, frame: machine, rapid: true }` | An action under another name. `move` defaults to absolute work coordinates and `G1` |

Values arrive in the channel's unit and are converted for GRBL. Lengths go out in mm with `G21` on every line, so the machine's own unit mode never matters. Reads from a controller with `$13=1` (inch reports) are converted back.

Because a raw line would bypass every limit in the device file, the driver deliberately has no raw G-code action.

## How the protocol is handled

- Lines go out one at a time, and each line waits for its `ok` or `error:N`, with the error number translated into a sentence.
- Status comes from the `?` realtime byte. Reads within `status_age` share one report so a page of channels costs one query.
- Work and machine positions are converted with the `WCO` offset. When a report has no `WCO` the driver reads `$#` and `$G` once.
- GRBL answers motion lines with `ok` when the lines are queued, and `jog` and `move` then poll until the machine is idle and return `done`, or return `started` after `action_wait`.
- `$H` blocks the line until homing ends. If homing takes longer than `action_wait` the action returns `started` and the `ok` is collected in the background.
- `ALARM:N` fails the command in flight. After a hard or soft limit GRBL ignores everything but a reset, and the driver refuses lines until a reset is sent.
- The banner `Grbl 1.1h ['$' for help]` means the board reset, so commands in flight fail.

## Safe state

The driver sends feed hold (`!`), waits up to 2 s for the machine to stop, then sends a soft reset (Ctrl-X), which turns the spindle, laser and coolant off. If the machine was moving GRBL comes back in `ALARM:3`, so home or clear the alarm before the next job. The file's own safe state steps run afterwards, and turning an output off while GRBL is in alarm counts as done when `$G` shows the output is already off.

Because a software stop is not an emergency stop, keep a physical e-stop that cuts motor and spindle power.

## Setup

1. Install the extra with `uv tool install --compile-bytecode "openhal-hub[grbl] @ git+https://github.com/sohan-bhat/OpenHAL"`.
2. Because the driver opens the port exclusively, close any sender that holds the port (UGS, Candle, LightBurn, bCNC).
3. Start from `openhal/drivers/grbl/examples/3018-router.hal.yaml`. Set `match.usb` or the port path, and set limits that fit your machine and work.
4. Run `openhal file validate`, then confirm the limits by hand.

## Parameters

| Key | Default | Meaning |
|---|---|---|
| `port` | required | Device path, pyserial URL or `auto` (uses `match.usb`) |
| `baud` | 115200 | Baud rate |
| `timeout` | `5 s` | How long to wait for `ok` or a status report |
| `settle` | `2 s` | Longest wait for the banner after opening the port |
| `action_wait` | `8 s` | How long motion actions wait before answering `started`. At most 9 s |
| `status_age` | `200 ms` | Reuse a status report this fresh across reads |

## Example device file

```yaml
device: { name: 3018 CNC router, manufacturer: SainSmart }
id: router
match: { usb: ["1a86:7523"] }
connect: { grbl: auto, baud: 115200 }
read:
  state: { type: enum, values: [idle, run, hold, jog, alarm, door, check, home, sleep] }
  position_z: { unit: mm }
write:
  spindle_speed: { unit: rpm, min: 0, max: 10000, confirm: confirm-each-time }
actions:
  jog:
    args:
      x: { unit: mm, min: -20, max: 20 }
      feed: { unit: mm/min, min: 10, max: 1000 }
    require: ["state == idle"]
    confirm: confirm-each-time
  hold: {}
safe_state:
  - { spindle_speed: 0 }
hazard: high
```

## Known limitations

- G-code files are not streamed, so run jobs from a sender and use this driver to watch, hold and stop the jobs.
- Overrides (feed, rapid and spindle percentages) are not exposed yet.
- Only the active work coordinate system is used for `work_*` reads and `set_work_zero`.
- In laser mode `M4` only fires while moving, so setting `laser_power` alone never burns. `{ laser: constant }` uses `M3`, which keeps the laser at power during moves.
- Because GRBL would clamp spindle speeds above `$30` or below `$31` silently, the driver refuses those speeds.

## Hazard defaults

The default hazard is `high`, because spindles, bits and lasers cut and burn, and axes can crush. Every change and action on a high hazard device waits for a person's approval, and keeping `confirm: confirm-each-time` in the file as well makes the intent visible.

## Sources

- Grbl v1.1 Interface, https://github.com/gnea/grbl/blob/master/doc/markdown/interface.md (status reports, `ok`, `error:N`, `ALARM:N`, realtime bytes, streaming)
- Grbl v1.1 Commands, https://github.com/gnea/grbl/blob/master/doc/markdown/commands.md (`$$`, `$#`, `$G`, `$I`, `$X`, `$H`, `$J=`)
- Grbl v1.1 Jogging and Laser Mode, https://github.com/gnea/grbl/blob/master/doc/markdown/jogging.md and laser_mode.md
- Error and alarm code tables, https://github.com/gnea/grbl/tree/master/doc/csv (messages paraphrased, GRBL is GPL-3.0 and no code was copied)
