# 0001 Python 3.12+ managed with uv for the hub and everything around it

## Context

The hub, drivers, safety kernel, CLI, MCP server, Python library and driver writer must share one codebase. The hardware ecosystem OpenHAL wraps (pyserial, PyVISA, pymodbus, bleak, mido, hidapi, gpiozero, picamera2, aioesphomeapi, asyncua, roslibpy, PyLabRobot, LeRobot) is overwhelmingly Python.

## Options considered

1. Python 3.12+ with uv.
2. Rust core with Python bindings. Stronger isolation and performance, but every driver would still be Python and the binding layer adds a second safety surface.
3. TypeScript on Node. Good for MCP and the dashboard, weak hardware library coverage.

## Decision

Python 3.12+ for all hub-side code, managed with uv, packaged with hatchling. asyncio throughout the hub. Pydantic v2 for models, pint for units, Typer for the CLI, FastAPI for the local API, the official MCP Python SDK for the MCP server, SQLite through the standard library for storage.

## Consequences

- One language for the safety path and every driver.
- Drivers are in-process Python, so a malicious driver is trusted code. The kernel guarantees that no OpenHAL code path other than the kernel reaches a driver's write method (ADR 0004), and the threat model states the remaining risk honestly.
- The dashboard and website are TypeScript (ADR 0008, ADR 0009) and talk to the hub only through the local API.
