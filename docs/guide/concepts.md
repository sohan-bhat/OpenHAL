# Concepts

OpenHAL is an open protocol between AI clients and hardware. This page defines its parts.

## Hub

The [Hub](glossary:hub) is one process on your computer or a Raspberry Pi. It owns every device. Clients talk to it with JSON-RPC 2.0 messages over a WebSocket or stdio, or through the MCP server, which maps onto the same methods.

## Device files

Each device has a [Device File](glossary:device-file) that lists what can be read, what can be changed, the limits on every change and the safe state.

```yaml tested include=examples/plant-waterer/plant-waterer.hal.yaml
```

A file is read-only until a person confirms its limits. Tools may suggest limits. They can never confirm them.

## Safety kernel

The [Safety Kernel](glossary:safety-kernel) decides every command, from every client, in a fixed order. It checks units, range, step, rate of change, interlocks, the token's scope and confirmation, and stops at the first failure. It is plain code with no model in it. A value it can't trust counts as unsafe.

## Drivers and grants

A [Driver](glossary:driver) speaks one protocol, such as SCPI or Moonraker. It can change hardware only with a [Grant](glossary:grant), a single-use permission the kernel issues for one exact command.

## Errors

A refused command is a JSON-RPC error with a stable code and name.

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

Every request comes from a principal. A person uses the human token. An agent uses an agent token with a scope, `read`, `control_low` or `control_medium`. A device file sets its hazard class, `low`, `medium` or `high`. Every change to a high hazard device waits for a person.

## Conformance levels

Hubs and drivers declare a [Conformance Level](glossary:conformance-level). Core covers discovery and reads. Control adds changes and stop. Full adds actions, routines and confirmations.

## What OpenHAL doesn't do

It can't make firmware obey, and it doesn't replace e-stops, enclosures or interlocks wired in hardware.
