# bambu driver

The bambu driver reads a Bambu Lab printer's status and pauses, resumes and stops prints through the printer's local MQTT broker, with paho-mqtt. The printer needs LAN-only mode and Developer Mode on.

## Local access status

Checked 2026-10-24.

- Since January 2025, Authorization Control firmware gates print starts, motion, temperature, fans, the AMS and calibration in cloud and normal LAN mode, from 01.08.03.00 on X1 and later on the P and A series. MQTT status stays readable.
- Developer Mode, opt-in at the printer on X1, P1, A1 and A1 mini, leaves MQTT, the live stream and FTP open on the local network. Bambu Lab gives no support for the mode, and the owner secures the network. Reports of the mode on H2D and P2S are unchecked.
- Section 3.1 of the Bambu Lab Terms of Use, quoted secondhand, restricts building software for Bambu Lab products without consent. In April 2026 Bambu Lab sent a cease-and-desist to an OrcaSlicer fork that reached Bambu Cloud posing as Bambu Studio. The owner reviewed this on 2026-10-25 and approved the driver.

The driver uses only the local MQTT interface and the LAN access code, never Bambu Cloud, Bambu Connect or an authorization bypass, and never poses as Bambu Studio. The driver sends only status requests and pause, resume, stop, speed level and chamber light commands. Without Developer Mode, commands fail with a hint and reads still work.

## Setup

```sh
uv tool install --compile-bytecode "halkit[bambu] @ git+https://github.com/sohan-bhat/OpenHAL"
```

1. On the printer, turn on LAN-only mode, then Developer Mode. Note the access code and serial number.
2. `export BAMBU_ACCESS_CODE=12345678` with your code.
3. Put the certificate fingerprint in `cert_sha256`, as in step 2 of docs/hardware-tests/bambu.md.

| Parameter | Default | Meaning |
|---|---|---|
| `host` | required | Printer address. `bambu: 192.168.1.50` is shorthand |
| `serial` | required | Serial number, which names the MQTT topics |
| `port` | `8883` | MQTT over TLS |
| `token_env` | `BAMBU_ACCESS_CODE` | Variable holding the access code |
| `cert_sha256` | none | Quoted SHA-256 certificate fingerprint, colons optional |
| `ca_env` | none | Instead of `cert_sha256`, a variable holding the path of Bambu Lab's CA certificate, checked with the serial |
| `timeout` | `5 s` | Login, status and acknowledgement deadline |
| `reply_wait` | `2 s` | Time allowed for a command reply |
| `safe_stop` | `stop` | What a hub stop sends, `stop` or `pause` |

The printer certificate names the serial and is signed by Bambu Lab's own CA, so ordinary TLS checks fail. The driver checks the pin before the access code leaves the hub.

## Channels

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
| `speed_level` | `spd_lvl` | enum of silent, standard, sport, ludicrous, settable |
| `chamber_light` | `lights_report` | bool, settable |

Other report fields read through a map such as `map: { field: cooling_fan_speed, scale: 6.6667 }`, with an optional `unit`. Actions `pause`, `resume` and `stop` take no arguments, and `map: { command: pause }` gives one another name. `discover()` listens for SSDP on UDP port 2021 and sends nothing. `describe()` suggests channels from the report.

## Behavior

- The driver requests one full report on connect and merges later reports, since P1 and A1 printers send only changes. Unsent fields read as no value. No polling.
- Commands go out at QoS 1 and are never queued. A missing broker acknowledgement drops the connection, so no command arrives late.
- A failure reply raises `DriverError` with the printer's reason, and some firmware sends no reply, so check `state`. Login and pin failures name what to check.

## Example

`openhal/drivers/bambu/examples/p1s-lan.hal.yaml` reads a P1S and pauses, resumes and stops, with stop confirmed.

## Limitations

- By design, no print start, upload, camera, AMS, G-code, temperature targets or motion.
- MQTT 3.1.1, one printer per file.
- Untested on real printers. The simulator follows community documentation of the report format.

## Hazard default and safe state

Medium. `safe_state_support` is `native`. A hub stop sends `stop` and the firmware ends the print, turns the heaters off and parks the head. A lost connection leaves the print running.

## Sources

- Bambu Lab, Firmware Update Introducing New Authorization Control System, 2025-01-16, https://blog.bambulab.com/firmware-update-introducing-new-authorization-control-system-2/
- Bambu Lab, Updates and Third-Party Integration with Bambu Connect, 2025-01-20, https://blog.bambulab.com/updates-and-third-party-integration-with-bambu-connect/
- Bambu Lab wiki, Third-party integration, not loaded here, https://wiki.bambulab.com/en/software/third-party-integration
- Bambu Lab Terms of Use, not loaded here, https://bambulab.com/en-us/policies/terms
- Consumer Rights Wiki, Bambu Lab Authorization Control System, https://consumerrights.wiki/w/Bambu_Lab_Authorization_Control_System
- Tom's Hardware on the April 2026 cease-and-desist, https://www.tomshardware.com/3d-printing/developer-re-enables-3d-printer-features-that-bambu-lab-disabled-firm-promptly-threatens-legal-action-orcaslicer-bambulab-project-now-shuttered
- OpenBambuAPI, community documentation of the MQTT messages, https://github.com/Doridian/OpenBambuAPI/blob/main/mqtt.md
- MQTT Version 3.1.1, OASIS Standard, https://docs.oasis-open.org/mqtt/mqtt/v3.1.1/os/mqtt-v3.1.1-os.html
