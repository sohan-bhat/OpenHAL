---
title: Why we built OpenHAL
description: Because agents can already drive hardware, OpenHAL defines one place where every command is checked against the limits a person confirmed.
date: 2026-10-24
author: OpenHAL contributors
draft: true
---

An agent can read a datasheet, code a serial protocol and move a motor in an afternoon, but no part of that path holds the limits a person would set or enforces those limits the same way for every client.

## The gap

Single-device tools exist for Arduino boards, 3D printers, bench instruments and robots. Each of these tools has its own model of a device and its own rules, and some of the tools have no rules at all. Because no two tools describe a device the same way, no single place checks what may run.

## The protocol

OpenHAL is an open protocol with a versioned specification, and the specification defines two things.

1. The [Device File](glossary:device-file) lists what a device can read and change, the limits on each change and the safe state. A person confirms the limits, and until then the file is read-only.
2. Clients send JSON-RPC 2.0 messages over the hub protocol to one [Hub](glossary:hub), and the hub's [Safety Kernel](glossary:safety-kernel) checks every command before a [Driver](glossary:driver) runs the command.

```yaml tested include=examples/print-babysitter/printer.hal.yaml
```

A request over a limit is blocked with a stable code, a registry name and a reason that cites the rule. A request inside every limit runs, and the hub holds a request that can't be undone until a person approves the request. This trace is recorded from the reference hub with a simulated printer and its webcam.

```scenario
```

## Why a protocol

A tool serves one client, but with a protocol any client, in any language, reaches any driver under the same rules. MCP remains the interface for agents and maps onto the same methods.

## MHS

Anthropic's Model Hardware Standard is a limited research preview for invited labs, and OpenHAL is not affiliated with Anthropic or MHS. OpenHAL is open source and usable today with simulators, and the project plans to stay compatible with MHS.

## What OpenHAL does not do

OpenHAL has no control over what a device's firmware does and doesn't replace e-stops, enclosures or interlocks wired in hardware, so OpenHAL is not a safety system. The hub checks each request against what a person allowed, and the hub stops every device on request.

The [quickstart](/docs/quickstart/) runs the print babysitter demo and needs no hardware.
