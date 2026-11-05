# matter driver

The matter driver reads and controls Matter devices through a Matter Server, the WebSocket service that runs the Matter fabric for Home Assistant and other controllers. Each device file names one node. Attributes become channels and cluster commands become changes and actions. When Home Assistant already runs the Matter Server, the homeassistant driver reaches the same devices through entities.

## Server status

Checked 2026-10-24. python-matter-server was archived in June 2026 at 8.1.2. The successor, matterjs-server from the Open Home Foundation, aims to keep the same WebSocket API with a few intentional differences. The driver uses only the shared `start_listening`, `read_attribute`, `write_attribute` and `device_command` commands plus server info and event messages. The driver is tested against a simulator of the python-matter-server format, not against matterjs-server.

## Supports

- Actions that run any cluster command, including timed commands for door locks.
- A connect check that every attribute and command cluster exists on the node.
- `describe()` suggests channels for on and off, level, color temperature, temperature, humidity, pressure, occupancy, contact, battery, power, thermostat, fan, window covering and door lock.

## Setup

```sh
uv tool install --compile-bytecode "halkit[matter] @ git+https://github.com/sohan-bhat/OpenHAL"
```

Commission the device into the Matter Server with the server frontend or Home Assistant and note the node id. The server listens on `ws://<host>:5580/ws`.

| Parameter | Default | Meaning |
|---|---|---|
| `url` | required | Matter Server WebSocket such as `ws://192.168.1.10:5580/ws`. `matter: "ws://..."` is shorthand |
| `node` | required | Node id |
| `timeout` | `5 s` | Connect and response deadline |

## Channel maps

```yaml
read:
  temperature: { unit: degC, map: { path: 1/1026/0, scale: 0.01 } }
  occupied: { type: bool, map: { path: 1/1030/0, bit: 0 } }
write:
  power: { type: bool, map: { path: 1/6/0, on_command: On, off_command: Off } }
  level:
    unit: percent
    min: 0
    max: 100
    map:
      path: 1/8/0
      scale: 0.3937
      command: MoveToLevelWithOnOff
      payload: { level: "{value}", transitionTime: 0, optionsMask: 0, optionsOverride: 0 }
  heating_setpoint: { unit: degC, min: 7, max: 30, map: { path: 1/513/18, scale: 0.01 } }
actions:
  identify:
    args: { seconds: { unit: s, min: 1, max: 30 } }
    map: { endpoint: 1, cluster: 3, command: Identify, payload: { identifyTime: "{seconds}" } }
```

| Key | Meaning |
|---|---|
| `path` | `endpoint/cluster/attribute` in decimal, or separate `endpoint`, `cluster` and `attribute` |
| `scale`, `offset` | value = attribute × scale + offset |
| `unit` | Unit of the scaled attribute, when not the channel unit |
| `bit` | One bit of a bitmap as a bool |
| `lookup` | Attribute numbers to enum values |
| `command`, `payload` | Run this command with `{value}` in the payload instead of setting the attribute |
| `on_command`, `off_command` | Bool commands for true and false |
| `timed_ms` | Timed interaction, needed by locks and some covers |

Values going out round to whole attribute units.

## Behavior

- Reads come from the server's subscription pushes. A null attribute reads as no value.
- A command returns with the device's response. An error status fails with `DriverError` naming the Matter status, such as `CONSTRAINT_ERROR` or `UNSUPPORTED_WRITE`.
- An unavailable node fails reads and reports disconnected, since the last values may be stale.
- Connect failures name what to check. Server errors carry the server's error name, such as `node not ready`, and a silent server raises `TimeoutError`.

## Example

`openhal/drivers/matter/examples/eve-energy-plug.hal.yaml` switches an Eve Energy plug and reads the plug's power.

## Limitations

- No commissioning, binding, access control or OTA updates. Use the Matter Server frontend.
- Matter events such as button presses are not channels yet.
- One node per file. A bridge is one node with several endpoints, so map the endpoints in one file.

## Hazard default and safe state

Low. Locks, covers and plugs that switch heaters need a higher hazard, and lock commands need `confirm-each-time`. `safe_state_support` is `file`, sent while the server and node are reachable.

## Sources

- python-matter-server WebSocket API, https://github.com/matter-js/python-matter-server/blob/main/docs/websockets_api.md
- python-matter-server message models, https://github.com/matter-js/python-matter-server/blob/main/matter_server/common/models.py
- python-matter-server repository and archive notice, https://github.com/matter-js/python-matter-server
- matterjs-server, https://github.com/matter-js/matterjs-server
- Connectivity Standards Alliance, Matter specification, https://csa-iot.org/developer-resource/specifications-download-request/
