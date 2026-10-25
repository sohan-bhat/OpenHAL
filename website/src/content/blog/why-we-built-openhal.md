---
title: Why we built OpenHAL
description: AI agents can already write the code that moves a motor. Nothing stood between that code and the motor. OpenHAL is that layer, and it is open.
date: 2026-10-24
author: OpenHAL contributors
draft: true
---

An AI agent can read a datasheet, write a serial protocol and drive a stepper in an afternoon. What it can't do is know that the fan next to your plant should never run flat out for ten minutes, or that the heater on the same bench needs that fan moving first. Somebody has to write that down, and something has to enforce it every time, no matter which agent is asking.

## Every tool is an island

When we looked at what exists, we found good single-device tools. There are MCP servers for Arduino boards, for 3D printers, for bench instruments over SCPI and for ROS robots. Home Assistant has its own. Each one has its own idea of a device and its own safety rules, and several have none. Nothing describes a device the same way twice, nothing enforces limits in one place, and nothing lets a routine span a printer and a power supply under the same rules.

## One file per device, one place that decides

OpenHAL gives every device a small file that says what can be read, what can be changed, the limits on each change and the safe state. A person confirms those limits. Until then the file is read-only, and no agent can confirm it on anyone's behalf.

A local hub owns every device. Every write and every action, from an MCP client, the command line, a Python script, a routine or the dashboard, goes through one safety kernel. The kernel is plain code with no model in it. It checks units, range, step, rate of change, interlocks and confirmation, in a fixed order, and it fails closed. If it can't trust a value, the command is blocked.

```yaml tested
device: Desk fan controller
id: desk-fan
connect: { serial: auto, board: arduino-uno }
read:
  temperature: { unit: degC, every: 1 s }
write:
  fan_speed: { unit: percent, min: 0, max: 100, max_change_per_s: 20 }
safe_state: { fan_speed: 0 }
notes: "Fan is next to the plant. Never run above 80 for more than 10 minutes."
```

## The limit line

Real gauges have a red line where you must not go. We drew every limit in OpenHAL the same way, in the dashboard, on this site and in the playground. When the kernel blocks a command, you see the attempt land past the line and the reason underneath it, in words that name the rule.

## Why open, and why now

Anthropic previewed the Model Hardware Standard in August 2026. It is for labs and advanced manufacturing, in a closed preview. Makers, teaching labs and small labs can't get in, and they are the people with a bench full of equipment and an AI client already open.

MHS is for labs, in a closed preview. OpenHAL is open and works today. We plan to be compatible. Device files use the same read and write idea, so they can map onto MHS once its spec is public.

## What it doesn't do

OpenHAL is not a safety system. It can't make firmware obey, and it doesn't replace an e-stop, an enclosure or an interlock wired in hardware. It makes sure that what an agent asks for is checked against what a person allowed, every time, and it gives you one button that stops everything.

The [quickstart](/docs/quickstart/) takes about ten minutes and needs no hardware.
