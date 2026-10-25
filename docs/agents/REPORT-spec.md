# Specification workstream report

The dated specification is written against the current ADR 0015, with the new error names, methods, notifications and `hal/shutdown`. The names test passes against the ADR tables. Lint, format and mypy are clean. The full suite ran 1004 passed, 1 failed. The failure was `test_driver_passes_conformance[scpi]`, a connect timeout during a 690 s run while other agents were loading the machine. When I reran `tests/conformance` on its own, all 22 passed. My changes are docs plus one new test, so they can't have caused it.

I rebased the branch onto main at `ade705c`. That made the worktree's ADR identical to main's, so I didn't need the `cp`. No ADR file is in my commits. The work is in 14 commits, all unpushed, with no trailers. Two commits are under 50 lines: a stdio wording fix and a link fix.

### Files
In `spec/2026-10-24/`:
- `index.md`: introduction, draft status, "not a standard", not affiliated with Anthropic or MHS, the RFC 2119 and RFC 8174 sentence, and the glossary of the 10 terms.
- `architecture.md`: roles, the one-hub model, a Mermaid diagram of one blocked and one granted `hal/write`, and the MCP mapping.
- `basic/lifecycle.md`: initialize, version negotiation and shutdown.
- `basic/transports.md`: WebSocket, stdio and authentication.
- `basic/messages.md`: JSON-RPC rules, the error object, shared types, all 17 methods and all 6 notifications, each with an example exchange.
- `device-files.md`: every rule from the old `spec/SPEC.md`, rewritten with MUST, SHOULD and MAY. Section numbers 0 to 12 are unchanged, so old "spec section N" references still work. I added rules the reference code enforces but the old spec didn't state (see below).
- `safety.md`: guarantees, the 14 checks with kernel code and registry name, unknown values, Grants, hazard classes, confirmations, stop and unlock, watchdogs, the full registry table, and the reason templates.
- `drivers.md`: the interface, 12 rules, Conformance Levels, and the conformance suite checks by level.
- `routines.md`, `security.md` and `changelog.md`.

Top level of `spec/`:
- `versions.json`, as briefed.
- `SPEC.md` and `CHANGELOG.md` are now short pointers into the dated version.
- New `VERSIONING.md`, `ERRORS.md`, `CONFORMANCE.md` and `GLOSSARY.md`, each summarizing and linking into the dated files.
- `MHS-MAPPING.md` and `spec/schema/` are untouched. `schema.md` and `schema.json` are linked but not written.

Test: `tests/spec/test_spec_names.py`, 40 cases, no comments.
- It parses the ADR's method, notification and error tables, plus `hal/initialized` and `hal/shutdown` from the Lifecycle section.
- Every `hal/...` name and UPPER_SNAKE name in my spec files must be in the ADR. `HA_TOKEN` is allowlisted and file paths are ignored.
- Every ADR name must appear somewhere in the spec.
- Every code shown next to a name must match, whether in a table, in "NAME (-32xxx)" form, in "-32xxx NAME" form, or in JSON error objects.
- The registry table in `safety.md` must match the ADR row for row.
- Every kernel `BLOCK_CODES` entry must map to exactly one name.
- The exact LIMIT_EXCEEDED reason must appear in the architecture, safety and messages pages.
- `versions.json` must name this version as latest.

### Decisions
- Every example uses the canonical values. The reason reads `fan_speed 150 % exceeds the limit of 100 % (desk-fan.hal.yaml, confirmed by sohan 2026-10-24)`. The action examples add one action, `spin_test`, to desk-fan.
- The Device File format stays version 0.1 in the `openhal` field. It keeps its semantic versioning, separate from the dated spec versions.
- Added rules taken from the reference code:
  - unknown driver names are rejected unless they start with `x-`
  - parameter names that look like secrets are rejected
  - safe state values and `watchdog.then` values must be within their limits
  - `effects` must name write channels
  - heartbeat must be between 100 ms and 1 h
  - enum values must be unique, and step and rate must be greater than zero
  - the limits hash coverage is stated
  - a reference to an unregistered device blocks every write on the hub

### Choices the protocol workstream should confirm
No `openhal/protocol` package exists yet, so I chose these shapes myself. Please confirm them or I'll align to theirs:
- **Types.** `DeviceSummary` and `DeviceDescription` fields, `Decision` as `{ status, device, target, value, unit, error?, requestId? }`, and the `ConfirmationRequest`, `RoutineSummary` and `AuditEntry` fields.
- **Commands.** `Write` and `Action` carry `kind`. `Wait` is `{ kind: "wait", duration }`.
- **Values.** `at` is an RFC 3339 UTC string, though the hub emits epoch floats today. `data.limit` and `data.requested` are quantity strings such as `"100 %"`.
- **Notification levels.** `hal/confirmationRequested` is Full. `hal/deviceAdded` and `hal/deviceRemoved` MAY be sent at any level, because the ADR doesn't say.
- **Pending versus error.** `hal/write` and `hal/action` return the pending result. CONFIRMATION_REQUIRED is the error for commands that can't wait, such as a routine's.
- **Templates.** Only the LIMIT_EXCEEDED templates are normative. I proposed `below_min` as "`{channel} {requested} is below the limit of {limit} (...)`".
- **stdio bridge.** `openhal rpc` writes only messages to stdout, sends diagnostics to stderr, and closes the WebSocket when stdin closes. A batch gets INVALID_REQUEST.

### Proposed contract fixes (I did not change the ADR)
1. The ADR's MCP mapping still lists `read_many` under `hal/read` and `plan_check` under `hal/dryRun`. They should map to `hal/readMany` and `hal/planCheck`.
2. The ADR's LIMIT_EXCEEDED example says `2026-11-02`. The canonical value is `2026-10-24`.
3. The ADR doesn't give the Conformance Level of `hal/deviceAdded`, `hal/deviceRemoved` or `hal/confirmationRequested`.
4. CONFIRMATION_REQUIRED's meaning ("queued, `data.requestId`") conflicts with the pending result of `hal/write`. Write down which one applies when.

### Gaps between code and docs
- ADR 0004 says the conformance suite tries used, expired and wrong-target Grants. The suite only tries a write with no Grant. The spec describes what the suite actually does.
- ADR 0007 says Python routines only have the routine API in scope. The engine actually `exec`s them with full builtins. The spec says plainly that they run as trusted code with no sandbox.
- `DriverInfo.conformance` isn't in `base.py` yet. The spec describes it as the protocol brief defines it, defaulting to `control`.
- The spec keeps the old rule that loaders SHOULD warn on a newer minor format version. The loader doesn't warn.
- `suspect` marking for readings outside `range` is done by individual Drivers, not centrally by the hub.
- A LIMIT_EXCEEDED reason for a session-tightened limit would wrongly cite the file's confirmation. A template for session limits is needed.

## Orchestrator note

Saved by the orchestrator from the agent's hand-back. Merged into main. Proposed ADR fixes 1 to 4 and the session-limit template were applied to ADR 0015, and the chosen message shapes were sent to the protocol workstream as the contract.
