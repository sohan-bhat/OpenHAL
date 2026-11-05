# marlin driver

The `marlin` driver connects to printers and machines running Marlin over USB serial. The driver reads temperatures, positions and SD print state, sets heater targets and the part fan, and runs homing and SD print control.

## Supports

| Channel name | Kind | G-code |
|---|---|---|
| `extruder_temp`, `bed_temp`, `chamber_temp` | read, degC or any temperature unit | M105 or M155 auto-report |
| `position_x`, `position_y`, `position_z`, `position_e` | read, mm or any length unit | M114 |
| `sd_printing` bool, `sd_progress` percent | read | M27 |
| `extruder_target`, `bed_target`, `chamber_target` | write, temperature unit | M104 T0, M140, M141 |
| `fan_speed` | write, percent | M106 P0 S0 to 255 |
| `home` with `axes` x, y, z, xy or all | action | G28 |
| `pause`, `resume`, `cancel` | action | M25, M24, M524 |

Other names need a `map`.

| Map | Meaning |
|---|---|
| `{ temperature: T1, field: target }` | Heater `T0` to `T7`, `B` or `C`, actual or target |
| `{ position: Z }` | One axis from M114 |
| `{ sd: progress }` | `printing` or `progress` from M27 |
| `{ heater: T1 }` | Write that heater's target |
| `{ fan: 1 }` | Write fan 0 to 7 |
| `{ command: home }` | `home`, `pause`, `resume` or `cancel` under another name |

Fan percent sends `round(percent * 255 / 100)`. No raw G-code action exists, since a raw line would bypass the file's limits.

## How the protocol is handled

- After opening, the driver allows `settle` for the `start` banner, then sends `M110 N0`.
- Every line carries a number and checksum such as `N12 M104 T0 S200.0*93`, and `Resend` requests are answered.
- `echo:busy: processing` keeps a command alive past `timeout`.
- With `Cap:AUTOREPORT_TEMP:1` in M115, temperatures come from M155 reports, so reads work during long moves.
- `home` returns `started` after `action_wait` while the printer is busy.
- A `start` banner mid-session means the board reset, so commands in flight fail and the heaters are off.
- `Error:Printer halted` marks the device disconnected until the printer is reset and reconnected.

## Safe state

Every heater target goes to 0. `m112_on_stop: true` also sends M112, after which the firmware needs a reset.

## Setup

1. Install with `uv tool install --compile-bytecode "halkit[marlin] @ git+https://github.com/sohan-bhat/OpenHAL"`.
2. Close any program holding the port, such as OctoPrint, Pronterface or a slicer.
3. Start from `openhal/drivers/marlin/examples/ender-3-v2.hal.yaml` and set `match.usb` or the port and your printer's limits.

| Key | Default | Meaning |
|---|---|---|
| `port` | required | Device path, pyserial URL or `auto` with `match.usb` |
| `baud` | 115200 | Baud rate |
| `timeout` | `5 s` | Longest printer silence before a command fails |
| `settle` | `2 s` | Longest boot banner delay after opening |
| `action_wait` | `8 s` | Time before `home` returns `started`, at most 9 s |
| `autoreport` | `2 s` | M155 interval, or `0 s` to poll with M105 |
| `checksums` | true | Line numbers and checksums |
| `m112_on_stop` | false | Add M112 to the safe state |

## Known limitations

- Fan speed reads back the last value sent, or unknown before the first write.
- Pause, resume and cancel act only on SD card prints.
- No moves other than homing, no G-code streaming and no `describe()`.
- A second hotend needs a `map` with `temperature: T1` or `heater: T1`.
- The driver can't detect whether the firmware's thermal protection is on.

## Hazard defaults

`medium`. Keep `confirm: confirm` on the hotend target and `home`.

## Sources

- Marlin G-code reference for M104, M105, M106, M110, M112, M114, M115, M140, M141, M155, M24, M25, M27, M524 and G28, https://marlinfw.org/docs/gcode/
- Marlin host protocol notes in the RepRap G-code wiki for line numbers, checksums, `ok` and `Resend`, https://reprap.org/wiki/G-code
- Marlin configurations repository, used only for the device estimate with no code, https://github.com/MarlinFirmware/Configurations
