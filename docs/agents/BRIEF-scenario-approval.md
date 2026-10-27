# Brief: the print babysitter story ends with the owner's approval

Read docs/agents/COMMON.md first, then docs/DESIGN.md ("Canonical demo scenario", which now has step 6, and "Copy voice"), openhal/demo/ with its tests, and BRIEF-scenario-printer.md for how the record works.

## What the owner asked

The landing story stops at a pending cancel, so the story never resolves. The owner wants these changes.
- The owner approves the cancel. The hub shows the approval, the kernel's confirmation check passes, the grant flows to the driver, and the printer's state becomes cancelled.
- The last step shows the last few audit log lines (6 requests, 1 refused, 1 confirmed by a person), as the hub's audit log holds them.
- The 300 °C nozzle step gets a "#" reason line like every other step, for example "# a hotter nozzle might help the corner stick".
- The printer panel shows the nozzle, so the 260 °C limit has something to protect.
- New copy rules (DESIGN.md, Copy voice). Name the subject instead of writing "it" or "them". Never write a contrast like "An agent can't loosen them. Only a person editing the device file can." No vague wrap-ups like "That fixes it."

## Goal

1. **The record.** `uv run openhal demo --record docs/demo/scenario.yaml` adds these after the pending cancel, every value taken from what the hub answered.
   - A human principal labeled owner approves the request the way a person would, over the hub's real protocol with the human token. Record the approval exchange, the kernel's second check, the grant, the action's result and the printer's state afterwards from the Moonraker simulator (Klipper reports `cancelled`).
   - Narration for every exchange, including the nozzle's reason line.
   - The printer's nozzle temperature and target at each moment the story shows the printer.
   - The audit log at the end, with the counts (requests, refused, confirmed by a person) and the last few lines exactly as `openhal audit` prints them, read from the hub.
   - What the kernel does for a read. The kernel checks the channel and the device, needs no grant and logs the read. Record this in a shape the website can show.
   Two runs give the same file. Keep the five minute expiry. The approval happens during the run, well inside the window, so no copy may say the person approves in the morning or after waking up.
2. **Every surface that tells the story follows the record.** The README trace and the sentence under it (show the approval if the trace stays short), docs/QUICKSTART.md, docs/guide, the CLI demo output and the MCP prompts. The plant waterer stays the Arduino example.
3. **Copy rules in the files you own.** Rewrite every "X can't do this. Only Y can." contrast and every vague "it", "them" or "that" whose noun isn't in the same sentence. Find them with `git grep -n -i "only a person\|only a human\|only you"` and by reading. Leave normative spec text, protocol error messages, kernel messages and error codes as they are. List the kernel and protocol messages that use "Only a human can" in your report for a later round, because the website's Playground kernel mirrors them.
4. **Tests.** tests/docs/test_scenario_docs.py, tests/demo and every test that pins the story follow the new record. Regenerate website/tests/kernel-parity/expected.json (`uv run python -m tests.website.kernel_parity`) and website/src/content/generated/python-api.json (`uv run python -m tests.website.python_api`) if your changes move them.

## Signal early

As soon as the new record is committed, send `main` the commit hash and the record's new shape, with the keys and one example of each new item. Then keep going. The website round wires the story to that commit.

## Gates

COMMON.md's gates, plus `uv run openhal demo` and `uv run openhal demo --full`, read as a person would read them.

## Files you own

openhal/demo/, the help and output text in openhal/cli/, the prompts and tool descriptions in openhal/mcp/, docs/demo/, README.md, docs/ except docs/DESIGN.md, docs/agents/ and docs/verification/ui.md, examples/print-babysitter/README.md, tests/ except tests/website/kernel_parity.py, and the two generated website files named above.

## Not yours

website/ (except the two generated files), dashboard/, the kernel's and hub's behavior, normative spec text and every safety rule.
