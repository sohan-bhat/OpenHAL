# Progress

## Current milestone

Phase B. Drivers, interfaces, routines (M3 to M6), with M9 driver writer started by the orchestrator.

## Active subagents

- interfaces (Opus, own worktree and branch). Owns openhal/client/, openhal/mcp/, openhal/cli/ except file_cmd.py, docs/interfaces/, tests/interfaces/. Brief in docs/agents/BRIEF-interfaces.md. Covers M5.
- drivers-1 (Opus, own worktree and branch). Owns the serial, firmata, scpi, moonraker, octoprint, marlin, homeassistant and esphome driver packages, their tests and docs. Brief in docs/agents/BRIEF-drivers-1.md. Covers M3 drivers.
- drivers-2 (Opus, own worktree and branch). Owns the rpi-gpio, rpi-camera, mqtt, modbus, ble, midi, hid, uvc and http driver packages, their tests and docs. Brief in docs/agents/BRIEF-drivers-2.md. Covers M4.
- Orchestrator builds the driver writer server side (M9) and the firmware library (M10) while these run.

Concurrency cap is 3 subagents at once, lower than the 5 the build prompt allows, because the owner's standing rule caps parallel agents at 3. Every coding subagent runs on Opus 5.5 and may not start subagents of its own.

## Done

- Repository created at ~/code/openhal.
- Research brief copied to docs/research/OPENHAL_RESEARCH.md, updated with OpenMHP, DCP, Octopus, HACP and EMQ findings.
- Name check recorded in docs/research/SOURCES.md.

- M0 complete. ARCHITECTURE, SAFETY, THREAT_MODEL, DESIGN, COVERAGE plan, ADRs 0001 to 0012 and the spec draft are written and committed.

- M1 complete. Pydantic models, JSON Schema, 14 examples, `openhal file validate` and `openhal file schema`, spec CHANGELOG and versioning policy, MHS mapping, DEPENDENCIES. 128 tests, ruff and mypy clean.

- M2 complete. Driver base with sealed methods and single-use grants, the safety kernel with every check, audit log with hash chain and head file, confirmation queue, stop and unlock, dry runs, tokens and pairing, device locks, the hub with polling, heartbeats and reconnects, the local API v1, the conformance suite, driver discovery from packages. Independent safety review done, 22 findings, all fixed (docs/agents/REVIEW-safety.md).
- M3 discovery and library matching done (openhal/hub/discovery.py). Drivers batch 1 running.
- M6 routine engine done on the server side (YAML and Python routines, triggers, dry runs with simulated waits, approvals for high hazard, stop disables routines, API routes). CLI and MCP parts come with the interfaces workstream.

## Next

- Driver writer (M9), firmware library and protocol (M10), wiring the Pi stop button once rpi-gpio lands, then merge the three workstreams one at a time.

## Milestone 2 review

Built. Everything in the M2 list, plus the safety review and its fixes. 326 tests pass, kernel branch coverage about 96 percent, ruff and mypy clean.

Weak. Drivers run in-process, so a malicious driver remains a residual risk (T17). Rate-limited channels block after any failure until a fresh read, which is safe but can be sticky for devices with slow reads. Hub-wide blocking on a dangling reference is strict and will surprise people during setup, so the CLI and dashboard must explain it well.

Would change. Move drivers out of process for third-party code. Give the kernel a single place that defines unknown, instead of the flags spread across runtime and kernel.

## Milestone 1 review

Built. The spec models with every section of SPEC.md, a restricted YAML loader (no anchors, aliases or custom tags, size limit), unit handling that converts degF against degC limits and uses delta units for temperature rates, a three-valued expression language with its own parser, the generated JSON Schema with a test that it matches the models, fourteen example files and the validate CLI.

Weak. Location strings for errors raised inside model validators come from the message text rather than the error path. Driver parameters are not validated until drivers exist. The schema describes limits as number or string, so editors can't check units.

Would change. Move per-driver parameter models next to each driver and reference them from the schema with a discriminated union once all drivers exist.

## Milestone 0 review

Built. The research brief with the October findings, sources, twelve ADRs, the architecture with seven diagrams, the safety model with a fixed check order and stable codes, the threat model with twenty threats mapped to tests, the design system with verified contrast figures, the coverage plan and the v0.1 spec draft.

Weak. Device estimates in the coverage plan are reasoning only and still need sources. The MHS mapping depends on a spec nobody can read yet. The expression semantics for unknown values are conservative and may block legitimate commands when a sensor is slow.

Would change. Nothing structural yet. The spec draft will be tightened as the models are written.

## Known issues

- PyPI name `openhal` is taken by an unrelated project. See NEEDS_HUMAN.md and ADR 0002.
