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
| `error.data.limit`, `requested` | The limit and the requested value as Quantity objects, such as `{"value": 30, "unit": "s"}` or `{"value": 20, "unit": "%/s"}`. A non-numeric `requested` is the value as sent |
| `error.data.argument` | The action argument, for an error about one argument |
| `error.data.runs`, `per` | An action's `max_runs`, for a `RATE_LIMITED` about runs. `per` is a Quantity such as `{"value": 1, "unit": "h"}` |
| `error.data.interlock` | The Device File's reason for an interlock or requirement. When present it is the whole `message` |
| `error.data.expected` | For `UNIT_INVALID` on a number sent as one string, the Quantity it should have been |
| `error.data.file`, `confirmedBy`, `confirmedAt` | The Device File and the human confirmation behind the limit |
| `error.data.requestId` | The Confirmation Request, for `CONFIRMATION_REQUIRED` and `REQUEST_CLOSED` |
| `error.data.action` | The action, for errors about `hal/action` |
| `error.data.tightenedBy` | The Principal that tightened a session limit, for a `LIMIT_EXCEEDED` caused by it |
| `error.data.method` | The method, for `METHOD_NOT_FOUND` and for `SCOPE_DENIED` on a human-only method |
| `error.data.routine` | The routine, for errors raised by a routine step |
| `error.data.problems` | Each schema problem, for `INVALID_PARAMS` |

Fields that don't apply are omitted.

## Values

- A number travels with its unit apart, never as one string ([ADR 0016](../../../docs/adr/0016-one-value-format.md)). A channel value is `"value": 31, "unit": "%"`. Everywhere else a number is a Quantity object `{ "value": 20, "unit": "s" }`.
- A number without a unit, or sent as one string such as `"20 s"`, is refused with `UNIT_INVALID`. A `unit` on a non-numeric value is refused the same way.
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
| `Quantity` | `{ value, unit }`, a finite number and its unit |
| `Write` | `{ kind: "write", device, channel, value, unit? }` |
| `Action` | `{ kind: "action", device, action, args }`, with numeric `args` as Quantity objects |
| `Wait` | `{ kind: "wait", duration }`, with `duration` a Quantity of time such as `{"value": 2, "unit": "s"}`, at most 1 h |
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

Every example on this page uses the plant waterer from [examples/plant-waterer/](../../../examples/plant-waterer/), confirmed by sohan on 2026-10-24. It reads `soil_moisture` in `%` and `tank` as `empty` or `ok`. Its action `water` takes a `duration` from 1 s to 30 s, runs at most 3 times per 1 h and needs `tank == ok`. The tank is full and the soil reads 31 %.

### hal/devices/list

Lists every registered Device. Params `{}`. Result `{ devices: [DeviceSummary] }`.

```json
→ {"jsonrpc": "2.0", "id": 2, "method": "hal/devices/list", "params": {}}
← {"jsonrpc": "2.0", "id": 2, "result": {"devices": [
     {"id": "plant-waterer", "name": "Arduino plant waterer", "model": null, "manufacturer": null,
      "driver": "openhal-firmware", "hazard": "low", "writable": true, "connected": true,
      "conformance": "full", "verification": "unverified", "unavailable": null}]}}
```

### hal/devices/describe

Describes one Device. Params `{ device }`. Result `{ device: DeviceDescription }`. An unknown id gets `UNKNOWN_TARGET`.

```json
→ {"jsonrpc": "2.0", "id": 3, "method": "hal/devices/describe", "params": {"device": "plant-waterer"}}
← {"jsonrpc": "2.0", "id": 3, "result": {"device": {
     "id": "plant-waterer", "name": "Arduino plant waterer", "driver": "openhal-firmware", "hazard": "low",
     "writable": true, "connected": true, "conformance": "full", "verification": "unverified",
     "read": {"soil_moisture": {"type": "number", "unit": "%", "everyS": 1, "range": [0, 100]},
              "tank": {"type": "enum", "everyS": 1, "values": ["empty", "ok"]}},
     "write": {},
     "actions": {"water": {"description": "Run the pump for a number of seconds.",
                           "args": {"duration": {"type": "number", "unit": "s", "min": 1, "max": 30}},
                           "require": ["tank == ok"], "effects": [], "confirm": "none", "suggested": false},
                 "stop": {"description": "Turn the pump off now.", "args": {}, "require": [], "effects": [],
                          "confirm": "none", "suggested": false}},
     "safeState": [{"action": "stop"}], "interlocks": [],
     "watchdog": {"heartbeatS": 1, "onLoss": "safe_state", "maxDuration": []},
     "confirmed": {"by": "sohan", "at": "2026-10-24"}, "unconfirmed": [], "file": "plant-waterer.hal.yaml"}}}
```

### hal/read

Reads one channel now. Params `{ device, channel }`. Result is a `Reading`. A disconnected Device gets `DEVICE_UNAVAILABLE`. A failed read gets `DRIVER_ERROR`.

```json
→ {"jsonrpc": "2.0", "id": 4, "method": "hal/read", "params": {"device": "plant-waterer", "channel": "soil_moisture"}}
← {"jsonrpc": "2.0", "id": 4, "result": {"device": "plant-waterer", "channel": "soil_moisture", "value": 31,
     "unit": "%", "at": "2026-10-24T14:02:00Z", "suspect": false}}
```

### hal/readMany

Reads several channels. Params `{ items: [{ device, channel }] }`. Result `{ readings: [...] }` in the order asked. Each entry is a `Reading`, or `{ device, channel, error }` for a read that failed. One failed read does not fail the request.

```json
→ {"jsonrpc": "2.0", "id": 5, "method": "hal/readMany", "params": {"items": [
     {"device": "plant-waterer", "channel": "tank"}, {"device": "plant-waterer", "channel": "humidity"}]}}
← {"jsonrpc": "2.0", "id": 5, "result": {"readings": [
     {"device": "plant-waterer", "channel": "tank", "value": "ok", "unit": null, "at": "2026-10-24T14:02:00Z",
      "suspect": false},
     {"device": "plant-waterer", "channel": "humidity", "error": {"code": -32004,
      "message": "plant-waterer has no channel humidity",
      "data": {"name": "UNKNOWN_TARGET", "kernelCode": "unknown_target", "device": "plant-waterer",
               "channel": "humidity"}}}]}}
```

### hal/write

Sets one write channel. Params `{ device, channel, value, unit }`. A number carries its unit in `unit`, as `"value": 60, "unit": "%"` ([ADR 0016](../../../docs/adr/0016-one-value-format.md)). A number sent as one string such as `"60 %"` gets `UNIT_INVALID`. Level Control.

- If every check passes, the Driver applies the value and the result is `{ status: "done", device, channel, value, unit }`.
- If the command needs a human, it is queued and the result is `{ status: "pending", requestId, expiresInS }`.
- If the Safety Kernel blocks it, the response is an error from the [registry](../safety.md#error-registry). Nothing reaches the Driver.
- If the Driver fails, the response is `DRIVER_ERROR` and the channel is unknown until a readback.

The plant waterer has no write channels. Its pump runs only through `water`, so the duration limit always applies. A `hal/write` to it gets `UNKNOWN_TARGET`.

```json
→ {"jsonrpc": "2.0", "id": 6, "method": "hal/write",
   "params": {"device": "plant-waterer", "channel": "pump", "value": true}}
← {"jsonrpc": "2.0", "id": 6, "error": {"code": -32004, "message": "plant-waterer has no channel pump",
     "data": {"name": "UNKNOWN_TARGET", "kernelCode": "unknown_target", "device": "plant-waterer",
              "channel": "pump", "requested": true}}}
```

The desk lamp in [spec/examples/ha-desk-lamp.hal.yaml](../../examples/ha-desk-lamp.hal.yaml) has a `brightness` channel from 1 % to 100 %, confirmed by sohan on 2026-10-24. A blocked and a granted `hal/write` on it.

```json
→ {"jsonrpc": "2.0", "id": 7, "method": "hal/write",
   "params": {"device": "desk-lamp", "channel": "brightness", "value": 150, "unit": "%"}}
← {"jsonrpc": "2.0", "id": 7, "error": {"code": -32010,
     "message": "brightness 150 % exceeds the limit of 100 % (ha-desk-lamp.hal.yaml, confirmed by sohan 2026-10-24)",
     "data": {"name": "LIMIT_EXCEEDED", "kernelCode": "above_max", "device": "desk-lamp", "channel": "brightness",
              "requested": {"value": 150, "unit": "%"}, "limit": {"value": 100, "unit": "%"},
              "file": "ha-desk-lamp.hal.yaml", "confirmedBy": "sohan", "confirmedAt": "2026-10-24",
              "kernelMessage": "Blocked. The brightness limit is 100 % (max). Asked for 150 %."}}}
→ {"jsonrpc": "2.0", "id": 8, "method": "hal/write",
   "params": {"device": "desk-lamp", "channel": "brightness", "value": 60, "unit": "%"}}
← {"jsonrpc": "2.0", "id": 8, "result": {"status": "done", "device": "desk-lamp", "channel": "brightness",
     "value": 60, "unit": "%"}}
```

### hal/dryRun

Evaluates commands in order as if each allowed one had run. Nothing is sent to any Device. Params `{ commands: [Write or Action] }`. Result `{ decisions: [Decision] }`, one per command. A blocked command is reported in its Decision, not as an error response.

```json
→ {"jsonrpc": "2.0", "id": 9, "method": "hal/dryRun", "params": {"commands": [
     {"kind": "action", "device": "plant-waterer", "action": "water", "args": {"duration": {"value": 120, "unit": "s"}}},
     {"kind": "action", "device": "plant-waterer", "action": "water", "args": {"duration": {"value": 20, "unit": "s"}}}]}}
← {"jsonrpc": "2.0", "id": 9, "result": {"decisions": [
     {"status": "blocked", "device": "plant-waterer", "target": "action:water", "value": null, "unit": null,
      "error": {"code": -32010,
                "message": "water duration 120 s exceeds the limit of 30 s (plant-waterer.hal.yaml, confirmed by sohan 2026-10-24)",
                "data": {"name": "LIMIT_EXCEEDED", "kernelCode": "above_max", "device": "plant-waterer",
                         "action": "water", "argument": "duration", "limit": {"value": 30, "unit": "s"},
                         "requested": {"value": 120, "unit": "s"}, "file": "plant-waterer.hal.yaml",
                         "confirmedBy": "sohan", "confirmedAt": "2026-10-24"}}},
     {"status": "allowed", "device": "plant-waterer", "target": "action:water",
      "value": {"duration": {"value": 20, "unit": "s"}}, "unit": null}]}}
```

### hal/planCheck

Checks a whole plan before any of it runs. Params `{ steps: [Write, Action or Wait] }`, at most 200 steps. Each step is evaluated in order as if the earlier steps had run. A `Wait` step advances the simulated clock, so rate limits are judged as in a real run. Result `{ ok, decisions: [Decision], problems: [string] }`. `decisions` has one entry per `Write` or `Action`. `ok` is `true` only when every Decision is `allowed` and `problems` is empty.

Four waterings 10 minutes apart. The fourth is over the limit of 3 runs per 1 h.

```json
→ {"jsonrpc": "2.0", "id": 10, "method": "hal/planCheck", "params": {"steps": [
     {"kind": "action", "device": "plant-waterer", "action": "water", "args": {"duration": {"value": 20, "unit": "s"}}},
     {"kind": "wait", "duration": {"value": 10, "unit": "min"}},
     {"kind": "action", "device": "plant-waterer", "action": "water", "args": {"duration": {"value": 20, "unit": "s"}}},
     {"kind": "wait", "duration": {"value": 10, "unit": "min"}},
     {"kind": "action", "device": "plant-waterer", "action": "water", "args": {"duration": {"value": 20, "unit": "s"}}},
     {"kind": "wait", "duration": {"value": 10, "unit": "min"}},
     {"kind": "action", "device": "plant-waterer", "action": "water", "args": {"duration": {"value": 20, "unit": "s"}}}]}}
← {"jsonrpc": "2.0", "id": 10, "result": {"ok": false, "problems": [], "decisions": [
     {"status": "allowed", "device": "plant-waterer", "target": "action:water",
      "value": {"duration": {"value": 20, "unit": "s"}}, "unit": null},
     {"status": "allowed", "device": "plant-waterer", "target": "action:water",
      "value": {"duration": {"value": 20, "unit": "s"}}, "unit": null},
     {"status": "allowed", "device": "plant-waterer", "target": "action:water",
      "value": {"duration": {"value": 20, "unit": "s"}}, "unit": null},
     {"status": "blocked", "device": "plant-waterer", "target": "action:water", "value": null, "unit": null,
      "error": {"code": -32011,
                "message": "water may run at most 3 times per 1 h (plant-waterer.hal.yaml, confirmed by sohan 2026-10-24)",
                "data": {"name": "RATE_LIMITED", "kernelCode": "rate_limited", "device": "plant-waterer",
                         "action": "water", "runs": 3, "per": {"value": 1, "unit": "h"},
                         "file": "plant-waterer.hal.yaml", "confirmedBy": "sohan", "confirmedAt": "2026-10-24"}}}]}}
```

### hal/stop

Puts every Device in its safe state and refuses every command until a human sends `hal/unlock`. Params `{ reason? }`. Any Principal MAY stop. Result `{ devices: [{ device, status, detail }] }` with `status` one of `safe`, `partial`, `failed`, `no_safe_state` or `pending` ([Safety](../safety.md#stop-and-unlock)).

```json
→ {"jsonrpc": "2.0", "id": 11, "method": "hal/stop", "params": {"reason": "water on the floor"}}
← {"jsonrpc": "2.0", "id": 11, "result": {"devices": [
     {"device": "plant-waterer", "status": "safe", "detail": "water on the floor"}]}}
```

While the Hub is stopped, every `hal/write` and `hal/action` gets `STOPPED`.

### hal/unlock

Lifts the stop lock. Params `{ phrase: "unlock" }`. Result `{ ok: true }`.

- Only a human Principal may unlock. Any other Principal gets `SCOPE_DENIED`.
- A phrase other than `unlock` gets `INVALID_PARAMS`.
- While a stop is still being applied, the Hub answers `BUSY`.

An agent tries to unlock.

```json
→ {"jsonrpc": "2.0", "id": 12, "method": "hal/unlock", "params": {"phrase": "unlock"}}
← {"jsonrpc": "2.0", "id": 12, "error": {"code": -32003, "message": "Only a human can call hal/unlock",
     "data": {"name": "SCOPE_DENIED", "kernelCode": "not_permitted", "method": "hal/unlock",
              "kernelMessage": "Only a person can call hal/unlock."}}}
```

### hal/action

Runs one action. Params `{ device, action, args }`, with numeric arguments as Quantity objects such as `{"value": 20, "unit": "s"}`. Level Full. The result is `{ status: "done", result }`, or `{ status: "pending", requestId, expiresInS }` when the action waits for a human. Blocks and failures are errors, as for `hal/write`.

```json
→ {"jsonrpc": "2.0", "id": 13, "method": "hal/action",
   "params": {"device": "plant-waterer", "action": "water", "args": {"duration": {"value": 20, "unit": "s"}}}}
← {"jsonrpc": "2.0", "id": 13, "result": {"status": "done",
     "result": {"device": "plant-waterer", "action": "water", "args": {"duration": {"value": 20, "unit": "s"}}}}}
```

The examples below give `water` the confirmation tier `confirm`, so a person approves each new request. The same command now waits.

```json
→ {"jsonrpc": "2.0", "id": 14, "method": "hal/action",
   "params": {"device": "plant-waterer", "action": "water", "args": {"duration": {"value": 20, "unit": "s"}}}}
← {"jsonrpc": "2.0", "id": 14, "result": {"status": "pending", "requestId": "9f2c41d07a3b6e15", "expiresInS": 300}}
```

### hal/confirmations/list

Lists Confirmation Requests. Params `{ status? }`. Without `status`, only pending requests are listed. Result `{ requests: [ConfirmationRequest] }`. A human Principal sees every request. Any other Principal sees only its own.

```json
→ {"jsonrpc": "2.0", "id": 15, "method": "hal/confirmations/list", "params": {}}
← {"jsonrpc": "2.0", "id": 15, "result": {"requests": [
     {"requestId": "9f2c41d07a3b6e15", "status": "pending",
      "command": {"kind": "action", "device": "plant-waterer", "action": "water",
                  "args": {"duration": {"value": 20, "unit": "s"}}},
      "requestedBy": "agent:claude", "createdAt": "2026-10-24T14:02:00Z", "expiresAt": "2026-10-24T14:07:00Z"}]}}
```

### hal/confirmations/approve

Approves a pending request. Params `{ requestId }`. Only a human Principal may approve. Any other Principal gets `SCOPE_DENIED`. The Safety Kernel runs every check again against the current state, then runs the command. The result is the `Decision`, with `status` `done`, `blocked` or `failed`. A request that is unknown or no longer pending gets `REQUEST_CLOSED`.

```json
→ {"jsonrpc": "2.0", "id": 16, "method": "hal/confirmations/approve", "params": {"requestId": "9f2c41d07a3b6e15"}}
← {"jsonrpc": "2.0", "id": 16, "result": {"status": "done", "device": "plant-waterer", "target": "action:water",
     "value": {"duration": {"value": 20, "unit": "s"}}, "unit": null}}
```

### hal/confirmations/reject

Rejects a pending request. Params `{ requestId, reason? }`. Only a human Principal may reject. The result is the updated `ConfirmationRequest`. A request that is unknown or no longer pending gets `REQUEST_CLOSED`.

```json
→ {"jsonrpc": "2.0", "id": 17, "method": "hal/confirmations/reject",
   "params": {"requestId": "4b7e0c2a9d1f8e63", "reason": "the soil is still wet"}}
← {"jsonrpc": "2.0", "id": 17, "result": {"requestId": "4b7e0c2a9d1f8e63", "status": "rejected",
     "command": {"kind": "action", "device": "plant-waterer", "action": "water",
                 "args": {"duration": {"value": 10, "unit": "s"}}},
     "requestedBy": "agent:claude", "createdAt": "2026-10-24T14:05:00Z", "expiresAt": "2026-10-24T14:10:00Z",
     "decidedBy": "human:sohan"}}
```

### hal/routines/list

Lists stored routines ([Routines](../routines.md)). Params `{}`. Result `{ routines: [RoutineSummary] }`. The routine here is `morning-water` from the [routine tutorial](../../../docs/guide/tutorials/create-a-routine.md), which waters for 20 s when the soil reads below 35 %.

```json
→ {"jsonrpc": "2.0", "id": 18, "method": "hal/routines/list", "params": {}}
← {"jsonrpc": "2.0", "id": 18, "result": {"routines": [
     {"id": "morning-water", "kind": "yaml", "enabled": false, "sha256": "97a213e3...", "devices": ["plant-waterer"],
      "maxHazard": "low", "triggers": ["every 3600 s"], "disabledReason": "new routine"}]}}
```

### hal/routines/dryRun

Evaluates every command in every branch of a routine as the routine would send it. Nothing runs. Params `{ routineId }`. Result `{ ok, decisions: [Decision], problems: [string] }`, with `ok` as for `hal/planCheck`. An unknown id gets `UNKNOWN_TARGET`.

```json
→ {"jsonrpc": "2.0", "id": 19, "method": "hal/routines/dryRun", "params": {"routineId": "morning-water"}}
← {"jsonrpc": "2.0", "id": 19, "result": {"ok": true, "problems": [], "decisions": [
     {"status": "allowed", "device": "plant-waterer", "target": "action:water",
      "value": {"duration": {"value": 20, "unit": "s"}}, "unit": null}]}}
```

### hal/audit/query

Reads the audit log, newest entry first. Params `{ device?, status?, event?, since?, limit? }`. `since` is a sequence number and returns only later entries. `limit` defaults to 200 and is capped at 5000. Result `{ entries: [AuditEntry] }`. Text that quotes a Device is returned inside a data block ([Security](../security.md#prompt-injection)).

```json
→ {"jsonrpc": "2.0", "id": 20, "method": "hal/audit/query",
   "params": {"device": "plant-waterer", "status": "blocked", "limit": 1}}
← {"jsonrpc": "2.0", "id": 20, "result": {"entries": [
     {"seq": 41, "at": "2026-10-24T14:02:00Z", "event": "action", "principal": "agent:claude",
      "device": "plant-waterer", "target": "action:water", "status": "blocked", "code": "above_max",
      "body": {"args": {"duration": {"value": 120, "unit": "s"}},
               "message": "Blocked. The duration limit is 30 s (max). Asked for 120 s."},
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
← {"jsonrpc": "2.0", "method": "hal/value", "params": {"device": "plant-waterer", "channel": "soil_moisture",
     "value": 46, "unit": "%", "at": "2026-10-24T14:02:30Z", "suspect": false}}
← {"jsonrpc": "2.0", "method": "hal/blocked", "params": {"device": "plant-waterer", "target": "action:water",
     "error": {"code": -32012, "message": "pump can't run while tank is empty",
               "data": {"name": "INTERLOCK_BLOCKED", "kernelCode": "interlock", "device": "plant-waterer",
                        "action": "water", "interlock": "pump can't run while tank is empty",
                        "file": "plant-waterer.hal.yaml", "confirmedBy": "sohan", "confirmedAt": "2026-10-24"}}}}
← {"jsonrpc": "2.0", "method": "hal/stopped", "params": {"reason": "water on the floor", "by": "agent:claude",
     "devices": [{"device": "plant-waterer", "status": "safe"}]}}
← {"jsonrpc": "2.0", "method": "hal/deviceAdded", "params": {"device": {"id": "plant-waterer",
     "name": "Arduino plant waterer", "model": null, "manufacturer": null, "driver": "openhal-firmware",
     "hazard": "low", "writable": true, "connected": true, "conformance": "full", "verification": "unverified",
     "unavailable": null}}}
← {"jsonrpc": "2.0", "method": "hal/deviceRemoved", "params": {"device": "plant-waterer"}}
← {"jsonrpc": "2.0", "method": "hal/confirmationRequested", "params": {"request": {
     "requestId": "9f2c41d07a3b6e15", "status": "pending",
     "command": {"kind": "action", "device": "plant-waterer", "action": "water",
                 "args": {"duration": {"value": 20, "unit": "s"}}},
     "requestedBy": "agent:claude", "createdAt": "2026-10-24T14:02:00Z", "expiresAt": "2026-10-24T14:07:00Z"}}}
```
