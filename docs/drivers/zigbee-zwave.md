# zigbee-zwave driver

The zigbee-zwave driver reaches Zigbee devices through Zigbee2MQTT and Z-Wave nodes through zwave-js-server, the two bridges most home setups already run. One device file names one device, and the URL picks the bridge, `mqtt://` for Zigbee2MQTT and `ws://` for zwave-js-server.

If the devices already live in Home Assistant, the homeassistant driver is the other route. The homeassistant driver reaches the same devices through Home Assistant's entities instead of the bridge, which suits setups where Home Assistant owns the Zigbee or Z-Wave stick.

## What it supports

- For Zigbee2MQTT, the driver supports every feature in a device's `exposes` list, binary, numeric, enum and text, including features nested in lights, switches and composite values.
- For zwave-js-server, the driver supports every value a node reports, named by command class, endpoint, property and property key, with the unit and states from its metadata.
- Read channels and control channels, where a Z-Wave channel mapped to `currentValue` is set through `targetValue` and read back from `currentValue`.
- A check on connect that every channel exists on the bridge, can be read or set as the file requires, and has a matching type and unit.
- Health from the MQTT session, Zigbee2MQTT's bridge state and device availability, or from the WebSocket and the node's dead or alive status.
- `describe()` returns suggested channels built from what the bridge reports, with the bridge's own limits marked suggested.

## Setup

```sh
uv tool install --compile-bytecode "openhal-hub[zigbee-zwave] @ git+https://github.com/sohan-bhat/OpenHAL"
```

For Zigbee, Zigbee2MQTT must publish to a broker the hub can reach. Turn on availability in Zigbee2MQTT if you want offline devices reported. For Z-Wave, run zwave-js-server or Z-Wave JS UI with its WebSocket server on, usually port 3000.

## Parameters

| Parameter | Default | Meaning |
|---|---|---|
| `url` | required | `mqtt://host:1883` or `mqtts://host:8883` for Zigbee2MQTT, `ws://host:3000` or `wss://` for zwave-js-server. The shorthand `zigbee-zwave: "mqtt://..."` sets it |
| `friendly_name` | required for Zigbee | The device's friendly name in Zigbee2MQTT |
| `node` | required for Z-Wave | The node id |
| `base_topic` | `zigbee2mqtt` | Zigbee2MQTT's base topic |
| `username`, `token_env` | none | MQTT user name, and the variable that holds its password |
| `ca_env` | none | An environment variable that holds the path of a CA bundle for `mqtts://` |
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
| `property` | both | Zigbee. The exposed property, the channel name by default, with dots for nested values such as `color.x`. Z-Wave. The value's property |
| `command_class` | Z-Wave | The command class number |
| `endpoint` | Z-Wave | The endpoint, `0` by default |
| `property_key` | Z-Wave | The property key, for meters and notifications |
| `target` | Z-Wave | The property to set, `targetValue` by default when `property` is `currentValue` |
| `scale`, `offset` | both | channel value = bridge value × scale + offset |
| `unit` | both | The bridge's unit when it doesn't report one |

Bridge units are converted to the channel unit (`°C` to `degF`, for example). Values the bridge counts in steps are rounded to a whole step before they go out.

## How reads and commands behave

- Reads come from what the bridge last pushed, with the time the value arrived. On connect the driver requests the properties that support `get` from Zigbee2MQTT, and takes Z-Wave values from the server's state. Battery sensors often report only when they wake, so a sensor value can read as no value at first.
- A command returns once the bridge acknowledges the command, which means the broker's acknowledgement for Zigbee2MQTT and the `node.set_value` result for zwave-js-server. A failed Z-Wave status raises `DriverError`, and the device's new state arrives when the device reports the change.
- Commands are never queued, and a lost MQTT acknowledgement drops the connection so nothing arrives late.

## Examples

- `ikea-bulb-zigbee2mqtt.hal.yaml` switches and dims an IKEA bulb through Zigbee2MQTT.
- `zooz-plug-zwave.hal.yaml` reads power and energy from a Zooz plug and switches the plug through zwave-js-server, with a watchdog that turns the plug off after two hours.

## Errors

- A broker or server that can't be reached, failed authentication, a missing password variable, an unknown friendly name or node, and a bridge that sends nothing raise `DriverError` with a message that names what to check.
- A channel the bridge doesn't have, can't set, or reports with a different type or unit fails the connect with `DriverError` naming the channel.
- A value of the wrong type on read raises `DriverError`. A command that fails at the bridge raises `DriverError` with the bridge's reason, and a bridge that doesn't respond raises `TimeoutError`.

## Limitations

- The driver has no actions, scenes, groups, pairing, OTA updates or network management, because those belong in the bridge's own interface.
- The driver uses zwave-js-server schema 40 at most, and newer servers still accept schema 40.
- Non-linear conversions, such as mired to kelvin, are left to the device file as raw values.

## Hazard default and safe state

The default hazard is low, because most Zigbee and Z-Wave devices are lights, sensors and plugs. A plug can switch anything, so set the file's hazard to match the load. Neither bridge has an emergency command, so `safe_state_support` is `file`. The hub sends the device file's safe state like any other command, which needs the bridge and the device to be up. Use the device's own power-on and timeout settings as the real fallback.

## Sources

- Zigbee2MQTT MQTT topics and messages, https://www.zigbee2mqtt.io/guide/usage/mqtt_topics_and_messages.html
- Zigbee2MQTT exposes, https://www.zigbee2mqtt.io/guide/usage/exposes.html
- zwave-js-server API, https://github.com/zwave-js/zwave-js-server
- zwave-js value IDs, https://zwave-js.github.io/node-zwave-js/#/api/valueid
- zwave-js SetValueResult, https://zwave-js.github.io/node-zwave-js/#/api/node?id=setvalue
- MQTT Version 3.1.1, OASIS Standard, https://docs.oasis-open.org/mqtt/mqtt/v3.1.1/os/mqtt-v3.1.1-os.html
