# Brief: the nozzle cools after the cancel

Read docs/agents/COMMON.md first, then the "Canonical demo scenario" section of docs/DESIGN.md, openhal/demo/ and the Moonraker simulator in openhal/drivers/moonraker/ with their tests.

## What the owner asked

The landing story's last steps show the printer's nozzle at 215 °C after the owner approves the cancel. The owner wants the nozzle shown cooling after the cancel instead.

## Goal

1. **The simulator.** Make the Moonraker simulator handle a cancel the way a common Klipper setup does, where the CANCEL_PRINT macro that Mainsail and Fluidd ship runs TURN_OFF_HEATERS. The extruder and bed targets go to 0, and the temperatures fall toward the simulator's ambient temperature at a plausible rate. The fall follows a deterministic clock in the recorded run, so two recordings still give the same file. A pause keeps the heaters as they are, as before.
2. **The record.** `uv run openhal demo --record docs/demo/scenario.yaml` shows the cooling with values the hub reads from the simulator, never typed by hand. For example, the printer view after owner-approves has an extruder target of 0 °C, and a later reading or view shows the nozzle temperature below 215 °C and falling. Keep the record's existing shape and add only what the cooling needs, so the website can wire the values with small changes. Describe any new key in your report.
3. **Everything that pins the old values follows.** That covers tests/demo, tests/docs/test_scenario_docs.py, the Moonraker driver's tests and conformance checks that use the simulator, the README and QUICKSTART blocks that `uv run python -m openhal.demo.readme` generates, and website/tests/kernel-parity/expected.json (`uv run python -m tests.website.kernel_parity`) if the change moves it.

## Signal early

As soon as the new record is committed, send `main` the commit hash and the new values and keys, then keep going. A website round wires the story to them.

## Gates

COMMON.md's gates, plus `uv run openhal demo` and `uv run openhal demo --full`, read as a person would read them, and two recordings compared with `cmp`.

## Files you own

The simulator in openhal/drivers/moonraker/ (the simulator only, never the driver's behavior), openhal/demo/, docs/demo/, the tests named above, the generated README and QUICKSTART blocks and website/tests/kernel-parity/expected.json.

## Not yours

The Moonraker driver itself, the kernel, the hub, website/ except the parity file, dashboard/, docs/DESIGN.md and every safety rule.
