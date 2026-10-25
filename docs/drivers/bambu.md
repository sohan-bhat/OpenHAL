# bambu driver

The bambu driver reads a Bambu Lab printer's status and pauses, resumes and stops prints over the printer's own MQTT broker on the local network. It needs the printer in LAN-only mode with Developer Mode on. It uses paho-mqtt, the same client as the mqtt driver.

## Local access status

Checked on 2026-10-24. Read this before you connect a printer.

- In January 2025 Bambu Lab added Authorization Control to its firmware. Starting a print and controlling motion, temperature, fans, the AMS and calibration now need authorization in cloud mode and in normal LAN mode. Status reports over MQTT stay readable. X1 printers got it first, from firmware 01.08.03.00, and the P and A series followed.
- Bambu Lab's follow-up post describes Developer Mode, an opt-in setting for X1, P1, A1 and A1 mini printers. It must be turned on at the printer, leaves MQTT, the live stream and FTP open on the local network, and makes the owner responsible for securing that network. Bambu Lab says it won't give customer support for this mode. Later guides report Developer Mode on newer models too, but this wasn't checked on an H2D or P2S.
- Bambu Lab's Terms of Use restrict using its technology to develop software associated with its products without consent (section 3.1, quoted secondhand because the terms page didn't load here). In April 2026 Bambu Lab sent a cease-and-desist letter to the maintainer of an OrcaSlicer fork that reached Bambu Cloud by presenting itself as Bambu Studio. The owner reviewed this on 2026-10-25 and approved shipping the driver.

What this driver does with that.

- It talks only to the printer on the local network, only through the MQTT interface Developer Mode leaves open, and only with the LAN access code shown on the printer's screen.
- It never contacts Bambu Cloud, never uses Bambu Connect or its keys, never presents itself as Bambu Studio and never tries to get around authorization.
- It sends only status requests and the pause, resume, stop, speed level and chamber light commands. It doesn't start prints, upload files, send G-code, change temperatures or move axes.
- Without Developer Mode the printer refuses the commands, and the driver reports the refusal with a hint to turn the mode on. Reads keep working.

## What it supports

- Reads of the print state, nozzle, bed and chamber temperatures and targets, progress, time left, the current and total count from `layer_num` and `total_layer_num`, the job name, the error code and the Wi-Fi signal, plus any other report field through a map.
- The speed level (silent, standard, sport, ludicrous) and the chamber light as control channels.
- Pause, resume and stop as actions.
- Native safe state. A hub stop sends `stop`, or `pause` with `safe_stop: pause`.
- `discover()` listens for the printers' own SSDP announcements on UDP port 2021 and sends nothing.
- `describe()` proposes channels from the printer's report.

## Setup

```sh
uv pip install 'openhal-hub[bambu]'
```

1. On the printer's screen, open the network settings, turn on LAN-only mode, then turn on Developer Mode. Note the access code and the serial number shown there.
2. Put the access code in an environment variable, `export BAMBU_ACCESS_CODE=12345678`.
3. Read the printer certificate's fingerprint and put it in `cert_sha256`, as in step 2 of docs/hardware-tests/bambu.md.

## Parameters

| Parameter | Default | Meaning |
|---|---|---|
| `host` | required | The printer's address. The shorthand `bambu: 192.168.1.50` sets it |
| `serial` | required | The printer's serial number, which names its MQTT topics |
| `port` | `8883` | MQTT over TLS |
| `token_env` | `BAMBU_ACCESS_CODE` | The environment variable that holds the LAN access code |
| `cert_sha256` | none | The SHA-256 fingerprint of the printer's certificate, quoted, with or without colons |
| `ca_file` | none | Instead of `cert_sha256`, Bambu Lab's authority certificate. The driver then checks the certificate names the serial |
| `timeout` | `5 s` | Login, status and acknowledgement deadline |
| `reply_wait` | `2 s` | How long to wait for the printer's reply to a command |
| `safe_stop` | `stop` | What a hub stop sends, `stop` or `pause` |

The printer's certificate names its serial number rather than its address and is signed by Bambu Lab's own authority, so ordinary TLS checks fail. The driver checks the fingerprint, or the authority and the serial, before the access code leaves the hub.

## Channels

Channels are named after what they read. A map can read any other field of the report, `map: { field: cooling_fan_speed, scale: 6.6667 }` for example, with an optional `unit` the field is in.

| Channel | Report field | Type and unit |
|---|---|---|
| `state` | `gcode_state` | enum of idle, prepare, slicing, running, pause, finish, failed |
| `nozzle_temp`, `nozzle_target` | `nozzle_temper`, `nozzle_target_temper` | degC |
| `bed_temp`, `bed_target` | `bed_temper`, `bed_target_temper` | degC |
| `chamber_temp` | `chamber_temper` | degC |
| `progress` | `mc_percent` | percent |
| `remaining` | `mc_remaining_time` | min |
| `layer`, `total_layers` | `layer_num`, `total_layer_num` | dimensionless |
| `job` | `subtask_name` | string |
| `print_error` | `print_error` | dimensionless |
| `wifi_signal` | `wifi_signal` | string |
| `speed_level` | `spd_lvl` | enum, control channel |
| `chamber_light` | `lights_report` | bool, control channel |

Actions are named `pause`, `resume` and `stop`, or map to one with `map: { command: pause }`. They take no arguments.

## How reads and commands behave

- After connecting, the driver asks for a full report once. X1 printers then send full reports and P1 and A1 printers send only what changed, so the driver merges every report into one state. A field the printer hasn't sent reads as no value.
- Commands go out at QoS 1 and wait for the broker's acknowledgement. If the printer answers with a result, a failure becomes a `DriverError` with the printer's reason. Some firmware doesn't answer every command, so a missing answer is not an error. Read `state` to see what happened.
- Commands are never queued. Without an acknowledgement the driver drops the connection, so a command can't arrive late.
- The driver doesn't poll. Bambu Lab printers push their state, and P1 printers are known to struggle with frequent full status requests.

## Example

`openhal/drivers/bambu/examples/p1s-lan.hal.yaml` reads a P1S and lets pause, resume and stop through, with stop needing a confirmation.

## Errors

- A missing access code variable, a certificate that doesn't match the pin, a refused login and a printer that sends no report for the serial number raise `DriverError` that says what to check.
- A command the printer refuses raises `DriverError` with its reason. A refusal about verification adds the hint to turn on Developer Mode.
- A report value that isn't the channel's type raises `DriverError` on read.

## Limitations

- No print start, file upload, camera, AMS control, G-code, temperature targets or motion. These are left out on purpose.
- MQTT 3.1.1 only, and one printer per device file.
- Untested on real printers so far. The simulator follows the community documentation of the report format, which Bambu Lab doesn't publish.

## Hazard default and safe state

The default hazard is medium, because a printer has heaters and moving parts. `safe_state_support` is `native`. A hub stop sends `stop`, and the firmware ends the print, turns the heaters off and parks the head. The printer handles a lost connection on its own and keeps printing.

## Sources

- Bambu Lab, Firmware Update Introducing New Authorization Control System, 2025-01-16, https://blog.bambulab.com/firmware-update-introducing-new-authorization-control-system-2/
- Bambu Lab, Updates and Third-Party Integration with Bambu Connect, 2025-01-20, https://blog.bambulab.com/updates-and-third-party-integration-with-bambu-connect/
- Bambu Lab wiki, Third-party integration, https://wiki.bambulab.com/en/software/third-party-integration (not loaded here, check it directly)
- Bambu Lab Terms of Use, https://bambulab.com/en-us/policies/terms (not loaded here, section 3.1 quoted secondhand)
- Consumer Rights Wiki, Bambu Lab Authorization Control System, https://consumerrights.wiki/w/Bambu_Lab_Authorization_Control_System
- Tom's Hardware on the April 2026 cease-and-desist, https://www.tomshardware.com/3d-printing/developer-re-enables-3d-printer-features-that-bambu-lab-disabled-firm-promptly-threatens-legal-action-orcaslicer-bambulab-project-now-shuttered
- OpenBambuAPI, community documentation of the MQTT messages, https://github.com/Doridian/OpenBambuAPI/blob/main/mqtt.md
- MQTT Version 3.1.1, OASIS Standard, https://docs.oasis-open.org/mqtt/mqtt/v3.1.1/os/mqtt-v3.1.1-os.html
