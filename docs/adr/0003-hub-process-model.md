# 0003 One hub process owns every device, every client is a thin client

## Context

Safety rules must be enforced in one place. Agents reach OpenHAL through MCP (usually a stdio subprocess launched by the AI client), people through the CLI and dashboard, scripts through the Python library, and routines run unattended.

## Options considered

1. Every interface embeds its own kernel and opens devices directly. Two clients could drive the same device with separate rate-limit state. Rejected.
2. One daemon owns all devices and the kernel. Every interface is a client of its local API.
3. Option 2 plus an embedded mode where the same hub object runs inside one process, for tests, the demo and scripts that want no daemon.

## Decision

Option 3.

- `openhald` is the only process that opens hardware. It owns the registry, drivers, safety kernel, routine engine, audit log, confirmation queue and the local HTTP and WebSocket API on 127.0.0.1:7420.
- `openhal mcp` is a stdio MCP server that forwards every tool call to the daemon with its agent token.
- The CLI and the Python library are clients of the same API.
- The embedded hub (`openhal.Hub`) is the same class the daemon runs. It is used by tests, `openhal demo` and scripts that opt in. Embedded and daemon mode can't both open the same device because the hub takes an exclusive lock file per device port.

## Consequences

- Rate limits, interlocks across devices and watchdogs see every command no matter which interface sent it.
- MCP startup needs the daemon running. `openhal mcp` starts it if it is not running and prints a clear error if it can't.
