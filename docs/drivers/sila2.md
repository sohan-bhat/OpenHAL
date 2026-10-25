# sila2 driver

The `sila2` driver talks to lab automation devices through SiLA 2, using the official `sila2` Python package. Properties become read channels, observable properties become streams, and commands become actions and the way channels change.

| | |
|---|---|
| Driver name | `sila2` |
| Library | sila2 0.14.0 (MIT), with grpcio 1.84 (Apache-2.0) and lxml 6 (BSD-3-Clause) |
| Extra | `uv tool install --compile-bytecode "openhal-hub[sila2] @ git+https://github.com/sohan-bhat/OpenHAL"` |
| Hazard default | medium |
| Conformance | full |
| Safe state | from the device file. SiLA has no general emergency behavior |
| Self-describe | yes, from the server's Feature Definitions |

## What it supports

Every channel and action names its SiLA feature in a `map`. The client loads each feature from the server's own Feature Definition, so no generated code is needed.

| Map | Meaning |
|---|---|
| `{ feature: TemperatureController, property: CurrentTemperature }` | A property. An observable one is a stream |
| `{ feature: TemperatureController, property: DeviceState, field: LidClosed }` | One element of a structure property |
| `{ feature: TemperatureController, command: SetTargetTemperature, parameter: TargetTemperature, readback: TargetTemperature }` | A channel that changes through a command and reads back from a property |
| `{ feature: ShakeController, command: Shake, parameters: { rpm: Speed, seconds: Duration } }` | An action. Each argument names the parameter it fills |
| `{ ..., base: { Mode: Gentle } }` | Fixed values for the other parameters of a command |

`feature` is the feature identifier, or its fully qualified form such as `org.example/lab/TemperatureController/v1` to pin a version. `unit` overrides the Unit constraint and `scale` multiplies the SiLA value.

## How the protocol is handled

- connect() opens the gRPC channel and checks every feature, property, command and parameter the file names, with their types. Anything that doesn't fit stops the connect with a reason.
- Units come from each data type's Unit constraint label. A channel whose unit can't be converted from it is refused on connect.
- Unobservable properties are read on demand. Observable properties are subscribed on connect and the newest value is kept, so a read costs no round trip and is unknown until the first value arrives.
- SiLA properties are read-only, so a channel changes through a command with one parameter. Without `readback` it reads back as the last value the driver sent.
- An observable command waits up to `action_wait` and answers `done` with its responses, or answers `started` and keeps running on the server.
- Defined execution errors fail the command with their identifier and message, for example `TooHot`. Constraint violations come back as validation errors.
- The sila2 client is blocking, so every call runs in a worker thread with a deadline. Connecting gets 8 s, since the client compiles each feature definition.
- sila2 0.14 loads two builds of its framework protos, which protobuf's default implementation refuses once another package, such as the ESPHome driver's aioesphomeapi, has loaded protobuf. The driver registers one build under both names first, so SiLA devices work next to every other driver in one hub.

## Safe state

SiLA has no general stop command, and the core features have none either, so the driver has no native safe state. Give the device file a `safe_state` with the device's own stop commands and safe setpoints. They run in order on every stop.

## Discovery

`openhal discover` listens for `_sila._tcp.local.` services with mDNS for 2 s and lists each server with its address and the values from its TXT record. Listening never touches a device.

## Setup

1. Install the extra with `uv tool install --compile-bytecode "openhal-hub[sila2] @ git+https://github.com/sohan-bhat/OpenHAL"`.
2. Get the server's CA certificate (SiLA servers encrypt by default, many with a self-signed CA in their mDNS record) and save it as a PEM file.
3. Start from `openhal/drivers/sila2/examples/thermoshaker.hal.yaml`, or call `describe` for a proposal, and keep only what you need.
4. Run `openhal file validate`, then confirm the limits by hand.

## Parameters

| Key | Default | Meaning |
|---|---|---|
| `host` | required | SiLA server host name or address |
| `port` | 50052 | SiLA server port |
| `insecure` | false | Connect without encryption, for development servers only |
| `ca_env` | none | The name of an environment variable that holds the path of the server's CA certificate, a PEM file. The device file never names the path itself |
| `timeout` | `5 s` | Per call |
| `action_wait` | `8 s` | How long an observable command waits before answering `started`. At most 9 s |

## Example device file

```yaml
device: Thermoshaker
id: thermoshaker
connect: { sila2: thermoshaker.lab.local, port: 50052, ca_env: THERMOSHAKER_CA }
read:
  temperature: { unit: degC, stream: true, map: { feature: TemperatureController, property: CurrentTemperature } }
write:
  target:
    unit: degC
    min: 4
    max: 60
    map: { feature: TemperatureController, command: SetTargetTemperature, parameter: TargetTemperature, readback: TargetTemperature }
actions:
  stop_shaking: { map: { feature: ShakeController, command: StopShaking } }
safe_state:
  - { action: stop_shaking }
  - { target: 22 }
hazard: medium
```

## Known limitations

- Lists, binaries, dates, times and nested structures in parameters are not sent yet. Structure properties are read one element at a time.
- Running observable commands can't be cancelled, because SiLA's CancelController is optional and rarely implemented. Use the device's own stop command.
- SiLA metadata, such as lock identifiers from LockController, is not sent.

## Hazard defaults

`medium`. Lab devices heat, spin and move plates. Raise the file's hazard to `high` for devices that can injure, such as centrifuges and robotic arms.

## Sources

- SiLA 2 Part A (overview and concepts) and Part B (mapping to gRPC), https://sila-standard.com/standards/
- SiLA feature definition schema and core features, https://gitlab.com/SiLA2/sila_base
- sila2 Python package documentation, https://sila2.gitlab.io/sila_python/
