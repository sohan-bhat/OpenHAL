# Brief: drivers batch 2 (Tier 1, second half)

## Goal

Implement these Tier 1 drivers to the contract in docs/drivers/WRITING-A-DRIVER.md, each fully tested against a mock or protocol simulator, passing the conformance suite.

1. `rpi-gpio`. Raspberry Pi GPIO through gpiozero (digital out, digital in, PWM, servo), with pins named in the device file. Tests use gpiozero's mock pin factory. Also expose a stop-button helper the hub can use to call stop on a GPIO input, a function `watch_stop_button(pin, on_press)` in the package, documented but not wired into the hub (the orchestrator wires it).
2. `rpi-camera`. Raspberry Pi camera modules through picamera2, read-only `image` channels (JPEG bytes). picamera2 isn't installable on macOS, so import it lazily, test against a fake that implements the calls you use, and record what a human must test on a Pi.
3. `mqtt`. paho-mqtt. Channel `map` gives a state topic, a command topic and a payload format (raw number, JSON path, on and off words). Retained values seed reads. Test with an in-process broker if a permissively licensed one exists (check amqtt), otherwise a fake transport.
4. `modbus`. pymodbus, RTU and TCP. Channel `map` gives register, kind (coil, discrete, holding, input), format (uint16, int16, uint32, int32, float32, with word order) and scale. Test with pymodbus's own server simulator.
5. `ble`. bleak. GATT characteristics with format and scale in `map`, notifications for `stream` channels, writes to writable characteristics. describe() maps standard GATT services where the UUID is known (Environmental Sensing, Battery). Test with a fake BleakClient.
6. `midi`. mido with python-rtmidi. Read CC and note values as streams, write notes and CCs for LEDs and parameters. Test with mido's virtual ports or a fake backend.
7. `hid`. hidapi. Report format described in `map` (report id, byte offsets, bit masks). Test with a fake device object.
8. `uvc`. OpenCV (opencv-python-headless) read-only frame capture as JPEG bytes. Test with a fake VideoCapture.
9. `http`. httpx. Endpoints described in the device file (method, path, JSON path for reads, body template for writes), or generated from an OpenAPI document by describe(). Test with httpx.MockTransport.

Write a small simulator where no library simulator is good enough. Simulators live in each driver's `simulator.py` and are reused by tests and conformance.

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

- openhal/drivers/rpi_gpio/, rpi_camera/, mqtt/, modbus/, ble/, midi/, hid/, uvc/, http/ (package directories use underscores, NAME uses the hyphenated driver name, for example NAME = "rpi-gpio")
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

Write docs/agents/REPORT-drivers-2.md. Files changed, tests added, conformance results per driver, dependencies with versions and licenses, open issues, decisions made, contract change proposals.
