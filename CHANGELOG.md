# Changelog

Every notable change to OpenHAL is listed here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). The package version is MAJOR.MINOR.PATCH, and the specification and the hub protocol carry MAJOR.MINOR, as [ADR 0017](docs/adr/0017-version-numbers.md) sets out.

## [Unreleased]

## [0.1.0] - 2026-11-05

The first release. Every driver is tested on a simulator, and none is tested on real hardware yet.

### Added

- Specification v0.1, with the device file format (`.hal.yaml`), the hub protocol over JSON-RPC, the error registry and a conformance suite for drivers.
- The safety kernel. Every write and action goes through the kernel, which checks units, limits, rate of change, interlocks, watchdogs, scope and confirmation before a driver acts. A driver acts only on a single-use grant for that exact command.
- Risk levels. Each channel and action is low, medium or high risk. Low and medium targets take commands within the device's own range, and a high risk target stays read-only until a person confirms its limits.
- One stop puts every device in its safe state, and every decision goes into a hash-chained audit log.
- Each change that runs records the first 12 hex digits of its grant and the commands the driver sent to the device in the audit log.
- The hub, with a REST API, the hub protocol over WebSocket and over stdio with `openhal rpc`, and an MCP server with 36 tools through `openhal mcp`.
- The `openhal` command line. `openhal init` sets up the config folder, tokens, devices, MCP clients and the background service, and `openhal start` runs the hub.
- `openhal demo`, an agent babysitting a 3D print on a simulated Klipper printer and camera, with no hardware and no API key. `openhal demo --full` runs the whole system with a simulated plant waterer.
- 36 hardware drivers, from serial, Firmata and the OpenHAL Arduino library to Klipper, OctoPrint, SCPI instruments, Home Assistant, ESPHome, MQTT, Modbus, ROS 2, OPC UA, research microscopes through Micro-Manager and Ocean spectrometers through python-seabreeze. Each driver passes the conformance suite against a simulator, and none is verified on real hardware yet.
- A MuJoCo driver that runs any MuJoCo model as a simulated device.
- The OpenHAL Arduino library, which describes a board to the hub and offers each free pin as a channel.
- A device library of 35 device files. Every file is unverified until a person checks the file's limits.
- The Inspector, a browser dashboard for devices, held requests, limits and the audit log.
- The driver writer, which drafts a device file for an unknown device, and routines and runs for timed steps.
- The Python client, `openhal.connect` and `openhal.aconnect`.
- One-line installers for macOS, Linux and Windows, a Raspberry Pi install script, and a background service with launchd on macOS and systemd on Linux.
- The `halkit` command, the same CLI as `openhal`, so `uvx halkit demo` and `pipx run halkit demo` run with no clone.
- The `/openhal` command for Claude Code. `openhal init` saves the command when init adds OpenHAL to Claude Code, and the Claude Code plugin ships the same command. A bare `/openhal` checks the connection and shows what the agent may do on each device.

[Unreleased]: https://github.com/sohan-bhat/OpenHAL/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/sohan-bhat/OpenHAL/releases/tag/v0.1.0
