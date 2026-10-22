# Interfaces workstream report

**Branch:** `worktree-agent-a47b8b408074d7efd`. It has 23 commits of my own, each between about 50 and 450 lines, all with conventional messages, the global identity (sohan-bhat) and no trailers. I merged `main` into the branch twice: once for the routine, discovery and pair/code routes you announced, and once more because the first merge pulled in `main`'s two failing spec tests, which later `main` commits fixed.

**docs/agents/REPORT-interfaces.md was not written.** The harness blocks subagents from writing report .md files, so the full report is below. It is ready to paste into that path.

**Checks (all pass):**
- `uv run pytest`: 399 passed, 49 of them in `tests/interfaces`.
- `uv run ruff check openhal tests`: clean.
- `uv run ruff format openhal tests`: 125 files already formatted.
- `uv run mypy openhal`: no issues.

---

## What was built

### Python client (`openhal/client/`)
- `Client` (sync) and `AsyncClient` with one method per route. That covers docs/api/openapi.json, every ADR 0014 route and the proposed token routes.
- `connect()` and `aconnect()` call `whoami` straight away, so a wrong address or token fails at once.
- Every route is described once in `calls.py`, and both clients use that one list.
- Responses are typed pydantic models that keep fields they don't know.
- Exceptions: `HubNotRunning`, `Unauthorized`, `NotFound`, `NotSupported` (a `NotFound` raised when an older hub has no such route), `Refused`, `BadRequest`, `HubError`.
- Token lookup order: explicit argument, then `OPENHAL_TOKEN`, then `$OPENHAL_HOME/human.token`. Proxy environment variables are ignored, so a token never goes through a proxy.
- `ramp_to()` moves a channel in steps that each pass `max_change_per_s`. docs/SAFETY.md already promised this. The kernel still checks every step.
- `AsyncClient.events()` streams `/v1/live`.
- I updated the models to the new shapes you sent. Routine summaries have `enabled_by` and `disabled_reason`, and routine detail has `source_raw`. Runs have `routine_id` and `trigger`. Steps are typed loosely because run steps can be `{if, result}`. Stop results can be safe, partial, failed, pending or no_safe_state.

### MCP server (`openhal/mcp/`, started with `openhal mcp`)
- Built on `mcp.server.mcpserver.MCPServer` from SDK 2.3.0. I checked the installed API before using it: FastMCP was renamed and the test client is `mcp.Client(server)`.
- 28 tools: the 20 from the brief plus `hub_status`, `get_routine`, `enable_routine`, `disable_routine`, `discover_devices`, `get_writer_session`, `get_test_plan` and `device_file_schema`.
- The tool list, descriptions written for models and input schemas live in `tools.py`. Outputs are typed and include units, block codes and limits. Tools carry read-only and destructive annotations.
- Two prompts. `set_up_device` walks through discovery, the driver writer and the limits interview. `write_routine` uses the real routine YAML format from `openhal/routines`.
- The token comes from `OPENHAL_TOKEN` or `--token-file`, never from the human token file.
- A human token is refused, both at startup and on the first tool call. This matters because the hub treats a human's command as already confirmed.
- If the hub is down, the server starts `openhald` once in the background (ADR 0003). If that fails, every tool says how to start it.
- String readings and driver error text are wrapped in device-data blocks, on top of the blocks the hub already builds.

### CLI (`openhal/cli/`)
- One module per group, all registered in `main.py`. `file_cmd.py` is untouched.
- Commands:
  - `init`, `status`, `devices`, `discover`
  - `read`, `write`, `action`, `dry-run` (also takes a plan file), `stop`, `unlock`
  - `confirm list|show|approve|reject`
  - `log` (with `--verify`)
  - `routine list|show|new|dry-run|enable|disable|run|delete|approve`
  - `writer start|show|propose|interview|finish|plan`
  - `token create|list|revoke`, `pair`, `mcp`, `doctor`
  - The existing `file validate|schema`, plus a new `file confirm`
- Exit codes: 0 success, 1 blocked or refused, 2 usage error, 3 hub not running, 4 token problem.

### Docs
docs/interfaces/MCP.md (setup for Claude Desktop, Claude Code, Cursor and a generic client), CLI.md and PYTHON.md.

## Files
- **Added:**
  - `openhal/client/{__init__,aio,calls,errors,models,ramp,settings,sync,transport}.py`
  - `openhal/mcp/{__init__,prompts,server,tools}.py`
  - `openhal/cli/{_common,_tty,confirm_cmd,control_cmd,doctor_cmd,file_confirm_cmd,hub_cmd,init_cmd,log_cmd,mcp_cmd,routine_cmd,token_cmd,writer_cmd}.py`
  - `docs/interfaces/{MCP,CLI,PYTHON}.md`
  - `tests/interfaces/{conftest,fake_hub,test_client,test_client_routines,test_client_planned_routes,test_live_events,test_mcp,test_cli,test_cli_groups}.py`
- **Changed:** `openhal/cli/main.py`.

## Tests
- **How they run:** a real embedded hub with the mock fan and heater.
  - Async tests use `httpx.ASGITransport`.
  - The sync client and CLI tests use a `BridgeTransport`, which forwards each request to the hub running on a background event loop. So the CLI is tested against the real kernel with no socket.
  - Routines, discovery (mock driver only) and pair/code are tested against the real routes.
  - The writer routes and the proposed token routes use an `httpx.MockTransport` fake that follows ADR 0014's who-may-call column. A `SplitTransport` sends those routes to the fake and everything else to the real hub.
  - Live events are tested against uvicorn on a loopback port.
  - MCP tools are tested both by calling them directly and through the SDK's in-process client.
- **What they prove:**
  - A device note can't close its data block early.
  - An agent is refused by the hub even when the confirmation phrase is typed.
  - `--phrase` is accepted only when `require_tty` is false.
  - `init` sets the expected file modes.
  - `file confirm` binds the limits hash, and a later limit change makes the file read-only again.
- **Checked by hand, not in the suite:**
  - `openhal mcp` over real stdio, using `StdioServerParameters`.
  - A full run with `openhald` on a scratch config folder and the mock device only: init, file confirm, status, write, token create, pair, stop, unlock, log, verify, doctor.
- No real hardware was touched at any point.

## Decisions
- **TTY rule widened.** The ADR 0012 terminal plus typed-phrase rule applies to every human-only CLI command, not just confirm and unlock. That adds `routine enable`, `routine run`, `routine approve`, `writer interview`, `writer finish` and `file confirm`. The phrase is read from `/dev/tty`, not stdin, so an agent can't pipe it in.
- **`init` leaves the sample read-only.** The spec says tools must not add `confirmed`, so the sample device stays read-only until the person runs `openhal file confirm`. `init` also sets `hub.db` to mode 0600.
- **`file confirm` added.** The F15 validator warning already names this command, but nothing implemented it. It writes `confirmed: {by, at, sha256}` using `limits_sha256()`, and refuses while any entry is `suggested: true`. I registered it on `file_cmd.app` from `main.py`, so `file_cmd.py` is unchanged.
- **Token commands can fall back to the database.** When the hub is down or has no token routes, they work on `hub.db` in the config folder directly. This is the same bootstrap path `init` already needs, and only the folder's owner can use it.
- **`enable_routine` is an MCP tool.** ADR 0007's opt-in lets an agent enable low hazard YAML routines. Without the opt-in, the hub refuses it.

## Open issues
1. `openhal.connect()` and `openhal.aconnect()` need a change to `openhal/__init__.py`, which I don't own. For now they are `openhal.client.connect()` and `openhal.client.aconnect()`.
2. httpx is only in the `hub` extra, but the CLI imports the client. So `openhal file validate` breaks on a base install without httpx.
3. The writer and token routes are tested against fakes only. When they land, shrink `PREFIXES` in `tests/interfaces/fake_hub.py` and move those tests to the real hub.
4. Confirmation requests carry `created_at` and `expires_at` on the hub's monotonic clock, so clients can't show how long is left.
5. When the hub creates `hub.db` itself, it uses mode 0644. `doctor` flags this and `init` fixes it.
6. The automatic `openhald` start from `openhal mcp` has no automated test, because the test would start a real daemon.
7. The hub doesn't reload device files, so `file confirm` and `writer finish` tell the person to restart `openhald`.

## Contract change proposals
1. **Top-level connect.** Add a lazy `__getattr__` to `openhal/__init__.py` that returns `openhal.client.connect` and `openhal.client.aconnect`.
2. **httpx as a core dependency.** Move `httpx>=0.28` from the `hub` extra to `dependencies` in pyproject.toml.
3. **Token routes, all human only.**
   - `POST /v1/tokens` with `{name, kind, scope}` returns `{token, token_id, name, kind, scope, created_at, revoked}`. The plain token appears only in this answer.
   - `GET /v1/tokens` returns the list without tokens.
   - `DELETE /v1/tokens/{id}` returns `{ok}`, or 404 when there is no active token with that id.
   - The client and CLI are already built against these shapes.
4. **Expiry in seconds.** Add `expires_in_s` to every confirmation request view.
5. **Private hub database.** Create `hub.db` with mode 0600 in `Hub.__init__`, the same way `approval.key` is created.
6. **Data blocks on the server.** Wrap string readings, `last_error` and audit details that quote device output in data blocks on the server, so every client gets them. Until then the MCP server does it itself.
7. **openapi.json.** Regenerate docs/api/openapi.json. The routine, discovery and pair/code routes are served but not in the checked-in document.

## Orchestrator note

Saved by the orchestrator from the agent's hand-back, because the harness blocks subagents from writing report files. Merged into main as one merge commit after a clean merge. The full suite passed with 411 tests once httpx moved to the core dependencies.
