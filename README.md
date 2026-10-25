<h1 align="center">OpenHAL</h1>

<h3 align="center">One open layer between AI agents and real hardware.</h3>

<p align="center">Agents read and control your devices. A safety kernel checks every change first.</p>

<p align="center">
  <a href="#quickstart"><img alt="Python 3.12+" src="https://img.shields.io/badge/python-3.12%2B-2D5B8C?logo=python&logoColor=white"></a>
  <a href="docs/interfaces/MCP.md"><img alt="MCP server" src="https://img.shields.io/badge/MCP-server-15181B"></a>
  <a href="docs/drivers/COVERAGE.md"><img alt="17 drivers, simulator tested" src="https://img.shields.io/badge/drivers-17%2C%20simulator%20tested-276B43"></a>
  <a href="LICENSE"><img alt="License Apache-2.0" src="https://img.shields.io/badge/license-Apache--2.0-F2B705"></a>
  <img alt="Status v0.1 in development" src="https://img.shields.io/badge/status-v0.1%20in%20development-2B3035">
</p>

<p align="center"><img src="docs/assets/openhal-diagram.png" alt="Clients such as Claude Desktop, Claude Code, Cursor and the Python library connect to OpenHAL over MCP or its API. Inside OpenHAL, device files feed the safety kernel, which blocks a fan speed of 150 percent against a limit of 100 percent, and only granted commands reach the drivers. The drivers connect to 3D printers, bench instruments, Arduino and ESP32 boards, smart home devices, cameras and sensors." width="100%"></p>

## Quickstart

```
git clone https://github.com/sohan-bhat/OpenHAL.git && cd OpenHAL
uv sync --all-extras
uv run openhal init
uv run openhald
```

`init` adds a simulated desk fan, so no hardware is needed. Connect your AI client with [docs/interfaces/MCP.md](docs/interfaces/MCP.md).

## Docs

[Safety model](docs/SAFETY.md) · [Device file spec](spec/SPEC.md) · [Drivers](docs/drivers/COVERAGE.md) · [Architecture](docs/ARCHITECTURE.md) · [Arduino library](firmware/arduino/OpenHAL/README.md)

## License

Apache-2.0
