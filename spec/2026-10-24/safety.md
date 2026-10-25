# Safety

This section states what a Safety Kernel MUST do. A Hub at Conformance Level `control` or `full` MUST evaluate every command through a Safety Kernel that meets every requirement here.

## Guarantees

1. **One path.** Every command, from any source, MUST be evaluated by the Safety Kernel. Sources include every Client, routines, the dashboard, the driver writer, bridges and the stop command itself. A Driver MUST accept a change only with a single-use Grant the Safety Kernel issued for that exact Device, target and value.
2. **Deterministic.** The Safety Kernel MUST NOT use a model, network calls or randomness to decide. The same state and the same command MUST produce the same decision and the same message.
3. **Limits come from humans.** Agents MAY tighten limits for their own session. Nothing MAY loosen a limit except a human editing the Device File, which records who and when. A Device File with unconfirmed limits loads read-only.
4. **Stop works.** One stop command MUST put every Device in its safe state and refuse every other command until a human unlocks.
5. **Fail closed.** Any unexpected exception inside the Safety Kernel MUST block the command and be logged. Nothing fails open.
6. **Everything is recorded.** Every read request, command, block, confirmation, stop and unlock MUST be appended to an audit log with a hash chain.

## The checks, in order

The Safety Kernel evaluates a command against the current state in this fixed order and MUST stop at the first failure. Each failure has a stable kernel code and a registry name.

| # | Check | Blocks when | Kernel code | Name |
|---|---|---|---|---|
| 1 | Command shape | Unknown Device, channel or action, wrong argument names, malformed payload | `unknown_target`, `bad_request` | UNKNOWN_TARGET, INVALID_PARAMS |
| 2 | Stop lock | The global stop lock is set | `stopped` | STOPPED |
| 3 | File state | The Device File has unconfirmed limits (read-only mode) | `read_only_file` | UNVERIFIED_LIMITS |
| 4 | Device state | The Driver is not connected, is in a fault state, or is applying its safe state. Also, any registered Device whose expressions name a Device that isn't registered blocks every command on the Hub, because a misspelled id protects nothing | `device_unavailable`, `misconfigured` | DEVICE_UNAVAILABLE, MISCONFIGURED |
| 5 | Principal scope | The Principal's kind or scope does not cover this Device's hazard class or this operation | `not_permitted` | SCOPE_DENIED |
| 6 | Units | The value has no unit, the unit can't be converted to the channel unit, or the result is not finite | `bad_unit` | UNIT_INVALID |
| 7 | Type and enum | The value is the wrong type, not one of the allowed values, too long, or doesn't match the pattern | `bad_value` | INVALID_VALUE |
| 8 | Range | Below `min` or above `max`, including session limits | `below_min`, `above_max` | LIMIT_EXCEEDED |
| 9 | Step | Not a multiple of `step` from `min` | `bad_step` | INVALID_VALUE |
| 10 | Rate of change | The change from the last known value exceeds `max_change_per_s` times the elapsed time, or the current value is unknown | `rate_limited` | RATE_LIMITED |
| 11 | Interlocks | An action's `require` doesn't hold, or an interlock that applies is not satisfied by the current and commanded state | `interlock` | INTERLOCK_BLOCKED |
| 12 | Watchdog budget | The value would start or continue a state whose max duration is already used up | `duration_exceeded` | WATCHDOG_TRIPPED |
| 13 | Serialization | Another command holds the Device for longer than 5 s | `busy` | BUSY |
| 14 | Confirmation | The channel or action needs confirmation, or the Device is high hazard, and there is no valid approval | `needs_confirmation`, `queue_full` | CONFIRMATION_REQUIRED, QUEUE_FULL |

Check 13 runs before the others. Commands to one Device MUST run one at a time. A command waits up to 5 s for the Device, and is then evaluated against the state the previous command left.

A command that passes every check gets a Grant and runs. A command that reaches check 14 without an approval goes to the confirmation queue, and `hal/write` or `hal/action` returns a pending result with its `requestId`.

## Unknown values

1. A channel's value is unknown when nothing has been read since the Hub connected, when a sensor reading is older than `max(10 s, 3 x heartbeat)`, while a command to that channel is in flight, after a command to it failed or timed out (it may have landed), and after an action that lists it in `effects`.
2. A write channel's last commanded value stays known while the Device is connected, because the Device holds it.
3. The Hub SHOULD read such channels back right away when it can.
4. Unknown MUST NOT let a command pass. Interlocks treat it as not satisfied, rate limits block until a fresh value arrives, and watchdog rules keep counting.
5. While a command to one Device is in flight, the channels it may change are unknown to every other Device's interlocks.

## Rules for specific checks

- **Units.** Values are converted to the channel's declared unit with one pinned unit registry. `85 degF` against a `max: 30 degC` channel is converted to 29.44 degC first, then compared. Bare numbers MUST be refused for `number` channels.
- **Range tolerance.** A value within 1e-12 relative of a limit passes.
- **Step tolerance.** A value within 1e-6 of one step passes.
- **Rate of change.** The reference value is the newest known value for that channel, whether the Safety Kernel accepted it or read it from the Device. If nothing is known since connecting, the first command is measured from the channel's safe-state value, or from `min` if there is no safe state. If the value became unknown after connecting, the command is blocked until a fresh reading arrives. The allowed change is `max_change_per_s * elapsed_seconds`, with elapsed time on a monotonic clock, capped at 3600 s, and a relative tolerance of 1e-9. Commands that fail this check are blocked, not ramped. A Client that wants to move further issues steps that each pass.
- **String patterns** MUST run with a time budget so no value can stall the Safety Kernel. The reference uses 50 ms. A value whose check runs out of time is refused.
- **Interlocks** use the expression language of [Device files](device-files.md#7-interlocks-and-expressions) and are parsed by the Hub's own parser. Expressions MUST NOT be evaluated as code.
- **Session limits.** A Client MAY narrow `min`, `max` or `max_change_per_s` for its own session. A request that would widen a limit MUST be refused with `cannot_loosen` (MISCONFIGURED). This version exposes session limits through MCP and REST only.

## Grants

1. A Grant names one Device, one target (`write:<channel>`, `action:<name>` or `safe_state`) and one exact value in the channel's unit.
2. Only the Safety Kernel can create a Grant. Constructing one any other way MUST fail.
3. A Grant MUST be consumed on use, and MUST be refused if it was already used, has expired, or names another Device, target or value. The reference expiry is 5 s.
4. A Driver receives a verifier bound to its own Device, not a reference to the Safety Kernel.
5. A stop and a lost connection revoke every live Grant for the Device.

## Principals and hazard classes

| Hazard | Examples | Agent scope needed | Confirmation |
|---|---|---|---|
| `low` | sensors, LEDs, small fans, displays | `control_low` | as the Device File says |
| `medium` | motors, pumps, printers, heaters | `control_medium` | as the Device File says |
| `high` | lasers, CNC spindles, high voltage, high-power heaters, robots that can injure | `control_medium` to request, never to execute | every command waits for a human, every time |

1. An agent with scope `read` MUST NOT change write channels or run actions.
2. A human Principal's own command counts as confirmed. Every other check still applies to it.
3. The `system` Principal is internal to the Hub. It applies safe states and watchdog actions and is never accepted from a Client.
4. A routine runs with the scope of whoever enabled it, capped at `control_medium` ([Routines](routines.md)).
5. A routine MAY drive a high hazard Device only when the Device File holds a human-signed approval for that routine's content hash ([Device files](device-files.md#9-hazard-class-and-approvals)). Changing the routine invalidates the approval.

## Confirmations

1. Agents never confirm. A command that needs confirmation is queued as a Confirmation Request.
2. A Confirmation Request holds the exact command, the requesting Principal, the dry-run result at the time of the request and an expiry. The reference expiry is 5 minutes.
3. Each Principal MAY have at most 20 pending requests, and the queue holds at most 100. A full queue refuses new requests with QUEUE_FULL. It MUST NOT evict another Principal's request.
4. Only a human Principal may approve or reject. Other Principals may see the status of their own requests.
5. Approval MUST re-run every check against the current state. If the command would now be blocked, it is blocked, not executed.
6. Tier `confirm` lets one approval cover identical repeat requests from the same Principal for 10 minutes. Tier `confirm-each-time` approves exactly one execution. High hazard is always `confirm-each-time`.
7. A routine cannot wait for a person. Its command that needs confirmation is blocked with CONFIRMATION_REQUIRED, except on a high hazard Device whose file carries a valid signed approval for that routine.
8. Every change of a request's status (expired, cancelled, approved, rejected) MUST be logged. Expired requests are rejected automatically.

## Stop and unlock

1. Any Principal MAY stop, including agents. Only a human MAY unlock.
2. A stop runs in this order. Set the lock, cancel pending Confirmation Requests, clear approval windows, disable routines, cancel any command still in flight, apply every Device's safe state, then report the result per Device.
3. Every safe-state step MUST run even if an earlier one fails. A Driver with native safe-state support runs its own safe behavior first, then the Device File's steps.
4. The result per Device is `safe`, `partial` (some steps failed), `failed`, `no_safe_state`, or `pending` when a command was still running and couldn't be cancelled in time.
5. A command that was in flight during a stop MUST reapply the safe state when it returns, so it can't win.
6. Unlock MUST be refused while a stop is still being applied, and clears approval windows again.
7. Unlock requires the typed phrase `unlock`. The reference CLI also requires an interactive terminal by default.

## Watchdogs

1. **Heartbeat.** The Hub checks each Device at its `heartbeat` interval. On connection loss it applies the safe state where `on_loss` asks for it, marks the Device unavailable and blocks commands until it reconnects.
2. **Max duration.** A rule's budget starts when its expression becomes true and only resets once the expression has been false for `reset_after`, so a brief dip doesn't refill it. While the budget runs, an unknown value counts as true.
3. When a budget runs out, the Hub applies the rule's `then`. A failed action is retried with backoff, and a `then` mapping that fails three times escalates to the safe state.

## Limits provenance

1. A Device File accepts commands only when a human confirmed its limits ([Device files](device-files.md#12-limits-provenance)).
2. A confirmation that carries `sha256` is bound to the file's limits, so any later change makes the file read-only again.
3. A LIMIT_EXCEEDED reason MUST name the Device File and the human confirmation behind the limit. `data.confirmedBy` and `data.confirmedAt` come from the channel's own `confirmed`, or else the file's.

## Error registry

A blocked or failed command is a JSON-RPC error ([Messages](basic/messages.md#errors)). `data.name` is what Clients branch on. Numbers are stable across versions and MUST NOT be reused. Every kernel code maps to exactly one name.

| Code | Name | Kernel codes | Meaning |
|---|---|---|---|
| -32700 | PARSE_ERROR | | Invalid JSON |
| -32600 | INVALID_REQUEST | | Not a JSON-RPC request |
| -32601 | METHOD_NOT_FOUND | | Unknown method, or one above the Hub's Conformance Level |
| -32602 | INVALID_PARAMS | `bad_request` | Params don't match the schema |
| -32603 | INTERNAL_ERROR | `internal_error` | A bug in the Hub |
| -32001 | NOT_INITIALIZED | | `hal/initialize` hasn't run |
| -32002 | UNAUTHORIZED | | Missing or unknown token |
| -32003 | SCOPE_DENIED | `not_permitted` | The Principal's token scope doesn't cover this Device or method |
| -32004 | UNKNOWN_TARGET | `unknown_target` | No such Device, channel or action |
| -32005 | DEVICE_UNAVAILABLE | `device_unavailable` | Disconnected or not ready |
| -32010 | LIMIT_EXCEEDED | `above_max`, `below_min` | Outside the Device File's confirmed limits |
| -32011 | RATE_LIMITED | `rate_limited` | Faster than `max_change_per_s` allows right now |
| -32012 | INTERLOCK_BLOCKED | `interlock` | An interlock or action requirement doesn't hold, or a value it needs is unknown |
| -32013 | CONFIRMATION_REQUIRED | `needs_confirmation` | Needs a person. `data.requestId` names the request when it was queued |
| -32014 | STOPPED | `stopped` | The Hub is stopped until a person unlocks |
| -32015 | UNVERIFIED_LIMITS | `read_only_file` | The Device File's limits aren't confirmed by a person, so it is read-only |
| -32016 | INVALID_VALUE | `bad_value`, `bad_step` | Wrong type, step, enum value or pattern |
| -32017 | WATCHDOG_TRIPPED | `duration_exceeded` | A watchdog budget is used up |
| -32018 | BUSY | `busy` | Another command holds the Device |
| -32019 | QUEUE_FULL | `queue_full` | The confirmation queue is full |
| -32020 | DRIVER_ERROR | `driver_error` | The Device or its protocol failed, and the channel is unknown until a readback |
| -32021 | MISCONFIGURED | `misconfigured`, `cannot_loosen` | The Hub's Device Files are inconsistent, or a change would loosen a confirmed limit |
| -32022 | REQUEST_CLOSED | `expired`, `rejected` | The Confirmation Request expired or was rejected |
| -32023 | UNIT_INVALID | `bad_unit` | A missing, unknown or incompatible unit, or a value that isn't finite |

### Reason messages

`error.message` is formed from `data`, one template per name. The Safety Kernel's own message stays available as `data.kernelMessage`. Every reason SHOULD name the rule, the limit and what to do next.

The LIMIT_EXCEEDED templates are normative.

| Kernel code | Template |
|---|---|
| `above_max` | `{channel} {requested} exceeds the limit of {limit} ({file}, confirmed by {confirmedBy} {confirmedAt})` |
| `below_min` | `{channel} {requested} is below the limit of {limit} ({file}, confirmed by {confirmedBy} {confirmedAt})` |

For an action argument, `{channel}` is `{action} {argument}`. For the canonical example the reason reads `water duration 120 s exceeds the limit of 30 s (plant-waterer.hal.yaml, confirmed by sohan 2026-10-24)`.
