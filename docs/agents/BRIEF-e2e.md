# Brief: the end-to-end demo (M14)

Read docs/agents/COMMON.md first. Then read openhal/demo/ (the three-exchange `openhal demo`), openhal/cli/demo_cmd.py, docs/demo/scenario.yaml, examples/plant-waterer/, openhal/drivers/openhal_firmware/ (driver, simulator, discovery), openhal/writer/ and `openhal writer`, openhal/mcp/, openhal/routines/ and spec/2026-10-24/routines.md.

## Goal

One command runs the whole system on mocks, end to end, and records what happened.

`openhal demo --full` does this against a real hub on loopback in a temporary home, with nothing touching hardware.

1. Discovery finds the simulated plant waterer board as an openhal-firmware device. If the driver can't discover a simulated board today, add a general way for it to (for example a port list it scans), never a demo-only shortcut in the safety path.
2. The driver writer runs on examples/plant-waterer/plant-waterer.ino, even if the device library also matches the board.
3. A scripted limits interview answers as the human and confirms the limits through the same flow a person uses.
4. A real MCP client session over stdio (`openhal mcp` with an agent token) reads soil moisture, then drafts a routine that waters when soil moisture is below 40 %. The human side enables it through the human token. The routine runs on the simulated board and soil moisture rises.
5. The agent asks for `water` with duration 120 s and gets LIMIT_EXCEEDED, and nothing reaches the board.
6. `--record PATH` writes each step as YAML. Commit the result as docs/demo/e2e.yaml.

The values must agree with docs/demo/scenario.yaml wherever they overlap (the 30 s limit, the 120 s request, the error message and the device file name). docs/demo/scenario.yaml stays the three-exchange record the README uses. Don't change it or the plain `openhal demo`.

## Tests

tests/demo/test_e2e.py runs the full demo at simulator speed and checks every step, the agreement with scenario.yaml, and that the committed e2e.yaml matches a fresh run in every field that doesn't depend on time.

## Docs

Replace the desk fan routine in spec/2026-10-24/routines.md with the routine this demo uses, in the one value format. Add a short section on `openhal demo --full` to docs/guide/quickstart.md.

## Files you own

openhal/demo/ (new modules, plus small changes to scenario.py), openhal/cli/demo_cmd.py, tests/demo/, docs/demo/e2e.yaml, spec/2026-10-24/routines.md, the demo section of docs/guide/quickstart.md, and openhal/drivers/openhal_firmware/ only for discovery of simulated boards.

## Not yours

The kernel, the protocol, the MCP tools and the routine engine. If one of them stops the demo, propose the change in your report and work around it only outside the safety path.
