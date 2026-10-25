# Concepts

OpenHAL sits between an AI agent and real equipment. This page explains the parts and the words the rest of the documentation uses.

## Device files

Every device has a small YAML file that ends in `.hal.yaml`. It says how to find the device, which driver talks to it, what can be read, what can be changed, the limits on every change and the state that is safe to leave it in.

```yaml tested
device: Desk fan controller
id: desk-fan
connect: { serial: auto, board: arduino-uno }
read:
  temperature: { unit: degC, every: 1 s }
write:
  fan_speed: { unit: percent, min: 0, max: 100, step: 1, max_change_per_s: 20 }
safe_state: { fan_speed: 0 }
hazard: low
```

Read channels are values the hub can read. Write channels are values it can set, each with a unit and its limits. Actions are named operations with typed arguments, like homing a printer. The full format is in the [spec](../../spec/SPEC.md).

## Limits come from people

A file loads read-only until a person confirms its limits, with `openhal file confirm` or the limits interview. A tool may suggest limits, and they stay marked `suggested: true` until someone confirms them. The confirmation carries a hash of the limits, so a later change makes the file read-only again.

Agents can tighten limits for their own session. They can never loosen them.

## The hub and the kernel

The hub (`openhald`) is one process on your laptop or a Raspberry Pi. It owns every device. Inside it, the safety kernel decides every write and every action, from every source. It checks the command shape, the stop lock, the file state, the device state, the token's scope, units, type, range, step, rate of change, interlocks, watchdog budgets and confirmation, in that order, and stops at the first failure.

The kernel is plain code with no model in it. The same command against the same state always gets the same decision and the same message. Only a command that passes every check gets a grant, and a driver can only write with a grant for that exact device, channel and value.

## Unknown never passes

A value the hub can't trust is unknown. That covers a sensor reading that is too old, a channel with a command in flight, and a channel after a failed command. Interlocks treat unknown as not satisfied, and a rate limit blocks until a fresh reading arrives. Unknown always leads to a block, never to a pass.

## Interlocks

An interlock ties one channel to another, on the same device or another one on the same hub.

```yaml tested
device: Resin curing heater
id: curing-heater
connect: { mqtt: mqtt.local }
write:
  power: { unit: W, min: 0, max: 60 }
safe_state: { power: 0 }
interlocks:
  - if: "power > 0 W"
    require: "desk-fan.fan_speed >= 30 %"
    message: "The heater needs the desk fan at 30 % or more."
hazard: medium
```

If an interlock names a device that isn't registered, no device on the hub can be written until it is fixed. A misspelled id protects nothing, so the hub won't guess.

## Who is asking

Every command comes from a principal. A person uses the human token from `openhal init`, and a command from a person counts as confirmed. An agent uses an agent token with a scope. `read` allows reads only, `control_low` covers low hazard devices and `control_medium` covers low and medium. Routines run unattended under their own identity.

## Hazard classes and confirmation

A device file sets `hazard` to `low`, `medium` or `high`. A file with write channels and no hazard class counts as medium.

A channel or action can ask for confirmation. With `confirm`, one approval covers the same request from the same client for ten minutes. With `confirm-each-time`, every request waits for a person. On a high hazard device every write and action waits for a person every time, whatever the file says, and an agent's request goes to the confirmation queue.

## Stop

`openhal stop` locks writes, cancels pending requests, pauses routines and puts every device in its safe state. Any principal may stop, including an agent. Only a person may lift the stop.

## Text from devices is data

Text that comes from devices, manuals, sketches and device notes reaches agents inside `<device-data>` blocks with a line saying it is data. Nothing inside can change a limit or approve anything, whatever it says.

## What OpenHAL doesn't do

It can't make a person choose sensible limits, and it can't make firmware obey. It isn't a substitute for e-stops, enclosures, interlocks wired in hardware or certified safety systems. The [safety model](../SAFETY.md) says exactly what is guaranteed and what isn't.
