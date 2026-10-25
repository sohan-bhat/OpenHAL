# Protocol workstream report

The hub now speaks the OpenHAL protocol over WebSocket at `/rpc` and over stdio through `openhal rpc`. It covers every method, notification and error name in the current ADR on main and in spec/2026-10-24 (messages.md, lifecycle.md, safety.md). The REST API is unchanged and its tests still pass. I merged main into the branch, so the worktree ADR is main's copy, and none of my commits touch the ADR. All work is committed on branch `worktree-agent-aca8dfa41339698b9` and the tree is clean. Nothing was pushed, and no real hardware was touched.

### Gates
- **pytest:** the full suite ran 1119 passed, 1 failed. The failure was `test_checked_in_openapi_document_is_current`, because I added the `/v1/rpc/log` route. I regenerated `docs/api/openapi.json` and reran `tests/hub` (31 passed). I did not rerun the whole suite after that last change.
- **ruff check, ruff format --check, mypy openhal:** all clean.
- **Pre-existing flake:** `test_driver_passes_conformance[scpi]` timed out on connect once, in my first baseline run. It passed every later run.

### Files
New package `openhal/protocol/`:
- `version.py`: `PROTOCOL_VERSIONS = ["2026-10-24"]` and the negotiation rule.
- `errors.py`: the registry. 24 entries with code, name, kernel codes, meaning and a reason template. The LIMIT_EXCEEDED templates are the normative ones, including the below-min and session-limit wording.
- `messages.py`: Pydantic models for every message, camelCase on the wire, using the spec's shapes. It also holds the method and notification tables with their levels.
- `convert.py`: turns hub objects into messages, converts times to RFC 3339, and builds errors through `build_error(Facts)`, which both the hub and the MCP server use.
- `dispatch.py`: one dispatcher per hub (`Dispatcher.for_hub`). It enforces the lifecycle, conformance gating and human-only methods.
- `session.py`, `notify.py`: per-connection state, and fan-out of the hub's events as notifications.
- `log.py`: the ring buffer of the last 2,000 messages. `token` is redacted and any `ohal_` token text is scrubbed.
- `websocket.py`, `stdio.py`: the two transports.
- `client.py`: `ProtocolClient`, a small client for `/rpc`.
- `schema.py`: the schema generator.

Other files:
- `openhal/hub/api.py`: `/rpc`, `GET /v1/rpc/log?since=`, and the WebSocket `/v1/rpc/log/live` (people only). The sockets get the REST network guard plus a loopback Origin check.
- `openhal/cli/rpc_cmd.py`, registered in `openhal/cli/main.py`.
- `openhal/drivers/base.py`: `DriverInfo.conformance`, default "control". uvc and rpi-camera are "core".
- `openhal/conformance/suite.py`: checks above the declared level are reported as skipped.
- `openhal/drivers/catalog.py` and `drivers/catalog.json`: each driver's `conformance`.
- `openhal/mcp/errors.py` (new) and `openhal/mcp/tools.py`: decisions gain `error`.
- `spec/2026-10-24/schema.json` and `schema.md`, generated.
- `tests/spec/test_spec_names.py`: every check now runs against the ADR and against `openhal.protocol`.
- Tests in `tests/protocol/`: errors, conformance levels, lifecycle, trace, methods, notifications, schema, stdio, mcp_errors.

### What the tests cover
- Every method and every one of the 24 error names, over both transports. The stdio side runs the real bridge in-process, and one test also runs the actual `openhal rpc` process.
- The exact LIMIT_EXCEEDED trace with the canonical values. It is read 20 %, blocked at 150 %, granted 60 %, with `fan_speed 150 % exceeds the limit of 100 % (desk-fan.hal.yaml, confirmed by sohan 2026-10-24)`.
- The session-limit reason, version negotiation, lifecycle ordering, and that agents get SCOPE_DENIED on approve, reject and unlock.
- PARSE_ERROR for bad JSON, INVALID_REQUEST for a batch, and a hub limited to core answering only core methods.
- Every notification, including a block made over REST showing up as `hal/blocked`.
- The message log: people only, tokens never stored, live feed works.
- The Origin guard, schema freshness, and MCP errors matching protocol errors exactly.

### Decisions and contract change proposals
1. **`hal/blocked` error shape.** The ADR and spec tables say `{ code, name, message, data }`, but the spec examples and the JSON-RPC error shape put `name` inside `data`. I followed the examples. Please fix the tables.
2. **Extra fields in `error.data`.** The data model accepts more fields than the spec lists. I add `action`, `tightenedBy` (the session-limit reason has to be formed from data), `problems` for INVALID_PARAMS, `method` for METHOD_NOT_FOUND and for SCOPE_DENIED on human-only methods, and `routine`. `data.limit` and `data.requested` are quantity strings, and a rate reads `20 %/s`. Please add these to the spec.
3. **Who gets `hal/confirmationRequested`.** It goes to people and to the principal that asked, not to every connection. This matches `hal/confirmations/list`, where agents see only their own requests. The spec says every connection, which would leak other agents' requests.
4. **stdio close.** When stdin closes, `openhal rpc` closes the WebSocket once the requests it already sent have been answered, at most 30 s. Closing straight away would leave `echo ... | openhal rpc` with no answer. Only messages go to stdout, and diagnostics go to stderr (exit 3 when there's no hub). It sends an Authorization header only from `--token-file` or `OPENHAL_TOKEN`, never from the human token file. Otherwise the client sends its token in `hal/initialize`.
5. **`hal/action` result.** The result is `{ status: "done", result: { device, action, args } }` because the kernel throws away what the driver's action returns. Making the kernel pass that on would need a kernel change.
6. **`hal/planCheck` and `hal/routines/dryRun`.** A step that needs a person keeps status `needs_confirmation` and carries CONFIRMATION_REQUIRED. `hal/dryRun` leaves out the error, as the spec example does.
7. **Unknown request id.** An unknown id on approve or reject gets REQUEST_CLOSED with `kernelCode: "expired"`, as the spec asks. Please say which kernel code applies.
8. **Times.** `createdAt` and `expiresAt` are worked out from the kernel's monotonic clock. Units are sent as the device file declares them, so the test fixture declares `"%"` to match the spec examples.
9. **DeviceSummary.** It now has only the spec's 10 fields, so `unavailable`, `lastError` and `source` are gone from the protocol (REST still has them). I'd suggest adding `unavailable` back to the spec.
10. **Before initialize.** Unknown methods sent before `hal/initialize` get NOT_INITIALIZED, the literal reading of lifecycle rule 5. A second `hal/initialize` gets INVALID_REQUEST.
11. **Human-only refusals.** These methods are refused before the kernel, as REST does it, so those refusals don't reach the audit log.
12. **MCP reasons.** MCP reasons match the protocol only when the MCP server can reach `/rpc` (it calls `hal/devices/describe` for who confirmed the limit). With an in-process transport, as in the interfaces tests, it falls back to the REST view and leaves "confirmed by" out. The cleaner fix is for REST decision views to carry the hub-built `error`, but `views.py` isn't mine. MCP `plan_check` and `read_many` still go through REST, so `plan_check` has no wait steps.
13. **Message log entries.** `at` is epoch seconds, not RFC 3339, because the log isn't protocol traffic. The Inspector may want that converted.

### Commit sizes
Two commits are over the 450-line guide. The models commit was about 560 lines after formatting. The generated `schema.json` commit is about 3,600 lines, and that file is generated so it can't be split.

## Orchestrator note

Saved by the orchestrator from the agent's hand-back. Merged into main, where the full suite passed with 1120 tests. Proposals 1, 2, 3, 7 and 9 were applied to ADR 0015 and the spec, and DeviceSummary gained `unavailable`. Proposal 12 (REST decision views carrying the hub-built error) is open.
