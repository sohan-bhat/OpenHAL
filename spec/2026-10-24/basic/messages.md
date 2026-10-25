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
| `error.data.limit`, `requested` | The limit and the requested value, for limit errors |
| `error.data.file`, `confirmedBy`, `confirmedAt` | The Device File and the human confirmation behind the limit |
| `error.data.requestId` | The Confirmation Request, for `CONFIRMATION_REQUIRED` and `REQUEST_CLOSED` |

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
| `DeviceSummary` | `id`, `name`, `model`, `manufacturer`, `driver`, `hazard`, `writable`, `connected`, `conformance` and `verification` |
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
