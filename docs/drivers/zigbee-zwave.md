# zigbee-zwave driver

The zigbee-zwave driver reaches Zigbee devices through Zigbee2MQTT and Z-Wave nodes through zwave-js-server. The URL picks the bridge, `mqtt://` or `ws://`, and each device file names one device. The homeassistant driver reaches the same devices when Home Assistant owns the stick.

## Supports

- Every Zigbee2MQTT `exposes` feature, nested ones included, and every zwave-js value by command class, endpoint, property and property key, with units and states from the metadata.
- A Z-Wave channel on `currentValue` is set through `targetValue`.
- Connect checks each channel's existence, access, type and unit.
- `describe()` suggests channels from the bridge, with the bridge's limits as suggestions.

## Setup

```sh
uv tool install --compile-bytecode "halkit[zigbee-zwave] @ git+https://github.com/sohan-bhat/OpenHAL"
```

Zigbee2MQTT must publish to a broker the hub can reach, with availability on. Z-Wave needs zwave-js-server or Z-Wave JS UI with the WebSocket server on, usually port 3000.

| Parameter | Default | Meaning |
|---|---|---|
| `url` | required | `mqtt://host:1883` or `mqtts://host:8883` for Zigbee2MQTT, `ws://host:3000` or `wss://` for zwave-js-server. `zigbee-zwave: "mqtt://..."` is shorthand |
| `friendly_name` | required for Zigbee | Zigbee2MQTT friendly name |
| `node` | required for Z-Wave | Node id |
| `base_topic` | `zigbee2mqtt` | Zigbee2MQTT base topic |
| `username`, `token_env` | none | MQTT user and the variable holding the password |
| `ca_env` | none | Variable holding a CA bundle path for `mqtts://` |
| `timeout` | `5 s` | Connect and acknowledgement deadline |

## Channel maps

```yaml
read:
  temperature: { unit: degC }
  power: { unit: W, map: { command_class: 50, property: value, property_key: 66049 } }
write:
  brightness: { unit: percent, min: 1, max: 100, map: { scale: 0.3937 } }
  relay: { type: bool, map: { command_class: 37, property: currentValue } }
```

| Key | Bridge | Meaning |
|---|---|---|
| `property` | both | Zigbee exposed property, by default the channel name, with dots for nested values such as `color.x`. For Z-Wave, the value's property |
| `command_class` | Z-Wave | Command class number |
| `endpoint` | Z-Wave | Endpoint, default `0` |
| `property_key` | Z-Wave | Property key for meters and notifications |
| `target` | Z-Wave | Property to set, by default `targetValue` when `property` is `currentValue` |
| `scale`, `offset` | both | value = bridge value × scale + offset |
| `unit` | both | Bridge unit when the bridge reports none |

Bridge units convert to the channel unit, such as `°C` to `degF`, and stepped values round to a whole step before sending.

## Behavior

- Reads return the bridge's last push. Battery sensors may read as none until the sensor wakes.
- A command returns on the broker acknowledgement or the `node.set_value` result. Commands are never queued, and a lost MQTT acknowledgement drops the connection.
- Connect failures name what to check. Failed commands raise `DriverError` with the bridge's reason, and unanswered ones `TimeoutError`.
- Health follows the MQTT session, bridge state and availability, or the WebSocket and node status.

## Examples

- `ikea-bulb-zigbee2mqtt.hal.yaml` switches and dims an IKEA bulb through Zigbee2MQTT.
- `zooz-plug-zwave.hal.yaml` reads power and energy from a Zooz plug and switches the plug through zwave-js-server, with a watchdog that turns the plug off after two hours.

## Limitations

- No actions, scenes, groups, pairing, OTA updates or network management.
- zwave-js-server schema 40 at most, which newer servers accept.
- Non-linear conversions such as mired to kelvin stay raw.

## Hazard default and safe state

Low, but match the hazard to what a plug switches. `safe_state_support` is `file`. The device's own power-on and timeout settings are the real fallback.

## Sources

- Zigbee2MQTT MQTT topics and messages, https://www.zigbee2mqtt.io/guide/usage/mqtt_topics_and_messages.html
- Zigbee2MQTT exposes, https://www.zigbee2mqtt.io/guide/usage/exposes.html
- zwave-js-server API, https://github.com/zwave-js/zwave-js-server
- zwave-js value IDs, https://zwave-js.github.io/node-zwave-js/#/api/valueid
- zwave-js SetValueResult, https://zwave-js.github.io/node-zwave-js/#/api/node?id=setvalue
- MQTT Version 3.1.1, OASIS Standard, https://docs.oasis-open.org/mqtt/mqtt/v3.1.1/os/mqtt-v3.1.1-os.html
