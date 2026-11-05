# octoprint driver

The `octoprint` driver connects to printers that OctoPrint controls, through OctoPrint's REST API with httpx. The driver reads temperatures, printer state and job progress, sets heater targets and the part fan, and runs homing and job control. Channel names match the moonraker driver where the API allows. `describe()` builds channels from the current printer profile.

## Supports

| Channel name | Kind | Endpoint |
|---|---|---|
| `state` | read, enum of standby, printing, paused, cancelling, error, offline | `GET /api/printer`, from `state.flags` |
| `state_text` | read, string | `state.text`, such as `Operational` |
| `extruder_temp`, `bed_temp`, `chamber_temp` | read, temperature | `temperature.tool0`, `bed`, `chamber` |
| `progress`, `filename` | read | `GET /api/job`, with `progress.completion` unknown without a job |
| `extruder_target`, `bed_target`, `chamber_target` | write, temperature | `POST /api/printer/tool`, `/bed`, `/chamber` with `command: target` |
| `fan_speed` | write, percent | `POST /api/printer/command` with `M106 P0 S0..255` |
| `home` with `axes` x, y, z, xy or all | action | `POST /api/printer/printhead` with `command: home` |
| `pause`, `resume`, `cancel` | action | `POST /api/job` |

Other names take a `map`. Reads use `{ heater: tool1 }`, `tool0` to `tool9`, `bed` or `chamber`, with `field: actual` or `field: target`. Writes use `{ heater: tool1 }` or `{ fan: 1 }`, and actions use `{ command: home }` and the like.

## Behavior

- The API key from `token_env` goes out as `X-Api-Key`. A missing variable fails the connect, and a 403 means a bad key.
- A 409, for a disconnected printer or a wrong state, fails the command and `state` reads `offline`.
- `health()` counts a non-operational printer as disconnected.
- `fan_speed` reads back the last value sent, since OctoPrint has no fan read, and unknown before the first write or after a failed one.
- `home` returns `queued`, since OctoPrint queues homing.

## Safe state

Every heater in the file, plus tool0 and the bed, gets target 0.

## Setup

1. Install with `uv tool install --compile-bytecode "halkit[octoprint] @ git+https://github.com/sohan-bhat/OpenHAL"`.
2. In OctoPrint under Settings, Application Keys, create a key for a user with the Control permission.
3. Run `export OCTOPRINT_API_KEY=...` where the hub runs.
4. Start from `openhal/drivers/octoprint/examples/prusa-mk3s-octopi.hal.yaml`.

| Key | Default | Meaning |
|---|---|---|
| `host` | required | OctoPrint host |
| `port` | 80 | HTTP port |
| `scheme` | `http` | `http` or `https` |
| `path` | empty | Sub path prefix such as `/octoprint` |
| `token_env` | `OCTOPRINT_API_KEY` | Variable holding the API key |
| `timeout` | `5 s` | Per request |

## Known limitations

- No file upload, selection or print start.
- Fan changes made on the printer's display don't show.
- Printer profiles hold no heater maxima, so `describe()` uses placeholders of 250, 100 and 60 degC. Lower the placeholders to the printer's real limits.
- The driver can't check the firmware's thermal protection.

## Hazard defaults

`medium`. Keep `confirm: confirm` on the hotend target and `home`.

## Sources

- OctoPrint REST API, printer operations, https://docs.octoprint.org/en/master/api/printer.html
- OctoPrint REST API, job operations, https://docs.octoprint.org/en/master/api/job.html
- OctoPrint REST API, version and printer profiles, https://docs.octoprint.org/en/master/api/version.html and https://docs.octoprint.org/en/master/api/printerprofiles.html
- OctoPrint API keys, https://docs.octoprint.org/en/master/bundledplugins/appkeys.html
