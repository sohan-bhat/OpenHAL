# opcua driver

The `opcua` driver connects to OPC UA servers, the interface of most current PLCs, process equipment and LADS lab instruments. Variables become channels with their engineering units, and methods become actions.

| | |
|---|---|
| Driver name | `opcua` |
| Library | asyncua 2.1.0 (LGPL-3.0 or later, used unmodified as a library) |
| Extra | `uv tool install --compile-bytecode "openhal-hub[opcua] @ git+https://github.com/sohan-bhat/OpenHAL"` |
| Hazard default | medium |
| Conformance | full |
| Safe state | from the device file. OPC UA has no general emergency behavior |
| Self-describe | yes, by browsing the Objects folder |

## What it supports

Every channel and action names its node in a `map`, with node ids in the OPC UA string form.

| Map | Meaning |
|---|---|
| `{ node: "ns=2;s=Pump.Speed" }` | A variable, read, or set when the file's `write` section names the variable |
| `{ node: "nsu=urn:example:skid;s=Pump.Speed" }` | The same, with the namespace URI instead of its index |
| `{ node: "ns=2;s=Tank.Level", unit: percent, scale: 100 }` | `unit` overrides the node's EngineeringUnits, `scale` multiplies the OPC UA value |
| `{ object: "ns=2;s=Pump", method: "ns=2;s=Pump.Start", inputs: [rate] }` | A method call. `inputs` lists the action's arguments in the method's order |

Node ids may be numeric (`i=2258`), string (`s=...`), GUID (`g=...`) or opaque (`b=...`). `nsu=` ids are resolved against the server's namespace array on connect, so a file keeps working when the server renumbers its namespaces.

## How the protocol is handled

- connect() checks every node the file names. Variables must exist, variables in the `write` section must be writable for this user, and methods must exist with as many inputs as the map lists. Anything else stops the connect with a reason.
- Units come from each variable's EngineeringUnits, by UNECE code (`CEL`, `KPA`, `RPM`, `P1` and about 45 others) or its display name. A channel whose unit can't be converted from the node's unit fails the connect, so a degF node can't be read as degC by mistake.
- Reads check the status code, so Bad fails the read and Uncertain marks the reading suspect, and a reading outside the channel's `range` is also suspect.
- A change sends a Variant of the node's own data type. For integer nodes the driver blocks a value that isn't whole or doesn't fit the type, and nothing is sent.
- Method arguments go out as the method's input types, and because OPC UA arguments carry no units, the value is sent in the argument's declared unit.

## Safe state

OPC UA has no general stop, so the driver has no native safe state. Give the device file a `safe_state` with the equipment's own stop, such as a Stop method and setpoints of 0. The safe state's steps run in order on every stop.

## Discovery

`openhal discover` calls FindServers on `opc.tcp://127.0.0.1:4840`, the usual local discovery server, to list the servers registered there, and discovery never reads or changes a variable.

## Setup

1. Install the extra with `uv tool install --compile-bytecode "openhal-hub[opcua] @ git+https://github.com/sohan-bhat/OpenHAL"`.
2. Find the endpoint URL and the node ids with the PLC's tool or a generic client such as UaExpert.
3. Start from `openhal/drivers/opcua/examples/dosing-pump.hal.yaml`, or call `describe` for a draft.
4. Run `openhal file validate`, then confirm the limits by hand.

## Parameters

| Key | Default | Meaning |
|---|---|---|
| `endpoint` | required | `opc.tcp://host:port/path` |
| `timeout` | `4 s` | Per request |
| `user` | none | User name for username login |
| `token_env` | none | Name of the environment variable that holds the password for `user` |
| `security` | none | asyncua security string, for example `Basic256Sha256,SignAndEncrypt,client.der,client.pem` |
| `browse_depth` | 3 | How many object levels describe browses |

## Example device file

```yaml
device: Dosing pump skid
id: dosing
connect: { opcua: "opc.tcp://plc.local:4840" }
read:
  tank_level: { unit: percent, map: { node: "nsu=urn:example:skid;s=Tank.Level" } }
write:
  speed: { unit: rpm, min: 0, max: 1200, max_change_per_s: 200, map: { node: "nsu=urn:example:skid;s=Pump.Speed" } }
actions:
  stop: { map: { object: "nsu=urn:example:skid;s=Pump", method: "nsu=urn:example:skid;s=Pump.Stop" } }
safe_state:
  - { action: stop }
  - { speed: 0 }
interlocks:
  - { if: "speed > 0 rpm", require: "tank_level > 5 percent" }
hazard: medium
```

## Known limitations

- Subscriptions are not used, so each read is one request and the hub's polling sets the rate.
- Arrays, structures and enumerated data types beyond String and the numeric and Boolean types are not mapped.
- When the server has no EURange, describe returns limits of 0 to 0 for numeric changes, so nothing moves until a person sets real limits.
- asyncua is LGPL-3.0, installed as a separate package and not modified or copied.

## Hazard defaults

The default hazard is `medium`, because PLCs drive pumps, heaters, valves and motors. Raise the file's hazard to `high` for anything that can injure, and keep the PLC's own interlocks and e-stop circuit in place, because the device file adds limits and does not replace them.

## Sources

- OPC UA specification, Part 4 services, Part 6 mappings and Part 8 data access, https://reference.opcfoundation.org/
- LADS companion specification, https://reference.opcfoundation.org/LADS/v100/docs/
- UNECE Recommendation 20 unit codes, https://unece.org/trade/uncefact/cl-recommendations
- asyncua documentation, https://opcua-asyncio.readthedocs.io/
