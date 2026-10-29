# Concepts

OpenHAL is an open protocol between agents and hardware. This page defines the protocol's parts.

## What the name means

OpenHAL stands for Open Hardware Abstraction Layer, and each of the last three words names a part of the system.

- **Hardware.** The hardware is any device OpenHAL controls. Each device has a [Device File](glossary:device-file) that lists the device's channels and the limits a person confirmed.
- **Abstraction.** A hardware abstraction layer gives every device the same interface, so an agent reads and changes a 3D printer, a bench power supply or an Arduino board with the same few requests while the device file and the driver handle the differences.
- **Layer.** The layer is the [Hub](glossary:hub) between the agent and the hardware, where the [Safety Kernel](glossary:safety-kernel) checks every request against the device file's limits before a [Driver](glossary:driver) sends a command to the device.

## Hub

The [Hub](glossary:hub) is one process on your computer or a Raspberry Pi, and the hub owns every device. Clients talk to the hub with JSON-RPC 2.0 messages over a WebSocket or stdio, or through the MCP server, which maps onto the same methods.

## Device files

Each device has a [Device File](glossary:device-file) that lists what can be read, what can be changed, the limits on every change and the safe state.

```yaml tested include=examples/print-babysitter/printer.hal.yaml
```

A file is read-only until a person confirms its limits. A limit a tool suggests stays a suggestion until a person confirms the limit.

## Safety kernel

The [Safety Kernel](glossary:safety-kernel) evaluates every command, from every client, in a fixed order. The kernel checks units, range, step, rate of change, interlocks, the token's scope and confirmation, and stops at the first failure. The kernel is plain code with no model in it, and an unknown value, such as a stale reading, counts as unsafe.

## Drivers and grants

A [Driver](glossary:driver) speaks one protocol, such as SCPI or Moonraker. A driver changes hardware only with a [Grant](glossary:grant), a single-use permission the kernel issues for one exact command.

## Errors

A refused command returns a JSON-RPC error with a stable code and name.

| Code | Name | Meaning |
|---|---|---|
| -32010 | LIMIT_EXCEEDED | Outside the confirmed limits |
| -32011 | RATE_LIMITED | Faster than the rate limit allows right now |
| -32012 | INTERLOCK_BLOCKED | An interlock doesn't hold |
| -32013 | CONFIRMATION_REQUIRED | Waiting for a person |
| -32014 | STOPPED | The hub is stopped |
| -32015 | UNVERIFIED_LIMITS | The device file isn't confirmed |

The specification lists every code.

## Principals and hazard classes

Every request comes from a principal. A person uses the human token, and an agent uses an agent token with a scope of `read`, `control_low` or `control_medium`. A device file sets its hazard class to `low`, `medium` or `high`, and every change to a high hazard device waits for a person.

## Conformance levels

Hubs and drivers declare a [Conformance Level](glossary:conformance-level). Core covers discovery and reads, Control adds changes and stop, and Full adds actions, routines and confirmations.

## What OpenHAL doesn't do

OpenHAL leaves firmware in charge of each device and doesn't replace e-stops, enclosures or interlocks wired in hardware.
