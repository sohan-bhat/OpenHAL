# Independent safety review of the kernel

Reviewer. An independent agent working from the code and the safety documents only.
Date. 2026-10-24.
Scope. `openhal/kernel/`, `openhal/drivers/base.py`, `openhal/drivers/mock/driver.py`, `openhal/spec/` and `openhal/audit/log.py`, checked against docs/SAFETY.md, docs/THREAT_MODEL.md and spec/SPEC.md.

Every proof of concept lives in `tests/review_safety/` and uses only the mock driver or small subclasses of it. Each test is named after its finding and fails against the current code. Run them with this command.

```
export PATH="$HOME/Library/Python/3.13/bin:$PATH"; cd ~/code/openhal; uv run pytest tests/review_safety -q
```

At the time of writing all 17 tests fail, which is the intended result. The existing suite in `tests/kernel` still passes.

## Summary

| # | Severity | Finding | Test |
|---|---|---|---|
| F01 | critical | Unknown same-device values are evaluated as bare words, so interlocks and preconditions pass on unknown state | `test_f01_unknown_becomes_word.py` |
| F02 | high | Cross-device interlocks are checked against stale state while another device's write is in flight | `test_f02_cross_device_interlock_race.py` |
| F03 | high | Stop reports a device safe while an older write is still landing, and that write wins | `test_f03_stop_during_inflight_write.py` |
| F04 | high | A brief dip resets a max_duration budget, ignoring `reset_after` | `test_f04_watchdog_budget_reset_by_dip.py` |
| F05 | high | An action with `effects` resets the rate reference to a stale snapshot | `test_f05_action_effects_reset_rate_reference.py` |
| F06 | high | Driver exceptions outside three types escape `execute()` with no audit entry | `test_f06_driver_exception_escapes.py` |
| F07 | high | A backtracking `pattern` lets one agent write freeze the kernel and the stop path | `test_f07_pattern_backtracking_freezes_kernel.py` |
| F08 | medium | A driver can reach the kernel through its verifier and drive other devices | `test_f08_driver_reaches_kernel.py` |
| F09 | medium | Several events the documents promise to log leave no audit entry | `test_f09_audit_gaps.py` |
| F10 | medium | The audit hash chain does not cover the columns the log is filtered and displayed by | `test_f10_audit_columns_not_hashed.py` |
| F11 | medium | A watchdog action that fails once is never retried | `test_f11_watchdog_never_retries.py` |
| F12 | medium | A watchdog rule stops counting when its value becomes unknown | `test_f12_watchdog_unknown_never_fires.py` |
| F13 | medium | Human-only powers are plain arguments on the public kernel API | none |
| F14 | medium | A driver timeout or failure leaves the kernel's view of the hardware stale | none |
| F15 | medium | Limit confirmations are not bound to file content and do not cover file-level limits | none |
| F16 | medium | The safe state stops at its first failing step | none |
| F17 | medium | Cross-device references to unregistered devices silently disable interlocks | `test_f17_unvalidated_device_reference.py` |
| F18 | low | A confirm that finishes during a stop re-creates an approval window the stop cleared | none |
| F19 | low | `unlock` is not serialized with `stop_all` | none |
| F20 | low | The kernel ignores `Reading.unit` | none |
| F21 | low | Code and SAFETY.md disagree on check 13, step tolerance and range tolerance | none |
| F22 | low | An agent can evict other pending requests by filling the queue | none |

Totals. 1 critical, 6 high, 10 medium, 5 low.

## Critical

### F01. Unknown same-device values are evaluated as bare words

- **Severity:** critical
- **Breaks:** SAFETY.md check 11 note ("An interlock that refers to a value the hub can't currently read counts as not satisfied"), spec section 7 semantics ("Unknown values always lead to a block, never to a pass"), guarantee 5 (fail closed).
- **Where:** `openhal/spec/expressions.py`, `_resolve` and `_evaluate_compare`. Reached from `Kernel._check_interlocks`, action `require` checks in `Kernel._evaluate`, the watchdog check 12, `Kernel.tick` and the new `Kernel.evaluate_expression`.

When a bare reference cannot be resolved, `_resolve` returns the marker `"word"`, and `_evaluate_compare` then turns the reference into the string of its own name. This is meant for enum words such as `idle`, but it also fires for real channels whose value is unknown or stale. The comparison then has a definite answer instead of unknown. `guard_open != true` compares the string `"guard_open"` with the boolean `true` and returns True. `state != jammed` compares `"state"` with `"jammed"` and returns True. `moving == true` returns False, so an interlock written as `if: "moving == true"` never applies while `moving` is unknown.

The effect is that the most common interlock shapes fail open exactly when a sensor goes quiet, which is the situation interlocks exist for. Read channels become unknown after `max(10 s, 3 x heartbeat)` without a fresh reading, and after any failed read. The same conversion happens for action effects, which the kernel deliberately marks unknown, and inside `_foreign_resolver` for the owning device's bare names.

**Repro.**

1. Register a device whose read channel `guard_open` is bool, with the interlock `if: "power > 0 %"` and `require: "guard_open != true"`.
2. Connect with the mock reporting `guard_open = true` (the guard is open), then let 60 s pass so the reading is stale.
3. Send `Write(press, power, "50 %")` as an agent.
4. The write is `done`. It should be blocked with `interlock`.

The second test shows the same for an action precondition `state != jammed` while the last reading was `jammed`.

**Fix.** Decide at load time which bare names are channels and which are words, because the device file knows its own channels. Parse bare names that match a channel of the owning device into `Ref` and all others into `Lit` words, and never convert an unresolved `Ref` into a word at evaluation time. An unresolved channel must stay unknown (`None`). Add tests for `!=`, `== true`, `== false` and `not` on unknown bool and enum channels, on both sides of an interlock and in `require` and `max_duration.when`.

## High

### F02. Cross-device interlocks are checked against stale state during in-flight writes

- **Severity:** high
- **Breaks:** SAFETY.md check 11 ("not satisfied by current or commanded state"), the concurrency note ("the other is evaluated against the new state"), threat T3 (parallel clients).
- **Where:** `Kernel.execute` and `Kernel._run`. The lock is per device, and `runtime.accepted` is written only after the driver returns.

An interlock that spans two devices is evaluated by a command to either device, but the two commands hold different locks. While the heater write is waiting on its transport, the heater's `accepted` value is still the old one, so a fan write is evaluated as if the heater were off. Both commands pass, and the hardware ends in the state the interlock forbids.

**Repro.**

1. Register FAN and HEATER from `tests/kernel/conftest.py`. HEATER carries the interlock `power > 0 W` needs `desk-fan.fan_speed >= 30 %`.
2. Set the fan to 40 %, advance the clock 5 s and give the heater driver 0.2 s of latency.
3. Run `Write(heater, power, "50 W")` and `Write(desk-fan, fan_speed, "0 %")` concurrently with `asyncio.gather`.
4. Both are `done`. The heater is at 50 W and the fan at 0 %.

**Fix.** Treat a pending command as commanded state before awaiting the driver. One option is to record the commanded value in a per-device "in flight" map under the lock and have the resolver prefer it (or treat the channel as unknown) until the write completes or fails. A simpler option is to take the locks of every device that shares an interlock with the target, in a fixed order, for the whole evaluate and run sequence.

### F03. Stop reports a device safe while an older write is still landing

- **Severity:** high
- **Breaks:** guarantee 4 ("One stop command puts every device in its safe state"), the stop order in SAFETY.md, threat T5.
- **Where:** `Kernel._stop_device`, `Kernel._run`.

`_stop_device` waits at most 2 s for the device lock and then applies the safe state while the earlier command is still running. `grants.revoke_all` has no effect on a grant that was already consumed. When the earlier write returns, the device holds the commanded value, `runtime.accepted` records it, and the stop report still says `safe`. Nothing re-applies the safe state. Writes that legitimately take longer than 2 s are normal for motion (a G-code move followed by `M400`), ramps and slow buses, and `DRIVER_TIMEOUT_S` allows up to 10 s.

**Repro.**

1. Register FAN with a `MockDriver` subclass whose `_write` sleeps 3 s for nonzero values and is instant for zero.
2. Start `Write(desk-fan, fan_speed, "40 %")` as a task, then call `stop_all` 50 ms later.
3. `stop_all` returns with the fan reported `safe`. When the write task finishes, the fan is at 40 % and the hub is stopped.

**Fix.** Keep the `asyncio.Task` of each in-flight command per device. On stop, cancel it, wait for it to settle (bounded), and apply the safe state after it. Independently, in `_run` check after the driver returns whether a stop happened since the grant was issued (a stop generation counter works) and, if so, re-apply the safe state and log it. Report `safe` only when no older command can still land.

### F04. A brief dip resets a max_duration budget

- **Severity:** high
- **Breaks:** spec section 8 ("The budget resets when the expression has been false for at least `reset_after`"), SAFETY.md watchdogs, threat T10.
- **Where:** `Kernel.tick`, the `active is False` branch, which sets `state.active_since = None` the first time it sees the expression false.

`reset_after` is applied only to the `exhausted` flag. The running budget itself restarts after any single tick that sees the expression false. An agent that dips below the threshold for one tick before the budget runs out gets a fresh full budget, and can keep the device over the limit almost indefinitely.

**Repro.**

1. Register FAN and HEATER. The heater rule is `power > 40 W` for 60 s with `reset_after: 30 s`. Set the fan to 40 %.
2. Write 50 W and tick. After 55 s write 30 W and tick. After 1 s write 50 W and tick. After 55 s tick again.
3. The heater spent 110 of 111 s above 40 W and the rule never fires.

**Fix.** Track accumulated true time instead of a start time. Keep `active_since` (or an accumulated budget) while the expression is false and reset it only when `now - false_since >= reset_after`. Count unknown as true (see F12).

### F05. An action with `effects` resets the rate reference to a stale snapshot

- **Severity:** high
- **Breaks:** SAFETY.md check 10 and its note on the reference value, threat T3, spec section 5 (`effects` exist so that interlocks and watchdogs "can account for it").
- **Where:** `Kernel._run` pops `runtime.accepted[effect]` after an action. `Kernel._rate_reference` then falls back to `runtime.reads[channel]`, which may be the snapshot from connection time, with the elapsed time measured from that old read.

After the action, the hub does not know the channel's value, but the rate check acts as if the channel had been sitting at its old snapshot value for an hour. On a 1 %/s channel the next write may jump by up to 3600 %. The interlock resolver has the same problem in the other direction. `DeviceRuntime.latest` never treats a write channel as stale, so after the action interlocks are evaluated against the old snapshot value as if it were known.

**Repro.**

1. Register a pump with `speed` (0 to 100 %, `max_change_per_s: 1`) and an action `prime` with `effects: [speed]`. Use a mock subclass whose `_write` returns `None`, which the base contract allows.
2. Connect and advance 3600 s. Write 10 %. Advance 1 s and run `prime`.
3. Write 100 %. It is `done`, a jump of 90 % in about 1 s on a 1 %/s channel.

**Fix.** After an action with effects, record each effect channel as unknown with the current time instead of deleting it. For the rate check, an unknown reference should block until a fresh read arrives (or allow only a change from a fresh read). For interlocks, an unknown effect must stay unknown until a read after the action replaces it. Reading the effect channels back immediately after the action is the cleanest way to restore a known value.

### F06. Driver exceptions outside three types escape `execute()` with no audit entry

- **Severity:** high
- **Breaks:** guarantee 5 ("Any unexpected exception inside the kernel blocks the command and is logged"), guarantee 6, threat T12.
- **Where:** `Kernel._run` catches only `GrantError`, `DriverError`, `OSError` and `TimeoutError`.

A driver that raises anything else (`ValueError` while parsing a reply, `KeyError`, `RuntimeError`, `asyncio.CancelledError`) after the command was sent makes `execute()` raise into the caller. No `write` or `action` entry is written, so the audit log has no record of a change that reached hardware, and `runtime.accepted` is not updated, so later rate and interlock checks use the old value.

**Repro.**

1. Register FAN with a mock subclass whose `_write` performs the write and then raises `ValueError`.
2. `execute(Write(desk-fan, fan_speed, "40 %"))` raises `ValueError`. The fan is at 40 % and `audit.entries(event="write")` is empty.

**Fix.** Wrap the driver call in `except BaseException` handling that always logs (re-raise `CancelledError` and `KeyboardInterrupt` after logging). Return a `failed` decision with code `driver_error` for every other exception. When the outcome is unknown, mark the channel unknown (see F14) instead of leaving the old accepted value in place.

### F07. A backtracking `pattern` lets one agent write freeze the kernel

- **Severity:** high
- **Breaks:** guarantee 4 (stop works), guarantee 5, threat T16 (malicious or malformed input). The spec already requires a timeout for `match` regexes but not for channel patterns.
- **Where:** `openhal/kernel/checks.py`, `normalize`, `re.fullmatch(spec.pattern, raw)`. The model only checks that the pattern compiles (`_check_regex`).

`evaluate` is synchronous and runs on the event loop. A string channel with a common pattern such as `^([a-z]+ ?)+$` backtracks exponentially on a value like `"aaaa...a!"`. In testing a 23 character value held the loop for over a second and a 24 character value for about 3 s. Each extra character roughly doubles the time, and `max_length` may be up to 4096. While the regex runs, `stop_all`, heartbeats, `connection_lost` and `tick` cannot run. The agent fully controls the value. The human only had to write an ordinary looking pattern.

**Repro.**

1. Register a device with `text: { type: string, max_length: 64, pattern: "^([a-z]+ ?)+$" }`.
2. Call `kernel.evaluate(Write(sign, text, "a" * 22 + "!"))`. It takes several seconds.

**Fix.** Use a linear time regex engine for channel patterns (the `re2` binding, or the `regex` module with a `timeout`), or reject nested quantifiers at load time. Treat a timeout as `bad_value`. Also consider running `evaluate` with a hard time budget so no future check can starve the stop path.

## Medium

### F08. A driver can reach the kernel through its verifier

- **Severity:** medium
- **Breaks:** threat T17, whose control claims the malicious driver test "proves it can't use the kernel path to reach other devices".
- **Where:** `Kernel.register` attaches `self._verify_grant`, a bound method. `Driver._verify.__self__` is the Kernel, with `grants`, `devices` and every other driver.

**Repro.** A lamp driver's `_write` takes `self._verify.__self__`, issues a grant for `desk-fan write:fan_speed 100.0` and calls the fan driver's `write`. The fan goes to 100 % with no kernel check (`test_f08_driver_reaches_kernel.py`).

**Fix.** Attach a closure or a small callable object that holds only the grant book's `consume` bound to one device id, not a bound method of the Kernel. Do not expose `devices` or `grants` from anything a driver receives. Even so, an in-process driver can find any object through `gc`, so update T17 to say the kernel path is closed to drivers only against accidents, and that full isolation needs out-of-process drivers.

### F09. Several events the documents promise to log leave no audit entry

- **Severity:** medium
- **Breaks:** guarantee 6 ("Every read request, write attempt, block, confirmation, stop and unlock is in an append-only audit log"), the confirmation queue rule ("Expired requests are rejected automatically and logged").
- **Where and what:**
  - `ConfirmationQueue.expire` changes the status to `expired` without logging. A log entry appears only if a human later tries to approve.
  - `ConfirmationQueue.add` silently cancels the oldest pending request when the queue is full.
  - `stop_all` does not log which requests it cancelled.
  - `Kernel.read` logs nothing when the driver raises or times out.
  - `Kernel.tighten` does not log refusals for `bad_unit` (the `UnitError` handler raises a `Block` that the following `except Block` cannot catch), for `min` above `max`, or for a non-numeric channel.
  - Safe state steps and watchdog `then` writes change hardware without a per-channel entry that records the value, and `_apply_rule` logs `watchdog ... done` before it acts.
  - `Kernel.unregister` is not logged.

**Repro.** `test_f09_audit_gaps.py` covers expiry, failed reads, a refused tighten and the safe state write.

**Fix.** Log from the queue through a callback the kernel provides, log in a `finally` block in `read`, move the `bad_unit` handling inside the logging path in `tighten`, and log each hardware change made by the system path as a `write` or `action` with `before` and `after`.

### F10. The audit hash chain does not cover the indexed columns

- **Severity:** medium
- **Breaks:** threat T15 (audit history edited to hide an event).
- **Where:** `AuditLog.append` hashes only the JSON body. `event`, `principal`, `device`, `target`, `status` and `code` are separate columns. `entries()` filters on them and returns them, and `verify()` never compares them with the body.

**Repro.** Append two entries to a file-backed log, drop the update trigger with sqlite3, change entry 2's `status`, `code` and `principal` columns, and reopen. `verify()` returns `(True, None)` and `entries(status="done")` no longer shows the write (`test_f10_audit_columns_not_hashed.py`). Removing the newest rows is also undetectable, because nothing anchors the head hash outside the database.

**Fix.** In `verify()`, check that every column equals the corresponding body field, or build `Entry` objects only from the body. Publish the head hash outside the database (for example in a separate append-only file or in each `openhal log verify` report) so truncation can be detected.

### F11. A watchdog action that fails once is never retried

- **Severity:** medium
- **Breaks:** SAFETY.md watchdogs ("When the budget runs out the hub applies the rule's action"), threat T10.
- **Where:** `Kernel.tick` sets `exhausted = True` before `_apply_rule` and fires only when not exhausted. `_apply_rule` swallows the failure.

**Repro.** Run the heater above 40 W past its 60 s budget, make one write fail when the rule fires, then let writes work again. Twenty five seconds later the heater is still at 50 W (`test_f11_watchdog_never_retries.py`).

**Fix.** Keep a per-rule "applied successfully" flag. While a rule is exhausted and its expression is still true or unknown, retry the action on every tick (with a backoff) and escalate to the safe state if a `then` mapping keeps failing.

### F12. A watchdog rule stops counting when its value becomes unknown

- **Severity:** medium
- **Breaks:** spec section 7 ("Unknown values always lead to a block, never to a pass") applied to section 8.
- **Where:** `Kernel.tick` acts only on `True` and `False`. An unknown result does nothing. The existing test `test_tick_with_unknown_values_and_failed_rule` asserts this behavior, so it looks intended, but it contradicts the stated principle.

**Repro.** An oven rule `temp > 80 degC` for 10 s starts with `temp` at 95 degC. The sensor stops answering. Thirty seconds later the rule has not fired (`test_f12_watchdog_unknown_never_fires.py`).

**Fix.** Treat an unknown `when` as true for budget accounting, or at least fire the rule when it was last known true and has been unknown for longer than its remaining budget.

### F13. Human-only powers are plain arguments on the public kernel API

- **Severity:** medium
- **Breaks:** threat T4 and the rules "Agents never confirm" and "Only a human may unlock", if any caller other than the hub's authenticated paths can reach the kernel object.
- **Where:** `Kernel.execute(..., confirmed=True)` and `Kernel.evaluate(..., confirmed=True)` skip check 14 for any principal, including an agent on a high hazard device. `Principal` is a plain dataclass, so `Principal("human", ...)` and the importable `SYSTEM` principal pass every human-only gate (`confirm`, `unlock`, `approve_routine`). `Kernel.sign` signs routine approvals for any caller.

**Repro.** Register LASER from `tests/kernel/conftest.py`. `await kernel.execute(Action(laser, home), agent("a", "control_medium"))` is queued as `pending`, as it should be. The same call with `confirmed=True` runs the action on the high hazard laser at once, with no request in the queue and no human involved.

**Fix.** Replace the `confirmed` boolean with a request object that only `confirm()` can produce (a private token checked against the queue), make `execute` refuse `SYSTEM` from outside the kernel, and make `sign` private. Document that the Python library is a trusted interface, and keep agents away from it. The hub was outside this review, so whether any hub path passes these through was not checked.

### F14. A driver timeout or failure leaves the kernel's view stale

- **Severity:** medium
- **Breaks:** SAFETY.md check 10 and 11 assumptions ("the last value the kernel accepted"), threat T12.
- **Where:** `Kernel._run`. On `TimeoutError` or `DriverError` the kernel keeps the previous accepted value, although a timed-out command may well have reached the device. `asyncio.wait_for` cancels the driver coroutine at 10 s, after the bytes may have been sent.

If a heater write of 50 W times out but lands, the kernel still believes the heater is at 0 W, so an interlock such as "heater on needs the fan" no longer protects fan writes, and the next rate check starts from the wrong value.

**Fix.** On any failure after the grant was consumed, mark the channel unknown with the current time and trigger a read back. Interlocks then block until the state is known again (once F01 is fixed).

### F15. Limit confirmations are not bound to file content and do not cover file-level limits

- **Severity:** medium
- **Breaks:** guarantee 3 and spec section 12 ("Every limit (min, max, step, rate, values, interlocks, watchdog rules, safe state, hazard) MUST be confirmed by a human"), threats T6 and T20.
- **Where:** `DeviceFile.unconfirmed` checks only write channels and actions. A file whose channels each carry `confirmed` but which has no top-level `confirmed` is writable even though its interlocks, watchdog rules, safe state and hazard were never confirmed. `confirmed` is also just a name and a date, so any later edit to a confirmed file (a tool rewriting it, the writer adding `hazard: low`, an interlock removed) keeps it writable.

**Fix.** Store a hash of the canonical limit content next to each confirmation and treat a mismatch as unconfirmed. Require a top-level confirmation (or one per section) for interlocks, watchdog, safe state and hazard. Make the spec consistent, since section 12's first bullet and its writable rule disagree.

### F16. The safe state stops at its first failing step

- **Severity:** medium
- **Breaks:** guarantee 4.
- **Where:** `Kernel._apply_safe_state`, inner `apply()`. The native `driver.safe_state` runs first and each file step runs in sequence with no per-step handling, so one exception skips every later step. A driver whose native safe state raises (for example "feed hold not supported in this mode") never gets its outputs switched off.

**Fix.** Run every step even when an earlier one fails, collect the errors, and report `partial` or `failed` with the list. Consider retrying failed steps once.

### F17. Cross-device references to unregistered devices silently disable interlocks

- **Severity:** medium
- **Breaks:** SAFETY.md check 11, spec section 1 ("Interlocks and routines refer to devices by id").
- **Where:** `DeviceFile._check_expression` skips references with a device part, and `Kernel.register` does not check them either. `_check_interlocks` decides whether an interlock "touches" a command by comparing `ref.device` with the commanded device's id, so a misspelled id never matches the real device.

**Repro.** A fan file holds `if: "fan_speed < 30 %"` and `require: "heatr.power == 0 W"` (the heater's id is `heater`). With the fan at 0 %, `Write(heater, power, "50 W")` is `done` (`test_f17_unvalidated_device_reference.py`). The same happens when the referenced device is simply not registered, and an interlock owned by a device disappears for every other device when its owner is unregistered or fails to load.

**Fix.** At registration, and whenever a device is added or removed, check every cross-device reference against the registered ids and refuse writes to any device named by a dangling reference (or refuse to register the file). Treat an interlock whose owner is missing as blocking for the devices it names.

## Low

### F18. A confirm that finishes during a stop re-creates an approval window

- **Severity:** low
- **Where:** `Kernel.confirm` writes `_approval_windows[key]` after its `execute` returns. `stop_all` clears the windows at its start. If a confirmed write is in flight when stop runs, the window is created after the stop. After the human unlocks, the agent can repeat the command for up to 10 minutes without a fresh approval.
- **Fix.** Create the window before awaiting, or check a stop generation counter before storing it. Clear windows on unlock as well.

### F19. `unlock` is not serialized with `stop_all`

- **Severity:** low
- **Where:** `unlock` does not take `_stop_lock`, so a human can lift the lock while safe states are still being applied, and writes are accepted while other devices are still being made safe.
- **Fix.** Take `_stop_lock` in `unlock`, or refuse to unlock while a stop is in progress.

### F20. The kernel ignores `Reading.unit`

- **Severity:** low
- **Where:** `note_reading` stores `reading.value` and every resolver assumes the channel unit. A driver that reports a temperature in degF for a degC channel, with the unit set correctly on the reading, feeds wrong numbers into interlocks and rate checks.
- **Fix.** Convert readings whose unit differs from the channel unit, and treat unconvertible readings as unknown.

### F21. Code and SAFETY.md disagree on check 13 and on tolerances

- **Severity:** low
- **Where:** check 13 (`busy`) is not a check in `_evaluate`. `execute` waits up to 5 s for the device lock and only then evaluates. The step check uses an absolute tolerance of 1e-6 steps, while SAFETY.md says 1e-9 relative. The range check accepts values within 1e-12 relative above `max`.
- **Fix.** Align the document and the code, and pick one tolerance rule for all three.

### F22. An agent can evict other pending requests by filling the queue

- **Severity:** low
- **Where:** `ConfirmationQueue.add` cancels the oldest pending request when 100 are pending, with no per-principal quota and no log entry. An agent can push out a request the human was about to review.
- **Fix.** Add a per-principal limit and refuse new requests from a principal at its limit instead of evicting others.

## Areas checked and found sound

- **Grants.** `Grant` cannot be built without the private guard, a copied or foreign grant is refused because `consume` checks identity in the book's private table, grants are single use, bound to device, target and a value digest, expire after 5 s, and are revoked on stop and on connection loss.
- **Sealed driver methods.** `write`, `action`, `safe_state`, `attach` and `_consume` cannot be overridden in a subclass body, and `attach` refuses a second kernel. Bypasses that need deliberate monkeypatching fall under the accepted malicious driver risk (see F08).
- **Unit conversion.** Bare numbers are rejected for numeric channels. NaN and infinity are rejected when parsing and after conversion. `85 degF` against a degC limit is converted before comparing. Offset units are not auto-converted, so `40 delta_degC` is refused for a degC channel instead of being misread. Percent and dimensionless convert correctly, and range checks always run on the converted value, so no unit choice moves a value past a limit. Rates use delta units for degC and degF.
- **Range, step and type checks.** Type checks reject booleans for numbers, non-strings for enums and strings, and over-long strings before the pattern runs. Huge and tiny magnitudes stay finite or are rejected.
- **Session limits.** `tighten` compares against the current effective limits, so repeated calls cannot widen anything, and NaN cannot be supplied. `effective_limits` only narrows. Tightened limits also apply when a queued request is approved.
- **Confirmation.** Only human principals can confirm or reject, requests expire on the kernel clock, approval re-runs every check, a request cannot be approved twice, high hazard is always `confirm-each-time` and gets no approval window, routines on high hazard devices need an HMAC approval bound to device, routine name and content hash, and the approval message format cannot be made to collide because `routine` and `sha256` are pattern-restricted. The content hash comes from the caller in `Principal.ref`, so its correctness depends on the routine engine, which was not reviewed.
- **Stop lock.** After `stopped` is set every write and action, including human ones and approvals, is blocked with `stopped`. Pending requests are cancelled and approval windows cleared (apart from F18). Only a human with the phrase can unlock.
- **Fail closed in evaluation.** `evaluate` catches every exception and returns `internal_error`, and nothing between evaluation and the grant can be interrupted, since there is no `await` in between.
- **Expression parser.** There is no `eval`, input is limited to 256 characters and 16 levels, non-finite numbers are refused, and comparisons of incompatible units return unknown. Cross-device references that do not resolve stay unknown (the bare word problem in F01 affects only same-device names).
- **Device file loader.** Files are size-limited, YAML aliases, anchors and custom tags are refused, only YAML 1.2 booleans are accepted, unknown keys are refused, limits must be finite and ordered, safe state and watchdog values are range-checked against the channel, and no path from a device file is opened by the kernel.
- **Audit chain basics.** Each entry's hash covers the previous hash and the body, update and delete triggers are present, and `verify()` catches edits to the body (the gaps are in F09 and F10).

## Not reviewed

- `openhal/hub/` and `openhal/conformance/`, which were being edited during the review. Token handling, the MCP and HTTP layers, LAN binding, the routine engine and the CLI's TTY check were therefore not examined. F13 matters only if any of those layers pass agent input into the flagged arguments.
- Real hardware drivers. Only the mock driver exists in this tree.
- `Kernel.evaluate_expression`, which appeared in `kernel.py` during the review. It resolves only references that name a device, so bare names there always become words (F01) and an expression such as `a != b` with bare names is always true.

## Resolution (orchestrator, 2026-10-24)

Every finding was fixed. All 17 proof-of-concept tests in tests/review_safety/ now pass and stay in the suite as regression tests. Findings without a proof test have one in tests/kernel/test_review_fixes.py.

| # | Fix |
|---|---|
| F01 | Bare names are split into channels and words at parse time using the owning device's channel set. An unresolved channel is always unknown. Device files reject words that aren't enum values. |
| F02 | Channels with a command in flight are unknown to every resolver, so other devices' interlocks block while a change is pending. |
| F03 | Stop increments a generation counter, cancels in-flight commands, waits for the device lock, and reports `pending` if it can't get it. A command that returns after a stop reapplies the safe state. |
| F04 | The max-duration budget resets only after the expression has been false for `reset_after`. |
| F05 | Action effects are marked unknown and read back. A rate-limited channel with an unknown value blocks writes until a fresh reading arrives. |
| F06 | Every driver exception after the grant is caught, logged and reported as `failed`. Cancellation not caused by a stop is logged and re-raised. |
| F07 | String patterns run on the `regex` engine with a 50 ms budget. A timeout refuses the value. |
| F08 | Drivers receive a grant verifier bound to their own device instead of a bound kernel method. T17 now says this guards against accidents, not malice. |
| F09 | Request expiry, cancellation and every status change are logged. Failed reads, every tighten refusal, unregister and each safe-state and watchdog write are logged, the watchdog after it acts. |
| F10 | `verify()` checks every column against the hashed body, entries are built from the body, and a head file next to the database detects a removed tail. |
| F11 | Failed watchdog actions are retried with backoff, and a `then` mapping that fails three times escalates to the safe state. |
| F12 | Once a rule is counting, an unknown value keeps it counting. |
| F13 | The `confirmed` flag is gone. Only the queue's own approved request for the exact command counts. The system principal is refused by `execute`, and approval signing is private. The kernel API is documented as trusted. |
| F14 | A failed or timed-out command marks its channels unknown and reads them back. |
| F15 | Interlocks, watchdog, safe state and hazard need a file-level confirmation. `confirmed.sha256` binds a confirmation to the file's limits, and the validator warns when it is missing. |
| F16 | Every safe-state step runs even after a failure, with `partial` reported. |
| F17 | Any dangling cross-device reference blocks every write on the hub with `misconfigured`. Interlocks of an unregistered device keep protecting the devices they name. |
| F18 | Approval windows are only created when no stop happened during the confirm, and are cleared on unlock. |
| F19 | Unlock is refused while a stop is being applied. |
| F20 | Readings in another unit are converted into the channel unit. Unconvertible or non-finite readings are unknown. |
| F21 | SAFETY.md now describes check 13 as serialization before evaluation and gives the real tolerances. |
| F22 | Each principal may have 20 pending requests. A full queue refuses rather than evicts. |
