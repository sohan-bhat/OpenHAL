---
title: Why we built OpenHAL
description: Agents can already drive hardware, so OpenHAL checks every command in one place against limits a person confirmed.
date: 2026-10-24
author: OpenHAL contributors
draft: true
---

An agent can read a datasheet, code a serial protocol and move a motor in an afternoon. Single-device tools for boards, printers, instruments and robots each bring a different device model and different rules, so no single place checks what may run.

## The protocol

OpenHAL is an open protocol with a versioned specification that defines two things.

1. The [Device File](glossary:device-file) lists what a device reads and changes, the limits on each change and the safe state. High risk channels and actions stay read-only until a person confirms the limits.
2. Clients send JSON-RPC 2.0 messages to one [Hub](glossary:hub), and the hub's [Safety Kernel](glossary:safety-kernel) checks every command before a [Driver](glossary:driver) runs the command.

```yaml tested include=examples/print-babysitter/printer.hal.yaml
```

A request over a limit is blocked with a stable code, a registry name and a reason that cites the rule. A request inside every limit runs, and the hub holds a request that can't be undone until a person approves. These steps come from the reference hub with a simulated printer and webcam.

```scenario
```

## Why a protocol

A tool serves one client. With a protocol, any client in any language reaches any driver under the same rules, and MCP maps onto the same methods.

## MHS

Anthropic's Model Hardware Standard is a limited research preview for invited labs. OpenHAL is not affiliated with Anthropic or MHS, and the project plans to stay compatible with MHS.

## What OpenHAL does not do

OpenHAL is not a safety system. Firmware still controls each device, and OpenHAL doesn't replace e-stops, enclosures or hardware interlocks.

The [quickstart](/docs/quickstart/) runs the print babysitter demo with no hardware.
