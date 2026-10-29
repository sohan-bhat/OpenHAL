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

Every example on this page uses the 3D printer and its camera from [examples/print-babysitter/](../../../examples/print-babysitter/), confirmed by owner on 2026-10-24. The printer reads `state`, `extruder_temp`, `bed_temp` and `progress`. Its write channel `extruder_target` takes 0 to 260 degC and `bed_target` takes 0 to 110 degC, changing by at most 50 and 20 degC per second. Its action `pause` needs `state == printing`, and `cancel` waits for a person every time. `printer-cam` reads `frame`. A print is running with the bed at 60 degC.

### hal/devices/list

Lists every registered Device. Params `{}`. Result `{ devices: [DeviceSummary] }`.

```json
→ {"jsonrpc": "2.0", "id": 2, "method": "hal/devices/list", "params": {}}
← {"jsonrpc": "2.0", "id": 2, "result": {"devices": [
     {"id": "printer", "name": "Klipper 3D printer", "model": null, "manufacturer": null,
      "driver": "moonraker", "hazard": "medium", "writable": true, "connected": true,
      "conformance": "control", "verification": "unverified", "unavailable": null},
     {"id": "printer-cam", "name": "Printer camera", "model": null, "manufacturer": null,
      "driver": "http", "hazard": "low", "writable": true, "connected": true,
      "conformance": "control", "verification": "unverified", "unavailable": null}]}}
```

### hal/devices/describe

Describes one Device. Params `{ device }`. Result `{ device: DeviceDescription }`. An unknown id gets `UNKNOWN_TARGET`.

```json
→ {"jsonrpc": "2.0", "id": 3, "method": "hal/devices/describe", "params": {"device": "printer"}}
← {"jsonrpc": "2.0", "id": 3, "result": {"device": {
     "id": "printer", "name": "Klipper 3D printer", "driver": "moonraker", "hazard": "medium",
     "writable": true, "connected": true, "conformance": "control", "verification": "unverified",
     "read": {"state": {"type": "enum", "everyS": 1,
                        "values": ["standby", "printing", "paused", "complete", "cancelled", "error"]},
              "extruder_temp": {"type": "number", "unit": "degC", "everyS": 1, "range": [0, 320]},
              "bed_temp": {"type": "number", "unit": "degC", "everyS": 1, "range": [0, 130]},
              "progress": {"type": "number", "unit": "percent", "everyS": 5}},
     "write": {"extruder_target": {"type": "number", "unit": "degC", "min": 0, "max": 260, "maxChangePerS": 50,
                                   "confirm": "none", "suggested": false},
               "bed_target": {"type": "number", "unit": "degC", "min": 0, "max": 110, "maxChangePerS": 20,
                              "confirm": "none", "suggested": false}},
     "actions": {"pause": {"description": "Pause the print. Klipper parks the nozzle and keeps the heaters on.",
                           "args": {}, "require": ["state == printing"], "effects": [], "confirm": "none",
                           "suggested": false},
                 "resume": {"description": "Resume a paused print.", "args": {}, "require": ["state == paused"],
                            "effects": [], "confirm": "none", "suggested": false},
                 "cancel": {"description": "Cancel the print. It can't be resumed afterwards.", "args": {},
                            "require": [], "effects": [], "confirm": "confirm-each-time", "suggested": false}},
     "safeState": [{"extruder_target": 0, "bed_target": 0}],
     "interlocks": [{"if": "extruder_target > 0 degC", "require": "state != error",
                     "message": "Clear the printer error before heating."}],
     "watchdog": {"heartbeatS": 5, "onLoss": "hold", "maxDuration": []},
     "confirmed": {"by": "owner", "at": "2026-10-24"}, "unconfirmed": [], "file": "printer.hal.yaml"}}}
```

### hal/read

Reads one channel now. Params `{ device, channel }`. Result is a `Reading`. A disconnected Device gets `DEVICE_UNAVAILABLE`. A failed read gets `DRIVER_ERROR`.

```json
→ {"jsonrpc": "2.0", "id": 4, "method": "hal/read", "params": {"device": "printer", "channel": "bed_temp"}}
← {"jsonrpc": "2.0", "id": 4, "result": {"device": "printer", "channel": "bed_temp", "value": 60,
     "unit": "degC", "at": "2026-10-24T14:02:00Z", "suspect": false}}
```

### hal/readMany

Reads several channels. Params `{ items: [{ device, channel }] }`. Result `{ readings: [...] }` in the order asked. Each entry is a `Reading`, or `{ device, channel, error }` for a read that failed. One failed read does not fail the request.

```json
→ {"jsonrpc": "2.0", "id": 5, "method": "hal/readMany", "params": {"items": [
     {"device": "printer", "channel": "state"}, {"device": "printer", "channel": "humidity"}]}}
← {"jsonrpc": "2.0", "id": 5, "result": {"readings": [
     {"device": "printer", "channel": "state", "value": "printing", "unit": null, "at": "2026-10-24T14:02:00Z",
      "suspect": false},
     {"device": "printer", "channel": "humidity", "error": {"code": -32004,
      "message": "printer has no channel humidity",
      "data": {"name": "UNKNOWN_TARGET", "kernelCode": "unknown_target", "device": "printer",
               "channel": "humidity"}}}]}}
```

### hal/write

Sets one write channel. Params `{ device, channel, value, unit }`. A number carries its unit in `unit`, as `"value": 60, "unit": "%"` ([ADR 0016](../../../docs/adr/0016-one-value-format.md)). A number sent as one string such as `"60 %"` gets `UNIT_INVALID`. Level Control.

- If every check passes, the Driver applies the value and the result is `{ status: "done", device, channel, value, unit }`.
- If the command needs a human, it is queued and the result is `{ status: "pending", requestId, expiresInS }`.
- If the Safety Kernel blocks it, the response is an error from the [registry](../safety.md#error-registry). Nothing reaches the Driver.
- If the Driver fails, the response is `DRIVER_ERROR` and the channel is unknown until a readback.

A nozzle above its limit is blocked. A warmer bed inside its limit is granted.

```json
→ {"jsonrpc": "2.0", "id": 6, "method": "hal/write",
   "params": {"device": "printer", "channel": "extruder_target", "value": 300, "unit": "degC"}}
← {"jsonrpc": "2.0", "id": 6, "error": {"code": -32010,
     "message": "extruder_target 300 degC exceeds the limit of 260 degC (printer.hal.yaml, confirmed by owner 2026-10-24)",
     "data": {"name": "LIMIT_EXCEEDED", "kernelCode": "above_max", "device": "printer", "channel": "extruder_target",
              "requested": {"value": 300, "unit": "degC"}, "limit": {"value": 260, "unit": "degC"},
              "file": "printer.hal.yaml", "confirmedBy": "owner", "confirmedAt": "2026-10-24",
              "kernelMessage": "Blocked. The extruder_target limit is 260 degC (max). Asked for 300 degC."}}}
→ {"jsonrpc": "2.0", "id": 7, "method": "hal/write",
   "params": {"device": "printer", "channel": "bed_target", "value": 70, "unit": "degC"}}
← {"jsonrpc": "2.0", "id": 7, "result": {"status": "done", "device": "printer", "channel": "bed_target",
     "value": 70, "unit": "degC"}}
```

### hal/dryRun

Evaluates commands in order as if each allowed one had run. Nothing is sent to any Device. Params `{ commands: [Write or Action] }`. Result `{ decisions: [Decision] }`, one per command. A blocked command is reported in its Decision, not as an error response.

```json
→ {"jsonrpc": "2.0", "id": 8, "method": "hal/dryRun", "params": {"commands": [
     {"kind": "write", "device": "printer", "channel": "extruder_target", "value": 300, "unit": "degC"},
     {"kind": "action", "device": "printer", "action": "pause", "args": {}}]}}
← {"jsonrpc": "2.0", "id": 8, "result": {"decisions": [
     {"status": "blocked", "device": "printer", "target": "write:extruder_target", "value": null, "unit": "degC",
      "error": {"code": -32010,
                "message": "extruder_target 300 degC exceeds the limit of 260 degC (printer.hal.yaml, confirmed by owner 2026-10-24)",
                "data": {"name": "LIMIT_EXCEEDED", "kernelCode": "above_max", "device": "printer",
                         "channel": "extruder_target", "limit": {"value": 260, "unit": "degC"},
                         "requested": {"value": 300, "unit": "degC"}, "file": "printer.hal.yaml",
                         "confirmedBy": "owner", "confirmedAt": "2026-10-24"}}},
     {"status": "allowed", "device": "printer", "target": "action:pause", "value": {}, "unit": null}]}}
```

### hal/planCheck

Checks a whole plan before any of it runs. Params `{ steps: [Write, Action or Wait] }`, at most 200 steps. Each step is evaluated in order as if the earlier steps had run. A `Wait` step advances the simulated clock, so rate limits are judged as in a real run. Result `{ ok, decisions: [Decision], problems: [string] }`. `decisions` has one entry per `Write` or `Action`. `ok` is `true` only when every Decision is `allowed` and `problems` is empty.

The bed goes to 80 degC and then straight to 110 degC. The second step is faster than 20 degC per second allows. A `Wait` of 2 s between the steps makes the plan pass.

```json
→ {"jsonrpc": "2.0", "id": 9, "method": "hal/planCheck", "params": {"steps": [
     {"kind": "write", "device": "printer", "channel": "bed_target", "value": 80, "unit": "degC"},
     {"kind": "write", "device": "printer", "channel": "bed_target", "value": 110, "unit": "degC"}]}}
← {"jsonrpc": "2.0", "id": 9, "result": {"ok": false, "problems": [], "decisions": [
     {"status": "allowed", "device": "printer", "target": "write:bed_target", "value": 80, "unit": "degC"},
     {"status": "blocked", "device": "printer", "target": "write:bed_target", "value": null, "unit": "degC",
      "error": {"code": -32011,
                "message": "bed_target 110 degC changes faster than 20 degC/s allows right now (printer.hal.yaml, confirmed by owner 2026-10-24)",
                "data": {"name": "RATE_LIMITED", "kernelCode": "rate_limited", "device": "printer",
                         "channel": "bed_target", "limit": {"value": 20, "unit": "degC/s"},
                         "requested": {"value": 110, "unit": "degC"}, "file": "printer.hal.yaml",
                         "confirmedBy": "owner", "confirmedAt": "2026-10-24"}}}]}}
→ {"jsonrpc": "2.0", "id": 10, "method": "hal/planCheck", "params": {"steps": [
     {"kind": "write", "device": "printer", "channel": "bed_target", "value": 80, "unit": "degC"},
     {"kind": "wait", "duration": {"value": 2, "unit": "s"}},
     {"kind": "write", "device": "printer", "channel": "bed_target", "value": 110, "unit": "degC"}]}}
← {"jsonrpc": "2.0", "id": 10, "result": {"ok": true, "problems": [], "decisions": [
     {"status": "allowed", "device": "printer", "target": "write:bed_target", "value": 80, "unit": "degC"},
     {"status": "allowed", "device": "printer", "target": "write:bed_target", "value": 110, "unit": "degC"}]}}
```

### hal/stop

Puts every Device in its safe state and refuses every command until a human sends `hal/unlock`. Params `{ reason? }`. Any Principal MAY stop. Result `{ devices: [{ device, status, detail }] }` with `status` one of `safe`, `partial`, `failed`, `no_safe_state` or `pending` ([Safety](../safety.md#stop-and-unlock)).

```json
→ {"jsonrpc": "2.0", "id": 11, "method": "hal/stop", "params": {"reason": "the print came loose"}}
← {"jsonrpc": "2.0", "id": 11, "result": {"devices": [
     {"device": "printer", "status": "safe", "detail": "the print came loose"},
     {"device": "printer-cam", "status": "safe", "detail": "read-only device"}]}}
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
← {"jsonrpc": "2.0", "id": 12, "error": {"code": -32003, "message": "Calling hal/unlock takes a human principal",
     "data": {"name": "SCOPE_DENIED", "kernelCode": "not_permitted", "method": "hal/unlock",
              "kernelMessage": "Calling hal/unlock takes a human principal."}}}
```

### hal/action

Runs one action. Params `{ device, action, args }`, with numeric arguments as Quantity objects such as `{"value": 20, "unit": "s"}`. Level Full. The result is `{ status: "done", result }`, or `{ status: "pending", requestId, expiresInS }` when the action waits for a human. Blocks and failures are errors, as for `hal/write`.

```json
→ {"jsonrpc": "2.0", "id": 13, "method": "hal/action", "params": {"device": "printer", "action": "pause"}}
← {"jsonrpc": "2.0", "id": 13, "result": {"status": "done",
     "result": {"device": "printer", "action": "pause", "args": {}}}}
```

`cancel` has the confirmation tier `confirm-each-time`, so a person approves every request and the command waits.

```json
→ {"jsonrpc": "2.0", "id": 14, "method": "hal/action", "params": {"device": "printer", "action": "cancel"}}
← {"jsonrpc": "2.0", "id": 14, "result": {"status": "pending", "requestId": "9f2c41d07a3b6e15", "expiresInS": 300}}
```

### hal/confirmations/list

Lists Confirmation Requests. Params `{ status? }`. Without `status`, only pending requests are listed. Result `{ requests: [ConfirmationRequest] }`. A human Principal sees every request. Any other Principal sees only its own.

```json
→ {"jsonrpc": "2.0", "id": 15, "method": "hal/confirmations/list", "params": {}}
← {"jsonrpc": "2.0", "id": 15, "result": {"requests": [
     {"requestId": "9f2c41d07a3b6e15", "status": "pending",
      "command": {"kind": "action", "device": "printer", "action": "cancel", "args": {}},
      "requestedBy": "agent:claude", "createdAt": "2026-10-24T14:02:00Z", "expiresAt": "2026-10-24T14:07:00Z"}]}}
```

### hal/confirmations/approve

Approves a pending request. Params `{ requestId }`. Only a human Principal may approve. Any other Principal gets `SCOPE_DENIED`. The Safety Kernel runs every check again against the current state, then runs the command. The result is the `Decision`, with `status` `done`, `blocked` or `failed`. A request that is unknown or no longer pending gets `REQUEST_CLOSED`.

```json
→ {"jsonrpc": "2.0", "id": 16, "method": "hal/confirmations/approve", "params": {"requestId": "9f2c41d07a3b6e15"}}
← {"jsonrpc": "2.0", "id": 16, "result": {"status": "done", "device": "printer", "target": "action:cancel",
     "value": {}, "unit": null}}
```

### hal/confirmations/reject

Rejects a pending request. Params `{ requestId, reason? }`. Only a human Principal may reject. The result is the updated `ConfirmationRequest`. A request that is unknown or no longer pending gets `REQUEST_CLOSED`.

```json
→ {"jsonrpc": "2.0", "id": 17, "method": "hal/confirmations/reject",
   "params": {"requestId": "4b7e0c2a9d1f8e63", "reason": "the print can be saved"}}
← {"jsonrpc": "2.0", "id": 17, "result": {"requestId": "4b7e0c2a9d1f8e63", "status": "rejected",
     "command": {"kind": "action", "device": "printer", "action": "cancel", "args": {}},
     "requestedBy": "agent:claude", "createdAt": "2026-10-24T14:05:00Z", "expiresAt": "2026-10-24T14:10:00Z",
     "decidedBy": "human:owner"}}
```

### hal/routines/list

Lists stored routines ([Routines](../routines.md)). Params `{}`. Result `{ routines: [RoutineSummary] }`. The routine here is `pause-when-bed-cools`, which pauses the print when the bed reads below 50 degC.

```json
→ {"jsonrpc": "2.0", "id": 18, "method": "hal/routines/list", "params": {}}
← {"jsonrpc": "2.0", "id": 18, "result": {"routines": [
     {"id": "pause-when-bed-cools", "kind": "yaml", "enabled": false, "sha256": "a5cee2ce...", "devices": ["printer"],
      "maxHazard": "medium", "triggers": ["when printer.bed_temp < 50 degC"], "disabledReason": "new routine"}]}}
```

### hal/routines/dryRun

Evaluates every command in every branch of a routine as the routine would send it. Nothing runs. Params `{ routineId }`. Result `{ ok, decisions: [Decision], problems: [string] }`, with `ok` as for `hal/planCheck`. An unknown id gets `UNKNOWN_TARGET`.

```json
→ {"jsonrpc": "2.0", "id": 19, "method": "hal/routines/dryRun", "params": {"routineId": "pause-when-bed-cools"}}
← {"jsonrpc": "2.0", "id": 19, "result": {"ok": true, "problems": [], "decisions": [
     {"status": "allowed", "device": "printer", "target": "action:pause", "value": {}, "unit": null}]}}
```

### hal/audit/query

Reads the audit log, newest entry first. Params `{ device?, status?, event?, since?, limit? }`. `since` is a sequence number and returns only later entries. `limit` defaults to 200 and is capped at 5000. Result `{ entries: [AuditEntry] }`. Text that quotes a Device is returned inside a data block ([Security](../security.md#prompt-injection)).

```json
→ {"jsonrpc": "2.0", "id": 20, "method": "hal/audit/query",
   "params": {"device": "printer", "status": "blocked", "limit": 1}}
← {"jsonrpc": "2.0", "id": 20, "result": {"entries": [
     {"seq": 41, "at": "2026-10-24T14:02:00Z", "event": "write", "principal": "agent:claude",
      "device": "printer", "target": "write:extruder_target", "status": "blocked", "code": "above_max",
      "body": {"requested": {"value": 300, "unit": "degC"}, "limit": {"max": 260, "unit": "degC"},
               "message": "Blocked. The extruder_target limit is 260 degC (max). Asked for 300 degC."},
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
← {"jsonrpc": "2.0", "method": "hal/value", "params": {"device": "printer", "channel": "bed_temp",
     "value": 70, "unit": "degC", "at": "2026-10-24T14:02:30Z", "suspect": false}}
← {"jsonrpc": "2.0", "method": "hal/blocked", "params": {"device": "printer", "target": "write:extruder_target",
     "error": {"code": -32010,
               "message": "extruder_target 300 degC exceeds the limit of 260 degC (printer.hal.yaml, confirmed by owner 2026-10-24)",
               "data": {"name": "LIMIT_EXCEEDED", "kernelCode": "above_max", "device": "printer",
                        "channel": "extruder_target", "limit": {"value": 260, "unit": "degC"},
                        "requested": {"value": 300, "unit": "degC"}, "file": "printer.hal.yaml",
                        "confirmedBy": "owner", "confirmedAt": "2026-10-24"}}}}
← {"jsonrpc": "2.0", "method": "hal/stopped", "params": {"reason": "the print came loose", "by": "agent:claude",
     "devices": [{"device": "printer", "status": "safe"}, {"device": "printer-cam", "status": "safe"}]}}
← {"jsonrpc": "2.0", "method": "hal/deviceAdded", "params": {"device": {"id": "printer-cam",
     "name": "Printer camera", "model": null, "manufacturer": null, "driver": "http",
     "hazard": "low", "writable": true, "connected": true, "conformance": "control", "verification": "unverified",
     "unavailable": null}}}
← {"jsonrpc": "2.0", "method": "hal/deviceRemoved", "params": {"device": "printer-cam"}}
← {"jsonrpc": "2.0", "method": "hal/confirmationRequested", "params": {"request": {
     "requestId": "9f2c41d07a3b6e15", "status": "pending",
     "command": {"kind": "action", "device": "printer", "action": "cancel", "args": {}},
     "requestedBy": "agent:claude", "createdAt": "2026-10-24T14:02:00Z", "expiresAt": "2026-10-24T14:07:00Z"}}}
```
