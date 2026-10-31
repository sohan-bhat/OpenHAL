# Schema reference, v0.1

Generated from the reference models by `uv run python -m openhal.protocol.schema`. Do not edit it by hand.
The JSON Schema is [schema.json](schema.json). Field names are as they travel on the wire.

## Methods

| Method | Level | Params | Result |
|---|---|---|---|
| `hal/initialize` | Core | [InitializeParams](#initializeparams) | [InitializeResult](#initializeresult) |
| `hal/devices/list` | Core | [Empty](#empty) | [DevicesListResult](#deviceslistresult) |
| `hal/devices/describe` | Core | [DescribeParams](#describeparams) | [DescribeResult](#describeresult) |
| `hal/read` | Core | [ReadParams](#readparams) | [Reading](#reading) |
| `hal/readMany` | Core | [ReadManyParams](#readmanyparams) | [ReadManyResult](#readmanyresult) |
| `hal/write` | Control | [WriteParams](#writeparams) | [WriteDone](#writedone) or [Pending](#pending) |
| `hal/dryRun` | Control | [DryRunParams](#dryrunparams) | [DryRunResult](#dryrunresult) |
| `hal/planCheck` | Control | [PlanCheckParams](#plancheckparams) | [PlanResult](#planresult) |
| `hal/stop` | Control | [StopParams](#stopparams) | [StopResult](#stopresult) |
| `hal/unlock` | Control, human only | [UnlockParams](#unlockparams) | [UnlockResult](#unlockresult) |
| `hal/action` | Full | [ActionParams](#actionparams) | [ActionDone](#actiondone) or [Pending](#pending) |
| `hal/confirmations/list` | Full | [ConfirmationsListParams](#confirmationslistparams) | [ConfirmationsListResult](#confirmationslistresult) |
| `hal/confirmations/approve` | Full, human only | [ApproveParams](#approveparams) | [Decision](#decision) |
| `hal/confirmations/reject` | Full, human only | [RejectParams](#rejectparams) | [ConfirmationRequest](#confirmationrequest) |
| `hal/routines/list` | Full | [Empty](#empty) | [RoutinesListResult](#routineslistresult) |
| `hal/routines/dryRun` | Full | [RoutineDryRunParams](#routinedryrunparams) | [PlanResult](#planresult) |
| `hal/audit/query` | Full | [AuditQueryParams](#auditqueryparams) | [AuditQueryResult](#auditqueryresult) |

## Notifications

| Notification | Sent by | Level | Params |
|---|---|---|---|
| `hal/value` | Hub | Core | [Reading](#reading) |
| `hal/blocked` | Hub | Control | [BlockedParams](#blockedparams) |
| `hal/stopped` | Hub | Control | [StoppedParams](#stoppedparams) |
| `hal/deviceAdded` | Hub | Core | [DeviceAddedParams](#deviceaddedparams) |
| `hal/deviceRemoved` | Hub | Core | [DeviceRemovedParams](#deviceremovedparams) |
| `hal/confirmationRequested` | Hub | Full | [ConfirmationRequestedParams](#confirmationrequestedparams) |
| `hal/initialized` | Client | Core | [Empty](#empty) |
| `hal/shutdown` | Client | Core | [Empty](#empty) |

## Errors

| Code | Name | Kernel codes | Meaning |
|---|---|---|---|
| -32700 | PARSE_ERROR |  | Invalid JSON |
| -32600 | INVALID_REQUEST |  | Not a JSON-RPC request |
| -32601 | METHOD_NOT_FOUND |  | Unknown method, or one above the hub's conformance level |
| -32602 | INVALID_PARAMS | `bad_request` | Params don't match the schema |
| -32603 | INTERNAL_ERROR | `internal_error` | A bug in the hub |
| -32001 | NOT_INITIALIZED |  | hal/initialize hasn't run |
| -32002 | UNAUTHORIZED |  | Missing or unknown token |
| -32003 | SCOPE_DENIED | `not_permitted` | The principal's token scope doesn't cover this device or method |
| -32004 | UNKNOWN_TARGET | `unknown_target` | No such device, channel or action |
| -32005 | DEVICE_UNAVAILABLE | `device_unavailable` | Disconnected or not ready |
| -32010 | LIMIT_EXCEEDED | `above_max`, `below_min` | Outside the device file's confirmed limits |
| -32011 | RATE_LIMITED | `rate_limited` | Faster than max_change_per_s allows right now |
| -32012 | INTERLOCK_BLOCKED | `interlock` | An interlock or action requirement doesn't hold, or a value it needs is unknown |
| -32013 | CONFIRMATION_REQUIRED | `needs_confirmation` | Queued for a person, data.requestId names the request |
| -32014 | STOPPED | `stopped` | The hub is stopped until a person unlocks |
| -32015 | UNVERIFIED_LIMITS | `read_only_file` | The device file's limits aren't confirmed by a person, so it is read-only |
| -32016 | INVALID_VALUE | `bad_value`, `bad_step` | Wrong type, step, enum value or pattern |
| -32017 | WATCHDOG_TRIPPED | `duration_exceeded` | A watchdog budget is used up |
| -32018 | BUSY | `busy` | Another command holds the device |
| -32019 | QUEUE_FULL | `queue_full` | The confirmation queue is full |
| -32020 | DRIVER_ERROR | `driver_error` | The device or its protocol failed, and the channel is unknown until a readback |
| -32021 | MISCONFIGURED | `misconfigured`, `cannot_loosen` | The hub's device files are inconsistent, or a change would loosen a confirmed limit |
| -32022 | REQUEST_CLOSED | `expired`, `rejected` | The confirmation request expired or was rejected |
| -32023 | UNIT_INVALID | `bad_unit` | A missing, unknown or incompatible unit, or a value that isn't finite |

## Types

### Action

| Field | Type | Required | Description |
|---|---|---|---|
| `kind` | `"action"` | no |  |
| `device` | string | yes | A device id, for example printer. |
| `action` | string | yes | An action, for example pause. |
| `args` | map of [Quantity](#quantity) or boolean or string | no | Arguments by name. Numbers are Quantity objects. |

### ActionDone

| Field | Type | Required | Description |
|---|---|---|---|
| `status` | `"done"` | no |  |
| `result` | [ActionOutcome](#actionoutcome) | yes |  |

### ActionInfo

| Field | Type | Required | Description |
|---|---|---|---|
| `description` | string or null | no |  |
| `args` | map of object | yes |  |
| `require` | list of string | yes |  |
| `effects` | list of string | yes |  |
| `confirm` | string | yes |  |
| `suggested` | boolean | yes |  |
| `confirmed` | [Confirmed](#confirmed) or null | no |  |

### ActionOutcome

| Field | Type | Required | Description |
|---|---|---|---|
| `device` | string | yes |  |
| `action` | string | yes |  |
| `args` | map of [Quantity](#quantity) or boolean or string | yes | The arguments it ran with. Numbers are Quantity objects. |

### ActionParams

| Field | Type | Required | Description |
|---|---|---|---|
| `device` | string | yes | A device id, for example printer. |
| `action` | string | yes | An action, for example pause. |
| `args` | map of [Quantity](#quantity) or boolean or string | no |  |

### ApproveParams

| Field | Type | Required | Description |
|---|---|---|---|
| `requestId` | string | yes | A confirmation request id. |

### AuditEntry

| Field | Type | Required | Description |
|---|---|---|---|
| `seq` | integer | yes |  |
| `at` | string | yes | An RFC 3339 time in UTC, for example 2026-10-24T14:02:00Z. |
| `event` | string | yes |  |
| `principal` | string | yes |  |
| `device` | string or null | no |  |
| `target` | string or null | no |  |
| `status` | string or null | no |  |
| `code` | string or null | no |  |
| `body` | object | yes | The entry's details. Text that quotes a device is a data block. |
| `hash` | string | yes |  |

### AuditQueryParams

| Field | Type | Required | Description |
|---|---|---|---|
| `device` | string or null | no |  |
| `status` | string or null | no |  |
| `event` | string or null | no |  |
| `since` | integer | no | Only entries after this sequence number. |
| `limit` | integer | no |  |

### AuditQueryResult

| Field | Type | Required | Description |
|---|---|---|---|
| `entries` | list of [AuditEntry](#auditentry) | yes |  |

### BlockedParams

| Field | Type | Required | Description |
|---|---|---|---|
| `device` | string | yes |  |
| `target` | string | yes |  |
| `error` | [ErrorObject](#errorobject) | yes |  |

### Capabilities

| Field | Type | Required | Description |
|---|---|---|---|
| `notifications` | list of string | yes | Every notification this hub sends. |

### ConfirmationRequest

| Field | Type | Required | Description |
|---|---|---|---|
| `requestId` | string | yes |  |
| `status` | `"pending"` or `"approved"` or `"rejected"` or `"expired"` or `"cancelled"` or `"blocked"` or `"done"` or `"failed"` | yes |  |
| `command` | [Write](#write) or [Action](#action) | yes |  |
| `requestedBy` | string | yes |  |
| `createdAt` | string | yes | An RFC 3339 time in UTC, for example 2026-10-24T14:02:00Z. |
| `expiresAt` | string | yes | An RFC 3339 time in UTC, for example 2026-10-24T14:02:00Z. |
| `decidedBy` | string or null | no |  |

### ConfirmationRequestedParams

| Field | Type | Required | Description |
|---|---|---|---|
| `request` | [ConfirmationRequest](#confirmationrequest) | yes |  |

### ConfirmationsListParams

| Field | Type | Required | Description |
|---|---|---|---|
| `status` | `"pending"` or `"approved"` or `"rejected"` or `"expired"` or `"cancelled"` or `"blocked"` or `"done"` or `"failed"` or null | no | Leave out to list pending requests. |

### ConfirmationsListResult

| Field | Type | Required | Description |
|---|---|---|---|
| `requests` | list of [ConfirmationRequest](#confirmationrequest) | yes |  |

### Confirmed

A human confirmation of limits.

| Field | Type | Required | Description |
|---|---|---|---|
| `by` | string | yes |  |
| `at` | string | yes | The date or time of the confirmation, as 2026-10-24. |

### Decision

The Safety Kernel's result for one command. A blocked result carries its registry error.

| Field | Type | Required | Description |
|---|---|---|---|
| `status` | `"allowed"` or `"blocked"` or `"needs_confirmation"` or `"done"` or `"pending"` or `"failed"` | yes |  |
| `device` | string | yes |  |
| `target` | string | yes | write:<channel> or action:<name>. |
| `value` | any | no |  |
| `unit` | string or null | no |  |
| `error` | [ErrorObject](#errorobject) or null | no |  |
| `requestId` | string or null | no |  |

### DescribeParams

| Field | Type | Required | Description |
|---|---|---|---|
| `device` | string | yes | A device id, for example printer. |

### DescribeResult

| Field | Type | Required | Description |
|---|---|---|---|
| `device` | [DeviceDescription](#devicedescription) | yes |  |

### DeviceAddedParams

| Field | Type | Required | Description |
|---|---|---|---|
| `device` | [DeviceSummary](#devicesummary) | yes |  |

### DeviceDescription

A DeviceSummary plus channels, actions, safe state, interlocks, watchdog rules and limits provenance.

| Field | Type | Required | Description |
|---|---|---|---|
| `id` | string | yes |  |
| `name` | string | yes |  |
| `model` | string or null | no |  |
| `manufacturer` | string or null | no |  |
| `driver` | string | yes |  |
| `hazard` | `"low"` or `"medium"` or `"high"` | yes |  |
| `writable` | boolean | yes | False until a person confirms every limit. |
| `connected` | boolean | yes |  |
| `conformance` | `"core"` or `"control"` or `"full"` | yes | The driver's declared conformance level. |
| `verification` | string | yes | unverified, verified-on-simulator or verified-on-hardware. |
| `unavailable` | string or null | no | Why the device can't take commands right now, or null when it can. |
| `read` | map of [ReadChannelInfo](#readchannelinfo) | yes |  |
| `write` | map of [WriteChannelInfo](#writechannelinfo) | yes |  |
| `actions` | map of [ActionInfo](#actioninfo) | yes |  |
| `safeState` | list of object | yes |  |
| `interlocks` | list of [InterlockInfo](#interlockinfo) | yes |  |
| `watchdog` | [WatchdogInfo](#watchdoginfo) | yes |  |
| `confirmed` | [Confirmed](#confirmed) or null | yes | The file-level confirmation of the limits. |
| `unconfirmed` | list of string | yes | Limits no person has confirmed yet. |
| `file` | string or null | yes | The Device File, for example printer.hal.yaml. |
| `notes` | string or null | no | Device File notes, inside a device-data block. |

### DeviceRemovedParams

| Field | Type | Required | Description |
|---|---|---|---|
| `device` | string | yes |  |

### DeviceSummary

| Field | Type | Required | Description |
|---|---|---|---|
| `id` | string | yes |  |
| `name` | string | yes |  |
| `model` | string or null | no |  |
| `manufacturer` | string or null | no |  |
| `driver` | string | yes |  |
| `hazard` | `"low"` or `"medium"` or `"high"` | yes |  |
| `writable` | boolean | yes | False until a person confirms every limit. |
| `connected` | boolean | yes |  |
| `conformance` | `"core"` or `"control"` or `"full"` | yes | The driver's declared conformance level. |
| `verification` | string | yes | unverified, verified-on-simulator or verified-on-hardware. |
| `unavailable` | string or null | no | Why the device can't take commands right now, or null when it can. |

### DevicesListResult

| Field | Type | Required | Description |
|---|---|---|---|
| `devices` | list of [DeviceSummary](#devicesummary) | yes |  |

### DryRunParams

| Field | Type | Required | Description |
|---|---|---|---|
| `commands` | list of [Write](#write) or [Action](#action) | yes |  |

### DryRunResult

| Field | Type | Required | Description |
|---|---|---|---|
| `decisions` | list of [Decision](#decision) | yes |  |

### Empty

Params for methods that take none.

No fields.

### ErrorData

`error.data`. `name` is the registry name clients branch on. Fields that don't apply are left out.

| Field | Type | Required | Description |
|---|---|---|---|
| `name` | string | yes | The registry name, for example LIMIT_EXCEEDED. |
| `kernelCode` | string or null | no | The Safety Kernel's code, for example above_max. |
| `kernelMessage` | string or null | no | The Safety Kernel's own message. |
| `device` | string or null | no |  |
| `channel` | string or null | no |  |
| `action` | string or null | no |  |
| `argument` | string or null | no | The action argument the error is about. |
| `limit` | [Quantity](#quantity) or null | no | The limit that applied, such as 100 % or 20 %/s. |
| `requested` | [Quantity](#quantity) or boolean or integer or number or string or null | no | The requested value, a Quantity in the limit's unit when it had one, otherwise as sent. |
| `runs` | integer or null | no | How many runs an action's max_runs allows per window. |
| `per` | [Quantity](#quantity) or null | no | The window of an action's max_runs. |
| `interlock` | string or null | no | The reason the device file gives for an interlock. |
| `expected` | [Quantity](#quantity) or null | no | The shape a number sent as one string should take. |
| `file` | string or null | no | The Device File, for example printer.hal.yaml. |
| `confirmedBy` | string or null | no | Who confirmed the limit. |
| `confirmedAt` | string or null | no | When the limit was confirmed, as 2026-10-24. |
| `requestId` | string or null | no |  |
| `tightenedBy` | string or null | no | Who tightened the session limit that applied. |

Other fields may be added in later versions.

### ErrorObject

The JSON-RPC `error` member.

| Field | Type | Required | Description |
|---|---|---|---|
| `code` | integer | yes | The registry number, stable across versions. |
| `message` | string | yes | The human-readable reason, formed from data. |
| `data` | [ErrorData](#errordata) or null | no |  |

### Failure

| Field | Type | Required | Description |
|---|---|---|---|
| `jsonrpc` | `"2.0"` | no |  |
| `id` | integer or string or null | yes |  |
| `error` | [ErrorObject](#errorobject) | yes |  |

### Info

`clientInfo` and `hubInfo`.

| Field | Type | Required | Description |
|---|---|---|---|
| `name` | string | yes |  |
| `version` | string | yes |  |

### InitializeParams

| Field | Type | Required | Description |
|---|---|---|---|
| `protocolVersion` | string | yes | The newest version the client supports, a number such as 0.1. |
| `clientInfo` | [Info](#info) | yes |  |
| `token` | string or null | no | The bearer token, if not sent as a header. |

### InitializeResult

| Field | Type | Required | Description |
|---|---|---|---|
| `protocolVersion` | string | yes | The version the hub returns, such as 0.1. |
| `hubInfo` | [Info](#info) | yes |  |
| `conformance` | `"core"` or `"control"` or `"full"` | yes |  |
| `principal` | [PrincipalInfo](#principalinfo) | yes |  |
| `capabilities` | [Capabilities](#capabilities) | yes |  |

### InterlockInfo

| Field | Type | Required | Description |
|---|---|---|---|
| `if` | string | yes |  |
| `require` | string | yes |  |
| `message` | string or null | no |  |

### LogEntry

One message in the Inspector's log, from `GET /v1/rpc/log`.

| Field | Type | Required | Description |
|---|---|---|---|
| `seq` | integer | yes |  |
| `at` | number | yes |  |
| `direction` | `"in"` or `"out"` | yes |  |
| `client` | string or null | no |  |
| `principal` | string or null | no |  |
| `message` | any | yes |  |

### MaxDurationInfo

| Field | Type | Required | Description |
|---|---|---|---|
| `when` | string | yes |  |
| `forS` | number | yes |  |
| `resetAfterS` | number or null | no |  |
| `then` | any | yes |  |

### Notification

A JSON-RPC notification. It has no id and gets no response.

| Field | Type | Required | Description |
|---|---|---|---|
| `jsonrpc` | `"2.0"` | yes |  |
| `method` | string | yes |  |
| `params` | object or null | no |  |

### Pending

| Field | Type | Required | Description |
|---|---|---|---|
| `status` | `"pending"` | no |  |
| `requestId` | string | yes |  |
| `expiresInS` | number | yes |  |

### PlanCheckParams

| Field | Type | Required | Description |
|---|---|---|---|
| `steps` | list of [Write](#write) or [Action](#action) or [Wait](#wait) | yes |  |

### PlanResult

| Field | Type | Required | Description |
|---|---|---|---|
| `ok` | boolean | yes | True only when every Decision is allowed and problems is empty. |
| `decisions` | list of [Decision](#decision) | yes |  |
| `problems` | list of string | yes |  |

### PrincipalInfo

| Field | Type | Required | Description |
|---|---|---|---|
| `kind` | `"human"` or `"agent"` or `"routine"` or `"system"` | yes |  |
| `name` | string | yes |  |
| `scope` | `"read"` or `"control_low"` or `"control_medium"` | yes |  |

### Quantity

A number and its unit (ADR 0016), for example `{"value": 20, "unit": "s"}`.

| Field | Type | Required | Description |
|---|---|---|---|
| `value` | integer or number | yes |  |
| `unit` | string | yes |  |

### ReadChannelInfo

| Field | Type | Required | Description |
|---|---|---|---|
| `type` | string | yes |  |
| `unit` | string or null | no |  |
| `everyS` | number or null | no |  |
| `stream` | boolean | no |  |
| `range` | list of number or null | no |  |
| `values` | list of string or null | no |  |

### ReadFailure

| Field | Type | Required | Description |
|---|---|---|---|
| `device` | string | yes |  |
| `channel` | string | yes |  |
| `error` | [ErrorObject](#errorobject) | yes |  |

### ReadManyParams

| Field | Type | Required | Description |
|---|---|---|---|
| `items` | list of [ReadParams](#readparams) | yes |  |

### ReadManyResult

| Field | Type | Required | Description |
|---|---|---|---|
| `readings` | list of [Reading](#reading) or [ReadFailure](#readfailure) | yes |  |

### ReadParams

| Field | Type | Required | Description |
|---|---|---|---|
| `device` | string | yes | A device id, for example printer. |
| `channel` | string | yes | A channel, for example bed_target. |

### Reading

| Field | Type | Required | Description |
|---|---|---|---|
| `device` | string | yes |  |
| `channel` | string | yes |  |
| `value` | any | yes | A number in `unit`, a bool or text. Text is inside a device-data block. |
| `unit` | string or null | no |  |
| `at` | string | yes | An RFC 3339 time in UTC, for example 2026-10-24T14:02:00Z. |
| `suspect` | boolean | no | True when the reading lies outside the channel's range. |

### RejectParams

| Field | Type | Required | Description |
|---|---|---|---|
| `requestId` | string | yes | A confirmation request id. |
| `reason` | string or null | no |  |

### Request

A JSON-RPC request, which has an id and gets a response.

| Field | Type | Required | Description |
|---|---|---|---|
| `jsonrpc` | `"2.0"` | yes |  |
| `id` | integer or string | yes |  |
| `method` | string | yes |  |
| `params` | object or null | no |  |

### RoutineDryRunParams

| Field | Type | Required | Description |
|---|---|---|---|
| `routineId` | string | yes |  |

### RoutineSummary

| Field | Type | Required | Description |
|---|---|---|---|
| `id` | string | yes |  |
| `kind` | string | yes |  |
| `enabled` | boolean | yes |  |
| `sha256` | string | yes |  |
| `devices` | list of string | yes |  |
| `maxHazard` | string or null | no |  |
| `triggers` | list of string | yes |  |
| `disabledReason` | string or null | no |  |

### RoutinesListResult

| Field | Type | Required | Description |
|---|---|---|---|
| `routines` | list of [RoutineSummary](#routinesummary) | yes |  |

### StopDevice

| Field | Type | Required | Description |
|---|---|---|---|
| `device` | string | yes |  |
| `status` | string | yes | safe, partial, failed, no_safe_state or pending. |
| `detail` | string | yes |  |

### StopParams

| Field | Type | Required | Description |
|---|---|---|---|
| `reason` | string or null | no |  |

### StopResult

| Field | Type | Required | Description |
|---|---|---|---|
| `devices` | list of [StopDevice](#stopdevice) | yes |  |

### StoppedDevice

| Field | Type | Required | Description |
|---|---|---|---|
| `device` | string | yes |  |
| `status` | string | yes |  |

### StoppedParams

| Field | Type | Required | Description |
|---|---|---|---|
| `reason` | string | yes |  |
| `by` | string | yes |  |
| `devices` | list of [StoppedDevice](#stoppeddevice) | yes |  |

### Success

| Field | Type | Required | Description |
|---|---|---|---|
| `jsonrpc` | `"2.0"` | no |  |
| `id` | integer or string | yes |  |
| `result` | object | yes |  |

### UnlockParams

| Field | Type | Required | Description |
|---|---|---|---|
| `phrase` | string | yes | Type unlock. |

### UnlockResult

| Field | Type | Required | Description |
|---|---|---|---|
| `ok` | boolean | yes |  |

### Wait

| Field | Type | Required | Description |
|---|---|---|---|
| `kind` | `"wait"` | no |  |
| `duration` | [Quantity](#quantity) | yes | A time such as 2 s, at most 1 h. |

### WatchdogInfo

| Field | Type | Required | Description |
|---|---|---|---|
| `heartbeatS` | number | yes |  |
| `onLoss` | string or null | no |  |
| `maxDuration` | list of [MaxDurationInfo](#maxdurationinfo) | yes |  |

### Write

| Field | Type | Required | Description |
|---|---|---|---|
| `kind` | `"write"` | no |  |
| `device` | string | yes | A device id, for example printer. |
| `channel` | string | yes | A channel, for example bed_target. |
| `value` | string or boolean or integer or number | yes |  |
| `unit` | string or null | no |  |

### WriteChannelInfo

| Field | Type | Required | Description |
|---|---|---|---|
| `type` | string | yes |  |
| `unit` | string or null | no |  |
| `min` | number or null | no |  |
| `max` | number or null | no |  |
| `step` | number or null | no |  |
| `maxChangePerS` | number or null | no |  |
| `values` | list of string or null | no |  |
| `maxLength` | integer or null | no |  |
| `pattern` | string or null | no |  |
| `confirm` | string | yes | none, confirm or confirm-each-time. |
| `suggested` | boolean | yes | True while the limits are a suggestion no person has confirmed. |
| `confirmed` | [Confirmed](#confirmed) or null | no | Who confirmed this channel's limits. |

### WriteDone

| Field | Type | Required | Description |
|---|---|---|---|
| `status` | `"done"` | no |  |
| `device` | string | yes |  |
| `channel` | string | yes |  |
| `value` | any | yes |  |
| `unit` | string or null | no |  |

### WriteParams

| Field | Type | Required | Description |
|---|---|---|---|
| `device` | string | yes | A device id, for example printer. |
| `channel` | string | yes | A channel, for example bed_target. |
| `value` | string or boolean or integer or number | yes | A number, a bool, an enum value or text. |
| `unit` | string or null | no | The unit of a number, such as %. |
