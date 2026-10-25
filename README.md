<h1 align="center">OpenHAL</h1>

<h3 align="center">One open layer between AI agents and real hardware.</h3>

<p align="center">Agents read and control your devices. A safety kernel checks every change first.</p>

<p align="center">
  <a href="#quickstart"><img alt="Python 3.12+" src="https://img.shields.io/badge/python-3.12%2B-2D5B8C?logo=python&logoColor=white"></a>
  <a href="docs/interfaces/MCP.md"><img alt="MCP server" src="https://img.shields.io/badge/MCP-server-15181B"></a>
  <a href="docs/drivers/COVERAGE.md"><img alt="Drivers" src="https://img.shields.io/badge/drivers-17%20protocols-276B43"></a>
  <a href="#quickstart"><img alt="Platforms" src="https://img.shields.io/badge/runs%20on-macOS%20%7C%20Raspberry%20Pi-2B3035"></a>
  <a href="LICENSE"><img alt="License Apache-2.0" src="https://img.shields.io/badge/license-Apache--2.0-F2B705"></a>
  <img alt="Status" src="https://img.shields.io/badge/status-v0.1%20in%20development-B3261E">
</p>

```
$ openhal write demo-fan.fan_speed 150%
blocked above_max  Blocked. The fan_speed limit is 100 % (max). Asked for 150 %.
```

## Quickstart

```
git clone https://github.com/sohan-bhat/OpenHAL.git && cd OpenHAL
uv sync --all-extras
uv run openhal init
uv run openhald
```

Then, in a second terminal.

```
uv run openhal read demo-fan.temperature
```

`init` adds a simulated desk fan, so no hardware is needed. To connect Claude or another MCP client, see [docs/interfaces/MCP.md](docs/interfaces/MCP.md).

## How it works

- **Device files** describe what a device can read and change, with units and limits.
- **Drivers** speak the protocols. Serial, SCPI, Modbus, MQTT, BLE, MIDI, HID, Klipper, Home Assistant and more.
- **The safety kernel** checks ranges, rates, interlocks and confirmations, and a stop puts every device in its safe state.

A device stays read-only until a person confirms its limits. An AI can never confirm them.

## Docs

[Safety model](docs/SAFETY.md) · [Architecture](docs/ARCHITECTURE.md) · [Device file spec](spec/SPEC.md) · [Drivers](docs/drivers/COVERAGE.md) · [CLI](docs/interfaces/CLI.md) · [Python](docs/interfaces/PYTHON.md) · [Arduino library](firmware/arduino/OpenHAL/README.md)

## License

Apache-2.0
