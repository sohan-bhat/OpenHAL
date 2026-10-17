# Safety model

OpenHAL lets AI agents move real things. This document says exactly what the hub guarantees, how, and what it does not guarantee. It is the reference the safety kernel is written and reviewed against. If code and this document disagree, the code is wrong.

## Guarantees

1. **One path.** Every write and every action, from any source (MCP, CLI, Python library, routines, dashboard, driver writer, bridges, the stop command itself), is evaluated by the safety kernel. Drivers accept writes only with a single-use grant the kernel issued for that exact device, channel or action, and value (ADR 0004).
2. **Deterministic.** The kernel is plain Python with no model, no network calls and no randomness in decisions. The same state and the same command always produce the same decision and the same message.
3. **Limits come from humans.** Agents can tighten limits for their session. They can never loosen them. Loosening only happens when a human edits the device file, which records who and when. A device file with unconfirmed limits loads read-only.
4. **Stop works.** One stop command puts every device in its safe state and locks writes until a human unlocks.
5. **Fail closed.** Any unexpected exception inside the kernel blocks the command and is logged. Nothing fails open.
6. **Everything is recorded.** Every read request, write attempt, block, confirmation, stop and unlock is in an append-only audit log with a hash chain.

## The checks, in order

The kernel evaluates a command against the current state in this fixed order and stops at the first failure. Each failure has a stable code and a message that names the rule, the limit and what to do.

| # | Check | Blocks when | Code |
|---|---|---|---|
| 1 | Command shape | Unknown device, channel or action, wrong argument names, malformed payload | `unknown_target`, `bad_request` |
| 2 | Stop lock | The global stop lock is set | `stopped` |
| 3 | File state | The device file has unconfirmed limits (read-only mode), or failed validation | `read_only_file` |
| 4 | Device state | Driver not connected, in a fault state, or currently applying its safe state | `device_unavailable` |
| 5 | Principal scope | The token's kind or scope does not cover this device's hazard class or this operation | `not_permitted` |
| 6 | Units | Value has no unit, the unit can't be converted to the channel unit, or the result is not finite | `bad_unit` |
| 7 | Type and enum | Value is the wrong type, or not one of the allowed values | `bad_value` |
| 8 | Range | Below `min` or above `max` (including session limits tightened by an agent) | `below_min`, `above_max` |
| 9 | Step | Not a multiple of `step` from `min` (tolerance 1e-9 relative) | `bad_step` |
| 10 | Rate of change | The change from the last accepted value exceeds `max_change_per_s` times the elapsed time | `rate_limited` |
| 11 | Interlocks | Any interlock whose condition applies is not satisfied by current or commanded state | `interlock` |
| 12 | Watchdog budget | The value would start or continue a state whose max duration is already used up | `duration_exceeded` |
| 13 | Concurrency | Another command for the same device and channel is in flight | `busy` |
| 14 | Confirmation | The channel or action needs confirmation, or the device is high hazard, and there is no valid approval | `needs_confirmation` (queued, not a failure) |

A command that passes every check gets a grant and runs. A command that reaches check 14 without an approval goes to the confirmation queue.

### Notes on specific checks

- **Units.** Values are converted to the channel's declared unit with one pinned pint registry (ADR 0005). `85 degF` against a `max: 30 degC` channel is converted to 29.44 degC first, then compared. Temperatures in rate limits use delta units. Bare numbers are rejected, except for `bool`, `string` and `enum` channels.
- **Rate of change.** The reference value is the last value the kernel accepted for that channel, or the last value read from the device if nothing has been written since connecting. If neither exists, the first write is treated as a change from the channel's safe-state value, or from `min` if there is no safe state. The allowed change is `max_change_per_s * elapsed_seconds`, with elapsed time measured on a monotonic clock and capped at 3600 s. Writes that fail this check are blocked, not ramped. The library offers `ramp_to()`, which issues steps that each pass.
- **Concurrency.** Commands to one device are serialized. Two clients racing for the same channel get one accepted, then the other is evaluated against the new state.
- **Interlocks** are written in a small expression language (spec section 7), parsed by the hub's own parser. There is no `eval`. An interlock that refers to a value the hub can't currently read counts as not satisfied.
- **Session limits.** `tighten_limits` (MCP tool and API) lets a client narrow `min`, `max` or `max_change_per_s` for its own session. Requests that would widen a limit are rejected with `cannot_loosen`.

## Hazard classes

| Class | Examples | Agent scope needed | Confirmation |
|---|---|---|---|
| low | sensors, LEDs, small fans, displays | `control_low` | as the device file says |
| medium | motors, pumps, printers, heaters under the file's threshold | `control_medium` | as the device file says |
| high | lasers, CNC spindles, high voltage, high-power heaters, robots that can injure | no agent scope covers it | every write and action, every time |

A device file with write channels or actions and no `hazard` is treated as medium.

High hazard devices can be driven by a routine only when the device file holds a human-signed approval for that routine's content hash (spec section 9). Changing the routine invalidates the approval.

## Confirmation queue

- Requests needing confirmation are queued with the exact command, the requesting principal, the dry-run result at the time of the request and an expiry (default 5 minutes).
- Only a human principal can approve or reject. Agents can see the status of their own requests.
- Approval re-runs every check against the current state. If anything changed so that the command would now be blocked, it is blocked, not executed.
- Tiers. `confirm` lets one approval cover identical repeat requests from the same principal for 10 minutes. `confirm-each-time` approves exactly one execution. High hazard is always `confirm-each-time`.
- Expired requests are rejected automatically and logged.

## Stop and unlock

- `stop_all` is available from the CLI (`openhal stop`), MCP, the dashboard, the Python library and an optional Raspberry Pi GPIO input.
- Any principal may stop, including agents. Only a human may unlock.
- Order. Set the lock, cancel pending confirmations, pause routines, apply every device's safe state, report the result per device.
- Devices without a safe state are reported as such. The device file schema warns about write-capable devices with no safe state.
- `openhal unlock` needs a human token and, by default, an interactive terminal and the typed phrase `unlock`.

## Watchdogs

- **Heartbeat.** Each device has a health check interval. On connection loss the hub applies the safe state where the protocol allows it, marks the device unavailable and blocks writes until it reconnects.
- **Host heartbeat to firmware.** Devices running the OpenHAL firmware library fall to their safe state on their own if the hub's heartbeat stops (default 5 s).
- **Max duration.** Rules like "fan above 80 % for at most 10 minutes" are enforced by a hub timer. When the budget runs out the hub applies the rule's action (default the safe state) and logs it.

## Prompt injection

Text that comes from devices, manuals, sketches, bridges, G-code files and device notes is data. The hub:

- returns it to agents inside explicit data blocks (`<device-data source="...">...</device-data>`) with a fixed preamble that it is not instructions,
- never parses it for commands, limits or approvals,
- never changes a limit, approves a confirmation or starts an action because of anything it contains.

## Network exposure

- The API binds to 127.0.0.1 by default.
- LAN access needs `api.allow_lan = true` in the config and a paired token per client.
- There is no telemetry and no outbound connection except to devices and bridged systems the user configured.

## What OpenHAL does not guarantee

- That a human set sensible limits. Limits are only as good as the person who confirmed them.
- That a device obeys. If firmware ignores a command or a sensor lies, the kernel acts on what it was told.
- That an in-process third-party driver behaves. Bundled drivers pass the conformance suite and review, but a malicious driver could talk to its own hardware directly. Out-of-process drivers are on the roadmap.
- Protection from someone with full control of the user's account. See docs/THREAT_MODEL.md.
- Physical safety equipment. OpenHAL is not a substitute for e-stops, enclosures, interlocks wired in hardware or certified safety systems.
