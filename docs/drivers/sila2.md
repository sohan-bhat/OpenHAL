# sila2 driver

The `sila2` driver connects to SiLA 2 lab automation devices with the `sila2` package 0.14.0, loading features from the server's Feature Definitions. Properties become reads or streams, and commands become actions and channel changes. `describe` drafts a file from the definitions.

## Supports

Every channel and action names a SiLA feature in a `map`.

| Map | Meaning |
|---|---|
| `{ feature: TemperatureController, property: CurrentTemperature }` | A property. Observable properties stream |
| `{ feature: TemperatureController, property: DeviceState, field: LidClosed }` | One element of a structure property |
| `{ feature: TemperatureController, command: SetTargetTemperature, parameter: TargetTemperature, readback: TargetTemperature }` | A channel that changes through a command and reads back from a property |
| `{ feature: ShakeController, command: Shake, parameters: { rpm: Speed, seconds: Duration } }` | An action, each argument naming a parameter |
| `{ ..., base: { Mode: Gentle } }` | Fixed values for the command's other parameters |

`feature` is the identifier, or the fully qualified form such as `org.example/lab/TemperatureController/v1` to pin a version. `unit` overrides the Unit constraint and `scale` multiplies the value.

## How the protocol is handled

- Connect checks every named feature, property, command, parameter, type and unit, and allows 8 s for feature compilation.
- Observable properties stream from connect, and others read on demand.
- A channel changes through a one-parameter command and reads back the last value sent without `readback`.
- An observable command returns `done` within `action_wait`, or `started`.
- Execution errors fail the command with identifier and message, such as `TooHot`, and constraint violations return validation errors.
- sila2 0.14 loads two builds of the framework protos, which conflict once another package such as aioesphomeapi loads protobuf. The driver registers one build under both names, so SiLA runs beside every other driver.

## Safe state

SiLA has no general stop, so give the file a `safe_state` with the device's own stop commands and safe setpoints.

## Discovery

`openhal discover` lists `_sila._tcp.local.` mDNS services heard within 2 s.

## Setup

1. Install with `uv tool install --compile-bytecode "halkit[sila2] @ git+https://github.com/sohan-bhat/OpenHAL"`.
2. Save the server's CA certificate as a PEM file, since SiLA servers encrypt by default, often with a self-signed CA in the mDNS record.
3. Start from `openhal/drivers/sila2/examples/thermoshaker.hal.yaml` or `describe`.

| Key | Default | Meaning |
|---|---|---|
| `host` | required | Server host |
| `port` | 50052 | Server port |
| `insecure` | false | No encryption, for development servers only |
| `ca_env` | none | Variable holding the CA certificate PEM path |
| `timeout` | `5 s` | Per call |
| `action_wait` | `8 s` | Time before an observable command returns `started`, at most 9 s |

## Known limitations

- No lists, binaries, dates, times or nested structures in parameters yet.
- Running observable commands can't be cancelled. Use the device's own stop command.
- No SiLA metadata such as LockController lock identifiers.

## Hazard defaults

`medium`, since lab devices heat, spin and move plates. Use `high` for devices that can injure, such as centrifuges and robotic arms.

## Sources

- SiLA 2 Part A, overview and concepts, and Part B, mapping to gRPC, https://sila-standard.com/standards/
- SiLA feature definition schema and core features, https://gitlab.com/SiLA2/sila_base
- sila2 Python package documentation, https://sila2.gitlab.io/sila_python/
