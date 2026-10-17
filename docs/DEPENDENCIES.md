# Dependencies

Every third-party dependency, the version resolved in uv.lock when it was added, its license and why it is used. Driver dependencies are optional extras and are added by the driver that needs them.

Copyleft code is never copied into this repository. Libraries under weak copyleft licenses (LGPL, MPL) are used only as unmodified dependencies.

## Core

| Package | Version | License | Why |
|---|---|---|---|
| pydantic | 2.14.1 | MIT | Device file, command and API models |
| pint | 0.26.2 | BSD-3-Clause | The one unit registry (ADR 0005) |
| PyYAML | 6.0.3 | MIT | Device file parsing with a restricted safe loader |
| typer | 0.27.3 | MIT | CLI |
| rich | 15.0.0 | MIT | CLI output |

## Hub extra

| Package | Version | License | Why |
|---|---|---|---|
| fastapi | 0.162.0 | MIT | Local HTTP and WebSocket API |
| uvicorn | 0.54.0 | BSD-3-Clause | ASGI server for the hub |
| websockets | 17.3 | BSD-3-Clause | Live values to the dashboard, Moonraker and Home Assistant clients |
| httpx | 0.28.1 | BSD-3-Clause | Client library, HTTP drivers and bridges |
| mcp | 2.3.0 | MIT | Official MCP Python SDK |
| zeroconf | 0.151.5 | LGPL-2.1-or-later | mDNS discovery. Used unmodified as a dependency |

## Development

| Package | Version | License | Why |
|---|---|---|---|
| pytest | 9.1.1 | MIT | Tests |
| pytest-asyncio | 1.4.0 | Apache-2.0 | Async tests |
| pytest-cov | 7.1.0 | MIT | Coverage |
| hypothesis | 6.170.9 | MPL-2.0 | Property tests for the safety kernel. Development only |
| ruff | 0.17.2 | MIT | Lint and format |
| mypy | 2.4.0 | MIT | Type checks |
