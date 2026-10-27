# octoprint driver

The `octoprint` driver talks to printers that OctoPrint controls, through OctoPrint's REST API. The driver reads temperatures, the printer state and job progress, sets heater targets and the part fan, and runs homing and job control. Channel names match the moonraker driver where the API allows it.

| | |
|---|---|
| Driver name | `octoprint` |
| Library | httpx 0.28.1 (BSD-3-Clause) |
| Extra | `uv tool install --compile-bytecode "openhal-hub[octoprint] @ git+https://github.com/sohan-bhat/OpenHAL"` |
| Hazard default | medium |
| Safe state | native. Every heater in the file, plus tool0 and the bed, gets target 0 |
| Self-describe | yes, from the current printer profile |

## What it supports

| Channel name | Kind | Endpoint |
|---|---|---|
| `state` | read, enum (standby, printing, paused, cancelling, error, offline) | `GET /api/printer`, from `state.flags` |
| `state_text` | read, string | `state.text`, for example `Operational` |
| `extruder_temp`, `bed_temp`, `chamber_temp` | read, temperature | `temperature.tool0`, `bed`, `chamber` |
| `progress`, `filename` | read | `GET /api/job` (`progress.completion`, unknown with no job) |
| `extruder_target`, `bed_target`, `chamber_target` | write, temperature | `POST /api/printer/tool`, `/bed`, `/chamber` with `command: target` |
| `fan_speed` | write, percent | `POST /api/printer/command` with `M106 P0 S0..255` |
| `home` (arg `axes` x, y, z, xy or all) | action | `POST /api/printer/printhead` with `command: home` |
| `pause`, `resume`, `cancel` | action | `POST /api/job` |

Other names need a `map`, such as `{ heater: tool1 }` (or `tool0` to `tool9`, `bed`, `chamber`) with `field: actual` or `field: target` for reads, and `{ heater: tool1 }` or `{ fan: 1 }` for writes. Actions take `{ command: home }` and so on under another name.

Temperatures are degC on the wire and converted to the channel unit both ways.

## How the protocol is handled

- The API key comes from the environment variable named in `token_env` (default `OCTOPRINT_API_KEY`) and is sent as `X-Api-Key`. A missing variable fails the connect before any request, and a 403 means the key was refused.
- OctoPrint returns 409 when the printer isn't connected or the operation doesn't fit the current state. The driver turns that into an error that says the printer can't do this now, and `state` reads `offline`.
- `health()` reads `/api/printer`, and a printer that isn't operational counts as disconnected.
- OctoPrint has no fan read, so `fan_speed` reads back the last value this driver sent, and unknown before the first write or after a failed one.
- Homing is queued by OctoPrint and the request returns at once, so the action returns `queued`.

## Setup

1. Install the extra with `uv tool install --compile-bytecode "openhal-hub[octoprint] @ git+https://github.com/sohan-bhat/OpenHAL"`.
2. In OctoPrint, open Settings, Application Keys, and create a key for OpenHAL. A user with the Control permission is enough.
3. Export the key, for example `export OCTOPRINT_API_KEY=...`, in the environment the hub runs in.
4. Start from `openhal/drivers/octoprint/examples/prusa-mk3s-octopi.hal.yaml`.
5. Validate with `openhal file validate`, then confirm the limits by hand.

## Parameters

| Key | Default | Meaning |
|---|---|---|
| `host` | required | OctoPrint host name or address |
| `port` | 80 | HTTP port |
| `scheme` | `http` | `http` or `https` |
| `path` | empty | Prefix when OctoPrint runs under a sub path, for example `/octoprint` |
| `token_env` | `OCTOPRINT_API_KEY` | Environment variable that holds the API key |
| `timeout` | `5 s` | Deadline for each request |

## Example device file

```yaml
device: { name: Prusa MK3S, manufacturer: Prusa Research }
id: mk3s
connect: { octoprint: octopi.local, token_env: OCTOPRINT_API_KEY }
read:
  state: { type: enum, values: [standby, printing, paused, cancelling, error, offline], every: 2 s }
  extruder_temp: { unit: degC, every: 2 s }
  bed_temp: { unit: degC, every: 2 s }
write:
  extruder_target: { unit: degC, min: 0, max: 260, max_change_per_s: 50, confirm: confirm }
  bed_target: { unit: degC, min: 0, max: 100, max_change_per_s: 20 }
  fan_speed: { unit: percent, min: 0, max: 100 }
actions:
  home: { args: { axes: { type: enum, values: [x, y, z, xy, all] } }, require: ["state != printing"] }
safe_state:
  - { extruder_target: 0, bed_target: 0, fan_speed: 0 }
hazard: medium
```

## Known limitations

- File upload, selection and starting prints are not exposed.
- The fan speed can't be read from the printer, and a fan change made on the printer's own display isn't seen.
- Because printer profiles don't record heater maxima, proposals from `describe()` use placeholder heater maxima (250, 100 and 60 degC), so lower the maxima to your printer's real limits.
- The driver can't check the printer's firmware thermal protection, which remains the last line of defense.

## Hazard defaults

The default hazard is `medium`, because heaters and moving axes can burn or pinch, so keep `confirm: confirm` on the hotend target and on `home`.

## Sources

- OctoPrint REST API, printer operations, https://docs.octoprint.org/en/master/api/printer.html
- OctoPrint REST API, job operations, https://docs.octoprint.org/en/master/api/job.html
- OctoPrint REST API, version and printer profiles, https://docs.octoprint.org/en/master/api/version.html and https://docs.octoprint.org/en/master/api/printerprofiles.html
- OctoPrint API keys, https://docs.octoprint.org/en/master/bundledplugins/appkeys.html
