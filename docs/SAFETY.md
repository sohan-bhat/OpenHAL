# Safety model

Because AI agents move real things through OpenHAL, this document states exactly what the hub guarantees, how the hub enforces each guarantee, and what the hub does not guarantee. The safety kernel is written and reviewed against this document, so when the code and this document differ, the code is wrong.

## Guarantees

1. **One path.** Every write and every action, from any source (MCP, CLI, Python library, routines, dashboard, driver writer, bridges, the stop command itself), is evaluated by the safety kernel. Drivers accept writes only with a single-use grant the kernel issued for that exact device, channel or action, and value (ADR 0004).
2. **Deterministic.** The kernel is plain Python with no model, no network calls and no randomness in the checks, so the same state and the same command always produce the same result and the same message.
3. **Limits come from humans.** A person sets the limits in the device file, which records who confirmed the limits and when, and every command is checked against the limits. Agents may tighten limits for their own session. A device file with unconfirmed limits loads read-only.
4. **Stop works.** One stop command puts every device in its safe state and locks writes until a human unlocks.
5. **Fail closed.** Any unexpected exception inside the kernel blocks the command and is logged, so the kernel never passes a command after an internal failure.
6. **Everything is recorded.** Every read request, write attempt, block, confirmation, stop and unlock is in an append-only audit log with a hash chain.

## The checks, in order

The kernel evaluates a command against the current state in this fixed order and stops at the first failure. Each failure has a stable code and a message that names the rule, the limit and what to do.

| # | Check | Blocks when | Code |
|---|---|---|---|
| 1 | Command shape | Unknown device, channel or action, wrong argument names, malformed payload | `unknown_target`, `bad_request` |
| 2 | Stop lock | The global stop lock is set | `stopped` |
| 3 | File state | The device file has unconfirmed limits (read-only mode), or failed validation | `read_only_file` |
| 4 | Device state | Driver not connected, in a fault state, or currently applying its safe state. Also, any registered device whose interlock or condition names a device that isn't registered blocks every write on the hub, because a misspelled id protects nothing | `device_unavailable`, `misconfigured` |
| 5 | Principal scope | The token's kind or scope does not cover this device's hazard class or this operation | `not_permitted` |
| 6 | Units | Value has no unit, the unit can't be converted to the channel unit, or the result is not finite | `bad_unit` |
| 7 | Type and enum | Value is the wrong type, or not one of the allowed values | `bad_value` |
| 8 | Range | Below `min` or above `max` (including session limits tightened by an agent) | `below_min`, `above_max` |
| 9 | Step | Not a multiple of `step` from `min` (tolerance 1e-9 relative) | `bad_step` |
| 10 | Rate of change | The change from the last known value exceeds `max_change_per_s` times the elapsed time, or the current value is unknown | `rate_limited` |
| 11 | Interlocks | Any interlock whose condition applies is not satisfied by current or commanded state | `interlock` |
| 12 | Watchdog budget | The value would start or continue a state whose max duration is already used up | `duration_exceeded` |
| 14 | Confirmation | The channel or action needs confirmation, or the device is high hazard, and there is no valid approval | `needs_confirmation` (queued, not a failure), `queue_full` |

Check 13, serialization, happens before the others, so commands to one device run one at a time. The kernel holds a command for up to 5 s while the device is in use and blocks the command with `busy` when the device is still in use after 5 s, and a command that gets the device is evaluated against the state the previous command left.

A command that passes every check gets a grant and runs. A command that reaches check 14 without an approval goes to the confirmation queue.

### Unknown values

A channel's value is unknown when nothing has been read since the hub connected, when a sensor reading is older than `max(10 s, 3 x heartbeat)`, while a command to that channel is in flight, after a command to it failed or timed out (it may have landed), and after an action that lists it in `effects`. The hub reads such channels back right away when it can. The kernel counts an unknown value as unsafe, so interlocks treat an unknown value as not satisfied, rate limits block until a fresh value arrives, and watchdog rules keep counting.

### Notes on specific checks

- **Units.** Values are converted to the channel's declared unit with one pinned pint registry (ADR 0005). `85 degF` against a `max: 30 degC` channel is converted to 29.44 degC first, then compared. Temperatures in rate limits use delta units. The kernel blocks bare numbers, except for `bool`, `string` and `enum` channels.
- **Rate of change.** The reference value is the newest known value for that channel, whether the kernel passed the value or read the value from the device. If nothing is known since connecting, the first write is treated as a change from the channel's safe-state value, or from `min` if there is no safe state. If the value became unknown after connecting, the write is blocked until a fresh reading arrives. The allowed change is `max_change_per_s * elapsed_seconds`, with elapsed time measured on a monotonic clock and capped at 3600 s. A write that fails this check is blocked rather than ramped, so the library provides `ramp_to()`, which issues steps that each pass the check.
- **Tolerances.** Range limits allow values within 1e-12 relative of the limit, steps allow 1e-6 of one step, and rate limits allow 1e-9 relative.
- **String patterns** run on the `regex` engine with a time budget of 50 ms, so no value can stall the kernel, and the kernel blocks a value whose check runs out of time.
- **Concurrency.** Commands to one device are serialized, so when two clients race for the same channel, the kernel passes one command and then evaluates the other command against the new state. While a command to one device is in flight, the channels it may change are unknown to every other device's interlocks.
- **Interlocks** are written in a small expression language (spec section 7) and parsed by the hub's own parser, with no `eval`. An interlock that refers to a value the hub can't currently read counts as not satisfied.
- **Session limits.** With `tighten_limits` (MCP tool and API), a client can narrow `min`, `max` or `max_change_per_s` for the client's own session, and the kernel blocks a request that would widen a limit with `cannot_loosen`.

## Hazard classes

| Class | Examples | Agent scope needed | Confirmation |
|---|---|---|---|
| low | sensors, LEDs, small fans, displays | `control_low` | as set in the device file |
| medium | motors, pumps, printers, heaters under the file's threshold | `control_medium` | as set in the device file |
| high | lasers, CNC spindles, high voltage, high-power heaters, robots that can injure | `control_medium` to request, never to execute | every write and action is held for a human's approval, every time |

A device file with write channels or actions and no `hazard` is treated as medium.

High hazard devices can be driven by a routine only when the device file holds a human-signed approval for that routine's content hash (spec section 9), so changing the routine invalidates the approval.

## Limits provenance

A file is writable only when a human confirmed its limits (spec section 12). Interlocks, watchdog rules, the safe state and the hazard class need a file-level confirmation. A confirmation that carries `sha256` is bound to the file's limits, so any later change to them makes the file read-only again.

## Who confirms

- **Agents** never confirm, so an agent's command that needs confirmation is queued.
- **Humans** are the confirmers, so a command sent by a human principal (CLI with the human token, dashboard with a human session) counts as confirmed. Every other check still applies to it.
- **Routines** run unattended, so no person is there to approve a routine's command. A routine command that needs confirmation is blocked with `needs_confirmation` and the run fails, except on a high hazard device whose file carries a valid signed approval for that routine, where the approval is the confirmation.

## Confirmation queue

- Requests needing confirmation are queued with the exact command, the requesting principal, the dry-run result at the time of the request and an expiry (default 5 minutes).
- Each client may have at most 20 pending requests, and the queue holds at most 100. When the queue is full, the kernel blocks new requests with `queue_full` and never evicts someone else's request.
- Every change of a request's status (expired, cancelled, approved, rejected) is logged.
- Approving or rejecting a request takes a human principal, and agents see the status of their own requests.
- Approval re-runs every check against the current state, so a command that the current state would block is blocked instead of executed.
- Confirmation has two tiers. With `confirm`, one approval covers identical repeat requests from the same principal for 10 minutes, and with `confirm-each-time`, one approval covers exactly one execution, which is the only tier a high hazard device uses.
- Expired requests close automatically with the status `expired` and are logged.

## Stop and unlock

- `stop_all` is available from the CLI (`openhal stop`), MCP, the dashboard, the Python library and an optional Raspberry Pi GPIO input.
- The GPIO input is set in config.yaml as `stop_button: { pin: 27 }`, a BCM number, with the Pi's pull-up on unless `pull_up: false`. A press of the button stops every device. When the hub can't monitor the pin, the hub stops with an error at startup, so no one relies on a stop that isn't there. Because the button only sends a stop request to the hub, keep the hardware e-stop that cuts power.
- Any principal may stop, including agents, and unlocking takes a human principal.
- A stop sets the lock, cancels pending confirmations, clears approval windows, disables routines, cancels any command still in flight, applies every device's safe state and reports the result per device, in that order.
- Every safe-state step runs even if an earlier one fails. The result per device is `safe`, `partial` (some steps failed), `failed`, `no_safe_state`, or `pending` when a command was still running and couldn't be cancelled in time. When a command that was in flight during a stop returns, the hub reapplies the safe state, so the stop takes precedence over the command.
- The kernel blocks an unlock while a stop is still being applied, and an unlock clears approval windows again.
- Devices without a safe state are reported as such, and the device file loader reports a warning for write-capable devices with no safe state.
- `openhal unlock` needs a human token and, by default, an interactive terminal and the typed phrase `unlock`.

## Watchdogs

- **Heartbeat.** Each device has a health check interval. On connection loss the hub applies the safe state where the protocol allows a safe state, marks the device unavailable and blocks writes until the device reconnects.
- **Host heartbeat to firmware.** Devices running the OpenHAL firmware library fall to their safe state on their own if the hub's heartbeat stops (default 5 s).
- **Max duration.** Rules like "fan above 80 % for at most 10 minutes" are enforced by a hub timer. The budget starts when the rule's expression becomes true and only resets once the expression has been false for `reset_after`, so a brief dip doesn't refill it. While the budget runs, an unknown value counts as true. When the budget runs out the hub applies the rule's action (default the safe state). A failed action is retried with backoff, and a `then` mapping that fails three times escalates to the safe state.

## Prompt injection

Text that comes from devices, manuals, sketches, bridges, G-code files and device notes is data, so the hub handles that text in three ways.

- The hub returns the text to agents inside explicit data blocks (`<device-data source="...">...</device-data>`) with a fixed preamble stating that the text is not instructions.
- The hub never parses the text for commands, limits or approvals.
- The hub never changes a limit, approves a confirmation or starts an action because of anything the text contains.

## Network exposure

- The API binds to 127.0.0.1 by default.
- LAN access needs `api.allow_lan = true` in the config and a paired token per client.
- There is no telemetry and no outbound connection except to devices and bridged systems the user configured.

## The kernel's Python API is trusted

The hub builds principals from authenticated tokens, and agents reach the kernel only through the hub's HTTP and MCP interfaces. Code that holds the kernel object itself (the hub, routines, tests) could construct any principal, so that code is trusted. The kernel applies an approval only when the approval is the queue's own approved request, and approval signing is private to the kernel.

## What OpenHAL does not guarantee

- Limits are only as good as the person who confirmed the limits, so OpenHAL can't guarantee that a human set sensible limits.
- When firmware doesn't carry out a command or a sensor reports a wrong value, the kernel still uses the values the device reported, so OpenHAL can't guarantee that a device carries out each command.
- Bundled drivers pass the conformance suite and review, but a malicious in-process third-party driver could send commands to the driver's own hardware directly, so OpenHAL can't guarantee what such a driver sends. Out-of-process drivers are on the roadmap.
- OpenHAL doesn't protect against someone with full control of the user's account, as docs/THREAT_MODEL.md describes.
- OpenHAL is not a substitute for physical safety equipment such as e-stops, enclosures, interlocks wired in hardware or certified safety systems.
