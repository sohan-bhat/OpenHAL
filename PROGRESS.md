# Progress

## Current milestone

Phase D. The starter library (M12), packaging (M13), verification (M14) and handoff (M15).

## Active subagents

Cap is 3 agents at once (owner, 2026-10-25). Every coding agent runs on Opus 5.5, writes no code comments and starts no subagents. Briefs are in docs/agents/.

- website-3. The owner's list (quirks removed, trace narration as comments, Playground in the nav, diagram chips, one page container, no sideways scrolling, site search with Cmd K) and the reference driver out of the counts (BRIEF-website-3.md).
- inspector-4. The final critique's Inspector findings (BRIEF-inspector-4.md).

Queued. website-4, the final critique's website findings (BRIEF-website-4.md), after website-3 merges.

The final critic scored the website 3.5 and the Inspector 4 of 5 (FINAL-REPORT.md). The website is live at https://sohan-bhat.github.io/OpenHAL/ and redeploys from main.

Kernel coverage on the full suite, 2026-10-25. 100 % of lines but two, 99 % of branches. The four branches left are fail-closed guards the public API can't reach (an expression naming a device the reference check already blocked, a bare name in a hub expression, a missing asyncio task, and a safe state value that isn't a number on a rate-limited number channel).

Design round screenshots live in docs/design-rounds/, which is gitignored so they never reach a clone.

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
- One value format (ADR 0016). Numbers travel with their unit apart in every protocol message, REST body, MCP tool, the Python client and CLI --json. A number sent as one string gets UNIT_INVALID with the shape to use, and a test fails on any docs example that sends one. Messages say % for percent.
- The Arduino plant waterer is the canonical example (examples/plant-waterer/). The Arduino library gained actions with typed arguments, named states and internal outputs, the firmware protocol gained ACT, and the driver, simulator and sketch reader follow. `openhal demo` runs it against a real hub and `--record` writes docs/demo/scenario.yaml, which the README, docs/QUICKSTART.md and the tests read.
- Action run limits (max_runs) and requirement messages in device files.
- The README leads with the one-line description, the license and CI badges, the flow diagram, a three-command quickstart and the generated trace. The description is also in pyproject, the CLI help and the GitHub repository description.
- The mark is the stop bar mark (a request stroke meeting a stop bar above a return stroke). A circle, bar and square mark replaced it on 2026-10-25, and the owner asked for the stop bar mark back the same day.
- The safety red team suite (100 tests) merged, and its four findings RT-01 to RT-04 fixed. docs/SAFETY-REPORT.md.
- Driver SDK commands (`openhal driver new`, `driver test`, `driver list`).
- M11. All sixteen planned drivers are built to the Tier 1 standard and pass conformance on simulators (batch 3 grbl, alpaca, indi, ros2, opcua, sila2, pylabrobot, lerobot, and batch 4 onvif, bambu, can, knx, matter, pi-i2c-spi, upnp, zigbee-zwave). 35 drivers in all.
- The protocol website and the Inspector, all three design critique rounds, merged. WebKit browser tests could not run on this Mac (every WebKit page load stalls here) and still need a run elsewhere.
- Full-level conformance checks for actions. openhal-firmware declares full and runs them against the compiled PlantWaterer sketch.
- Code comments removed from all Python and C++ code.
- The bambu driver ships, approved by the owner on 2026-10-25.
- M12. The starter library, 33 unverified device files in library/ across 14 drivers, bundled in the wheel as openhal/library_data, with `openhal library list|show|add`. Discovery no longer matches on a USB class or mDNS type alone.
- M13. `openhal init` is a wizard in a terminal and takes safe defaults with `--yes`. It adds found and self-describing devices read-only, makes an agent token and prints or saves the MCP setup for Claude Desktop, Claude Code and Cursor. `openhal service` runs the hub under launchd or systemd. scripts/install-pi.sh installs on a Raspberry Pi. Install to the first agent read takes 9.6 s and 8.5 s (docs/verification/install.md), against a 60 s goal.
- M14 so far. `openhal demo --full` runs discovery, the driver writer on the plant waterer sketch, a scripted limits interview, an agent over MCP drafting a routine a person enables, the routine watering, and a refused 120 s water, all on mocks, recorded in docs/demo/e2e.yaml. The plant waterer is the main example on every page. tests/docs/test_commands.py checks every documented command against the CLI and runs the runnable ones on a mock hub, and tests/docs/test_consistency.py checks method names, error codes, traces, terms and conformance tables against ADR 0015, the schema and the code.
- Fixes found on the way. scpi notices a LAN instrument that closed its socket (the Linux CI failure). Home Assistant WebSocket connects wait for the first states. Siglent SPD supplies get their own commands. The LPD8 example has the right USB id. The writer confirms by name, gives the hub the saved path, polls self-described channels at their report interval, and asks for action requirements, run limits and a safe action, so a writer-made plant waterer has the same limits as the hand-written one.
- M15 so far. CONTRIBUTING, CODE_OF_CONDUCT (Contributor Covenant 2.1), SECURITY, docs/ROADMAP.md and docs/LAUNCH.md (drafts, never posted). docs/hardware-tests/README.md orders all 35 plans from lowest hazard to highest with the plant waterer first, and every plan runs from a checkout, confirms limits with `openhal file confirm`, says what to send back on failure and has a report template that earns `verified-on-hardware`.
- Safety fixes from the handoff report. No driver opens a file path from a device file (certificates and the pylabrobot deck come through `ca_env` and `deck_env`, and a test guards it). One daemon per config folder, and an audit chain a second writer can't fork. A run counts from its grant, so a run the hub never finished still counts after a restart. The GPIO stop button in config.yaml is watched, and a configured button the hub can't watch stops it from starting.
- Unit safety. pint no longer converts between angles and plain numbers (50 % to a degree channel, 1 Hz to rpm). Channels with no read-back stay controllable under a rate limit. A bare number gets UNIT_INVALID in dry runs instead of a hub error.
- REST reports conformance, simulated drivers, run limits, requirement reasons, the protocol version and the LAN setting.

## Next

- REST decision views should carry the hub-built protocol error so MCP reasons always name the confirmation (protocol report, proposal 12).
- tests/drivers/firmata/test_firmata.py::test_silent_board_times_out can time out under full-suite load on this Mac. It passes alone.
- Library matching proposals (library report). New `match` keys for Pi boards and HATs, libcamera models, Alpaca servers, MIDI port names and MQTT topics, so the six library files with no identifier can be matched. Discovery that reports more, with scpi sending `*IDN?`, moonraker browsing `_moonraker._tcp`, homeassistant listing entity ids, modbus scanning unit ids, mqtt listening for announce topics and esphome reporting `mdns`.
- Driver proposals still open. A restore_connection hook, a push path for drivers that receive values, cached-read declarations, per-driver install hints, argument references in action requirements, and YAML 1.1 warnings in openhal file validate.
- Packaging proposals. A `self_describing` flag in DriverInfo. Lazy imports so `openhal mcp` starts faster. Intel Mac installs need `--no-build` while cryptography and zeroconf ship Apple Silicon wheels only.
- Handoff proposals still open. The GRBL simulator stays idle after a hold where real GRBL 1.1 reports Hold:0. The driver scaffold's hardware test template should match docs/hardware-tests/README.md. Expected outputs in the plans quote kernel codes, so they change if the CLI moves to registry names.
- Verification and handoff, in progress. Lighthouse, axe and the orphan audit, the final critique, and FINAL-REPORT.md.
- Confirm on GitHub CI that the scpi fix passes on Linux (the owner approved the fix and the push on 2026-10-25).

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
