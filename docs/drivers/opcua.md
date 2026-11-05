# opcua driver

The `opcua` driver connects to OPC UA servers, the interface of most current PLCs, process equipment and LADS lab instruments, with asyncua 2.1.0. Variables become channels with their engineering units, methods become actions, and `describe` browses the Objects folder.

## Supports

Every channel and action names a node in a `map`.

| Map | Meaning |
|---|---|
| `{ node: "ns=2;s=Pump.Speed" }` | A variable, read, or set when the file's `write` section names the variable |
| `{ node: "nsu=urn:example:skid;s=Pump.Speed" }` | The same with the namespace URI instead of the index |
| `{ node: "ns=2;s=Tank.Level", unit: percent, scale: 100 }` | `unit` overrides EngineeringUnits, `scale` multiplies the value |
| `{ object: "ns=2;s=Pump", method: "ns=2;s=Pump.Start", inputs: [rate] }` | A method call, with `inputs` in the method's argument order |

Node ids may be numeric `i=2258`, string `s=...`, GUID `g=...` or opaque `b=...`. `nsu=` ids resolve against the namespace array on connect, so renumbered namespaces keep working.

## How the protocol is handled

- `connect()` checks that every variable exists, that `write` variables are writable for this user, and that methods exist with the listed input count.
- Units come from EngineeringUnits by UNECE code, such as `CEL`, `KPA`, `RPM`, `P1` and about 45 more, or by display name. A unit that can't convert fails the connect, so a degF node can't read as degC.
- Bad status fails a read. Uncertain status, or a value outside `range`, marks the reading suspect.
- Changes go out as the node's own data type. Fractional or out-of-range values for integer nodes are blocked.
- Method arguments go out as the declared input types, in each argument's declared unit.

## Safe state

OPC UA has no general stop, so give the file a `safe_state` with the equipment's own stop, such as a Stop method and zero setpoints. The steps run in order on every stop.

## Discovery

`openhal discover` calls FindServers on `opc.tcp://127.0.0.1:4840` and lists the registered servers without reading or changing anything.

## Setup

1. Install with `uv tool install --compile-bytecode "halkit[opcua] @ git+https://github.com/sohan-bhat/OpenHAL"`.
2. Find the endpoint URL and node ids with the PLC's tool or a client such as UaExpert.
3. Start from `openhal/drivers/opcua/examples/dosing-pump.hal.yaml` or `describe`.

| Key | Default | Meaning |
|---|---|---|
| `endpoint` | required | `opc.tcp://host:port/path` |
| `timeout` | `4 s` | Per request |
| `user` | none | User name for username login |
| `token_env` | none | Variable holding the password for `user` |
| `security` | none | asyncua security string, such as `Basic256Sha256,SignAndEncrypt,client.der,client.pem` |
| `browse_depth` | 3 | Object levels `describe` browses |

## Known limitations

- No subscriptions, so each read is one request at the hub's poll rate.
- No arrays, structures or enumerated data types beyond String, numbers and Boolean.
- Without EURange, `describe` sets numeric limits of 0 to 0 until a person sets real ones.
- asyncua is LGPL-3.0, installed separately, unmodified and not copied.

## Hazard defaults

`medium`, since PLCs drive pumps, heaters, valves and motors. Use `high` for anything that can injure, and keep the PLC's own interlocks and e-stop circuit.

## Sources

- OPC UA specification, Part 4 services, Part 6 mappings and Part 8 data access, https://reference.opcfoundation.org/
- LADS companion specification, https://reference.opcfoundation.org/LADS/v100/docs/
- UNECE Recommendation 20 unit codes, https://unece.org/trade/uncefact/cl-recommendations
- asyncua documentation, https://opcua-asyncio.readthedocs.io/
