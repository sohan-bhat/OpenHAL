# Brief: docs check and consistency (M14)

Read docs/agents/COMMON.md first. Then read docs/demo/scenario.yaml, examples/plant-waterer/, docs/adr/0015-openhal-hub-protocol.md, docs/adr/0016-one-value-format.md, spec/2026-10-24/schema.json, the README and tests/docs/.

## Goal

Every command in the docs runs as written, and every page agrees with the scenario file and the schema.

1. **The plant waterer replaces the desk fan everywhere** except spec/examples/, where the desk fan stays as a secondary example, and except printer `fan_speed` channels, which are a real printer part. Pages and code that still use the desk fan include spec/2026-10-24/ (architecture, schema, safety, security, device-files, basic/messages), spec/FIRMWARE-PROTOCOL.md, docs/ARCHITECTURE.md, docs/DESIGN.md (examples only), docs/guide/conformance.md, docs/interfaces/CLI.md and PYTHON.md, docs/drivers/openhal-firmware.md and docs/hardware-tests/openhal-firmware.md, the docstrings and help text in openhal/client/, openhal/mcp/ (tools and prompts), openhal/protocol/ (messages, errors, convert), openhal/routines/ (models and engine), openhal/writer/interview.py and openhal/cli/control_cmd.py, and the Arduino library README. Examples in ADRs change too, their decisions don't. Find the rest with grep. Values come from docs/demo/scenario.yaml and examples/plant-waterer/mock/plant-waterer.hal.yaml, in the one value format.
2. **Docs check.** tests/docs/test_commands.py extracts every `openhal ...` command from README.md, docs/ and spec/ code blocks, and runs each one that can run against the mock setup (a temp home, a hub on loopback with the simulated plant waterer) and checks it exits as the page implies. Commands that need real hardware or change the system (service install, the Pi script) are listed in the test with the reason they are skipped. Fix the pages, or the CLI when the page is right and the CLI is wrong.
3. **Consistency check.** A test that method names in docs match ADR 0015 and the schema, error codes match the registry, demo values (31 %, 46 %, 30 s, 120 s, 3 runs per 1 h and the messages) match docs/demo/scenario.yaml, and glossary terms are spelled one way. Extend tests/docs/test_scenario_docs.py and tests/docs/test_value_format.py where that fits.

## Files you own

spec/ except spec/examples/ and spec/2026-10-24/routines.md, docs/ except docs/agents/, docs/adr/ decisions, docs/hardware-tests/ other than openhal-firmware.md, docs/demo/, docs/guide/library.md, docs/guide/install.md, docs/guide/quickstart.md, docs/verification/ and docs/ROADMAP.md and LAUNCH.md. Also docstrings, help text and messages in openhal/ (not logic, unless a documented command is wrong), firmware/arduino/OpenHAL/README.md and tests/docs/.

## Not yours

README.md (report needed changes), website/, dashboard/, the kernel's logic, spec/examples/ and the files other agents own. Other agents are writing docs/guide/library.md, docs/guide/install.md, docs/hardware-tests/ and the demo section of docs/guide/quickstart.md in parallel, so leave those to them. Tests and fixtures that use the desk fan can stay.
