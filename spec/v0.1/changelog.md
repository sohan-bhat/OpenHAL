# Changelog

## v0.1 (draft)

The first draft of the OpenHAL specification, dated 2026-10-24.

### Version numbers

- On 2026-10-28 the draft dated 2026-10-24 became v0.1, because versions are now numbered `MAJOR.MINOR` ([ADR 0017](../../docs/adr/0017-version-numbers.md)). The requirements did not change.
- `hal/initialize` negotiates `0.1`. A `protocolVersion` that is not in the form `MAJOR.MINOR`, such as a date, gets `INVALID_PARAMS` (-32602) with a reason that names the supported versions.
- The draft moved from its dated folder to `spec/v0.1/`.

### Hub protocol

- JSON-RPC 2.0 messages over WebSocket at `/rpc` and over stdio through `openhal rpc`.
- Initialization with version negotiation, `hal/initialized` and `hal/shutdown`.
- Core methods `hal/initialize`, `hal/devices/list`, `hal/devices/describe`, `hal/read` and `hal/readMany`.
- Control methods `hal/write`, `hal/dryRun`, `hal/planCheck`, `hal/stop` and `hal/unlock`.
- Full methods `hal/action`, `hal/confirmations/list`, `hal/confirmations/approve`, `hal/confirmations/reject`, `hal/routines/list`, `hal/routines/dryRun` and `hal/audit/query`.
- Notifications `hal/value`, `hal/blocked`, `hal/stopped`, `hal/deviceAdded`, `hal/deviceRemoved` and `hal/confirmationRequested`.
- The error registry, codes -32700 to -32603 and -32001 to -32023, with one registry name per Safety Kernel code.
- Conformance Levels `core`, `control` and `full` for Hubs and Drivers.

### Device File format 0.1

- Identity and library matching (`device`, `id`, `match`).
- Driver selection with shorthand (`connect`).
- Read channels, write channels with min, max, step, rate and enum limits, and actions with typed arguments, requirements and run limits.
- Safe state as values, an action, or ordered steps.
- Interlocks and the expression language, with three-valued evaluation where unknown never passes.
- Watchdog heartbeat, loss behavior and max duration rules.
- Hazard classes and human-signed approvals for routines on high hazard Devices.
- Notes as data, provenance and verification status.
- Limits provenance. High risk targets stay read-only until a human confirms their limits.

### Risk levels

On 2026-11-03, at the owner's decision of 2026-11-02 ([ADR 0020](../../docs/adr/0020-risk-levels.md)).

- Every channel and action has a Risk Level, `low`, `medium` or `high`, which a Hub sets from the Device File. Reading is always `low`.
- Only high risk targets wait for a human to confirm their limits. Low and medium targets take commands within the Device File's range, and a low channel ignores a rate that is only `suggested`.
- A high risk action that can't be undone needs a human's approval at least once.
- Scope follows the lower of a target's Risk Level and the Device's hazard class.
- Device Files gain `risk` on write channels and actions, and `map.pin` ties targets on one pin to one level.
- The firmware protocol gains `PIN` and the `io`, `pb` and `ab` keys of `DESC`, and `DESC` may be up to 4,000 bytes.

### Safety, routines and security

- The Safety Kernel check order, unknown values, Grants, confirmations, stop and unlock.
- YAML and Python routines that run through the Safety Kernel and start disabled.
- Local-only network exposure by default, human and agent tokens, and text from Devices handled as data.
