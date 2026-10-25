---
title: Why we built OpenHAL
description: AI clients can already drive hardware. OpenHAL defines one place where every command meets the limits a person confirmed.
date: 2026-10-24
author: OpenHAL contributors
draft: true
---

An AI client can read a datasheet, write a serial protocol and move a motor in an afternoon. Nothing on that path knows the limits a person would set. Nothing enforces them the same way for every client.

## The gap

Single-device tools exist for Arduino boards, 3D printers, bench instruments and robots. Each has its own model of a device and its own rules, and some have none. No two describe a device the same way, and no one place decides what may run.

## The protocol

OpenHAL is an open protocol with a dated specification. It defines two things.

1. The [Device File](glossary:device-file). It lists what a device can read and change, the limits on each change and the safe state. A person confirms the limits. Until then the file is read-only.
2. The hub protocol. Clients speak JSON-RPC 2.0 to one [Hub](glossary:hub). Its [Safety Kernel](glossary:safety-kernel) decides every write and action before a [Driver](glossary:driver) may act.

```yaml tested
device: Desk fan controller
id: desk-fan
connect: { openhal-firmware: auto }
read:
  temperature: { unit: degC, every: 1 s }
write:
  fan_speed: { unit: percent, min: 0, max: 100, max_change_per_s: 20 }
safe_state: { fan_speed: 0 }
hazard: low
```

A request over the limit is refused with a stable code, a registry name and a reason that cites the rule. A request inside it runs.

```json tested
→ {"jsonrpc": "2.0", "id": 6, "method": "hal/write",
   "params": {"device": "desk-fan", "channel": "fan_speed", "value": "150 %"}}
← {"jsonrpc": "2.0", "id": 6, "error": {"code": -32010,
     "message": "fan_speed 150 % exceeds the limit of 100 % (desk-fan.hal.yaml, confirmed by sohan 2026-10-24)",
     "data": {"name": "LIMIT_EXCEEDED", "kernelCode": "above_max", "device": "desk-fan", "channel": "fan_speed",
              "limit": "100 %", "requested": "150 %", "file": "desk-fan.hal.yaml", "confirmedBy": "sohan",
              "confirmedAt": "2026-10-24"}}}
→ {"jsonrpc": "2.0", "id": 7, "method": "hal/write",
   "params": {"device": "desk-fan", "channel": "fan_speed", "value": "60 %"}}
← {"jsonrpc": "2.0", "id": 7, "result": {"status": "done", "device": "desk-fan", "channel": "fan_speed",
     "value": 60, "unit": "%"}}
```

## Why a protocol

A tool serves one client. A protocol lets any client, in any language, meet any driver under the same rules. MCP remains the interface for agents and maps onto the same methods.

## MHS

Anthropic's Model Hardware Standard is a limited research preview for invited labs. OpenHAL is not affiliated with Anthropic or MHS. It is open source, usable today with simulators, and it plans to stay compatible.

## What it does not do

OpenHAL is not a safety system. It can't make firmware obey, and it doesn't replace e-stops, enclosures or interlocks wired in hardware. It checks each request against what a person allowed, and it stops every device on request.

The [quickstart](/docs/quickstart/) runs a hub with a simulated fan and needs no hardware.
