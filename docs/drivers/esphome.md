# esphome driver

The `esphome` driver connects to ESPHome devices over the native API through aioesphomeapi 46.22.0, MIT. Channels bind to entities by object id, buttons become actions, and `describe()` builds channels from the entity list.

## Supports

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

A channel binds to the entity whose object id is the channel name, minus any `_brightness`, `_speed` or `_preset` suffix, or to `map: { object_id: pump_seconds, attribute: state }`. A missing entity fails the connect with the list of entities on the device. A write succeeds only when the device reports the new state within `timeout`, and fan speeds snap to the nearest level. `match.esphome` holds glob patterns for device info fields such as `name` and `model`.

## Setup

1. Install with `uv tool install --compile-bytecode "halkit[esphome] @ git+https://github.com/sohan-bhat/OpenHAL"`.
2. Add an `api:` block to the node. With `encryption: key: ...`, put the key in a variable such as `PLANT_PSK` and set `noise_psk_env`.
3. Add node failsafes such as an `on_turn_on` pump timer or `api: reboot_timeout`, and list the failsafes in `safe_state_note`.
4. Start from `openhal/drivers/esphome/examples/plant-waterer.hal.yaml` or `describe()`.

| Key | Default | Meaning |
|---|---|---|
| `host` | required | Host name, `.local` name or address |
| `port` | 6053 | Native API port |
| `noise_psk_env` | none | Variable holding the API encryption key |
| `password_env` | none | Variable holding the legacy API password |
| `timeout` | `5 s` | Handshake deadline and write confirmation window |

## Known limitations

- No covers, climate, locks, valves, media players, alarm panels or user-defined services yet.
- Lights expose state and brightness only.
- A deep-sleeping node reads as disconnected most of the time.
- Home Assistant automations on the same node bypass OpenHAL's limits.

## Hazard defaults

`low`, with `safe_state` from the device file only. A relay switching mains to a heater needs `medium` or `high`.

## Sources

- ESPHome native API component for port, encryption, password and reboot_timeout, https://esphome.io/components/api.html
- ESPHome api.proto message types, https://github.com/esphome/esphome/blob/dev/esphome/components/api/api.proto
- aioesphomeapi client, MIT, https://github.com/esphome/aioesphomeapi
- ESPHome mDNS and `_esphomelib._tcp` discovery, https://esphome.io/components/mdns.html
