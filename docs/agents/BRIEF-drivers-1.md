# Brief: drivers batch 1 (Tier 1, first half)

## Goal

Implement these Tier 1 drivers to the contract in docs/drivers/WRITING-A-DRIVER.md, each fully tested against a mock or protocol simulator, passing the conformance suite.

1. `serial`. Generic line-based serial protocols, configured entirely by the device file (each channel's `map` gives the query and parse rule, each write's `map` gives a command template). pyserial. Simulate with a pty pair or pyserial's loop:// URL.
2. `firmata`. Arduino-compatible boards running StandardFirmata (digital and analog reads, digital writes, PWM, servo). Write your own small Firmata client if the available libraries are unmaintained, and record why.
3. `scpi`. Bench instruments over VISA (PyVISA with pyvisa-py, USB-TMC, LAN, serial). Identification with `*IDN?`. Channel `map` gives query and set templates. describe() proposes channels for common instrument classes from the IDN string where it can. Test with pyvisa-sim.
4. `moonraker`. Klipper printers through the Moonraker API (HTTP and WebSocket JSON-RPC). Reads from printer objects (heaters, temperature sensors, fans, print state), writes heater targets and fan speed through G-code commands, actions for home, pause, resume and cancel. describe() builds channels from `printer.objects.list`. Medium hazard default.
5. `octoprint`. OctoPrint REST API. Same channel set where the API allows it. API key by environment variable.
6. `marlin`. Marlin firmware over USB serial. Line protocol with `ok` handshakes, temperature reports from M105 and auto-report, M104 and M140 targets, M106 fan, G28 home, M112 is never sent by default (it needs a firmware reset). Native safe state turns heaters off (M104 S0, M140 S0). Medium hazard default.
7. `homeassistant`. Bridge over the Home Assistant REST and WebSocket APIs. Exposes only entities named in the device file. Maps lights, switches, fans, numbers, selects, sensors and binary sensors to channels. describe() lists the selected entities with units. Token by environment variable. The device file's limits always apply.
8. `esphome`. ESPHome native API through aioesphomeapi. describe() maps entities (sensors, binary sensors, switches, lights, fans, numbers, selects, buttons) into channels and actions.

Also write a minimal, real SCPI and Moonraker simulator if no library simulator is good enough. Simulators live in each driver's `simulator.py` and are reused by tests and conformance.

## Definition of done, for each driver

- The package layout, rules and docs page in docs/drivers/WRITING-A-DRIVER.md.
- Tests for normal operation, disconnects, timeouts, malformed responses and every error path, in tests/drivers/<name>/.
- `conformance.py` with a case that passes `tests/conformance/test_conformance.py` (it discovers your driver automatically).
- At least one example device file in the package's examples/ that validates with `uv run openhal file validate`.
- docs/drivers/<name>.md and docs/hardware-tests/<name>.md (read-only steps first, then the smallest safe writes, each with exact commands, expected output and a report template).
- A `catalog.json` entry with the device estimate and its reasoning and sources.
- Optional dependencies added as a pyproject extra named after the driver. Record each new dependency, version and license in your report so the orchestrator can add it to docs/DEPENDENCIES.md. Prefer permissive licenses. Check each library's current version, license and maintenance status first.
- Protocol knowledge comes from official docs and specs. Never copy code from copyleft projects (Kiln is AGPL-3.0). List the sources you used in each docs page.

## Files you own

- openhal/drivers/serial/, firmata/, scpi/, moonraker/, octoprint/, marlin/, homeassistant/, esphome/
- tests/drivers/serial/ and so on for each driver
- docs/drivers/<name>.md and docs/hardware-tests/<name>.md for each driver
- pyproject.toml, only to add the optional extras for your drivers and their test dependencies (the orchestrator resolves merge conflicts)

## Contracts (read first, don't change)

docs/drivers/WRITING-A-DRIVER.md, openhal/drivers/base.py, openhal/drivers/mock/ (the reference driver and conformance case), openhal/conformance/suite.py, spec/SPEC.md, openhal/spec/models.py, docs/SAFETY.md, docs/adr/0004 and 0013.

## What you must not do

- Never send a write or action to real hardware. Everything runs against mocks and simulators.
- Don't edit files outside the paths you own. If you need a contract change, propose it in your report.
- Don't push, publish packages or post anything. Don't start subagents.
- Don't weaken a safety rule. Drivers never decide whether a change is safe and never confirm limits.

## Working setup

You work in your own git worktree on your own branch. Run `export PATH="$HOME/Library/Python/3.13/bin:$PATH"` then `uv sync --all-extras`, then `uv run pytest`, `uv run ruff check openhal tests`, `uv run ruff format openhal tests` and `uv run mypy openhal`. All must pass before you finish. Commit on your branch in small logical commits of roughly 50 to 450 lines, one driver at a time, with conventional commit messages, authored by the existing global git identity. Never set git config, never pass --author, and add no trailers of any kind.

Copy in docs. Plain, precise, a little dry. No em dashes or en dashes, and no colons or semicolons in running prose (headings, labels, tables and code are fine). No exclamation marks.

## Report

Write docs/agents/REPORT-drivers-1.md. Files changed, tests added, conformance results per driver, dependencies with versions and licenses, open issues, decisions made, contract change proposals.
