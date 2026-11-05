# Safety model

The safety kernel is reviewed against this page. Where the code and this page differ, the code is wrong.

## Guarantees

1. **One path.** The kernel checks every write and action from every client, routine, run, bridge and the stop command. A driver takes a write only with a single-use grant for that exact device, target and value, per ADR 0004.
2. **Deterministic.** The kernel is plain Python with no model, network calls or randomness, so the same state and command always give the same result.
3. **Risk decides where a person comes in.** Every channel and action has a [risk level](#risk-levels). High risk targets stay read-only until a person confirms their limits, and the file records who and when. Low and medium targets take commands within the device's own range. Agents may only tighten limits, for their own session. Only a person loosens a limit or lowers a level.
4. **Stop works.** One stop puts every device in its safe state and locks writes until a human unlocks.
5. **Fail closed.** An unexpected exception in the kernel blocks the command and is logged.
6. **Everything is recorded.** Every read, write attempt, block, confirmation, stop and unlock goes into an append-only, hash-chained audit log.

## The checks, in order

The kernel stops at the first failure. Each failure has a stable code and a message naming the rule, the limit and the next step.

| # | Check | Blocks when | Code |
|---|---|---|---|
| 1 | Command shape | Unknown device, channel or action, wrong argument names, malformed payload | `unknown_target`, `bad_request` |
| 2 | Stop lock | The stop lock is set | `stopped` |
| 3 | File state | The target's limits, or the file-level limits guarding the target, are unconfirmed, and the target is high risk or has suggested limits the device or library didn't supply | `read_only_file` |
| 4 | Device state | The driver is disconnected, faulted or applying its safe state. An interlock or condition naming an unregistered device blocks every write on the hub, since a misspelled id protects nothing | `device_unavailable`, `misconfigured` |
| 5 | Principal scope | The token's kind or scope doesn't cover the operation, or the lower of the target's risk level and the device's hazard class | `not_permitted` |
| 6 | Units | No unit, a unit that doesn't convert to the channel unit, or a non-finite result | `bad_unit` |
| 7 | Type and enum | Wrong type, or not an allowed value | `bad_value` |
| 8 | Range | Below `min` or above `max`, session limits included | `below_min`, `above_max` |
| 9 | Step | Not a multiple of `step` from `min` | `bad_step` |
| 10 | Rate of change | The change since the last known value exceeds `max_change_per_s` times the elapsed time, or the value is unknown. A suggested rate on a low risk channel doesn't apply | `rate_limited` |
| 11 | Interlocks | An applicable interlock fails on current or commanded state | `interlock` |
| 12 | Watchdog budget | The value would start or extend a state whose max duration is used up | `duration_exceeded` |
| 14 | Confirmation | The target needs confirmation, the device is high hazard, or a high risk action can't be undone, and no valid approval exists | `needs_confirmation`, `queue_full` |

Check 13, serialization, runs first, so commands to one device run one at a time. The kernel holds a command up to 5 s for a busy device, then blocks the command with `busy`. Each command is checked against the state the previous one left, and channels a command in flight may change are unknown to other devices' interlocks.

A command that passes gets a grant and runs. One that reaches check 14 without approval is queued, which is not a failure.

### Unknown values

A value is unknown before the first read after connecting, when a reading is older than `max(10 s, 3 x heartbeat)`, while a command to the channel is in flight, after that command failed or timed out, and after an action listing the channel in `effects`. The hub reads such channels back at once when possible. Unknown counts as unsafe. Interlocks fail, rate limits block until a fresh value, and watchdog rules keep counting.

### Notes on specific checks

- **Units.** One pinned pint registry converts to the channel unit, per ADR 0005, so `85 degF` against `max: 30 degC` compares as 29.44 degC. Temperature rates use delta units. Bare numbers are blocked except on `bool`, `string` and `enum` channels.
- **Rate of change.** The reference is the newest known value, passed or read. With nothing known since connecting, the first write counts from the safe-state value, or from `min` without one. Allowed change is `max_change_per_s * elapsed_seconds` on a monotonic clock, elapsed capped at 3600 s. A failing write is blocked, never ramped. The library's `ramp_to()` sends steps that each pass.
- **Tolerances.** Range 1e-12 relative, step 1e-6 of one step, rate 1e-9 relative.
- **String patterns** run on the `regex` engine with a 50 ms budget. A value whose check runs out of time is blocked.
- **Interlocks** use the expression language of spec section 7, read by the hub's own parser with no `eval`.
- **Session limits.** `tighten_limits`, an MCP tool and API route, narrows `min`, `max` or `max_change_per_s` for the caller's session. Widening is blocked with `cannot_loosen`.

## Risk levels

The hub sets levels from the device file and the device's own description, never from a list of device names. Rules are in `openhal/spec/risk.py` and [ADR 0023](adr/0023-risk-levels.md).

| Level | From | Default |
|---|---|---|
| low | Reading any channel. Light units such as lux or candela. Name words for light, sound or a display, such as brightness, buzzer or text | Commands at once within the device's full reported range, with no read-only start, interview, rate cap or approval |
| medium | Angle, angular speed, volume, flow or mass units. Lower power, voltage or current. Name words for pumps, valves, flow, motors, fans and servos. A bare pin with no such words, at least. Anything no rule covers | Commands at once within the device's reported range and rate, with no interview or approval |
| high | Temperature, length, speed, acceleration, force, torque or pressure units. Power above 100 W, voltage above 50 V or current above 10 A, either sign. Name words for heat, mains switching, machine motion or force, such as heater, relay, joint or spindle. Low words on a device whose name is high, such as a heat lamp. Each of three or more angle or length channels on one device, such as arm joints | Read-only until a person confirms the limits. An action that can't be undone is held for a person at least once |

- The file's `hazard` sets a floor.
- A name with none of these words takes the words of the device's name.
- No unit, or a unit the rules don't list, moves one level up.
- An action takes the highest of its name, its argument units and the channels the action changes.
- Channels and actions on one pin share the highest level on that pin.
- A `risk` with `by` and `at` sets the level up or down. A `risk` with no `by` only raises.
- Words in a channel's own name can set any level. Words from descriptions and enum values only raise, so device text can't lower a level.

A person can add confirmation or limits at any level, and stop, the safe state, the watchdogs and the audit log apply at every level. An action can be undone when every listed effect is a write channel, when the safe state runs the action, or when the device has an undoing action such as resume for pause.

`openhal risk set DEVICE.NAME LEVEL` raises a level at once. Lowering takes the typed phrase `confirm`, like widening a limit, or becomes a pending change for a person to approve. Agents see every level and change none. Every change goes into the device file and the audit log.

A plain OpenHAL board pin is medium, since the file has no word for what is wired there. A pin sharing its number with a high risk channel, such as a mapped heater, is high. The board blocks pin commands to pins its sketch claims.

## Hazard classes

| Class | Examples | Agent scope | Confirmation |
|---|---|---|---|
| low | sensors, LEDs, small fans, displays | `control_low` | as the device file sets |
| medium | motors, pumps, printers, heaters under the file's threshold | `control_medium`, or `control_low` for a low risk target | as the device file sets |
| high | lasers, CNC spindles, high voltage, high-power heaters, robots that can injure | `control_medium` to request, never to execute | a human approves every write and action, every time |

A file with write channels or actions and no `hazard` counts as medium.

## Limits provenance

High risk targets, and low or medium targets whose suggested limits came from neither the device nor the library, such as a manual, a sketch, an agent, a bridge or a hand-written file, take commands only after a human confirms their limits, per spec section 12. Interlocks, watchdog rules, the safe state and the hazard class need a file-level confirmation. A confirmation with `sha256` is bound to the limits, so any later limit change makes those targets read-only again. A file confirmed earlier keeps its limits.

## Who confirms

- **Agents** never confirm. Their commands that need confirmation are queued.
- **Humans** confirm. A command from a human principal, through the CLI with the human token or a dashboard human session, counts as confirmed and still passes every other check.
- **Routines** run unattended, so a routine command that needs confirmation is blocked with `needs_confirmation` and the run fails. On a high hazard device, a human-signed approval in the device file for the routine's content hash counts as the confirmation, per spec section 9. Any change to the routine voids the approval.

## Confirmation queue

- Each request holds the exact command, the principal, the dry-run result at request time and an expiry, 5 minutes by default.
- At most 20 pending requests per client and 100 in all. A full queue blocks new requests with `queue_full` and never evicts another request.
- Expired requests close as `expired`. Every status change is logged, including expiry, cancelling, approval and rejection.
- Approving or rejecting takes a human principal. Agents see the status of their own requests.
- Approval re-runs every check against the current state.
- Under `confirm`, one approval covers identical repeats from the same principal for 10 minutes. Under `confirm-each-time`, one approval covers one execution. High hazard devices use only `confirm-each-time`.

## Stop and unlock

- `stop_all` comes from `openhal stop`, MCP, the dashboard, the Python library and an optional Raspberry Pi GPIO input.
- Set the GPIO input in config.yaml as `stop_button: { pin: 27 }`, a BCM number. The Pi's pull-up is on unless `pull_up: false`. When the hub can't monitor the pin, the hub stops with an error at startup. The button only sends a stop request, so keep the hardware e-stop that cuts power.
- Any principal may stop. Unlocking takes a human principal.
- A stop sets the lock, cancels pending confirmations, clears approval windows, disables routines, ends every run, wait and sample, cancels commands in flight, applies every safe state and reports per device, in that order.
- Every safe-state step runs even after an earlier one fails. Each device reports `safe`, `partial`, `failed`, `no_safe_state`, or `pending` when a running command couldn't be cancelled in time. When that command returns, the hub reapplies the safe state.
- Unlock is blocked while a stop is still applying, and clears approval windows again.
- Devices without a safe state are reported as such. Loading a write-capable device file with no safe state gives a warning.
- `openhal unlock` needs a human token and, by default, an interactive terminal and the typed phrase `unlock`.

## Runs of steps

A run sends timed commands, per ADR 0019. The kernel checks each command, and the hub adds these rules.

- The hub checks the whole run as a plan first, and if a step is blocked nothing runs. Waits move a simulated clock and condition waits move the clock by nothing. After a condition wait, blocks that depend on live readings, such as interlocks, are left to the kernel when the command runs.
- Each command goes to the kernel as the principal that started the run, so rate checks use real elapsed time.
- The first step that isn't done ends the run. A step that needs confirmation ends the run with the request id, and approving runs only that command.
- Steps only read, change a channel, run an action or wait. No step approves, unlocks, widens a limit, enables a routine or carries a principal or request id.
- A stop, a cancel by the owner or a person, a revoked owner token or the time cap ends a run before its next step. A lowered time cap reaches a running run within a second.
- Other agents can't see or cancel a run. A person sees and cancels every run.
- `config.yaml` caps steps per run, seconds per run, wait or sample, and how many one token has going at once. Only a person changes the caps, and raising one takes the typed phrase `confirm`.
- The audit log records each run's start, end and steps with the run id, next to the kernel's entries.

## Watchdogs

- **Heartbeat.** Each device has a health check interval. On connection loss the hub applies the safe state where the protocol allows, marks the device unavailable and blocks writes until the device reconnects.
- **Host heartbeat to firmware.** Boards running the OpenHAL firmware library go to their safe state on their own when the hub's heartbeat stops, after 5 s by default.
- **Max duration.** A hub timer enforces rules such as "fan above 80 % for at most 10 minutes". The budget starts when the expression turns true and resets only after the expression stays false for `reset_after`. Unknown counts as true while the budget runs. When the budget runs out, the hub applies the rule's action, the safe state by default. Failed actions retry with backoff, and a `then` mapping that fails three times escalates to the safe state.

## Prompt injection

Text from devices, manuals, sketches, bridges, G-code files and device notes is data. The hub returns such text inside `<device-data source="...">...</device-data>` blocks with a fixed preamble stating the text is not instructions. The hub never parses such text for commands, limits or approvals, and never changes a limit, approves a request or starts an action because of such text.

## Network exposure

- The API binds to 127.0.0.1 by default.
- LAN access needs `api.allow_lan = true` and a paired token per client.
- No telemetry, and no outbound connections except to devices and bridged systems the user configured.

## The kernel's Python API is trusted

Agents reach the kernel only through the hub's HTTP and MCP interfaces, where principals come from authenticated tokens. Code holding the kernel object, such as the hub, routines and tests, could build any principal, so that code is trusted. The kernel applies only approvals from the queue's own approved requests, and approval signing is private to the kernel.

## What OpenHAL does not guarantee

- Limits are only as good as the person who confirmed the limits.
- A fresh device's low and medium targets run within the range the device or library suggested. The risk rules err high but use only names and units, so check levels with `openhal risk show` and fix one with `openhal risk set`.
- The kernel uses the values a device reports, so OpenHAL can't guarantee that firmware carries out a command or that a sensor reads true.
- A malicious in-process third-party driver could command its own hardware directly. Bundled drivers pass conformance and review, and out-of-process drivers are on the roadmap.
- OpenHAL doesn't protect against someone with full control of the user's account, as docs/THREAT_MODEL.md describes.
- OpenHAL is no substitute for e-stops, enclosures, hardware interlocks or certified safety systems.
