# 0015 The OpenHAL hub protocol is JSON-RPC 2.0, versioned by date

## Context

OpenHAL is presented and specified as an open protocol, the way MCP is. Until now clients spoke a REST API (ADR 0012, 0014). A protocol needs one message format that any language can implement, with lifecycle, transports, structured errors and conformance levels. MCP stays the agent-facing interface and maps onto the protocol's methods.

## Decision

### Messages and transports

- Messages are JSON-RPC 2.0 requests, responses and notifications, UTF-8 JSON.
- Transports
  - **WebSocket** at `ws://127.0.0.1:7420/rpc`, one JSON-RPC message per text frame. Auth is the same bearer token as the REST API, in the `Authorization` header or in `hal/initialize` params `token`.
  - **stdio**, one JSON-RPC message per line, through `openhal rpc`, which bridges stdio to the hub's WebSocket for clients that spawn a process.
- The REST API (`/v1`) stays as a convenience for the dashboard and scripts. Both front ends call the same hub functions, so behavior is identical.

### Versions

- Spec versions are dated, `YYYY-MM-DD`. The first is **2026-10-24**. Each version lives in `spec/<version>/` with its own changelog entry, and `spec/versions.json` names `latest`.
- `hal/initialize` negotiates the version. The client sends the newest it supports, and the hub answers with that version or the newest it supports. A client that can't use the answer disconnects.

### Lifecycle

1. The client sends `hal/initialize` `{ protocolVersion, clientInfo: { name, version }, token? }`.
2. The hub answers `{ protocolVersion, hubInfo: { name, version }, conformance: "core" | "control" | "full", principal: { kind, name, scope }, capabilities: { notifications: [...] } }`.
3. The client sends the notification `hal/initialized`. The hub sends no other notification before it.
4. Any other method before `hal/initialize` gets error `NOT_INITIALIZED`.
5. Shutdown. The client sends the notification `hal/shutdown` and closes the transport. The hub releases nothing on its behalf, because devices belong to the hub.

### Methods

| Method | Params | Result | Level |
|---|---|---|---|
| `hal/initialize` | as above | as above | Core |
| `hal/devices/list` | `{}` | `{ devices: [DeviceSummary] }` | Core |
| `hal/devices/describe` | `{ device }` | `{ device: DeviceDescription }` (channels, units, limits, actions, safe state, hazard, conformance, verification, limits provenance) | Core |
| `hal/read` | `{ device, channel }` | `{ device, channel, value, unit, at, suspect }` | Core |
| `hal/readMany` | `{ items: [{ device, channel }] }` | `{ readings: [Reading or error] }` | Core |
| `hal/write` | `{ device, channel, value, unit }`, a number with its unit apart (ADR 0016), or a bool or enum | `{ status: "done", device, channel, value, unit }` or `{ status: "pending", requestId, expiresInS }` | Control |
| `hal/dryRun` | `{ commands: [Write or Action] }` | `{ decisions: [Decision] }` | Control |
| `hal/planCheck` | `{ steps: [Write, Action or wait] }` | `{ ok, decisions: [Decision], problems: [str] }` | Control |
| `hal/stop` | `{ reason? }` | `{ devices: [{ device, status, detail }] }` | Control |
| `hal/action` | `{ device, action, args }` | `{ status, result }` or pending | Full |
| `hal/confirmations/list` | `{ status? }` | `{ requests: [ConfirmationRequest] }` | Full |
| `hal/confirmations/approve` | `{ requestId }` (human principal only) | `Decision` | Full |
| `hal/confirmations/reject` | `{ requestId, reason? }` (human only) | `ConfirmationRequest` | Full |
| `hal/unlock` | `{ phrase: "unlock" }` (human only) | `{ ok }` | Control |
| `hal/routines/list` | `{}` | `{ routines: [RoutineSummary] }` | Full |
| `hal/routines/dryRun` | `{ routineId }` | `{ ok, decisions: [Decision], problems: [str] }` | Full |
| `hal/audit/query` | `{ device?, status?, event?, since?, limit? }` | `{ entries: [AuditEntry] }` | Full |

Notifications from the hub, after `hal/initialized`:

| Notification | Params | Level |
|---|---|---|
| `hal/value` | `{ device, channel, value, unit, at, suspect }` | Core |
| `hal/blocked` | `{ device, target, error: { code, message, data: { name, ... } } }` | Control |
| `hal/stopped` | `{ reason, by, devices: [{ device, status }] }` | Control |
| `hal/deviceAdded` | `{ device: DeviceSummary }` | Core |
| `hal/deviceRemoved` | `{ device }` | Core |
| `hal/confirmationRequested` | `{ request: ConfirmationRequest }`, sent only to human principals and to the principal that made the request | Full |

Clients subscribe to all notifications by default. A later version may add filters.

### Error registry

A blocked or failed command is a JSON-RPC error. `error.code` is the number, `error.message` is the human-readable reason, and `error.data` is `{ name, kernelCode, kernelMessage?, device?, channel?, action?, limit?, requested?, file?, confirmedBy?, confirmedAt?, tightenedBy?, requestId?, method?, routine?, problems? }`. `limit` and `requested` are Quantity objects such as `{"value": 100, "unit": "%"}` (ADR 0016). `name` is the registry name and is what clients branch on. Numbers are stable across versions and never reused.

| Code | Name | Kernel codes | Meaning |
|---|---|---|---|
| -32700 | PARSE_ERROR | | Invalid JSON |
| -32600 | INVALID_REQUEST | | Not a JSON-RPC request |
| -32601 | METHOD_NOT_FOUND | | Unknown method, or one above the hub's conformance level |
| -32602 | INVALID_PARAMS | `bad_request` | Params don't match the schema |
| -32603 | INTERNAL_ERROR | `internal_error` | A bug in the hub |
| -32001 | NOT_INITIALIZED | | `hal/initialize` hasn't run |
| -32002 | UNAUTHORIZED | | Missing or unknown token |
| -32003 | SCOPE_DENIED | `not_permitted` | The principal's token scope doesn't cover this device or method |
| -32004 | UNKNOWN_TARGET | `unknown_target` | No such device, channel or action |
| -32005 | DEVICE_UNAVAILABLE | `device_unavailable` | Disconnected or not ready |
| -32010 | LIMIT_EXCEEDED | `above_max`, `below_min` | Outside the device file's confirmed limits |
| -32011 | RATE_LIMITED | `rate_limited` | Faster than `max_change_per_s` allows right now |
| -32012 | INTERLOCK_BLOCKED | `interlock` | An interlock or action requirement doesn't hold, or a value it needs is unknown |
| -32013 | CONFIRMATION_REQUIRED | `needs_confirmation` | Queued for a person, `data.requestId` names the request |
| -32014 | STOPPED | `stopped` | The hub is stopped until a person unlocks |
| -32015 | UNVERIFIED_LIMITS | `read_only_file` | The device file's limits aren't confirmed by a person, so it is read-only |
| -32016 | INVALID_VALUE | `bad_value`, `bad_step` | Wrong type, step, enum value or pattern |
| -32017 | WATCHDOG_TRIPPED | `duration_exceeded` | A watchdog budget is used up |
| -32018 | BUSY | `busy` | Another command holds the device |
| -32019 | QUEUE_FULL | `queue_full` | The confirmation queue is full |
| -32020 | DRIVER_ERROR | `driver_error` | The device or its protocol failed, and the channel is unknown until a readback |
| -32021 | MISCONFIGURED | `misconfigured`, `cannot_loosen` | The hub's device files are inconsistent, or a change would loosen a confirmed limit |
| -32022 | REQUEST_CLOSED | `expired`, `rejected` | The confirmation request expired or was rejected. An unknown request id gets the same answer with `kernelCode: "expired"`, so a client can't learn another principal's request ids |
| -32023 | UNIT_INVALID | `bad_unit` | A missing, unknown or incompatible unit, or a value that isn't finite |

Every kernel code maps to exactly one name. A test enforces this.

Pending versus CONFIRMATION_REQUIRED. `hal/write` and `hal/action` answer a command that needs a person with the result `{ status: "pending", requestId, expiresInS }`, and the hub sends `hal/confirmationRequested`. The error CONFIRMATION_REQUIRED is for callers that cannot hold a pending request, such as a routine step or a command inside `hal/planCheck`, and carries `data.requestId` when a request was queued.

Reason messages are formed from `data`, one template per name. LIMIT_EXCEEDED reads `fan_speed 150 % exceeds the limit of 100 % (desk-fan.hal.yaml, confirmed by sohan 2026-10-24)`. The kernel's own message stays available as `data.kernelMessage`. When the limit that blocked the write is one a principal tightened for its session, the reason names that instead and never cites the file's confirmation, for example `fan_speed 80 % exceeds the session limit of 70 % (tightened by claude)`. Below the minimum reads `fan_speed -5 % is below the limit of 0 % (desk-fan.hal.yaml, confirmed by sohan 2026-10-24)`.

### Conformance levels

- **Core.** Initialize, list, describe, read, `hal/value`.
- **Control.** Core plus write, dry run, stop, unlock, `hal/blocked`, `hal/stopped`, all through a safety kernel that meets the Safety section of the spec.
- **Full.** Control plus actions, routines and confirmations.

Hubs declare their level in `hal/initialize`. Drivers declare theirs in `DriverInfo.conformance` (a read-only camera driver is Core). The conformance suite tests the declared level and nothing above it. The reference hub is Full.

### MCP mapping

| MCP tool | Method |
|---|---|
| `hub_status` | `hal/initialize` result |
| `list_devices` | `hal/devices/list` |
| `describe_device` | `hal/devices/describe` |
| `read` | `hal/read` |
| `read_many` | `hal/readMany` |
| `write` | `hal/write` |
| `action` | `hal/action` |
| `dry_run` | `hal/dryRun` |
| `plan_check` | `hal/planCheck` |
| `stop_all` | `hal/stop` |
| `get_confirmation_status` | `hal/confirmations/list` |
| `list_routines` | `hal/routines/list` |
| `run_routine_dry` | `hal/routines/dryRun` |
| `get_audit_log` | `hal/audit/query` |

Routine drafting, discovery and driver writer tools stay MCP and REST only in this version.

MCP tool results carry the same error names, codes and messages.

### Spec text

The specification uses MUST, SHOULD and MAY as in RFC 2119 and RFC 8174. Its schema reference is generated from the Pydantic models in `openhal/protocol/`, never written by hand.

## Consequences

- The hub gains `openhal/protocol/` (message models, the error registry, a dispatcher used by the WebSocket and stdio front ends) and `openhal rpc`.
- The website, README and Inspector show exchanges as message traces with these exact names.
- Not affiliated with Anthropic or MHS. OpenHAL is an open protocol with a specification, not a standard.
