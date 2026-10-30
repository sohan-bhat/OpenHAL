# matter driver

The matter driver reads and controls Matter devices through a Matter Server, the WebSocket service that runs the Matter fabric for Home Assistant and other controllers. Each device file names one node, and attributes become channels while cluster commands become channel changes and actions.

The Home Assistant bridge stays the other route. If Home Assistant already runs the Matter Server, the homeassistant driver reaches the same devices through their Home Assistant entities, and this driver connects to the Matter Server directly.

## Server status

This status was checked on 2026-10-24. python-matter-server was archived in June 2026, and 8.1.2 is its final version. The successor is matterjs-server, built on matter.js by the Open Home Foundation, which aims to keep the same WebSocket API and lists a few intentional differences. The driver uses only the documented commands both share (`start_listening`, `read_attribute`, `write_attribute`, `device_command`) and the server info and event messages. The driver was tested against a simulator of the python-matter-server format, not against matterjs-server.

## What it supports

- Read channels for any attribute, named by endpoint, cluster and attribute, with scale, offset and unit, one bit of a bitmap, or a lookup for enums.
- Control channels that set an attribute with `write_attribute`, or run a cluster command such as `MoveToLevelWithOnOff`, or pick `On` and `Off` for a bool. The attribute reads back the result.
- Actions that run any cluster command with their arguments in the payload, including timed commands such as door locks need.
- A check on connect that every attribute exists on the node and every command's cluster exists on its endpoint.
- Health from the WebSocket and the node's `available` flag.
- `describe()` returns suggested channels for the clusters the driver supports (on and off, level, color temperature, temperature, humidity, pressure, occupancy, contact, battery, power, thermostat, fan, window covering and door lock), scaled as the Matter specification defines.

## Setup

```sh
uv tool install --compile-bytecode "openhal-hub[matter] @ git+https://github.com/sohan-bhat/OpenHAL"
```

Commission the device into the Matter Server first, with the server's frontend or Home Assistant, and note the node id the device gets. The server listens on `ws://<host>:5580/ws`.

## Parameters

| Parameter | Default | Meaning |
|---|---|---|
| `url` | required | The Matter Server WebSocket, such as `ws://192.168.1.10:5580/ws`. The shorthand `matter: "ws://..."` sets it |
| `node` | required | The node id |
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
| `path` | `endpoint/cluster/attribute` in decimal. Or give `endpoint`, `cluster` and `attribute` |
| `scale`, `offset` | channel value = attribute × scale + offset |
| `unit` | The unit the scaled attribute is in, when not the channel unit |
| `bit` | Read one bit of a bitmap attribute as a bool |
| `lookup` | Attribute numbers to enum values |
| `command`, `payload` | Run this command with `{value}` in the payload instead of setting the attribute |
| `on_command`, `off_command` | For bool channels, the commands for true and false |
| `timed_ms` | Send the command as a timed interaction, needed by locks and some covers |

Because Matter attributes are integers, values going out are rounded to whole attribute units.

## How reads and commands behave

- The Matter Server subscribes to every attribute of every node, so reads come from its pushes with the time they arrived and cost no round trip. A null attribute reads as no value.
- A command returns when the server reports the device's response. An attribute change that returns an error status fails with `DriverError` naming the Matter status, such as `CONSTRAINT_ERROR` or `UNSUPPORTED_WRITE`.
- Because an unavailable node's last values may be stale, the node fails its reads and reports itself disconnected.

## Example

`openhal/drivers/matter/examples/eve-energy-plug.hal.yaml` switches an Eve Energy plug and reads its power.

## Errors

- A server that can't be reached, a server too old or not a Matter Server, and an unknown node raise `DriverError` with a message that names what to check.
- A channel whose attribute or cluster the node doesn't have fails the connect with `DriverError`.
- Server errors carry the server's error name, for example `node not ready` or `SDK stack error`, and its details. A server that doesn't respond raises `TimeoutError`.

## Limitations

- The driver has no commissioning, binding, access control or OTA updates, so use the Matter Server's own frontend for those tasks.
- Matter events (such as button presses) are not channels yet, and only attributes are.
- Each device file holds one node, and because bridged devices are nodes with several endpoints, map their endpoints in one file or one file per node.

## Hazard default and safe state

The default hazard is low, because most Matter devices are lights, plugs and sensors. Locks, covers and plugs that switch heaters need a higher hazard in their device file, and lock commands should need confirmation each time. Matter has no fabric-wide emergency command, so `safe_state_support` is `file`. The hub sends the device file's safe state like any other command, which needs the server and the node to be reachable.

## Sources

- python-matter-server WebSocket API, https://github.com/matter-js/python-matter-server/blob/main/docs/websockets_api.md
- python-matter-server message models, https://github.com/matter-js/python-matter-server/blob/main/matter_server/common/models.py
- python-matter-server repository and archive notice, https://github.com/matter-js/python-matter-server
- matterjs-server, https://github.com/matter-js/matterjs-server
- Connectivity Standards Alliance, Matter specification, https://csa-iot.org/developer-resource/specifications-download-request/
