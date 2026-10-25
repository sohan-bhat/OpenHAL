# Final report

OpenHAL v0.1, built 2026-10-24 and 2026-10-25 from the autonomous build prompt (milestones M0 to M15). Everything ran on mocks and simulators. Nothing was sent to real hardware.

## What was built, against the v0.1 scope

The research brief (docs/research/OPENHAL_RESEARCH.md, First version) set this scope. Each line says what shipped.

| v0.1 scope | What shipped |
|---|---|
| Mac and Raspberry Pi | Tests on macOS here and on Linux in GitHub CI, launchd and systemd user services (`openhal service`), and scripts/install-pi.sh for Raspberry Pi OS |
| Arduino over serial | The OpenHAL Arduino library (compiled for Uno and ESP32), the firmware protocol with self-description and actions, and the openhal-firmware, firmata and serial drivers |
| Bench instruments | The scpi driver with family proposals from `*IDN?`, plus modbus |
| Klipper printers | moonraker, plus marlin, octoprint, grbl and bambu |
| Home Assistant | homeassistant, plus esphome, mqtt, matter, zigbee-zwave, knx and upnp |
| Raspberry Pi pins and camera | rpi-gpio, rpi-camera and pi-i2c-spi, and the GPIO stop button |
| Spec v0.1 | The dated specification 2026-10-24 (spec/2026-10-24/) with the device file format, the JSON-RPC hub protocol (ADR 0015), one value format (ADR 0016), the error registry, conformance levels and the generated schema |
| The hub with limits, stop, log | The safety kernel (range, rate, run limits, requirements, interlocks, watchdog rules, confirmations, grants), stop and unlock, the hash-chained audit log, dry runs and routines |
| MCP, command line and Python | The MCP server, the `openhal` CLI and the sync and async Python client |
| Driver writer for sketches and instruments | Sketch, manual and self-description drafts, the limits interview (now with requirements, run limits and a safe action) and staged test plans |
| About 20 starter device files | 33 in library/, across 14 drivers, all unverified with suggested limits |

Beyond the scope, there are 34 drivers plus the mock reference driver, the protocol website, the OpenHAL Inspector, `openhal demo` and `openhal demo --full`, the `openhal init` wizard and a hardware test plan for every driver.

## Driver coverage

34 drivers and the mock reference driver (35 entries in the catalog), every one implemented and passing the conformance suite at its declared level on a simulator or fake that speaks the real protocol.

| Tier | Drivers |
|---|---|
| 0 | mock (the reference driver) |
| 1 | 18. openhal-firmware, firmata, serial, scpi, moonraker, marlin, octoprint, homeassistant, esphome, mqtt, modbus, rpi-gpio, rpi-camera, uvc, ble, midi, hid, http |
| 2 | 9. onvif, grbl, alpaca, indi, ros2, opcua, sila2, pylabrobot, lerobot |
| 3 | 7. bambu, can, knx, matter, pi-i2c-spi, upnp, zigbee-zwave |

| Conformance level | Drivers |
|---|---|
| Full (actions inside and outside limits, no action without a grant) | 15 |
| Control | 18, including mock |
| Core (read only) | 2, rpi-camera and uvc |

drivers/catalog.json is the source, and the README and the website render it.

## Tests and checks

| Check | Result on main, 2026-10-25 |
|---|---|
| Python tests | 3218 passed, 1 skipped (the shellcheck run, since shellcheck isn't installed here) |
| Lint and types | `ruff check`, `ruff format --check` and `mypy openhal` are clean |
| Safety kernel coverage | 100 % of lines but two and 99 % of branches. The four branches left are fail-closed guards the public API can't reach |
| Conformance | Every driver passes at its declared level. openhal-firmware also runs the Full checks against the compiled PlantWaterer sketch |
| Independent safety review | 22 findings (docs/agents/REVIEW-safety.md), all fixed with a regression test each in tests/review_safety/ |
| Red team | 100 tests in tests/redteam/. Four findings, RT-01 to RT-04, all fixed (docs/SAFETY-REPORT.md) |
| End to end | `openhal demo --full` runs discovery, the driver writer, a scripted limits interview, an agent over MCP, a routine a person enables, and a refused 120 s watering, recorded in docs/demo/e2e.yaml |
| Docs check | tests/docs/test_commands.py checks every documented command against the CLI and runs the runnable ones on a mock hub |
| Consistency check | tests/docs/test_consistency.py and test_scenario_docs.py check method names, error codes, traces, terms and demo values against ADR 0015, the schema and docs/demo/scenario.yaml |
| Install time | 9.6 s and 8.5 s from install to the first agent read of a self-describing board, against a 60 s goal (docs/verification/install.md) |

Safety fixes made during verification, each with a test.

- No driver opens a file path a device file names. Certificates and the pylabrobot deck come from environment variables, and a test guards every driver.
- One daemon per config folder, and an audit chain a second writer can't fork.
- A run counts from its grant, so a hub killed mid-command can't reset a run limit.
- The GPIO stop button in config.yaml is watched, and a configured button the hub can't watch stops it from starting.
- scpi notices a LAN instrument that closed its socket instead of reconnecting silently (the Linux CI failure).
- Home Assistant WebSocket connects wait for the first states, so a read right after connect can't find an empty cache.

## Website and Inspector

PENDING. Filled in when the quality workstream (Lighthouse, axe, the orphan audit) and the fresh critic hand back.

Known before that. The website builds 93 pages with zero warnings, and the Inspector builds clean. Both have unit tests and Playwright tests in Chromium and Firefox with axe in both themes. WebKit page loads stall on this Mac, so WebKit is item 2 in NEEDS_HUMAN.md.

## Subagent log

18 subagents ran, every one on Opus 5.5, each in its own git worktree with a brief in docs/agents/.

| Workstream | What it did |
|---|---|
| Independent kernel safety review | Tried to break the kernel from the code, SAFETY.md and THREAT_MODEL.md only. 22 findings |
| Interfaces | The MCP server, CLI and Python client |
| Drivers batch 1 and batch 2 | The 18 Tier 1 drivers |
| Website design review, round 1 | A fresh critique from screenshots and DESIGN.md |
| Specification | The dated specification 2026-10-24 |
| Protocol | The JSON-RPC hub protocol over WebSocket and stdio |
| Red team | The 100-test attack suite and SAFETY-REPORT.md |
| Drivers batch 3 and batch 4 | The 16 Tier 2 and Tier 3 drivers |
| Website | The protocol website, three design rounds |
| Inspector | The OpenHAL Inspector, three design rounds |
| Library | The 33-file starter library and `openhal library` |
| Packaging | The init wizard, services, the Pi script and install timing |
| End to end | `openhal demo --full` |
| Consistency | The plant waterer on every page, the docs check and the consistency check |
| Handoff | CONTRIBUTING, CODE_OF_CONDUCT, SECURITY, ROADMAP, LAUNCH and the hardware test plans |
| Quality | Lighthouse, axe and the orphan audit |

No workstream was cut for usage limits. Two were paused when the owner lowered the cap from 5 to 3 on 2026-10-25 (handoff with 11 commits saved, quality before it changed anything), and both were resumed and finished.

## Tooling

Installed and recorded in docs/TOOLING.md. The frontend-design, playwright, context7, chrome-devtools-mcp and typescript-lsp plugins, the d2-diagrams skill, the D2 CLI v0.9.0, SVGO 4.1.0, fonttools 4.67.0, the Playwright browsers and uv 0.13.5. The Arduino library was compiled with arduino-cli 1.1.1 for the AVR and ESP32 cores (firmware/arduino/OpenHAL/README.md). arduino-cli isn't on this machine's PATH now, so later sketch changes were checked with the host build in firmware/arduino/OpenHAL/extras/host, which compiles the real C++ and runs conformance against it.

Not used or not working. The draw.io plugin and Mermaid CLI weren't needed, since D2's grid layout gave a clean diagram. WebKit doesn't load pages on this Mac. shellcheck isn't installed, so the Pi script was checked with `bash -n` and a shellcheck run through `uvx --from shellcheck-py`.

## Known limitations and risks

- Every driver passes against a simulator built from the protocol documentation, which can share a misreading with the driver.
- Drivers run in the hub's process. A malicious driver could reach anything in it (THREAT_MODEL T17). The grant check guards against accidents, not malice.
- The MHS specification isn't public, so spec/MHS-MAPPING.md is built from the announcement and press coverage.
- Some library identifiers rest on community evidence (the Akai LPD8 USB id, the Siglent SDM3045X id, the Polar H10 name prefix), and six library files have no identifier their driver can report yet.
- The Raspberry Pi script and the Pi drivers have never run on a Pi.
- On an Intel Mac with an empty cache, installing needs `--no-build`, because cryptography and zeroconf ship Apple Silicon wheels only.
- The CLI prints kernel codes (`blocked above_max`) where the protocol uses registry names (LIMIT_EXCEEDED). Both are documented, but a person sees two vocabularies.

## Every NEEDS_HUMAN.md item, in order

1. Run the first hardware test, the plant waterer.
2. Run the WebKit browser tests on another machine.
3. Decide the PyPI distribution name (`openhal-hub` until then).
4. Check and buy a domain, then point the Pages site at it.

## The first hardware test

The Arduino plant waterer, following examples/plant-waterer/TEST-PLAN.md. It is the cheapest complete rig and runs the whole path, and the pump stays unplugged from its supply until step 11.

1. Wire an Arduino Uno with a capacitive soil sensor on A0, a float switch from pin 4 to GND and a 5 V relay module on pin 7. The pump's power goes through the relay contacts, never through the Arduino.
2. Flash examples/plant-waterer/plant-waterer.ino with the arduino-cli commands in the plan.
3. Read-only steps 1 to 5. The port is listed, discovery finds the board, the file loads read-only, and the soil and tank readings move when you wet the sensor and lift the float.
4. Steps 6 to 10 with the pump unplugged. Confirm the limits with `openhal file confirm`, then check that 120 s is refused with LIMIT_EXCEEDED, that an empty tank is refused with INTERLOCK_BLOCKED, that a 2 s run clicks the relay on and off, and that the relay falls off on its own within 3 s when the hub is killed.
5. Steps 11 to 13 with the pump plugged in. A real 5 s watering, the fourth run in an hour refused with RATE_LIMITED, a stop, and `openhal log --verify`.
6. Fill in the report template and save it in docs/hardware-tests/reports/.

## Ten decisions to double-check

1. ADR 0002. The distribution is `openhal-hub` because `openhal` is taken on PyPI. NEEDS_HUMAN item 3.
2. ADR 0003. Drivers run in the hub's process, with the residual risk above.
3. ADR 0004. Every hardware change goes through a single-use kernel grant for that exact device, target and value.
4. ADR 0015. The hub protocol is JSON-RPC 2.0 with dated spec versions, positioned as an open protocol and not affiliated with Anthropic or MHS.
5. ADR 0016. Values travel as a number and a unit apart on the wire, while device files and routines keep quantity strings like `30 s`.
6. A person's own command counts as their confirmation. Agents need `control_medium` to ask for high hazard commands, which always wait for a person.
7. The plant waterer's mock file ships confirmed by sohan so the demo can water. The real board's file and every copy `openhal init` makes are unconfirmed.
8. A dangling reference to an unregistered device blocks every command on that device until it is fixed (review finding F17). It is strict and will surprise people during setup.
9. LGPL dependencies (zeroconf, python-can) are used unmodified. No code is copied from copyleft projects.
10. The bambu driver ships after the owner's review of Bambu Lab's terms. It stays LAN only and never contacts Bambu Cloud.

## With one more week

- Move drivers out of process, one subprocess per driver with only its grants over a pipe, which closes T17.
- Run the plant waterer, an SCPI supply, a Klipper printer and a Home Assistant plug on real hardware and mark them `verified-on-hardware`.
- A push path for drivers whose devices send values, so streamed channels never need polling.
- Use registry names in CLI output, so a person and an agent see the same words.
- MHS import and export the day the MHS specification is public.
- Windows support, starting with serial and the service.
- A hosted device library with verified badges and reports.
