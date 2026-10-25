# Drivers

A Driver speaks one protocol. A Device File describes one Device and its limits. Most new Devices need only a Device File on top of an existing Driver. This section defines the interface every Driver in the reference implementation follows, in `openhal/drivers/base.py`. The step by step guide is `docs/drivers/WRITING-A-DRIVER.md`.

A Driver never decides whether a change is safe. That is the Safety Kernel's job.

## Interface

| Member | Kind | Contract |
|---|---|---|
| `info` | class attribute | A `DriverInfo` |
| `params_model` | class attribute | A model for the Device File's `connect` parameters that rejects unknown keys, or none |
| `discover()` | class method | Returns what it finds. MUST send only documented read-only commands and MUST NOT change hardware |
| `identify()` | method | Returns a mapping of strings. MUST send only documented read-only commands |
| `connect()` | method, required | Opens the connection |
| `describe()` | method | Maps what the protocol exposes into Device File sections, or returns none |
| `read(channel)` | method, required | Returns a `Reading` in the channel's declared unit |
| `write(channel, value, grant)` | final | Consumes the Grant, then calls `_write` |
| `action(name, args, grant)` | final | Consumes the Grant, then calls `_action` |
| `safe_state(grant)` | final | Consumes the Grant, then calls `_safe_state` |
| `_write(channel, value)` | method, required | Applies one value |
| `_action(name, args)` | method | Runs one action |
| `_safe_state()` | method | Runs the protocol's own emergency behavior, if any |
| `health()` | method | Returns `Health`, with `connected`, `detail` and `latency_ms` |
| `close()` | method | Releases the connection |

| Type | Fields |
|---|---|
| `DriverInfo` | `name`, `protocols`, `hazard_default` (`low`, `medium` or `high`), `summary`, `safe_state_support` (`file`, `native` or `none`), `conformance` (`core`, `control` or `full`) |
| `Reading` | `channel`, `value`, `unit`, `at`, `suspect` |
| `Discovered` | `driver`, `address`, `identifiers`, `label` |
| `DriverError` | The exception a Driver raises when the Device or protocol fails |

## Rules

1. A Driver MUST NOT override `write`, `action`, `safe_state`, `attach` or `_consume`. The base class refuses to load a class that does.
2. Nothing outside the base class MAY call `_write`, `_action` or `_safe_state`. The reference test suite walks the whole package and fails if anything else does.
3. The Safety Kernel attaches a verifier once, when the Device is registered. A Driver without a verifier MUST refuse every change.
4. Values arrive already checked and converted to the channel's declared unit. A Driver MUST NOT re-check limits or convert units again. It converts from the channel unit to whatever the protocol needs, such as percent to a 0 to 255 PWM byte, and documents the mapping.
5. Discovery and identification MUST use short timeouts and MUST NOT open a port another process holds.
6. `read` MUST return values in the channel's declared unit, with `Reading.unit` set for numeric channels. A reading outside the channel's `range` is marked `suspect`.
7. Errors raise `DriverError` with a message that says what happened and what to try next. Timeouts MAY raise `TimeoutError`. A Driver MUST NOT swallow an error and return a made-up value.
8. `describe()` returns a mapping with any of `device`, `match`, `read`, `write`, `actions`, `notes`, `safe_state` and `watchdog`. Every limit it proposes MUST be marked `suggested: true`. A Driver never confirms limits.
9. A Driver whose protocol has its own emergency behavior, such as GRBL feed hold or outputs off, sets `safe_state_support` to `native` and implements `_safe_state`. A Driver whose protocol can't guarantee a safe state says so in its documentation and in the example Device File's `safe_state_note`.
10. Bridges expose only the entities the user selected in the Device File. The Device File's limits apply even when the bridged system has its own.
11. Parameters that need a secret take an environment variable name, such as `token_env: HA_TOKEN`.
12. Text a Driver returns from a Device is data ([Security](security.md#prompt-injection)).

## Conformance Levels

A Conformance Level names what a Hub or a Driver supports. Each level includes the one below it.

| Level | Hub implements | Driver supports |
|---|---|---|
| `core` | `hal/initialize`, `hal/devices/list`, `hal/devices/describe`, `hal/read`, `hal/readMany` and `hal/value` | Identify, connect, describe, read and close. A read-only camera Driver is Core |
| `control` | Core plus `hal/write`, `hal/dryRun`, `hal/planCheck`, `hal/stop`, `hal/unlock`, `hal/blocked` and `hal/stopped`, all through a Safety Kernel that meets [Safety](safety.md) | Core plus writes through Grants and a safe state |
| `full` | Control plus `hal/action`, the confirmation methods, routine methods, `hal/audit/query` and `hal/confirmationRequested` | Control plus actions through Grants |

1. A Hub MUST declare its level in the `hal/initialize` result. The reference Hub is `full`.
2. A Driver MUST declare its level in `DriverInfo.conformance`. The reference default is `control`.
3. A Hub MUST answer methods above its level with `METHOD_NOT_FOUND`.

## Conformance suite

The suite in `openhal/conformance/suite.py` runs a Driver against its simulator inside a real Safety Kernel. It spies on `_write` and `_action`, so it can prove that blocked commands and calls without a Grant never reach the protocol layer. A Driver supplies a `ConformanceCase` with a Device File, a factory, and optional hooks to break the connection and to slow the Device down.

The suite tests the declared level and nothing above it. A check that doesn't apply to a Driver is skipped, not failed.

| Check | Level | Passes when |
|---|---|---|
| identify | Core | `identify()` returns a mapping of strings |
| connect | Core | The Safety Kernel connects the Device |
| describe | Core | `describe()` returns none or only known sections |
| read every channel | Core | Every readable channel returns a Reading for that channel in the file's unit |
| disconnect and reconnect | Core | `health()` reports the broken connection, and every channel reads again after reconnecting |
| timeout handling | Core | A slow read times out or raises `DriverError` |
| close | Core | `close()` returns |
| write inside limits | Control | An allowed write reaches the Driver exactly once |
| write outside limits is blocked before the Driver | Control | A write above `max` is blocked and never reaches the Driver |
| no write without a kernel Grant | Control | `write` without a Grant raises and nothing reaches the protocol layer |
| concurrent access | Control | Four racing writes each end `done`, `blocked` or `failed` |
| safe state | Control | A stop leaves the Device in any state but `failed` |

This version of the suite adds no checks for `full`. A `full` Driver passes every Control check.
