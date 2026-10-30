# OpenHAL specification

Version v0.1. Status draft.

## Introduction

OpenHAL is an open protocol for AI agents to discover, read and control hardware safely. This specification defines two things.

1. The Device File format. A Device File describes one Device, what can be read, what can be changed, the limits on every change, the safe state, and where the description came from.
2. The hub protocol. Clients connect to one Hub and send requests over JSON-RPC 2.0. The Hub owns every Device, and its Safety Kernel evaluates every command before a Driver may touch hardware.

OpenHAL is an open protocol with a specification. It is not a standard. OpenHAL is not affiliated with Anthropic or with Anthropic's Model Hardware Standard (MHS).

The reference implementation is the `openhal` Python package in this repository. Where this document and the reference implementation differ, this document is normative and the difference is a bug.

## Status

This is a draft. It may change before it is marked final. Changes are recorded in the [changelog](changelog.md). `spec/versions.json` names the latest version and the status of every version.

## Conformance keywords

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD", "SHOULD NOT", "RECOMMENDED", "NOT RECOMMENDED", "MAY", and "OPTIONAL" in this document are to be interpreted as described in BCP 14, [RFC 2119](https://www.rfc-editor.org/rfc/rfc2119) and [RFC 8174](https://www.rfc-editor.org/rfc/rfc8174), when, and only when, they appear in all capitals, as shown here.

Examples, notes and diagrams are informative. Everything else is normative.

## Documents

| Section | Covers |
|---|---|
| [Architecture](architecture.md) | Roles, the one-hub model and the path of one command |
| [Lifecycle](basic/lifecycle.md) | Initialization and version negotiation |
| [Transports](basic/transports.md) | WebSocket and stdio |
| [Messages](basic/messages.md) | JSON-RPC rules, every method and notification, with examples |
| [Device files](device-files.md) | The Device File format |
| [Safety](safety.md) | Requirements on a Safety Kernel and the error code registry |
| [Drivers](drivers.md) | The Driver interface and Conformance Levels |
| [Routines](routines.md) | Automations that run without a model |
| [Security](security.md) | Network exposure, tokens, prompt injection and limits of the guarantees |
| [Schema reference](schema.md) | Every message type and field, generated from the reference models ([schema.json](schema.json)) |
| [Changelog](changelog.md) | Changes in each version |

## Versions

Versions of this specification are numbered `MAJOR.MINOR`, such as `0.1`, and people see them with a leading v, as v0.1. Each version lives in `spec/v<version>/`, and [VERSIONING.md](../VERSIONING.md) explains what the numbers mean. The Device File format carries its own version number in the file's `openhal` field ([Device files](device-files.md#versioning)). This version of the specification defines Device File format 0.1.

## Terminology

Defined terms are capitalized wherever they appear.

| Term | Definition |
|---|---|
| Hub | The one process that owns every Device, its Driver, the Safety Kernel, the confirmation queue and the audit log. Clients reach Devices only through a Hub. |
| Client | A program that connects to a Hub and sends requests. An MCP server, a command line tool, the Inspector and a script are all Clients. |
| Device | One piece of hardware, or one set of entities in a bridged system, described by one Device File and registered with a Hub under a unique id. |
| Device File | A YAML document ending in `.hal.yaml` that describes one Device, its channels, actions, limits, safe state and provenance. |
| Driver | Code that communicates with Devices over one protocol. A Driver changes hardware only when it consumes a Grant. |
| Safety Kernel | The deterministic part of a Hub that evaluates every command against the Device File and the current state, and issues Grants for the ones that pass. |
| Grant | A single-use permission the Safety Kernel issues for exactly one operation, bound to one Device, one target and one value, with an expiry. |
| Principal | The identity behind a request. Its kind is `human`, `agent`, `routine` or `system`, and it carries a scope. |
| Conformance Level | One of `core`, `control` or `full`. It names the methods a Hub implements, or the capabilities a Driver supports. |
| Confirmation Request | A command that passed every check except confirmation and that the Hub holds in its queue until a human Principal approves or rejects the command, or until the request expires. |

Other terms are used in their plain sense. A channel is a named value on a Device. A read channel can be read. A write channel can be read and changed. An action is a named operation with typed arguments. A command is one change to a write channel or one run of an action. A safe state is the set of steps that leaves a Device safe to leave unattended. A routine is an automation that runs on the Hub without a model.
