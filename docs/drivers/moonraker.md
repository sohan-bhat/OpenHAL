# moonraker driver

The `moonraker` driver talks to Klipper printers through Moonraker, the API server behind Mainsail and Fluidd. The driver reads printer objects (heaters, sensors, fans, print state, toolhead), sets heater targets and fan speeds with Klipper G-code, and runs homing and print control.

| | |
|---|---|
| Driver name | `moonraker` |
| Libraries | httpx 0.28.1 (BSD-3-Clause), websockets 17.3 (BSD-3-Clause) |
| Extra | `uv tool install --compile-bytecode "openhal-hub[moonraker] @ git+https://github.com/sohan-bhat/OpenHAL"` |
| Hazard default | medium |
| Safe state | native. `TURN_OFF_HEATERS`. `printer.emergency_stop` only when `emergency_stop_on_stop` is true |
| Self-describe | yes, from `printer.objects.list` and the `configfile` object |

## What it supports

| Channel name | Kind | Printer object and field |
|---|---|---|
| `state` | read, enum | `print_stats.state` (standby, printing, paused, complete, cancelled, error) |
| `klippy_state`, `filename` | read, string | `webhooks.state`, `print_stats.filename` |
| `extruder_temp`, `bed_temp`, `chamber_temp` | read, temperature | `extruder`, `heater_bed`, `temperature_sensor chamber` |
| `progress` | read, percent | `virtual_sdcard.progress` times 100 |
| `position_x`, `position_y`, `position_z`, `homed_axes` | read | `toolhead.position`, `toolhead.homed_axes` |
| `extruder_target`, `bed_target` | write, temperature | `SET_HEATER_TEMPERATURE HEATER=... TARGET=...`, read back from `target` |
| `fan_speed` | write, percent | `M106 S0..255`, read back from `fan.speed` |
| `home` (arg `axes` x, y, z, xy or all) | action | `G28` |
| `pause`, `resume`, `cancel` | action | `printer.print.pause`, `resume`, `cancel` |

Other names need a `map`.

| Map | Meaning |
|---|---|
| `{ object: "temperature_sensor chamber", field: temperature }` | Any object and field. `index` picks a list element, `scale` multiplies |
| `{ heater: enclosure }` | A `heater_generic` (or `extruder1`, `heater_bed`) target |
| `{ fan: exhaust }` | A `fan_generic` speed, set with `SET_FAN_SPEED` |
| `{ command: home }` | Run `home`, `pause`, `resume` or `cancel` under another action name |

Temperatures are degC on the wire and converted to the channel unit both ways. Fan percent maps to `M106 S` as `round(percent * 255 / 100)` and to `SET_FAN_SPEED SPEED` as `percent / 100`.

The driver deliberately has no raw G-code action.

## How the protocol is handled

- `transport: http` polls one object per read, while `transport: websocket` subscribes to every object the file uses with `printer.objects.subscribe`, keeps a cache that `notify_status_update` refreshes, and reads from the cache without a round trip.
- An API key, when Moonraker requires one, is read from the environment variable named in `token_env` and sent as `X-Api-Key`.
- G-code requests return when Klipper has finished the command. Because the hub's driver timeout is 10 s, `home` waits up to `action_wait`, then returns `started` and finishes in the background with a deadline of 300 s.
- Klipper refuses heater targets above `max_temp` in printer.cfg, and that error, like every other Klipper or Moonraker error, fails the command with the original message.
- `health()` reads `printer.info` (or the subscribed `webhooks` object). Anything but `ready` reports the printer as disconnected with Klipper's own message, for example an MCU shutdown.
- `match.moonraker` is checked against `printer.info` on connect, with glob patterns, so a file can't drive the wrong printer.

## Setup

1. Install the extra with `uv tool install --compile-bytecode "openhal-hub[moonraker] @ git+https://github.com/sohan-bhat/OpenHAL"`.
2. If Moonraker has `[authorization]` with API keys, put the key in an environment variable such as `MOONRAKER_API_KEY` and set `token_env`. Otherwise add the hub's address to `trusted_clients`.
3. Start from `openhal/drivers/moonraker/examples/voron-2-4.hal.yaml`, or from the driver's `describe()` output.
4. Validate with `openhal file validate`, then confirm the limits by hand.

## Parameters

| Key | Default | Meaning |
|---|---|---|
| `host` | required | Moonraker host name or address |
| `port` | 7125 | Moonraker port |
| `scheme` | `http` | `http` or `https` (and `ws` or `wss` for the WebSocket) |
| `transport` | `http` | `http` to poll, `websocket` to subscribe |
| `token_env` | none | Environment variable that holds the API key |
| `timeout` | `5 s` | Deadline for each request |
| `action_wait` | `8 s` | How long `home` waits before returning `started`. At most 9 s |
| `emergency_stop_on_stop` | false | Also call `printer.emergency_stop` during the safe state |

## Example device file

```yaml
device: { name: Voron 2.4, manufacturer: Voron Design }
id: voron
match: { moonraker: { hostname: "voron*" } }
connect: { moonraker: voron.local, port: 7125, transport: websocket }
read:
  state: { type: enum, values: [standby, printing, paused, complete, cancelled, error], every: 1 s }
  extruder_temp: { unit: degC, every: 1 s, range: [0, 320] }
  bed_temp: { unit: degC, every: 1 s, range: [0, 130] }
write:
  extruder_target: { unit: degC, min: 0, max: 260, max_change_per_s: 50, confirm: confirm }
  bed_target: { unit: degC, min: 0, max: 110, max_change_per_s: 20 }
actions:
  home: { args: { axes: { type: enum, values: [x, y, z, xy, all] } }, require: ["state != printing"] }
safe_state:
  - { extruder_target: 0, bed_target: 0 }
hazard: medium
```

## Known limitations

- File uploads and starting prints are not exposed.
- `exclude_object`, macros and other Klipper commands need their own driver support, because the driver deliberately has no raw G-code action.
- With `transport: http` each read is one request, so poll intervals under about 200 ms per channel will load the printer's host.
- Because the safe state needs Moonraker to be reachable, Klipper's own `max_temp`, `verify_heater` and MCU watchdogs remain the protection when the network is down. Set `watchdog.on_loss: hold` when you'd rather let a print continue through a network drop.

## Hazard defaults

The default hazard is `medium`, because heaters and moving axes can burn or pinch, so keep `confirm: confirm` on the hotend target and on `home`.

## Sources

- Moonraker web API, https://moonraker.readthedocs.io/en/latest/web_api/ (printer.info, printer.objects.list, query and subscribe, gcode script, print control, emergency stop, JSON-RPC over WebSocket)
- Moonraker printer objects, https://moonraker.readthedocs.io/en/latest/printer_objects/
- Moonraker authorization, https://moonraker.readthedocs.io/en/latest/configuration/#authorization
- Klipper G-code reference, https://www.klipper3d.org/G-Codes.html (SET_HEATER_TEMPERATURE, SET_FAN_SPEED, TURN_OFF_HEATERS, M106)
