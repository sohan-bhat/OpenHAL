# Brief: the hub protocol (ADR 0015)

Read docs/agents/COMMON.md first.

## Goal

Implement the OpenHAL hub protocol exactly as docs/adr/0015-openhal-hub-protocol.md specifies, on top of the existing hub (openhal/hub/hub.py, openhal/kernel). The REST API stays and keeps passing its tests.

## Deliverables

1. **`openhal/protocol/` package**
   - `messages.py`: Pydantic models for every request, result, notification and error data in the ADR (initialize, devices/list, devices/describe, read, write, dryRun, stop, action, confirmations list, approve and reject, unlock, and the four notifications).
   - `errors.py`: the error registry, with numeric code, name, kernel codes and a reason template for each entry. Add a test that every kernel block code the kernel can emit maps to exactly one name. Grep openhal/kernel for every `Block("...")` and `code="..."`.
   - `dispatch.py`: one dispatcher, given a hub and a principal, that handles a parsed JSON-RPC message and returns a response. Both transports use it.
   - `version.py`: `PROTOCOL_VERSIONS = ["2026-10-24"]` and the negotiation rule.
   - The lifecycle rules: NOT_INITIALIZED before `hal/initialize`, and notifications only after `hal/initialized`.
   - LIMIT_EXCEEDED reasons read exactly like `fan_speed 150 % exceeds the limit of 100 % (desk-fan.hal.yaml, confirmed by owner 2026-11-02)`. Take the file name from the hub's DeviceInfo path, and the confirmer and date from the file's `confirmed`. Reasons for the other names come from templates too. Keep `data.kernelMessage`.
2. **WebSocket transport** at `/rpc` on the hub app.
   - Same auth and network guard as the REST API. The token goes in the Authorization header or in initialize params.
   - Notifications fan out from the hub's existing event stream (`hub._emit` / `/v1/live`).
3. **stdio transport.** `openhal rpc` bridges stdio lines to the hub's `/rpc` WebSocket. Add the command to the CLI. The CLI lives in openhal/cli/, and you may add `rpc_cmd.py` and register it in main.py.
4. **Conformance levels**
   - Add `conformance: Literal["core", "control", "full"]` to `DriverInfo`, defaulting to "control". Set "core" for read-only drivers (uvc, rpi-camera), and leave the rest at "control".
   - The hub reports "full" in initialize.
   - Extend the conformance suite (openhal/conformance/suite.py) so a Core driver is tested for Core only.
   - Add `conformance` to drivers/catalog.json through the generator (openhal/drivers/catalog.py), which can read it from DriverInfo or the package catalog entry.
5. **Schema reference generator.** `uv run python -m openhal.protocol.schema` writes `spec/2026-10-24/schema.json` (JSON Schema for every message) and `spec/2026-10-24/schema.md` (a generated reference with every type and field). Add a test that both are current.
6. **MCP mapping.** MCP tool errors carry the registry name, numeric code and reason. Change only what is needed in openhal/mcp/ for that.
7. **Message log for the Inspector**
   - The dispatcher records every JSON-RPC message it receives or sends, on either transport, in a ring buffer of the last 2,000. Each entry is `{ seq, at, direction: "in" | "out", client, principal, message }`.
   - Human principals only can read it: `GET /v1/rpc/log?since=<seq>` and a live feed at WebSocket `/v1/rpc/log/live`.
   - Tokens are never logged. Initialize params have `token` redacted.
8. **Tests** in tests/protocol/
   - Every method and every error name, over both transports. Use a real embedded hub with mock devices.
   - The exact LIMIT_EXCEEDED trace from the ADR.
   - Version negotiation.
   - Lifecycle ordering.
   - An agent can't approve, reject or unlock.
   - Malformed JSON gets PARSE_ERROR.
   - Batches are not supported in this version, so a batch gets INVALID_REQUEST.

## Files you own

openhal/protocol/, tests/protocol/, openhal/cli/rpc_cmd.py, the `/rpc` and `/v1/rpc/log` routes in openhal/hub/api.py, the DriverInfo field in openhal/drivers/base.py, openhal/conformance/suite.py, openhal/drivers/catalog.py, the drivers' DriverInfo lines, error mapping in openhal/mcp/, and spec/2026-10-24/schema.json and schema.md.

## Not yours

The spec prose (another workstream writes spec/2026-10-24/*.md), the website, the Inspector, README.md and docs/DESIGN.md.
