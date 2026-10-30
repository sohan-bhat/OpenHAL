# marlin driver

The `marlin` driver connects to printers and other machines running Marlin firmware over USB serial. The driver reads temperatures, positions and SD print state, sets heater targets and the part fan, and runs homing and SD print control.

| | |
|---|---|
| Driver name | `marlin` |
| Library | pyserial 3.5 (BSD-3-Clause), through the shared serial link |
| Extra | `uv tool install --compile-bytecode "openhal-hub[marlin] @ git+https://github.com/sohan-bhat/OpenHAL"` |
| Hazard default | medium |
| Safe state | native. Every heater target goes to 0. M112 only when `m112_on_stop` is true |
| Self-describe | no |

## What it supports

| Channel name | Kind | G-code |
|---|---|---|
| `extruder_temp`, `bed_temp`, `chamber_temp` | read, degC or any temperature unit | M105 or M155 auto-report |
| `position_x`, `position_y`, `position_z`, `position_e` | read, mm or any length unit | M114 |
| `sd_printing` (bool), `sd_progress` (percent) | read | M27 |
| `extruder_target`, `bed_target`, `chamber_target` | write, temperature unit | M104 T0, M140, M141 |
| `fan_speed` | write, percent | M106 P0 S0 to 255 |
| `home` (arg `axes` x, y, z, xy or all) | action | G28 |
| `pause`, `resume`, `cancel` | action | M25, M24, M524 |

Other names need a `map`.

| Map | Meaning |
|---|---|
| `{ temperature: T1, field: target }` | Heater `T0` to `T7`, `B` or `C`, the actual value or the target |
| `{ position: Z }` | One axis from M114 |
| `{ sd: progress }` | `printing` or `progress` from M27 |
| `{ heater: T1 }` | Write the target of that heater |
| `{ fan: 1 }` | Write fan index 0 to 7 |
| `{ command: home }` | Run `home`, `pause`, `resume` or `cancel` under another action name |

Temperatures are converted from degC to the channel unit and back, so a `degF` channel works. Fan percent maps to the PWM byte as `round(percent * 255 / 100)`.

Because a raw command would bypass every limit in the device file, the driver deliberately has no raw G-code action.

## How the protocol is handled

- After opening the port the driver waits up to `settle` for the `start` banner that most boards print after the reset on open, then sends `M110 N0`.
- Every command carries a line number and an XOR checksum (`N12 M104 T0 S200.0*93`). On `Resend` the driver sends the requested lines again and discards the extra `ok` that Marlin sends with the request.
- Commands in flight are tracked in order and resolved by `ok`, and `echo:busy: processing` keeps a command alive past `timeout`.
- The driver reads M115 on connect, and when the M115 response reports `Cap:AUTOREPORT_TEMP:1` the driver turns on `M155 S<autoreport>` and reads temperatures from the reports, so reads keep working during long moves.
- Because the hub's driver timeout of 10 s is shorter than many homing moves, `home` waits up to `action_wait`, and if the printer is still busy `home` returns `started` and the `ok` is collected in the background.
- `start` in the middle of a session means the board reset, so commands in flight fail, the numbering restarts, and heaters are off.
- `Error:Printer halted` means the firmware stopped itself, so the driver reports itself disconnected until the printer is reset and reconnected.

## Setup

1. Install the extra with `uv tool install --compile-bytecode "openhal-hub[marlin] @ git+https://github.com/sohan-bhat/OpenHAL"`.
2. Because the driver opens the port exclusively, close any other program that holds the port (OctoPrint, Pronterface, a slicer).
3. Start from `openhal/drivers/marlin/examples/ender-3-v2.hal.yaml`, set `match.usb` or the port path, and set limits that fit your printer.
4. Validate with `openhal file validate`, then confirm the limits by hand.

## Parameters

| Key | Default | Meaning |
|---|---|---|
| `port` | required | Device path, pyserial URL or `auto` (uses `match.usb`) |
| `baud` | 115200 | Baud rate |
| `timeout` | `5 s` | How long the printer may stay silent before a command fails |
| `settle` | `2 s` | Longest wait for the boot banner after opening |
| `action_wait` | `8 s` | How long `home` waits before returning `started`. At most 9 s |
| `autoreport` | `2 s` | M155 interval, or `0 s` to poll with M105 |
| `checksums` | true | Send line numbers and checksums |
| `m112_on_stop` | false | Also send M112 during the safe state. The firmware then needs a reset |

## Example device file

```yaml
device: { name: Ender-3 V2, manufacturer: Creality }
id: ender
match: { usb: ["1a86:7523"] }
connect: { marlin: auto, baud: 115200 }
read:
  extruder_temp: { unit: degC, every: 2 s, range: [0, 300] }
  bed_temp: { unit: degC, every: 2 s, range: [0, 120] }
write:
  extruder_target: { unit: degC, min: 0, max: 240, max_change_per_s: 50, confirm: confirm }
  bed_target: { unit: degC, min: 0, max: 90, max_change_per_s: 20 }
  fan_speed: { unit: percent, min: 0, max: 100 }
actions:
  home: { args: { axes: { type: enum, values: [x, y, z, xy, all] } }, confirm: confirm }
safe_state:
  - { extruder_target: 0, bed_target: 0, fan_speed: 0 }
hazard: medium
```

## Known limitations

- Fan speed can't be read back, so a read returns the last value this driver sent, or unknown before the first write.
- Pause, resume and cancel only act on prints started from the printer's SD card, so a print streamed by a host program has to be paused by that program.
- Moves other than homing are not exposed, and streaming G-code files is out of scope for this driver.
- Multi-extruder printers need a `map` with `temperature: T1` or `heater: T1` for the second hotend.
- The firmware's own thermal protection is the real last line of defense, and the driver can't detect whether that protection is enabled.

## Hazard defaults

The default hazard is `medium`, because heaters and moving axes can burn or pinch, so keep `confirm: confirm` on the hotend target and on `home`.

## Sources

- Marlin G-code reference, https://marlinfw.org/docs/gcode/ (M104, M105, M106, M110, M112, M114, M115, M140, M141, M155, M24, M25, M27, M524, G28)
- Marlin host protocol notes in the RepRap G-code wiki, https://reprap.org/wiki/G-code (line numbers, checksums, `ok`, `Resend`)
- Marlin configurations repository, https://github.com/MarlinFirmware/Configurations (used only for the device estimate, no code)
