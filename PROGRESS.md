# Progress

## Current milestone

Phase D. The starter library (M12), packaging (M13), verification (M14) and handoff (M15).

## Active subagents

Cap is 3 agents at once (owner, 2026-10-25). Every coding agent runs on Opus 5.5, writes no code comments and starts no subagents. Briefs are in docs/agents/.

- website-13. The schema reference back to 98 or more on a phone, and the home page's small diagram whole at 1024 px (BRIEF-website-13.md).

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
- The specification v0.1, first published as the dated draft 2026-10-24 (spec workstream, merged), and the hub protocol over WebSocket and stdio with the error registry, conformance levels, message log and generated schema (protocol workstream, merged). 1120 tests pass on main.
- The README per Part 16, with the animated flow diagram built from docs/diagrams/flow.d2 by scripts/build-diagrams, in light, dark and phone variants. Tooling recorded in docs/TOOLING.md.
- One value format (ADR 0016). Numbers travel with their unit apart in every protocol message, REST body, MCP tool, the Python client and CLI --json. A number sent as one string gets UNIT_INVALID with the shape to use, and a test fails on any docs example that sends one. Messages say % for percent.
- The Arduino plant waterer was the canonical example until 2026-10-26 (examples/plant-waterer/). The Arduino library gained actions with typed arguments, named states and internal outputs, the firmware protocol gained ACT, and the driver, simulator and sketch reader follow. `openhal demo` runs it against a real hub and `--record` writes docs/demo/scenario.yaml, which the README, docs/QUICKSTART.md and the tests read.
- Action run limits (max_runs) and requirement messages in device files.
- The README leads with the one-line description, the license and CI badges, the flow diagram, a three-command quickstart and the generated trace. The description is also in pyproject, the CLI help and the GitHub repository description.
- No logo. On 2026-10-25 the owner asked for a text wordmark like REA's, so the brand is OpenHAL set tight at weight 800, with the initials OH for icons.
- The safety red team suite (100 tests) merged, and its four findings RT-01 to RT-04 fixed. docs/SAFETY-REPORT.md.
- Driver SDK commands (`openhal driver new`, `driver test`, `driver list`).
- M11. All sixteen planned drivers are built to the Tier 1 standard and pass conformance on simulators (batch 3 grbl, alpaca, indi, ros2, opcua, sila2, pylabrobot, lerobot, and batch 4 onvif, bambu, can, knx, matter, pi-i2c-spi, upnp, zigbee-zwave). 34 device drivers in all, plus the mock reference driver.
- The protocol website and the Inspector, all three design critique rounds, merged. WebKit browser tests could not run on this Mac (every WebKit page load stalls here) and still need a run elsewhere.
- Full-level conformance checks for actions. openhal-firmware declares full and runs them against the compiled PlantWaterer sketch.
- Code comments removed from all Python and C++ code.
- The bambu driver ships, approved by the owner on 2026-10-25.
- M12. The starter library, 33 unverified device files in library/ across 14 drivers, bundled in the wheel as openhal/library_data, with `openhal library list|show|add`. Discovery no longer matches on a USB class or mDNS type alone.
- M13. `openhal init` is a wizard in a terminal and takes safe defaults with `--yes`. It adds found and self-describing devices read-only, makes an agent token and prints or saves the MCP setup for Claude Desktop, Claude Code and Cursor. `openhal service` runs the hub under launchd or systemd. scripts/install-pi.sh installs on a Raspberry Pi. Install to the first agent read takes 9.6 s and 8.5 s (docs/verification/install.md), against a 60 s goal.
- M14 so far. `openhal demo --full` runs discovery, the driver writer on the plant waterer sketch, a scripted limits interview, an agent over MCP drafting a routine a person enables, the routine watering, and a refused 120 s water, all on mocks, recorded in docs/demo/e2e.yaml. The plant waterer was the main example on every page until 2026-10-26. tests/docs/test_commands.py checks every documented command against the CLI and runs the runnable ones on a mock hub, and tests/docs/test_consistency.py checks method names, error codes, traces, terms and conformance tables against ADR 0015, the schema and the code.
- Fixes found on the way. scpi notices a LAN instrument that closed its socket (the Linux CI failure). Home Assistant WebSocket connects wait for the first states. Siglent SPD supplies get their own commands. The LPD8 example has the right USB id. The writer confirms by name, gives the hub the saved path, polls self-described channels at their report interval, and asks for action requirements, run limits and a safe action, so a writer-made plant waterer has the same limits as the hand-written one.
- M15 so far. CONTRIBUTING, CODE_OF_CONDUCT (Contributor Covenant 2.1), SECURITY, docs/ROADMAP.md and docs/LAUNCH.md (drafts, never posted). docs/hardware-tests/README.md orders all 35 plans from lowest hazard to highest with the plant waterer first, and every plan runs from a checkout, confirms limits with `openhal file confirm`, says what to send back on failure and has a report template that earns `verified-on-hardware`.
- Safety fixes from the handoff report. No driver opens a file path from a device file (certificates and the pylabrobot deck come through `ca_env` and `deck_env`, and a test guards it). One daemon per config folder, and an audit chain a second writer can't fork. A run counts from its grant, so a run the hub never finished still counts after a restart. The GPIO stop button in config.yaml is watched, and a configured button the hub can't watch stops it from starting.
- Unit safety. pint no longer converts between angles and plain numbers (50 % to a degree channel, 1 Hz to rpm). Channels with no read-back stay controllable under a rate limit. A bare number gets UNIT_INVALID in dry runs instead of a hub error.
- REST reports conformance, simulated drivers, run limits, requirement reasons, the protocol version and the LAN setting.
- Website round 5, the final critique's 17 findings. Every diagram on the site in the D2 house style, the Python reference grouped with each method's docstring and route, numbered spec sections with glossary links, Docs and Blog in the navigation, one left edge on every template, no text under 13 px, readable Inspector crops, and no green status dots. Every Client method now has a docstring, and the text trace prints `hal/value` as the JSON the hub sends.
- The 3D print babysitter is the main example (scenario-printer, website-6 and inspector-5, merged 2026-10-26). examples/print-babysitter/ has a Klipper printer through Moonraker and its webcam through the http driver, camera reads return the image (ADR 0015, amended), and `openhal demo --record` writes docs/demo/scenario.yaml from it. The landing story tells it in nine steps with the whole diagram in view, the Playground opens on four requests from the story with information marks, and the Inspector shows camera frames, a clear pending cancel and status words with no shapes or boxes. The plant waterer stays the Arduino example. The green and red are dulled everywhere, the diagrams included, and the message log keeps a frame's description instead of its pixels.
- The story resolves (scenario-approval and website-8, merged 2026-10-27). The recorded demo ends with the owner approving the cancel over the hub protocol, the kernel checking every limit again and the printer reading cancelled, and closes on the audit log with 6 requests, 1 refused and 1 confirmed by a person. The landing story lights every station a message passes, shows the read path through the kernel, keeps a two-line caption slot and ends on the audit log. The README, docs, CLI, MCP, Inspector and website copy name the subject and drop every can't and only contrast.
- The hub's own messages follow the owner's copy rules (copy-messages, merged 2026-10-27). Each human-only refusal is one plain sentence such as "Approving a request takes a human principal.", with every code, field and check unchanged, and the Playground mirrors the new words.
- The speed round (website-7, merged 2026-10-27). Pages send 31 to 73 % of their old weight, largest paint on a phone is 147 to 378 ms sooner, blocking time is 0 everywhere and desktop scores 100 on every page. Fonts are subset, inline diagrams carry no fonts and follow the theme in one SVG, the Inspector crops are responsive AVIF and WebP, pages prerender on hover, search snippets skip code, and a budget test guards every template (docs/verification/ui.md).
- Every page except the home page and every repo doc the site renders follow the owner's writing rules (site-copy, merged 2026-10-27).
- The landing story without boxes and the wordmark sequence (website-9, merged 2026-10-27). Scroll brings the wordmark down and walks through H, A and L with a short brief for each part, then the story plays as a sequence diagram with four lifelines, one arrow per request and the webcam's line drawing, and every caption follows the owner's writing rules.
- One header on every page, a collapsible sidebar and the version picker in the header (website-10, merged 2026-10-27). The header and footer use the 1360 px container everywhere, every documentation sidebar hides with a button and slides back in on hover at the left edge, and the spec version picker is a compact menu after GitHub.
- The nozzle cools after the cancel (scenario-cooling, merged 2026-10-27). The Moonraker simulator runs Klipper's CANCEL_PRINT macro, which turns the heaters off, and the record follows the nozzle from 215 °C to 154.65 °C after 30 s and 113.17 °C after 60 s on a deterministic clock.
- The home page's first screen and the owner's review (website-11, merged 2026-10-27). The hero has a small still sequence diagram and the demo's opening row, the first scroll drops both away into the wordmark sequence, the Run the demo block stacks its three commands again, the lifelines run Agent, Owner, OpenHAL hub and Printer with dashed replies, the webcam says what each frame shows, the nine captions are the owner's, the nozzle cools after the cancel and the labels read [hardware] [abstraction] [layer].
- Version numbers (spec-semver, merged 2026-10-28). The specification and the hub protocol use MAJOR.MINOR versions (ADR 0017), the draft is v0.1 in spec/v0.1/, and the hub negotiates "0.1".
- The docs on Astro Starlight (website-12, merged 2026-10-28). Starlight's header, sidebar, outline, search and pickers, themed with the design tokens, with one header on every page, a v0.1 version picker, a theme picker and redirects from the dated addresses. The whole-sidebar hiding is gone, because no maintained plugin offers that.

## Next

- REST decision views should carry the hub-built protocol error so MCP reasons always name the confirmation (protocol report, proposal 12).
- Library matching proposals (library report). New `match` keys for Pi boards and HATs, libcamera models, Alpaca servers, MIDI port names and MQTT topics, so the six library files with no identifier can be matched. Discovery that reports more, with scpi sending `*IDN?`, moonraker browsing `_moonraker._tcp`, homeassistant listing entity ids, modbus scanning unit ids, mqtt listening for announce topics and esphome reporting `mdns`.
- Driver proposals still open. A restore_connection hook, a push path for drivers that receive values, cached-read declarations, per-driver install hints, argument references in action requirements, and YAML 1.1 warnings in openhal file validate.
- Packaging proposals. A `self_describing` flag in DriverInfo. Lazy imports so `openhal mcp` starts faster. Intel Mac installs need `--no-build` while cryptography and zeroconf ship Apple Silicon wheels only.
- Handoff proposals still open. The GRBL simulator stays idle after a hold where real GRBL 1.1 reports Hold:0. The driver scaffold's hardware test template should match docs/hardware-tests/README.md. Expected outputs in the plans quote kernel codes, so they change if the CLI moves to registry names.
- Speed round proposals. A size-adjusted mono fallback in design/tokens.css so pages can drop the mono preload, the header wordmark inlined as SVG, a lighter first story() call, and the service worker for hashed /_astro/ files, which is the owner's call.
- Owner decision. Adding `effects: [extruder_target, bed_target]` to the print babysitter's cancel would let the hub read the 0 °C targets after a cancel, but the change alters the limits hash, so the owner would confirm printer.hal.yaml again (scenario-cooling report).
- Website budgets on documentation pages have under 1 % headroom after the sidebar and the version picker, so the docs rows in budget.spec.ts need a small new baseline at the next change (website-10 report).
- The schema reference page scores 84 on a phone after the move to Starlight, against 99 before, because the page has 4,685 elements and Starlight's outline scans them (website-12 report). Splitting the generated schema reference into one page per part, or a lighter outline for that page, would fix it.
- At 1024 px the home page's small diagram has its lifeline names cut off under the step row (website-12 report).
- A kernel parity case that tries approve, reject and unlock as an agent and records each message, so the Playground's three permission messages are checked against the hub (copy-messages report).
- Inspector proposals (inspector-5 report). Fold dashboard/e2e/print_hub.py into tests/inspector so the ruff and mypy gates cover it. A camera to device link in the Device File (`watches: [printer]`), so Confirmations shows the right camera without the picker. A read of the cached latest frame without a new snapshot. RFC 3339 times in /v1/confirmations instead of monotonic ones. `img-src 'self' data:` in any future Content-Security-Policy.
- Owner decisions. Whether `openhal init` keeps the plant waterer as its sample, which the Python SDK snippet follows. Whether an action whose approval can't hurt, like cancel on a paused printer, gets a confirmation window long enough to wake up to, since the reference expiry is 5 minutes and the hub allows at most an hour.
- Verification and handoff, in progress. Lighthouse, axe and the orphan audit, the final critique, and FINAL-REPORT.md.

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
