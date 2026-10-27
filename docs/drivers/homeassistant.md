# homeassistant driver

The `homeassistant` driver is a bridge. The driver exposes a few Home Assistant entities that the device file selects as one OpenHAL device, so the safety kernel's limits, interlocks and confirmations apply to them. Everything else in the Home Assistant instance stays out of reach.

| | |
|---|---|
| Driver name | `homeassistant` |
| Libraries | httpx 0.28.1 (BSD-3-Clause), websockets 17.3 (BSD-3-Clause) |
| Extra | `uv tool install --compile-bytecode "openhal-hub[homeassistant] @ git+https://github.com/sohan-bhat/OpenHAL"` |
| Hazard default | low (set the file's `hazard` to what the entities really drive) |
| Safe state | from the device file only |
| Self-describe | yes, the selected entities with their units and Home Assistant's own limits as suggestions |

## Which entities are exposed

- `entity` names one entity, or `entities` lists several. A channel's `map.entity` must be one of them, otherwise the file is refused when it loads.
- With neither, the entities named in channel maps are the selection.
- `match.homeassistant` is a glob, and every selected entity must match it.
- The device file's limits apply even when Home Assistant has its own. A `number` entity's `min`, `max` and `step` only appear in `describe()` as `suggested` values.

## Channel roles

A channel's role comes from the entity's domain and from the channel name or `map.attribute`. With one selected entity no map is needed. With several, give `map.entity` and name the channel after the role, or end its name with the role (`lamp_brightness`).

| Domain | Channel name or attribute | Type | Reads | Writes |
|---|---|---|---|---|
| light | `power` (any other name) | bool | state on or off | `light.turn_on`, `light.turn_off` |
| light | `brightness` | number, percent | `brightness` 0 to 255, 0 % when off | `light.turn_on` with `brightness_pct` |
| light | `color_temp` (`color_temp_kelvin`) | number, K | `color_temp_kelvin` | `light.turn_on` with `color_temp_kelvin` |
| switch, input_boolean | `power` | bool | state | `turn_on`, `turn_off` |
| fan | `power` | bool | state | `fan.turn_on`, `fan.turn_off` |
| fan | `speed` (`percentage`) | number, percent | `percentage` | `fan.set_percentage` |
| fan | `preset` (`preset_mode`) | enum | `preset_mode` | `fan.set_preset_mode` |
| number, input_number | `value` | number | state, converted from `unit_of_measurement` | `set_value`, converted to it |
| select, input_select | `option` | enum | state | `select_option` |
| sensor | any | number or string | state, converted from `unit_of_measurement` | read-only |
| binary_sensor | any | bool | state | read-only |
| any | `map: { attribute: name }` | any | that attribute | read-only |

Units from Home Assistant (`°C`, `°F`, `%`, `kWh`, `hPa` and the rest) are converted to the channel's unit. A sensor whose unit can't convert fails its read with a clear message.

An entity in state `unavailable` fails its reads, and `health()` reports the device disconnected. `unknown` reads as no value.

## Transports

- `transport: rest` (the default). `GET /api/states/<entity_id>` per read and `POST /api/services/<domain>/<service>` per write.
- `transport: websocket`. The driver authenticates, sends `subscribe_entities` for the selected entities only and keeps their states in a cache, so reads cost no round trip. Writes use `call_service`.

Both send the long-lived access token from the environment variable named in `token_env` (default `HA_TOKEN`).

## Setup

1. Install the extra with `uv tool install --compile-bytecode "openhal-hub[homeassistant] @ git+https://github.com/sohan-bhat/OpenHAL"`.
2. In Home Assistant, open your profile, Security, and create a long-lived access token. A non-admin user that can see only the needed entities is the safest choice.
3. Export it, for example `export HA_TOKEN=...`, where the hub runs.
4. Start from `openhal/drivers/homeassistant/examples/office-climate.hal.yaml`, or from `describe()`.
5. Validate with `openhal file validate`, then confirm the limits by hand.

## Parameters

| Key | Default | Meaning |
|---|---|---|
| `host` | required | Home Assistant host name or address |
| `port` | 8123 | Port |
| `scheme` | `http` | `http` or `https` (and `ws` or `wss`) |
| `token_env` | `HA_TOKEN` | Environment variable that holds the access token |
| `entity` | none | The one selected entity |
| `entities` | none | The selected entities, up to 64 |
| `transport` | `rest` | `rest` or `websocket` |
| `timeout` | `5 s` | Deadline for each request |

## Example device file

```yaml
device: Desk lamp
id: desk-lamp
match: { homeassistant: light.desk_lamp }
connect: { homeassistant: homeassistant.local, port: 8123, token_env: HA_TOKEN, entity: light.desk_lamp }
write:
  power: { type: bool }
  brightness: { unit: percent, min: 1, max: 100, step: 1 }
safe_state: { power: false }
hazard: low
```

## Known limitations

- Climate, cover, lock, vacuum, media player and other domains are read-only through `map.attribute` for now. Locks and covers move things and need their own careful mapping.
- The driver sees only what Home Assistant reports. An integration that marks a device available while it is not will fool the health check.
- Home Assistant automations can still change the same entities. OpenHAL limits only what goes through OpenHAL.
- Rate limits and interlocks act on OpenHAL commands. A human at a wall switch bypasses them, as it should.

## Hazard defaults

`low`. Lights, fans and sensors are the usual case. A switch that powers a heater or a pump deserves `medium` or `high` in the device file.

## Sources

- Home Assistant REST API, https://developers.home-assistant.io/docs/api/rest/
- Home Assistant WebSocket API, https://developers.home-assistant.io/docs/api/websocket/ (auth, call_service, subscribe_entities and its compressed state format)
- Entity attributes and services, https://developers.home-assistant.io/docs/core/entity/light/ and the fan, number and select pages next to it
- Long-lived access tokens, https://www.home-assistant.io/docs/authentication/
