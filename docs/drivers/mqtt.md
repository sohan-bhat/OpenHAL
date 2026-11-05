# mqtt driver

The mqtt driver reads device state from MQTT topics and publishes commands through a broker such as Mosquitto, with paho-mqtt and MQTT 3.1.1. Channel maps name the state topic, the command topic and the payload format, so Tasmota, Zigbee2MQTT, ESPHome, Shelly and homemade boards need no device-specific code.

## Supports

- Number, bool, string and enum reads from raw payloads such as `21.5` and `ON`, or from JSON through a JSON path.
- Writes that publish raw words, numbers, JSON built from a path, or a JSON template, at QoS 0 or 1 with an optional retain flag.
- Retained messages seed reads on connect.
- Username and password from an environment variable, and TLS.
- `describe()` listens briefly and suggests reads from active topics, all `dimensionless` until units are set.

## Setup

```sh
uv tool install --compile-bytecode "halkit[mqtt] @ git+https://github.com/sohan-bhat/OpenHAL"
```

| Parameter | Default | Meaning |
|---|---|---|
| `host` | required | Broker address. `mqtt: 192.168.1.10` is shorthand |
| `port` | `1883` | Broker port, usually `8883` with TLS |
| `client_id` | `oh-` plus the device id and a short hash | At most 23 characters. Each device needs a unique id, since a broker drops the older session on a clash |
| `username` | none | Broker user |
| `token_env` | none | Variable holding the broker password. Parameter names with `password` fail to load |
| `tls`, `ca_env` | `false`, none | TLS, with `ca_env` naming a variable that holds a CA bundle path |
| `keepalive` | `30` | Keep-alive in seconds |
| `timeout` | `5 s` | Connect and acknowledgement deadline |
| `qos` | `1` | Default command QoS |
| `prefix` | `""` | Prepended to every topic |
| `retain_commands` | `false` | Default command retain flag |
| `discover_topic` | `#` | Topic filter for `describe()`, under `prefix` |

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
| `state` | required for reads | Exact topic the device publishes on, no wildcards |
| `command` | required for writes | Exact command topic |
| `format` | `raw` | `raw` text or `json` |
| `json` | none | JSON path such as `$.ENERGY.Power`, also used to build command JSON |
| `template` | none | Command JSON template such as `{ state: "{value}", transition: 2 }` |
| `on`, `off` | `ON` and `OFF` for raw commands | Bool words. Reads accept a list |
| `scale`, `offset` | `1`, `0` | value = payload × scale + offset. Commands send the inverse, near-integers as integers |
| `qos`, `retain` | from the parameters | Per-command override |

A write channel without `state` reads back the last value sent.

## Behavior

- Reads return the newest message per state topic, or `None` before the first message.
- Commands are never queued and paho's reconnect is off, so a write during a broker outage fails and nothing replays later. The heartbeat reconnects with a fresh client.
- A QoS 1 command without a PUBACK within `timeout` fails with `TimeoutError` and drops the connection, so no command arrives late. A PUBACK shows only that the broker has the message, so watch the state topic.
- An unreachable broker, failed authentication, a missing password variable and payloads that don't parse as the channel's type raise `DriverError`.

## Example

`openhal/drivers/mqtt/examples/tasmota-plug.hal.yaml` reads power and energy from a Tasmota plug and switches the relay. Set `PowerRetain 1` on the plug so the relay state is retained.

## Limitations

- MQTT 3.1.1 only, with no MQTT 5 properties.
- No binary or protobuf payloads and no image channels.
- No actions. Model each command topic as a write channel.

## Hazard default and safe state

Medium, since MQTT topics can switch anything. `safe_state_support` is `file`, published while the broker and device are up. The device's own power-on and connection-loss behavior, such as Tasmota `PowerOnState`, is the real fallback.

## Sources

- MQTT Version 3.1.1, OASIS Standard, https://docs.oasis-open.org/mqtt/mqtt/v3.1.1/os/mqtt-v3.1.1-os.html
- Eclipse Paho Python client documentation, https://eclipse.dev/paho/files/paho.mqtt.python/html/
- Tasmota MQTT documentation, https://tasmota.github.io/docs/MQTT/
- Zigbee2MQTT MQTT topics and messages, https://www.zigbee2mqtt.io/guide/usage/mqtt_topics_and_messages.html
- RFC 9535 JSONPath, https://www.rfc-editor.org/rfc/rfc9535
