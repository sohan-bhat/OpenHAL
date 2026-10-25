# Messages

## JSON-RPC rules

1. Every message MUST be a JSON-RPC 2.0 request, response or notification, with `"jsonrpc": "2.0"`.
2. A request MUST carry an `id` that is a string or a number. The Hub answers each request with exactly one response carrying the same `id`.
3. A notification has no `id` and gets no response.
4. `params` MUST be an object. Positional params are not supported.
5. Batches are not supported in this version. The Hub answers a JSON array with `INVALID_REQUEST` (-32600).
6. Text that is not valid JSON gets `PARSE_ERROR` (-32700). Valid JSON that is not a request gets `INVALID_REQUEST` (-32600).
7. An unknown method, or one above the Hub's Conformance Level, gets `METHOD_NOT_FOUND` (-32601).
8. Params that don't match the method's schema get `INVALID_PARAMS` (-32602). Unknown param names are invalid.
9. Field names are camelCase. Method names use the `hal/` prefix.

The [schema reference](../schema.md) defines every type and field. It is generated from the reference models and wins over the summaries on this page.

## Errors

A blocked or failed command is a JSON-RPC error response.

| Field | Content |
|---|---|
| `error.code` | The registry number ([Safety](../safety.md#error-registry)) |
| `error.message` | The human-readable reason, formed from `data` by the name's template |
| `error.data.name` | The registry name. Clients MUST branch on `name`, not on the message |
| `error.data.kernelCode` | The Safety Kernel's code, for example `above_max` |
| `error.data.kernelMessage` | The Safety Kernel's own message |
| `error.data.device`, `channel` | The target, when there is one |
| `error.data.limit`, `requested` | The limit and the requested value as quantity strings, such as `"100 %"` or `"20 %/s"` |
| `error.data.file`, `confirmedBy`, `confirmedAt` | The Device File and the human confirmation behind the limit |
| `error.data.requestId` | The Confirmation Request, for `CONFIRMATION_REQUIRED` and `REQUEST_CLOSED` |
| `error.data.action` | The action, for errors about `hal/action` |
| `error.data.tightenedBy` | The Principal that tightened a session limit, for a `LIMIT_EXCEEDED` caused by it |
| `error.data.method` | The method, for `METHOD_NOT_FOUND` and for `SCOPE_DENIED` on a human-only method |
| `error.data.routine` | The routine, for errors raised by a routine step |
| `error.data.problems` | Each schema problem, for `INVALID_PARAMS` |

Fields that don't apply are omitted.

## Values

- A numeric value sent to the Hub MUST be a quantity string with a unit, such as `"60 %"` or `"85 degF"`. A bare number is refused with `UNIT_INVALID`.
- A `bool` channel takes `true` or `false`. An `enum` channel takes one of its values as a string. A `string` channel takes a string.
- A numeric value sent by the Hub is a number in the channel's declared unit, with that unit in `unit`.
- `at` is the time a value was observed, as an RFC 3339 timestamp in UTC.
- `suspect` is `true` when a reading lies outside its channel's `range` ([Device files](../device-files.md#3-read-channels)).

## Types

| Type | Summary |
|---|---|
| `DeviceSummary` | `id`, `name`, `model`, `manufacturer`, `driver`, `hazard`, `writable`, `connected`, `conformance`, `verification` and `unavailable` (why the Device can't take commands right now, or null) |
| `DeviceDescription` | A `DeviceSummary` plus channels with units and limits, actions, safe state, interlocks, watchdog rules, limits provenance (who confirmed and when, and what is still unconfirmed) and notes as a data block |
| `Reading` | `{ device, channel, value, unit, at, suspect }` |
| `Write` | `{ kind: "write", device, channel, value }` |
| `Action` | `{ kind: "action", device, action, args }`, with numeric `args` as quantity strings |
| `Wait` | `{ kind: "wait", duration }`, with `duration` a quantity of time such as `"2 s"`, at most 1 h |
| `Decision` | `{ status, device, target, value, unit, error?, requestId? }`. `target` is `write:<channel>` or `action:<name>`. `error` has the shape of a JSON-RPC error object |
| `ConfirmationRequest` | `{ requestId, status, command, requestedBy, createdAt, expiresAt, decidedBy? }`. `command` is a `Write` or an `Action` |
| `RoutineSummary` | `{ id, kind, enabled, sha256, devices, maxHazard, triggers, disabledReason? }` |
| `AuditEntry` | `{ seq, at, event, principal, device?, target?, status?, code?, body, hash }` |

A Decision's `status` is one of these.

| Status | Meaning |
|---|---|
| `allowed` | A dry run would run it now |
| `needs_confirmation` | A dry run would queue it for a human |
| `blocked` | The Safety Kernel refuses it. `error` names the reason |
| `done` | It ran |
| `pending` | It waits in the confirmation queue. `requestId` names the request |
| `failed` | It reached the Driver and failed. The affected channels are unknown until a readback |

A ConfirmationRequest's `status` is `pending`, `approved`, `rejected`, `expired`, `cancelled`, `blocked`, `done` or `failed`.

## Methods

| Method | Level | Section |
|---|---|---|
| `hal/initialize` | Core | [Lifecycle](lifecycle.md) |
| `hal/devices/list` | Core | [below](#haldeviceslist) |
| `hal/devices/describe` | Core | [below](#haldevicesdescribe) |
| `hal/read` | Core | [below](#halread) |
| `hal/readMany` | Core | [below](#halreadmany) |
| `hal/write` | Control | [below](#halwrite) |
| `hal/dryRun` | Control | [below](#haldryrun) |
| `hal/planCheck` | Control | [below](#halplancheck) |
| `hal/stop` | Control | [below](#halstop) |
| `hal/unlock` | Control | [below](#halunlock) |
| `hal/action` | Full | [below](#halaction) |
| `hal/confirmations/list` | Full | [below](#halconfirmationslist) |
| `hal/confirmations/approve` | Full | [below](#halconfirmationsapprove) |
| `hal/confirmations/reject` | Full | [below](#halconfirmationsreject) |
| `hal/routines/list` | Full | [below](#halroutineslist) |
| `hal/routines/dryRun` | Full | [below](#halroutinesdryrun) |
| `hal/audit/query` | Full | [below](#halauditquery) |

Every example on this page uses the same Device. `desk-fan` has a write channel `fan_speed` in `%` with a confirmed maximum of 100 %, confirmed by sohan on 2026-10-24. The fan runs at 20 %.

### hal/devices/list

Lists every registered Device. Params `{}`. Result `{ devices: [DeviceSummary] }`.

```json
→ {"jsonrpc": "2.0", "id": 2, "method": "hal/devices/list", "params": {}}
← {"jsonrpc": "2.0", "id": 2, "result": {"devices": [
     {"id": "desk-fan", "name": "Desk fan controller", "model": null, "manufacturer": null,
      "driver": "openhal-firmware", "hazard": "low", "writable": true, "connected": true,
      "conformance": "control", "verification": "unverified"}]}}
```

### hal/devices/describe

Describes one Device. Params `{ device }`. Result `{ device: DeviceDescription }`. An unknown id gets `UNKNOWN_TARGET`.

```json
→ {"jsonrpc": "2.0", "id": 3, "method": "hal/devices/describe", "params": {"device": "desk-fan"}}
← {"jsonrpc": "2.0", "id": 3, "result": {"device": {
     "id": "desk-fan", "name": "Desk fan controller", "driver": "openhal-firmware", "hazard": "low",
     "writable": true, "connected": true, "conformance": "control", "verification": "unverified",
     "read": {"temperature": {"type": "number", "unit": "degC"}},
     "write": {"fan_speed": {"type": "number", "unit": "%", "min": 0, "max": 100, "maxChangePerS": 20,
                             "confirm": "none"}},
     "actions": {}, "safeState": [{"fan_speed": 0}],
     "confirmed": {"by": "sohan", "at": "2026-10-24"}, "unconfirmed": [], "file": "desk-fan.hal.yaml"}}}
```

### hal/read

Reads one channel now. Params `{ device, channel }`. Result is a `Reading`. A disconnected Device gets `DEVICE_UNAVAILABLE`. A failed read gets `DRIVER_ERROR`.

```json
→ {"jsonrpc": "2.0", "id": 4, "method": "hal/read", "params": {"device": "desk-fan", "channel": "fan_speed"}}
← {"jsonrpc": "2.0", "id": 4, "result": {"device": "desk-fan", "channel": "fan_speed", "value": 20, "unit": "%",
     "at": "2026-10-24T14:02:00Z", "suspect": false}}
```

### hal/readMany

Reads several channels. Params `{ items: [{ device, channel }] }`. Result `{ readings: [...] }` in the order asked. Each entry is a `Reading`, or `{ device, channel, error }` for a read that failed. One failed read does not fail the request.

```json
→ {"jsonrpc": "2.0", "id": 5, "method": "hal/readMany", "params": {"items": [
     {"device": "desk-fan", "channel": "fan_speed"}, {"device": "desk-fan", "channel": "humidity"}]}}
← {"jsonrpc": "2.0", "id": 5, "result": {"readings": [
     {"device": "desk-fan", "channel": "fan_speed", "value": 20, "unit": "%", "at": "2026-10-24T14:02:00Z",
      "suspect": false},
     {"device": "desk-fan", "channel": "humidity", "error": {"code": -32004, "message": "desk-fan has no channel humidity.",
      "data": {"name": "UNKNOWN_TARGET", "kernelCode": "unknown_target", "device": "desk-fan", "channel": "humidity"}}}]}}
```

### hal/write

Sets one write channel. Params `{ device, channel, value }`. Level Control.

- If every check passes, the Driver applies the value and the result is `{ status: "done", device, channel, value, unit }`.
- If the command needs a human, it is queued and the result is `{ status: "pending", requestId, expiresInS }`.
- If the Safety Kernel blocks it, the response is an error from the [registry](../safety.md#error-registry). Nothing reaches the Driver.
- If the Driver fails, the response is `DRIVER_ERROR` and the channel is unknown until a readback.

A blocked write.

```json
→ {"jsonrpc": "2.0", "id": 6, "method": "hal/write",
   "params": {"device": "desk-fan", "channel": "fan_speed", "value": "150 %"}}
← {"jsonrpc": "2.0", "id": 6, "error": {"code": -32010,
     "message": "fan_speed 150 % exceeds the limit of 100 % (desk-fan.hal.yaml, confirmed by sohan 2026-10-24)",
     "data": {"name": "LIMIT_EXCEEDED", "kernelCode": "above_max", "device": "desk-fan", "channel": "fan_speed",
              "limit": "100 %", "requested": "150 %", "file": "desk-fan.hal.yaml", "confirmedBy": "sohan",
              "confirmedAt": "2026-10-24",
              "kernelMessage": "Blocked. The fan_speed limit is 100 % (max). Asked for 150 %."}}}
```

A granted write.

```json
→ {"jsonrpc": "2.0", "id": 7, "method": "hal/write",
   "params": {"device": "desk-fan", "channel": "fan_speed", "value": "60 %"}}
← {"jsonrpc": "2.0", "id": 7, "result": {"status": "done", "device": "desk-fan", "channel": "fan_speed",
     "value": 60, "unit": "%"}}
```

### hal/dryRun

Evaluates commands in order as if each allowed one had run. Nothing is sent to any Device. Params `{ commands: [Write or Action] }`. Result `{ decisions: [Decision] }`, one per command. A blocked command is reported in its Decision, not as an error response.

```json
→ {"jsonrpc": "2.0", "id": 8, "method": "hal/dryRun", "params": {"commands": [
     {"kind": "write", "device": "desk-fan", "channel": "fan_speed", "value": "150 %"},
     {"kind": "write", "device": "desk-fan", "channel": "fan_speed", "value": "60 %"}]}}
← {"jsonrpc": "2.0", "id": 8, "result": {"decisions": [
     {"status": "blocked", "device": "desk-fan", "target": "write:fan_speed", "value": null, "unit": "%",
      "error": {"code": -32010,
                "message": "fan_speed 150 % exceeds the limit of 100 % (desk-fan.hal.yaml, confirmed by sohan 2026-10-24)",
                "data": {"name": "LIMIT_EXCEEDED", "kernelCode": "above_max", "device": "desk-fan",
                         "channel": "fan_speed", "limit": "100 %", "requested": "150 %"}}},
     {"status": "allowed", "device": "desk-fan", "target": "write:fan_speed", "value": 60, "unit": "%"}]}}
```

### hal/planCheck

Checks a whole plan before any of it runs. Params `{ steps: [Write, Action or Wait] }`, at most 200 steps. Each step is evaluated in order as if the earlier steps had run. A `Wait` step advances the simulated clock, so rate limits are judged as in a real run. Result `{ ok, decisions: [Decision], problems: [string] }`. `decisions` has one entry per `Write` or `Action`. `ok` is `true` only when every Decision is `allowed` and `problems` is empty.

```json
→ {"jsonrpc": "2.0", "id": 9, "method": "hal/planCheck", "params": {"steps": [
     {"kind": "write", "device": "desk-fan", "channel": "fan_speed", "value": "40 %"},
     {"kind": "wait", "duration": "1 s"},
     {"kind": "write", "device": "desk-fan", "channel": "fan_speed", "value": "60 %"}]}}
← {"jsonrpc": "2.0", "id": 9, "result": {"ok": true, "problems": [], "decisions": [
     {"status": "allowed", "device": "desk-fan", "target": "write:fan_speed", "value": 40, "unit": "%"},
     {"status": "allowed", "device": "desk-fan", "target": "write:fan_speed", "value": 60, "unit": "%"}]}}
```

### hal/stop

Puts every Device in its safe state and locks writes until a human sends `hal/unlock`. Params `{ reason? }`. Any Principal MAY stop. Result `{ devices: [{ device, status, detail }] }` with `status` one of `safe`, `partial`, `failed`, `no_safe_state` or `pending` ([Safety](../safety.md#stop-and-unlock)).

```json
→ {"jsonrpc": "2.0", "id": 10, "method": "hal/stop", "params": {"reason": "smoke near the fan"}}
← {"jsonrpc": "2.0", "id": 10, "result": {"devices": [
     {"device": "desk-fan", "status": "safe", "detail": "smoke near the fan"}]}}
```

While the Hub is stopped, every write and action gets `STOPPED`.

### hal/unlock

Lifts the stop lock. Params `{ phrase: "unlock" }`. Result `{ ok: true }`.

- Only a human Principal may unlock. Any other Principal gets `SCOPE_DENIED`.
- A phrase other than `unlock` gets `INVALID_PARAMS`.
- While a stop is still being applied, the Hub answers `BUSY`.

```json
→ {"jsonrpc": "2.0", "id": 11, "method": "hal/unlock", "params": {"phrase": "unlock"}}
← {"jsonrpc": "2.0", "id": 11, "error": {"code": -32003, "message": "Only a human can unlock after a stop.",
     "data": {"name": "SCOPE_DENIED", "kernelCode": "not_permitted"}}}
```

The examples below add one action to `desk-fan`. `spin_test` takes `seconds` in `s` from 1 to 30 and has confirmation tier `confirm`.

### hal/action

Runs one action. Params `{ device, action, args }`, with numeric arguments as quantity strings. Level Full. The result is `{ status: "done", result }`, or `{ status: "pending", requestId, expiresInS }` when the action waits for a human. Blocks and failures are errors, as for `hal/write`.

```json
→ {"jsonrpc": "2.0", "id": 12, "method": "hal/action",
   "params": {"device": "desk-fan", "action": "spin_test", "args": {"seconds": "5 s"}}}
← {"jsonrpc": "2.0", "id": 12, "result": {"status": "pending", "requestId": "9f2c41d07a3b6e15", "expiresInS": 300}}
```

### hal/confirmations/list

Lists Confirmation Requests. Params `{ status? }`. Without `status`, only pending requests are listed. Result `{ requests: [ConfirmationRequest] }`. A human Principal sees every request. Any other Principal sees only its own.

```json
→ {"jsonrpc": "2.0", "id": 13, "method": "hal/confirmations/list", "params": {}}
← {"jsonrpc": "2.0", "id": 13, "result": {"requests": [
     {"requestId": "9f2c41d07a3b6e15", "status": "pending",
      "command": {"kind": "action", "device": "desk-fan", "action": "spin_test", "args": {"seconds": "5 s"}},
      "requestedBy": "agent:bench-agent", "createdAt": "2026-10-24T14:02:00Z", "expiresAt": "2026-10-24T14:07:00Z"}]}}
```

### hal/confirmations/approve

Approves a pending request. Params `{ requestId }`. Only a human Principal may approve. Any other Principal gets `SCOPE_DENIED`. The Safety Kernel runs every check again against the current state, then runs the command. The result is the `Decision`, with `status` `done`, `blocked` or `failed`. A request that is unknown or no longer pending gets `REQUEST_CLOSED`.

```json
→ {"jsonrpc": "2.0", "id": 14, "method": "hal/confirmations/approve", "params": {"requestId": "9f2c41d07a3b6e15"}}
← {"jsonrpc": "2.0", "id": 14, "result": {"status": "done", "device": "desk-fan", "target": "action:spin_test",
     "value": {"seconds": 5}, "unit": null}}
```

### hal/confirmations/reject

Rejects a pending request. Params `{ requestId, reason? }`. Only a human Principal may reject. The result is the updated `ConfirmationRequest`. A request that is unknown or no longer pending gets `REQUEST_CLOSED`.

```json
→ {"jsonrpc": "2.0", "id": 15, "method": "hal/confirmations/reject",
   "params": {"requestId": "9f2c41d07a3b6e15", "reason": "not while the plant is drying"}}
← {"jsonrpc": "2.0", "id": 15, "result": {"requestId": "9f2c41d07a3b6e15", "status": "rejected",
     "command": {"kind": "action", "device": "desk-fan", "action": "spin_test", "args": {"seconds": "5 s"}},
     "requestedBy": "agent:bench-agent", "createdAt": "2026-10-24T14:02:00Z", "expiresAt": "2026-10-24T14:07:00Z",
     "decidedBy": "human:sohan"}}
```

### hal/routines/list

Lists stored routines ([Routines](../routines.md)). Params `{}`. Result `{ routines: [RoutineSummary] }`.

```json
→ {"jsonrpc": "2.0", "id": 16, "method": "hal/routines/list", "params": {}}
← {"jsonrpc": "2.0", "id": 16, "result": {"routines": [
     {"id": "keep-cool", "kind": "yaml", "enabled": false, "sha256": "5d41c0a9...", "devices": ["desk-fan"],
      "maxHazard": "low", "triggers": ["every 30 s"], "disabledReason": "new routine"}]}}
```

### hal/routines/dryRun

Evaluates every command in every branch of a routine as the routine would send it. Nothing runs. Params `{ routineId }`. Result `{ ok, decisions: [Decision], problems: [string] }`, with `ok` as for `hal/planCheck`. An unknown id gets `UNKNOWN_TARGET`.

```json
→ {"jsonrpc": "2.0", "id": 17, "method": "hal/routines/dryRun", "params": {"routineId": "keep-cool"}}
← {"jsonrpc": "2.0", "id": 17, "result": {"ok": true, "problems": [], "decisions": [
     {"status": "allowed", "device": "desk-fan", "target": "write:fan_speed", "value": 60, "unit": "%"}]}}
```

### hal/audit/query

Reads the audit log, newest entry first. Params `{ device?, status?, event?, since?, limit? }`. `since` is a sequence number and returns only later entries. `limit` defaults to 200 and is capped at 5000. Result `{ entries: [AuditEntry] }`. Text that quotes a Device is returned inside a data block ([Security](../security.md#prompt-injection)).

```json
→ {"jsonrpc": "2.0", "id": 18, "method": "hal/audit/query",
   "params": {"device": "desk-fan", "status": "blocked", "limit": 1}}
← {"jsonrpc": "2.0", "id": 18, "result": {"entries": [
     {"seq": 41, "at": "2026-10-24T14:02:00Z", "event": "write", "principal": "agent:bench-agent",
      "device": "desk-fan", "target": "write:fan_speed", "status": "blocked", "code": "above_max",
      "body": {"requested": "150 %", "message": "Blocked. The fan_speed limit is 100 % (max). Asked for 150 %."},
      "hash": "a3f9..."}]}}
```

## Notifications

The Hub sends these notifications after `hal/initialized`, to every connection.

| Notification | Params | Sent when |
|---|---|---|
| `hal/value` | `{ device, channel, value, unit, at, suspect }` | A value is read, polled or streamed |
| `hal/blocked` | `{ device, target, error: { code, message, data } }`, with the registry name in `data.name` | The Safety Kernel blocks a command from any source |
| `hal/stopped` | `{ reason, by, devices: [{ device, status }] }` | A stop finishes |
| `hal/deviceAdded` | `{ device: DeviceSummary }` | A Device is registered |
| `hal/deviceRemoved` | `{ device }` | A Device is unregistered |
| `hal/confirmationRequested` | `{ request: ConfirmationRequest }` | A command enters the confirmation queue. Sent only to human Principals and to the Principal that made the request |

A Core Hub sends `hal/value`. A Control Hub also sends `hal/blocked` and `hal/stopped`. A Full Hub also sends `hal/confirmationRequested`. A Hub at any level MAY send `hal/deviceAdded` and `hal/deviceRemoved`. Every Hub lists what it sends in `capabilities.notifications`.

```json
← {"jsonrpc": "2.0", "method": "hal/value", "params": {"device": "desk-fan", "channel": "fan_speed", "value": 60,
     "unit": "%", "at": "2026-10-24T14:02:01Z", "suspect": false}}
← {"jsonrpc": "2.0", "method": "hal/blocked", "params": {"device": "desk-fan", "target": "write:fan_speed",
     "error": {"code": -32010,
               "message": "fan_speed 150 % exceeds the limit of 100 % (desk-fan.hal.yaml, confirmed by sohan 2026-10-24)",
               "data": {"name": "LIMIT_EXCEEDED", "kernelCode": "above_max", "device": "desk-fan",
                        "channel": "fan_speed", "limit": "100 %", "requested": "150 %"}}}}
← {"jsonrpc": "2.0", "method": "hal/stopped", "params": {"reason": "smoke near the fan", "by": "agent:bench-agent",
     "devices": [{"device": "desk-fan", "status": "safe"}]}}
← {"jsonrpc": "2.0", "method": "hal/deviceAdded", "params": {"device": {"id": "desk-fan",
     "name": "Desk fan controller", "model": null, "manufacturer": null, "driver": "openhal-firmware",
     "hazard": "low", "writable": true, "connected": true, "conformance": "control", "verification": "unverified"}}}
← {"jsonrpc": "2.0", "method": "hal/deviceRemoved", "params": {"device": "desk-fan"}}
← {"jsonrpc": "2.0", "method": "hal/confirmationRequested", "params": {"request": {
     "requestId": "9f2c41d07a3b6e15", "status": "pending",
     "command": {"kind": "action", "device": "desk-fan", "action": "spin_test", "args": {"seconds": "5 s"}},
     "requestedBy": "agent:bench-agent", "createdAt": "2026-10-24T14:02:00Z", "expiresAt": "2026-10-24T14:07:00Z"}}}
```
