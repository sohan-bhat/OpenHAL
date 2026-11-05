# homeassistant driver

The `homeassistant` driver exposes the Home Assistant entities a device file selects as one OpenHAL device, under the safety kernel's limits. The rest of Home Assistant stays out of reach.

## Which entities are exposed

- `entity` names one entity and `entities` lists several, and every `map.entity` must be one of the selected entities. With neither key, the entities in channel maps are the selection.
- Every selected entity must match the `match.homeassistant` glob.
- Home Assistant's own `min`, `max` and `step` appear only as `describe()` suggestions.

## Channel roles

A channel's role comes from the entity's domain and the channel name or `map.attribute`. With several entities, end each channel name with the role, such as `lamp_brightness`.

| Domain | Channel name or attribute | Type | Reads | Writes |
|---|---|---|---|---|
| light | `power` or any other name | bool | state on or off | `light.turn_on`, `light.turn_off` |
| light | `brightness` | number, percent | `brightness` 0 to 255, 0 % when off | `light.turn_on` with `brightness_pct` |
| light | `color_temp` or `color_temp_kelvin` | number, K | `color_temp_kelvin` | `light.turn_on` with `color_temp_kelvin` |
| switch, input_boolean | `power` | bool | state | `turn_on`, `turn_off` |
| fan | `power` | bool | state | `fan.turn_on`, `fan.turn_off` |
| fan | `speed` or `percentage` | number, percent | `percentage` | `fan.set_percentage` |
| fan | `preset` or `preset_mode` | enum | `preset_mode` | `fan.set_preset_mode` |
| number, input_number | `value` | number | state, converted from `unit_of_measurement` | `set_value`, converted back |
| select, input_select | `option` | enum | state | `select_option` |
| sensor | any | number or string | state, converted from `unit_of_measurement` | read-only |
| binary_sensor | any | bool | state | read-only |
| any | `map: { attribute: name }` | any | that attribute | read-only |

Home Assistant units convert to the channel unit. An `unavailable` entity fails reads and marks the device disconnected, and `unknown` reads as no value.

## Transports

`rest`, the default, sends `GET /api/states/<entity_id>` per read and `POST /api/services/<domain>/<service>` per write. `websocket` reads from a `subscribe_entities` cache and writes with `call_service`.

## Setup

1. Install with `uv tool install --compile-bytecode "halkit[homeassistant] @ git+https://github.com/sohan-bhat/OpenHAL"`.
2. Create a long-lived access token under your profile, Security, ideally for a non-admin user, and `export HA_TOKEN=...` where the hub runs.
3. Start from `openhal/drivers/homeassistant/examples/office-climate.hal.yaml` or `describe()`.

| Key | Default | Meaning |
|---|---|---|
| `host` | required | Host name or address |
| `port` | 8123 | Port |
| `scheme` | `http` | `http` or `https`, and `ws` or `wss` |
| `token_env` | `HA_TOKEN` | Variable holding the access token |
| `entity` | none | The one selected entity |
| `entities` | none | The selected entities, up to 64 |
| `transport` | `rest` | `rest` or `websocket` |
| `timeout` | `5 s` | Per request |

## Known limitations

- Climate, cover, lock, vacuum, media player and other domains are read-only through `map.attribute` for now.
- `health()` follows Home Assistant's availability flags.
- Home Assistant automations and wall switches bypass OpenHAL's limits.

## Hazard defaults

`low`, with `safe_state` from the device file only. A switch powering a heater or a pump needs `medium` or `high`.

## Sources

- Home Assistant REST API, https://developers.home-assistant.io/docs/api/rest/
- Home Assistant WebSocket API for auth, call_service and subscribe_entities, https://developers.home-assistant.io/docs/api/websocket/
- Entity attributes and services, https://developers.home-assistant.io/docs/core/entity/light/ and the fan, number and select pages beside the light page
- Long-lived access tokens, https://www.home-assistant.io/docs/authentication/
