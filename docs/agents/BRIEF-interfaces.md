# Brief: interfaces (MCP server, CLI, Python library)

## Goal

Build every client of the OpenHAL hub. The MCP server agents use, the `openhal` CLI people use, and the Python library scripts use. All three talk to the hub only through the local API (ADR 0003). None of them makes safety decisions. The kernel does.

## Definition of done

1. `openhal/client/` holds a sync and an async client of the API v1 (`openhal.connect()`, `openhal.aconnect()`), typed, with clear exceptions (`HubNotRunning`, `Unauthorized`, `NotFound`, `Refused`). Token lookup order is explicit argument, `OPENHAL_TOKEN` env var, `~/.openhal/human.token` (or `$OPENHAL_HOME/human.token`). It exposes methods for every route in docs/api/openapi.json and every route in docs/adr/0014-routine-writer-discovery-api.md.
2. `openhal/mcp/` holds a stdio MCP server built on the official MCP Python SDK (already installed, version 2.3.0, check its current API before writing code), started with `openhal mcp`. It has at least these tools, each with a precise description written for models, typed inputs and outputs that include units and block reasons.
   list_devices, describe_device, read, read_many, write, action, dry_run, plan_check, stop_all, tighten_limits, list_routines, draft_routine, run_routine_dry, get_audit_log, list_drivers, list_unknown_devices, start_driver_writer, propose_device_file, request_limits_interview, get_confirmation_status.
   Device notes and any device-sourced text are returned as the data blocks the hub already builds (`hub/views.py`). Add MCP prompts for "set up a new device" and "write a routine". The tool list and input schemas live in `openhal/mcp/tools.py`.
   The MCP server reads its agent token from `OPENHAL_TOKEN` or `--token-file`. If the hub isn't running it says how to start it.
3. The CLI in `openhal/cli/` (Typer, rich output, specific actionable errors) has at least these commands.
   openhal init, status, devices, read <device.channel>, write <device.channel> <value with unit>, action <device.action> [key=value ...], dry-run, stop, unlock, confirm (list, approve, reject), log (with verify), routine (list, new, dry-run, enable, disable, run), writer, token (create, list, revoke), pair, mcp, doctor, plus the existing `file validate` and `file schema`.
   `openhal init` creates the config folder, the human token file (mode 0600), a sample device file using the mock driver, and prints next steps. `openhal unlock` and `openhal confirm approve` require an interactive TTY and a typed phrase when `confirm.require_tty` is true (ADR 0012). `openhal token create --agent --scope control_low --name claude` prints the token once. `openhal pair` prints a pairing code (needs a route, see the note below). `openhal doctor` checks the daemon, the token, config permissions and installed driver extras.
   Keep `openhal/cli/main.py` as the app that registers groups, one module per group.
4. Setup docs. docs/interfaces/MCP.md with setup for Claude Desktop, Claude Code, Cursor and a generic MCP client. docs/interfaces/CLI.md (reference for every command). docs/interfaces/PYTHON.md (library reference with examples).
5. Tests in tests/interfaces/. Run CLI and library tests against a real embedded hub served in-process (httpx ASGITransport over `openhal.hub.api.create_app`, see tests/hub/test_api.py) for every route that exists now, and against an `httpx.MockTransport` fake for the ADR 0014 routes that don't exist yet. MCP tools are tested by calling the tool functions directly and through the SDK's in-memory client if it has one.

## Files you own

- openhal/client/ (new)
- openhal/mcp/ (new)
- openhal/cli/ (everything except file_cmd.py, which you may import but not change)
- docs/interfaces/ (new)
- tests/interfaces/ (new)

## Contracts you must follow (read first)

- docs/ARCHITECTURE.md, docs/SAFETY.md (who may do what), docs/adr/0003, 0006, 0007, 0012, 0013 and 0014.
- docs/api/openapi.json and openhal/hub/api.py (the server, read-only for you).
- openhal/hub/views.py (payload shapes), openhal/kernel/commands.py (Write, Action, Decision).

## What you must not do

- Don't edit files outside the paths you own. If you need a server change (for example a `POST /v1/pair/code` route for `openhal pair`, which only exists as `TokenStore.new_pairing_code()` today), write the proposal in your report and implement the client side against the shape you propose.
- Don't send anything to real hardware. Don't push, publish packages or post anything. Don't start subagents.
- Don't weaken any safety rule. Clients never approve, unlock or loosen anything on behalf of an agent.

## Working setup

You work in your own git worktree on your own branch. Run `export PATH="$HOME/Library/Python/3.13/bin:$PATH"` then `uv sync --all-extras` once, then `uv run pytest`, `uv run ruff check openhal tests`, `uv run ruff format openhal tests` and `uv run mypy openhal`. All must pass before you finish. Commit on your branch in small logical commits of roughly 50 to 450 lines, with conventional commit messages, authored by the existing global git identity. Never set git config, never pass --author, and add no trailers of any kind to commit messages.

Copy in docs and CLI output. Plain, precise, a little dry. No em dashes or en dashes, and no colons or semicolons in running prose (headings, labels, tables and code are fine). No exclamation marks. Never use the words unlock (except the literal command), seamless, supercharge, elevate, effortless, empower, revolutionary.

## Report

Write docs/agents/REPORT-interfaces.md. List files changed, tests added, open issues, decisions made, and any contract change proposals.
