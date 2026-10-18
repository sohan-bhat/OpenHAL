# 0014 API for routines, discovery and the driver writer

## Context

The interfaces workstream (MCP, CLI, Python library) runs in parallel with the orchestrator building the routine engine (M6), discovery (M3) and the driver writer (M9). Clients need the server shapes now.

## Decision

All under `/v1`, same auth as ADR 0012. "Human" means a human principal is required, otherwise any authenticated principal may call it subject to the kernel.

### Discovery

| Method and path | Body | Returns |
|---|---|---|
| `POST /v1/discover` | `{ "drivers": ["scpi", ...] }` optional | `{ "matched": [Match], "unknown": [Unknown], "errors": [{driver, error}] }` |
| `GET /v1/discover/unknown` | | `[Unknown]` from the last discovery |

`Match` is `{ address, driver, identifiers, label, library_file, device_id }`. `Unknown` is `{ id, address, driver, identifiers, label }`.

### Routines

| Method and path | Who | Body | Returns |
|---|---|---|---|
| `GET /v1/routines` | any | | `[RoutineSummary]` |
| `GET /v1/routines/{id}` | any | | `Routine` (summary plus `source`, `history`, `last_dry_run`) |
| `POST /v1/routines` | control scope or human | `{ id, kind: "yaml" or "python", source }` | `Routine`, always disabled |
| `POST /v1/routines/{id}/dry_run` | any | | `{ ok, decisions: [Decision], problems: [str] }` |
| `POST /v1/routines/{id}/enable` | human, or an agent under ADR 0007's opt-in | | `Routine` |
| `POST /v1/routines/{id}/disable` | any control scope or human | | `Routine` |
| `POST /v1/routines/{id}/run` | human | | `Run` |
| `DELETE /v1/routines/{id}` | human | | `{ ok }` |
| `POST /v1/routines/{id}/approve` | human | `{ device }` | the signed `Approval` added to that device file |

`RoutineSummary` is `{ id, kind, enabled, sha256, devices: [id], max_hazard, triggers: [str], drafted_by, last_run: Run or null }`. `Run` is `{ run_id, started_at, finished_at, status: "ok" | "blocked" | "failed" | "running", steps: [Decision], message }`.

### Driver writer

| Method and path | Who | Body | Returns |
|---|---|---|---|
| `POST /v1/writer/sessions` | control scope or human | `{ unknown_id? , driver?, params?, sketch_path?, manual_text? }` | `Session` |
| `GET /v1/writer/sessions/{id}` | any | | `Session` |
| `POST /v1/writer/sessions/{id}/propose` | any | `{ draft_yaml }` | `Session` (draft stored, every limit forced to `suggested: true`) |
| `GET /v1/writer/sessions/{id}/interview` | any | | `{ questions: [Question] }` |
| `POST /v1/writer/sessions/{id}/answers` | human | `{ answers: { question_id: value } }` | `Session` |
| `POST /v1/writer/sessions/{id}/finish` | human | `{ save_as? }` | `{ path, device_id, writable }` |
| `GET /v1/writer/sessions/{id}/test_plan` | any | | `{ steps: [TestStep] }` |

`Session` is `{ id, status: "detecting" | "drafting" | "interview" | "ready" | "saved", detected: {...}, sources: [str], draft_yaml, problems: [str], unconfirmed: [str] }`. Source text (sketch, manual, device output) is returned inside data blocks. `Question` is `{ id, channel, field, prompt, suggested, unit, reason }`. `TestStep` is `{ step, command, expected, needs_approval }`.

## Consequences

The interfaces workstream builds MCP tools, CLI commands and library methods for these endpoints and tests them against a fake transport. The orchestrator implements the server side and adds the routes to docs/api/openapi.json as they land.
