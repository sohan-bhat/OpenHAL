# Concepts

OpenHAL is an open protocol for agents to control hardware, with one device file per device and one hub that checks every command.

## What the name means

OpenHAL stands for Open Hardware Abstraction Layer.

- **Hardware.** Any device OpenHAL controls. Each device has a [Device File](glossary:device-file) with the device's channels and the limits a person confirmed.
- **Abstraction.** Every device gets the same interface, so an agent drives a 3D printer, a bench power supply or an Arduino board with the same few requests.
- **Layer.** The [Hub](glossary:hub) between the agent and the hardware. The [Safety Kernel](glossary:safety-kernel) checks every request against the device file before a [Driver](glossary:driver) sends a command.

## Hub

The [Hub](glossary:hub) is one process on your computer or a Raspberry Pi that owns every device. Clients connect with JSON-RPC 2.0 over a WebSocket or stdio, or through the MCP server.

## Device files

Each [Device File](glossary:device-file) lists what can be read and changed, the limits and the safe state.

```yaml tested include=examples/print-babysitter/printer.hal.yaml
```

Every channel and action has a risk level of low, medium or high. A high risk channel or action stays read-only until a person confirms the limits, and the rest take commands within the device's own range. A generated limit stays a suggestion until a person confirms the limit.

## Safety kernel

The [Safety Kernel](glossary:safety-kernel) checks units, range, step, rate of change, interlocks, token scope and confirmation, in that order, and stops at the first failure. The kernel is plain code with no model, and an unknown value such as a stale reading counts as unsafe.

## Drivers and grants

A [Driver](glossary:driver) implements one protocol, such as SCPI or Moonraker. A driver changes hardware only with a [Grant](glossary:grant), a single-use permission for one exact command.

## Errors

A blocked or held command returns a JSON-RPC error with a stable code and name.

| Code | Name | Meaning |
|---|---|---|
| -32010 | LIMIT_EXCEEDED | Outside the confirmed limits |
| -32011 | RATE_LIMITED | Faster than the rate limit |
| -32012 | INTERLOCK_BLOCKED | An interlock doesn't hold |
| -32013 | CONFIRMATION_REQUIRED | Held until a person approves |
| -32014 | STOPPED | The hub is stopped |
| -32015 | UNVERIFIED_LIMITS | The device file isn't confirmed |

The specification lists every code.

## Principals and hazard classes

A person uses the human token. An agent uses an agent token with a scope of `read`, `control_low` or `control_medium`. A device file's hazard class is `low`, `medium` or `high`, and the hub holds every change to a high hazard device until a person approves.

## Conformance levels

Hubs and drivers declare a [Conformance Level](glossary:conformance-level). Core covers discovery and reads, Control adds changes and stop, and Full adds actions, routines and confirmations.

## What OpenHAL doesn't do

Each device's firmware still controls the device. OpenHAL doesn't replace e-stops, enclosures or hardware interlocks.
