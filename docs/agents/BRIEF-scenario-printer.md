# Brief: the 3D print babysitter becomes the canonical scenario

Read docs/agents/COMMON.md first, then the "Canonical demo scenario" section of docs/DESIGN.md, which is the contract for this work, and openhal/demo/ with its tests.

## What the owner said

"Instead of a basic watering plant example use a more complex example. Like I can use Arduino IoT to water the plant as well without an agent. Do a task only an agent can do." The owner chose the 3D print babysitter. Someone starts a long print and asks an agent to keep an eye on it. The agent watches the camera, judges what is going wrong and acts, and the safety kernel keeps it inside the limits a person confirmed.

## Goal

1. **The example.** Add examples/print-babysitter/ with a README and two device files.
   - `printer.hal.yaml`, a Klipper printer reached through Moonraker (start from openhal/drivers/moonraker/examples/voron-2-4.hal.yaml). Readings `state`, `extruder_temp`, `bed_temp`, `progress`. `extruder_target` limited to 260 °C and `bed_target` to 110 °C, both with `max_change_per_s`. Actions `pause`, `resume` and `cancel`, with cancel waiting for a person. A safe state, a watchdog, hazard medium, confirmed by owner at 2026-10-24.
   - `printer-cam.hal.yaml`, a USB camera watching the bed (uvc), read-only.
   - Feed the camera simulator two frames for the story, the first layer with a lifted corner, then the print come loose. Draw them as plain line drawings in the house style (docs/DESIGN.md), never as fake photos, and say in the example's README that they are demo frames.
2. **The demo.** `openhal demo` runs the story against a real hub on a loopback port with the Moonraker and uvc simulators, connected as an agent over `/rpc`, exactly as the plant waterer demo does now. `openhal demo --record docs/demo/scenario.yaml` writes the record. The story is in DESIGN.md: read a camera frame, `bed_target` 60 °C to 70 °C done, `extruder_target` 300 °C gets LIMIT_EXCEEDED, the print comes loose, `pause` done, `cancel` pending until a person decides. Every number in the record comes from what the hub answered. Two runs give the same file.
3. **The plant waterer moves aside.** Keep examples/plant-waterer/ and everything that runs it. It stays the Arduino example and drives `openhal demo --full` (docs/demo/e2e.yaml), the driver writer tutorial and the first hardware test. If the plant waterer demo needs its own record to keep working, move it under docs/demo/ with a clear name rather than deleting it.
4. **Every surface that shows the main example.** The README (hero sentence under the trace, the generated trace, the quickstart output), docs/QUICKSTART.md, docs/guide, docs/interfaces, the informative examples in spec/2026-10-24 (never change normative text), the CLI help and demo output, the MCP prompts and tool descriptions, and the docstring examples in openhal/client and openhal/protocol. Use the printer wherever the plant waterer stood in as "the example". Keep it where the text is about Arduino, firmware or the driver writer.
5. **The trace.** openhal/demo/trace.py renders the new exchanges, including the image read (show what the hub sends, never the image bytes) and the pending result with its `requestId`. The README trace may show only the kernel moments if all five exchanges make it too long. Narration stays in `#` comment lines.
6. **The flow diagram.** docs/diagrams/flow.d2 and scripts/diagrams.py, rebuilt with scripts/build-diagrams. AI client, OpenHAL hub, Safety kernel, Driver, 3D printer, with the blocked branch showing the 300 °C refusal. The README hero keeps using these files.
7. **Tests.** tests/docs/test_scenario_docs.py, tests/docs/test_consistency.py, tests/demo and any other test that pins the old story follow the new one. Keep the property that every surface matches docs/demo/scenario.yaml. Regenerate website/tests/kernel-parity/expected.json (`uv run python -m tests.website.kernel_parity`) and website/src/content/generated/python-api.json (`uv run python -m tests.website.python_api`) when your changes move them. Those two generated files are the only website/ paths you write.

## Signal early

As soon as the new device files and docs/demo/scenario.yaml are committed on your branch, send a message to `main` with the commit hash and a short description of the record's shape, then keep going. The website and Inspector rounds start from that commit.

## Gates

COMMON.md's gates. Also run `uv run openhal demo` and `uv run openhal demo --full` and read their output as a person would. The website build will break where it reads the old scenario. That is expected, since the website round fixes it, so name the failing website tests in your report instead of editing website/.

## Files you own

openhal/ (demo, CLI, MCP, client, protocol docstrings and examples), examples/print-babysitter/ (new), docs/demo/, docs/ except docs/DESIGN.md, docs/agents/ and docs/verification/ui.md, spec/2026-10-24 informative examples, README.md, docs/diagrams/flow.d2, scripts/diagrams.py, and tests/ except tests/website/kernel_parity.py.

## Not yours

website/ (except the two generated files above), dashboard/, docs/DESIGN.md (propose changes), the kernel's behavior and every safety rule.
