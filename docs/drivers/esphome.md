# esphome driver

The `esphome` driver connects to ESPHome devices over the native API, the same protocol Home Assistant uses. Channels bind to the device's entities by object id, buttons become actions, and a write completes only when the device reports the new state.

| | |
|---|---|
| Driver name | `esphome` |
| Library | aioesphomeapi 46.22.0 (MIT), with protobuf, zeroconf, cryptography and noiseprotocol |
| Extra | `uv tool install --compile-bytecode "openhal-hub[esphome] @ git+https://github.com/sohan-bhat/OpenHAL"` |
| Hazard default | low |
| Safe state | from the device file only |
| Self-describe | yes, from the device's entity list |

## What it supports

| Entity | Channel | Type | Command |
|---|---|---|---|
| sensor | read | number, converted from `unit_of_measurement`, or string | none |
| text_sensor | read | string or enum | none |
| binary_sensor | read | bool | none |
| switch | write | bool | `switch_command` |
| light | write `<id>` | bool | `light_command` with state |
| light | write `<id>_brightness` | number, percent | `light_command` with brightness 0 to 1 |
| fan | write `<id>` | bool | `fan_command` with state |
| fan | write `<id>_speed` | number, percent | `fan_command` with `speed_level` out of `supported_speed_count` |
| fan | write `<id>_preset` | enum | `fan_command` with `preset_mode` |
| number | write | number, converted to `unit_of_measurement` | `number_command` |
| select | write | enum | `select_command` |
| button | action | no arguments | `button_command` |

A channel binds to the entity whose object id is the channel name, and a name ending in `_brightness`, `_speed` or `_preset` binds to the entity named by the rest of the name. `map: { object_id: pump_seconds, attribute: state }` sets both explicitly. Bindings are checked against the device's entity list on every connect, and a missing entity fails the connect with the list of entities the device has.

Because native API commands have no acknowledgement, the driver verifies each write by waiting up to `timeout` after the command for the state update that shows the new value. A device that doesn't report the new value fails the write, and a later read shows what the device really reports. Fan speeds snap to the nearest supported level, and the write's reading is the speed the fan really runs at.

`match.esphome` holds glob patterns for device info fields such as `name` and `model`, checked on connect.

## Setup

1. Install the extra with `uv tool install --compile-bytecode "openhal-hub[esphome] @ git+https://github.com/sohan-bhat/OpenHAL"`.
2. Give the node an `api:` block in its YAML. With `encryption: key: ...`, put the same base64 key in an environment variable such as `PLANT_PSK` and set `noise_psk_env`.
3. Prefer failsafes on the node itself, for example an `on_turn_on` automation that turns a pump off after a delay, or `api: reboot_timeout`. Because the hub can't detect those failsafes, mention them in `safe_state_note`.
4. Start from `openhal/drivers/esphome/examples/plant-waterer.hal.yaml` or from `describe()`.
5. Validate with `openhal file validate`, then confirm the limits by hand.

## Parameters

| Key | Default | Meaning |
|---|---|---|
| `host` | required | Host name, `.local` name or address |
| `port` | 6053 | Native API port |
| `noise_psk_env` | none | Environment variable that holds the API encryption key |
| `password_env` | none | Environment variable that holds the legacy API password |
| `timeout` | `5 s` | Handshake deadline, and how long a write waits for the new state |

## Example device file

```yaml
device: Plant waterer
id: plant
match: { mdns: _esphomelib._tcp, esphome: { name: "plant-*" } }
connect: { esphome: plant-node.local, port: 6053, noise_psk_env: PLANT_PSK }
read:
  soil_moisture: { unit: percent, every: 10 s, range: [0, 100] }
write:
  pump: { type: bool }
safe_state: { pump: false }
watchdog:
  max_duration:
    - when: "pump == true"
      for: 20 s
hazard: low
```

## Known limitations

- Covers, climate, locks, valves, media players, alarm panels and user-defined services are not mapped yet.
- RGB and white channels of lights are not exposed, only state and brightness.
- A node in deep sleep is unreachable most of the time, which the hub reports as disconnected.
- The native API allows one Home Assistant and several other clients. Commands from Home Assistant automations still reach the device and are outside OpenHAL's limits.

## Hazard defaults

The default hazard is `low`, because most nodes switch lights, fans, pumps and relays at low voltage, but a relay that switches mains to a heater needs `medium` or `high` in the device file.

## Sources

- ESPHome native API component, https://esphome.io/components/api.html (port, encryption, password, reboot_timeout)
- ESPHome api.proto, https://github.com/esphome/esphome/blob/dev/esphome/components/api/api.proto (message types, used through aioesphomeapi's generated classes)
- aioesphomeapi, https://github.com/esphome/aioesphomeapi (client API, MIT)
- ESPHome mDNS, https://esphome.io/components/mdns.html (`_esphomelib._tcp` discovery)
