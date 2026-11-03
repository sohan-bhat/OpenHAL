# 0019 General tools for agents, and runs of steps through the kernel

## Context

On 2026-11-02 the owner asked for more general, less hardcoded tools in the MCP server. The owner's standing rule is that features take any device, channel or action instead of one scenario. An agent on MCP had single reads, writes, actions and dry runs. A task with timing, such as blinking an output, stepping a value or acting once a reading crosses a value, took one tool call per command with the agent keeping time between calls. The agent also had to know device ids before it started, and some tool text named the printer example as if every hub had one.

## Decision

The hub gains four general building blocks, served over REST, the Python client (sync and async) and MCP. None of them is tied to a device, a task or a scenario.

### find

`GET /v1/find` searches every device's channels and actions by free text, unit, kind (readable, writable or action), hazard class and connected state, and returns `device.channel` or `device.action` targets with their type, unit, limits or arguments and latest value.

- Text matches device ids and names, channel and action names, action descriptions, enum values, units and the quantity a unit measures, so temperature finds a `degC` channel named `temp`. The quantity names come from the pinned unit registry.
- A unit matches every channel a value in that unit converts to, by the same conversion a command uses, so `degC` finds `degF` channels and `%` never finds an angle.
- readable includes write channels, because a write channel reads back.
- A search reads no driver and isn't a read in the audit log.

### wait_until and sample

`POST /v1/wait_until` reads the channels a condition names until the condition holds or the timeout passes. The condition is in the routine expression language with every channel as `device.channel`. The reply carries the readings of the check that held, or of the last check. `POST /v1/sample` reads channels at an interval over a duration and returns each series with first, last, min, max and mean over its number readings.

- Every reading goes through `Kernel.read`, so it is a read in the audit log.
- The checks use the values just read. A failed or unknown reading makes the condition unknown, and an unknown condition never counts as held.
- No check runs faster than `poll_floor_s`, and a sample takes at most 1000 readings of each channel.
- A stop ends a wait or a sample at once with status `stopped`.

### Runs of steps

`POST /v1/runs` takes a list of steps and an optional repeat count. A step is `read`, `write`, `action`, `wait` or `wait_until`. A write step may carry `increment`, which is added to its number value once for each repeat before it, so one step can step a value.

1. **Caps first.** Steps times repeats must be within `runs.max_steps`, the run's waits within `runs.max_seconds`, and every target and condition must name a real channel.
2. **Plan check.** Every write and action is evaluated in order with `Kernel.evaluate` on a shadow state, as `plan_check` does, with each wait moving the simulated clock and a `wait_until` moving it by nothing. When the plan check blocks a step, nothing runs and the run ends `blocked` at that step.
3. **Execution.** Each write and action goes to `Kernel.execute` as the caller's own principal with `wire=True`, exactly as `/v1/write` and `/v1/action` do. Units, limits, session limits, rate of change against real elapsed time, interlocks, watchdog budgets, scope, grants, the stop lock and confirmations apply to every step.
4. **The first step that isn't done ends the run.** The run reports the step, the repeat, the code and the reason.

| Status | When | Code |
|---|---|---|
| `running` | Steps are still going | |
| `done` | Every step ran | |
| `blocked` | The plan check or the kernel blocked a command | the kernel's block code |
| `pending` | A command needs a person | `needs_confirmation`, with `request_id` |
| `failed` | A command failed, a `wait_until` timed out, or a bug in the engine | `driver_error`, `condition_timeout`, `internal_error` |
| `cancelled` | A cancel, a stop, a revoked token, the time cap or the hub shutting down | `cancelled`, `stopped`, `token_revoked`, `time_cap`, `hub_closed` |

Rules that keep a run inside the kernel's checks.

- A run never approves, unlocks, widens a limit or enables a routine. The step kinds are a closed list, every step model forbids extra fields, and no step carries a principal or a request id.
- A step held for a person ends the run with the request id, so nothing inside a run holds for an approval. Approving the request runs only that command, and the steps after it never run.
- A stop from any principal or the stop button ends every run, wait and sample through the kernel's stop hook. A command in flight at that moment is cancelled by the kernel's own stop path, and the hub applies the safe state again when it returns.
- A run belongs to the principal that started it. Another agent gets no run by that id from `GET`, `cancel` or the list, and the attempt is in the audit log. A person sees and cancels every run.
- Revoking a token ends that token's runs, waits and samples.
- A run ends at `runs.max_seconds` from its start, with a wait or a `wait_until` cut short at that moment.
- One token has at most `runs.per_agent` runs, waits and samples going at once.
- The audit log records `run` when a run starts and ends, `run_step` for every step with the run id, `wait_until`, `sample`, `run_cancel` and `run_caps`, next to the kernel's own `read`, `write` and `action` entries.
- Runs live in the hub's memory. A restart ends them, and the audit log keeps them.

`POST /v1/runs` replies when the run ends or after `wait_s` (5 s by default, at most 30 s), so a short run returns its result and a longer one returns `running` with a `run_id`. `GET /v1/runs/{id}` takes `wait_s` too, so an agent can wait for the end without polling hard.

### Caps

`config.yaml` holds a `runs` section with safe defaults, 200 steps per run counting repeats, 600 s per run, wait or sample, and 2 at once per token. Only a person changes the caps, with `openhal runs caps` or `POST /v1/runs/caps`. A lower cap applies at once. A higher cap takes the typed phrase `confirm`, in a terminal when `confirm.require_tty` is true, as `openhal limits set` does to widen a limit. The hub writes the new `runs` section into `config.yaml` and keeps every other line.

### The MCP server

New tools are `find`, `wait_until`, `sample`, `run_steps`, `get_run`, `list_runs` and `cancel_run`. `list_runs` is the one tool beyond the brief. An agent that lost a run id to a long session needs a way back to its own runs, and the tool only lists what `GET /v1/runs` already shows that token. A run that a command blocked or failed carries the same registry error a `write` result carries.

The audit of the server's text found these and made them general.

- The device, channel and action argument hints gave `printer`, `bed_temp` and `pause` as if every hub had them. They now point at `find` and `list_devices`.
- `read_many` gave `printer.bed_temp` as its example and in its error. Both now describe the `device.channel` shape.
- The `action` tool named home and pulse. It now says the device file names the actions.
- The `write_routine` prompt showed a routine that pauses a printer. It now shows the shape with placeholders and starts from `find`.
- The server instructions told agents to send numbers as `'60 %'`, which the hub blocks since ADR 0016. They now say value and unit go apart.
- The routine id hint used one scenario's name. It now states the id's shape.

Examples that stay are format examples, such as `{"value": 20, "unit": "s"}`.

## Proposed protocol methods

The JSON-RPC methods of ADR 0015 don't change in this version. A later spec version could add these, each under the `hal/` prefix.

| Method | Params | Result | Level |
|---|---|---|---|
| `devices/find` | `{ text?, unit?, kind?, hazard?, connected?, limit? }` | `{ count, matches: [Match] }` | Core |
| `waitUntil` | `{ condition, timeoutS?, intervalS? }` | `{ status, held, result, waitedS, checks, readings: [Reading] }` | Core |
| `sample` | `{ targets, durationS, intervalS? }` | `{ status, intervalS, durationS, series: [Series] }` | Core |
| `runs/start` | `{ steps: [Step], repeat?, waitS? }` | `Run` | Control, with action steps at Full |
| `runs/get` | `{ runId, waitS?, last? }` | `Run` | Control |
| `runs/list` | `{}` | `{ runs: [Run] }` | Control |
| `runs/cancel` | `{ runId }` | `Run` | Control |
| `runs/caps` | `{}` | `{ maxSteps, maxSeconds, perAgent }` | Control |

A notification `runs/ended` with `{ runId, status, stop }` would let a client follow a run without polling. A run over a cap would want its own registry name with the next free number, because no current name fits. The MCP mapping would gain `find` to `devices/find`, `wait_until` to `waitUntil`, `sample` to `sample`, and `run_steps`, `get_run`, `list_runs` and `cancel_run` to the four `runs/` methods. Changing the caps stays a REST and CLI operation for a person.

## Consequences

- An agent can do a task with timing on any device in one call, and every command in it gets the same checks as a single write.
- `docs/SAFETY.md` states the run guarantees, and the red team covers a write that outruns its rate across repeats, a step after a stop, the time cap, a cancel by another agent and an interlock that fails partway.
- The plan check counts a `wait_until` as no time, so a plan that needs time to pass for a rate limit adds a `wait` step. This can block a run that would have passed, and never passes one the kernel would block.
