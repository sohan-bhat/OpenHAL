# Progress

## Current milestone

Phase C. The protocol theme and hub protocol (ADR 0015), the dated specification, the website as a protocol site, the README flow diagram, then the Inspector (M7).

## Active subagents

Cap is 5 agents at once (owner, latest 2026-10-24). Every coding agent runs on Opus 5.5, writes no code comments and starts no subagents.

- website (own worktree). Owns website/, docs/guide/, docs/design-rounds/ and tests/website/. Brief in docs/agents/BRIEF-website-2.md (protocol site). Resumed after the crash with 40 commits saved. Round 1 review findings are superseded by the theme change.

- Inspector (worktree agent-ab1476059128896a1). Owns dashboard/, openhal/hub/static/, tests/inspector/ and docs/design-rounds/inspector-*. Brief in docs/agents/BRIEF-inspector.md. Resumed after the crash.
- red team (own worktree). Owns tests/redteam/ and docs/SAFETY-REPORT.md. Brief in docs/agents/BRIEF-redteam.md. Never changes openhal/ code. Findings come back to the orchestrator to fix.
- drivers-3 (own worktree). grbl, ros2, opcua, sila2, indi, alpaca, pylabrobot, lerobot. Brief in docs/agents/BRIEF-drivers-3.md.
- drivers-4 (own worktree). onvif, bambu, can, knx, matter, pi-i2c-spi, upnp, zigbee-zwave. Brief in docs/agents/BRIEF-drivers-4.md. The owner asked for all sixteen planned drivers to be built, Tier 3 included.

## Done

- M0, M1, M2 complete (see the reviews below). Independent safety review with 22 findings, all fixed.
- M3 and M4. 17 Tier 1 drivers plus openhal-firmware, all passing conformance on simulators. Discovery and library matching.
- M5. MCP server, CLI and Python client (interfaces workstream), plus token routes, server-side data blocks and the OpenAPI document.
- M6. Routine engine with API routes.
- M9 server side. The driver writer (sketch and manual parsing, limits interview, staged test plans, sessions and routes).
- M10. The OpenHAL Arduino library, compiled for arduino:avr:uno and esp32:esp32:esp32, with its driver and a host build that runs conformance against the real C++.
- Repository published at github.com/sohan-bhat/OpenHAL at the owner's request.
- The protocol theme in docs/DESIGN.md, design/tokens.css and the Atkinson fonts. ADR 0015 for the JSON-RPC hub protocol.
- The dated specification 2026-10-24 (spec workstream, merged) and the hub protocol over WebSocket and stdio with the error registry, conformance levels, message log and generated schema (protocol workstream, merged). 1120 tests pass on main.
- The README per Part 16, with the animated flow diagram built from docs/diagrams/flow.d2 by scripts/build-diagrams, in light, dark and phone variants. Tooling recorded in docs/TOOLING.md.

## Next

- Merge the website and the Inspector as they hand back, then run their design critique rounds.
- REST decision views should carry the hub-built protocol error so MCP reasons always name the confirmation (protocol report, proposal 12).
- Fix the SCPI driver's disconnect detection on Linux, which is the only CI failure (2 of 965 tests on ubuntu). Then restore the CI badge.
- Remove code comments repo-wide after the open branches merge (owner rule).
- docs/demo/scenario.yaml from a real hub run, with a consistency test.
- Driver SDK commands (`openhal driver new`, `driver test`, `driver list`), Tier 2 and 3 drivers (M11), the starter library (M12), packaging (M13), the red-team suite, verification and handoff.

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
