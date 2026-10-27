# mqtt driver

The mqtt driver reads devices that publish their state on MQTT topics and controls devices that take commands on topics, through a broker such as Mosquitto. The driver uses paho-mqtt and MQTT 3.1.1. Each channel's map names the state topic, the command topic and how the payload is written, so Tasmota, Zigbee2MQTT, ESPHome, Shelly and homemade boards all work without device-specific code.

## What it supports

- Read channels of type number, bool, string and enum from raw payloads (`21.5`, `ON`) or JSON payloads with a JSON path.
- Write channels that publish raw words, numbers, JSON built from a path, or a JSON template.
- Retained messages seed reads right after connecting. Live messages replace them as they arrive.
- QoS 0 or 1 for commands, and an optional retain flag.
- Username and password, with the password from an environment variable, and TLS.
- `describe()` listens on the broker for a moment and proposes read channels from the topics it sees.

## Setup

```sh
uv tool install --compile-bytecode "openhal-hub[mqtt] @ git+https://github.com/sohan-bhat/OpenHAL"
```

You need a broker the hub can reach. Mosquitto works well and runs on a Raspberry Pi.

## Parameters

| Parameter | Default | Meaning |
|---|---|---|
| `host` | required | Broker address. The shorthand `mqtt: 192.168.1.10` sets it |
| `port` | `1883` | Broker port. TLS brokers usually use `8883` |
| `client_id` | `oh-` and the device id with a short hash | At most 23 characters, as MQTT 3.1.1 servers must accept. Each device needs its own, because a broker drops the older session when two clients share an id |
| `username` | none | Broker user name |
| `token_env` | none | Name of an environment variable holding the broker password |
| `tls`, `ca_env` | `false`, none | Use TLS. `ca_env` names an environment variable that holds the path of a CA bundle, since a device file never names a path |
| `keepalive` | `30` | Keep-alive interval in seconds |
| `timeout` | `5 s` | Connect and acknowledgement deadline |
| `qos` | `1` | Default QoS for commands |
| `prefix` | `""` | Prepended to every topic in the maps |
| `retain_commands` | `false` | Default retain flag for commands |
| `discover_topic` | `#` | Topic filter `describe()` listens on, under `prefix` |

The password parameter is `token_env`, not `password_env`, because the device file loader rejects any parameter whose name contains `password`.

## Channel maps

```yaml
read:
  temperature: { unit: degC, stream: true, map: { state: zigbee2mqtt/sensor, format: json, json: temperature } }
  door: { type: bool, map: { state: home/door, on: open, off: closed } }
write:
  relay:
    type: bool
    map: { state: stat/plug/POWER, command: cmnd/plug/POWER }
  brightness:
    unit: percent
    min: 0
    max: 100
    map: { state: zigbee2mqtt/lamp, command: zigbee2mqtt/lamp/set, format: json, json: brightness, scale: 0.3937 }
```

| Key | Default | Meaning |
|---|---|---|
| `state` | required for reads | Exact topic the device publishes on. Wildcards are not allowed |
| `command` | required for writes | Exact topic the driver publishes commands to |
| `format` | `raw` | `raw` text or `json` |
| `json` | none | JSON path to the value, such as `$.ENERGY.Power`. For commands, the JSON is built from the path |
| `template` | none | A JSON template for commands, such as `{ state: "{value}", transition: 2 }` |
| `on`, `off` | `ON` and `OFF` for raw commands | Words for bool channels. Reads accept a list |
| `scale`, `offset` | `1`, `0` | channel value = payload value × scale + offset. Commands send the inverse, and results within one millionth of a whole number go out as integers |
| `qos`, `retain` | from the parameters | Per-command override |

A write channel without a `state` topic reads back the last value the driver sent, or no value before the first write.

## How reads and writes behave

- MQTT only pushes. The driver subscribes to every state topic and keeps the newest message per topic, and a read returns it with the time it arrived. A topic that has had no message since connecting reads as no value (`None`), which the kernel treats as unknown.
- Commands are never queued. A write while the broker is down fails, and paho's automatic reconnect is off so nothing is replayed later on a new connection. The hub's heartbeat reconnects with a fresh client.
- A QoS 1 command waits for the broker's PUBACK. Without the PUBACK the write fails with `TimeoutError` and the driver drops the connection, so the broker can't deliver the command late. A PUBACK proves the broker has the message, not that the device acted. Watch the state topic for that.

## Example

`openhal/drivers/mqtt/examples/tasmota-plug.hal.yaml` reads power and energy from a Tasmota plug and switches its relay. Set `PowerRetain 1` on the plug so the relay state is retained.

## Errors

- Unreachable broker, refused credentials and a missing password variable raise `DriverError`.
- A payload that is not a number, not JSON, missing the JSON field, not an on or off word, or an enum value outside the list raises `DriverError` on read.
- No CONNACK or PUBACK within `timeout` raises `TimeoutError` or `DriverError` with the topic.

## Limitations

- MQTT 3.1.1 only. MQTT 5 properties are not used.
- No binary or protobuf payloads, and no image channels.
- No actions. Model each command topic as a write channel.
- `describe()` can only see topics that carry messages while it listens, so it proposes reads only, all `dimensionless` until you set the units.

## Hazard default and safe state

The default hazard is medium, because MQTT topics can switch anything. MQTT has no emergency behavior of its own, so `safe_state_support` is `file`. The hub publishes the device file's `safe_state` like any other command, which needs both the broker and the device to be up. Use the device's own power-on and connection-loss behavior (Tasmota `PowerOnState`, for example) as the real fallback.

## Sources

- MQTT Version 3.1.1, OASIS Standard, https://docs.oasis-open.org/mqtt/mqtt/v3.1.1/os/mqtt-v3.1.1-os.html
- Eclipse Paho Python client documentation, https://eclipse.dev/paho/files/paho.mqtt.python/html/
- Tasmota MQTT documentation, https://tasmota.github.io/docs/MQTT/
- Zigbee2MQTT MQTT topics and messages, https://www.zigbee2mqtt.io/guide/usage/mqtt_topics_and_messages.html
- RFC 9535 JSONPath, https://www.rfc-editor.org/rfc/rfc9535
