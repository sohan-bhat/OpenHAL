# moonraker driver

The `moonraker` driver connects to Klipper printers through Moonraker, the API server behind Mainsail and Fluidd, with httpx and websockets. The driver reads printer objects, sets heater targets and fan speeds with Klipper G-code, and runs homing and print control. `describe()` builds channels from `printer.objects.list` and `configfile`.

## Supports

| Channel name | Kind | Printer object and field |
|---|---|---|
| `state` | read, enum | `print_stats.state`, one of standby, printing, paused, complete, cancelled, error |
| `klippy_state`, `filename` | read, string | `webhooks.state`, `print_stats.filename` |
| `extruder_temp`, `bed_temp`, `chamber_temp` | read, temperature | `extruder`, `heater_bed`, `temperature_sensor chamber` |
| `progress` | read, percent | `virtual_sdcard.progress` times 100 |
| `position_x`, `position_y`, `position_z`, `homed_axes` | read | `toolhead.position`, `toolhead.homed_axes` |
| `extruder_target`, `bed_target` | write, temperature | `SET_HEATER_TEMPERATURE HEATER=... TARGET=...`, read back from `target` |
| `fan_speed` | write, percent | `M106 S0..255`, read back from `fan.speed` |
| `home` with `axes` x, y, z, xy or all | action | `G28` |
| `pause`, `resume`, `cancel` | action | `printer.print.pause`, `resume`, `cancel` |

Other names need a `map`.

| Map | Meaning |
|---|---|
| `{ object: "temperature_sensor chamber", field: temperature }` | Any object and field. `index` picks a list element and `scale` multiplies |
| `{ heater: enclosure }` | A `heater_generic`, `extruder1` or `heater_bed` target |
| `{ fan: exhaust }` | A `fan_generic` speed, set with `SET_FAN_SPEED` |
| `{ command: home }` | `home`, `pause`, `resume` or `cancel` under another name |

Fan percent sends `M106 S` as `round(percent * 255 / 100)` and `SET_FAN_SPEED SPEED` as `percent / 100`. No raw G-code action exists.

## How the protocol is handled

- `transport: http` polls one object per read. `websocket` subscribes to every object the file uses and reads from a cache.
- An API key from `token_env` goes out as `X-Api-Key`.
- G-code requests return when Klipper finishes. `home` returns `started` after `action_wait` and finishes in the background within 300 s.
- Klipper and Moonraker errors, such as a heater target above the printer.cfg `max_temp`, fail the command with the original message.
- `health()` reads `printer.info` or `webhooks`, and anything but `ready` reports disconnected with Klipper's message, such as an MCU shutdown.
- `match.moonraker` globs are checked against `printer.info` on connect.

## Safe state

A stop sends `TURN_OFF_HEATERS`. `emergency_stop_on_stop: true` also calls `printer.emergency_stop`.

## Setup

1. Install with `uv tool install --compile-bytecode "halkit[moonraker] @ git+https://github.com/sohan-bhat/OpenHAL"`.
2. With Moonraker `[authorization]` API keys, put the key in a variable such as `MOONRAKER_API_KEY` and set `token_env`. Otherwise add the hub's address to `trusted_clients`.
3. Start from `openhal/drivers/moonraker/examples/voron-2-4.hal.yaml` or `describe()`.

| Key | Default | Meaning |
|---|---|---|
| `host` | required | Moonraker host |
| `port` | 7125 | Moonraker port |
| `scheme` | `http` | `http` or `https`, and `ws` or `wss` |
| `transport` | `http` | `http` to poll, `websocket` to subscribe |
| `token_env` | none | Variable holding the API key |
| `timeout` | `5 s` | Per request |
| `action_wait` | `8 s` | Time before `home` returns `started`, at most 9 s |
| `emergency_stop_on_stop` | false | Add `printer.emergency_stop` to the safe state |

## Known limitations

- No file uploads or print starts.
- `exclude_object`, macros and other Klipper commands need driver support.
- With `transport: http`, polling under about 200 ms per channel loads the printer's host.
- The safe state needs Moonraker reachable, so Klipper's `max_temp`, `verify_heater` and MCU watchdogs cover a network drop. Set `watchdog.on_loss: hold` to keep a print running through a drop.

## Hazard defaults

`medium`. Keep `confirm: confirm` on the hotend target and `home`.

## Sources

- Moonraker web API for printer.info, printer objects, gcode script, print control, emergency stop and JSON-RPC over WebSocket, https://moonraker.readthedocs.io/en/latest/web_api/
- Moonraker printer objects, https://moonraker.readthedocs.io/en/latest/printer_objects/
- Moonraker authorization, https://moonraker.readthedocs.io/en/latest/configuration/#authorization
- Klipper G-code reference for SET_HEATER_TEMPERATURE, SET_FAN_SPEED, TURN_OFF_HEATERS and M106, https://www.klipper3d.org/G-Codes.html
