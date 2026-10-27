# Brief: the hub's own messages follow the owner's copy rules

Read docs/agents/COMMON.md first, then the "Copy voice" section of docs/DESIGN.md.

## What the owner said

"Stop saying 'That fixes it.' or 'An agent can't loosen them.' Be specific, don't say them or it unless really necessary. Also never use the format 'XYZ can't do this. Only this can'."

The README, docs, CLI help, MCP prompts, Inspector and website copy already follow these rules. The messages the hub itself returns still say "Only a human can approve a request." and similar, and the website's Playground repeats them word for word.

## Goal

1. **Messages.** Rewrite each human-facing message below into one plain sentence that names who does what, for example "Approving a request takes a human principal." or "Lifting a stop takes a human principal." Keep every error code, error name, data field and check exactly as it is. Only the words change.
   - openhal/kernel/kernel.py, the four "Only a human can ..." messages (about lines 612, 986, 1040 and 1282).
   - openhal/protocol/dispatch.py (about line 201) and openhal/protocol/errors.py (about line 202).
   - openhal/hub/api.py (about line 205), "Only a human can do this."
   - openhal/routines/engine.py (about lines 394, 396, 401, 425 and 493).
   - openhal/writer/engine.py (about lines 335 and 382, and the docstrings near lines 12 and 57) and openhal/writer/interview.py (near line 6). Line 335 also says "An AI can suggest", so say agent.
   - openhal/mcp/errors.py (the module docstring) and the `next_step` description in openhal/mcp/tools.py.
   - START_HINT in openhal/client/transport.py, the hub-not-running message in openhal/mcp/server.py, and the data-block marker in openhal/hub/views.py with its MCP counterparts, which must stay identical to each other.
   - The "Add it with" line in `openhal hub discover` output, and examples/plant-waterer/TEST-PLAN.md, which quotes that line.
   - The text `openhal library` generates for library/README.md. Regenerate library/README.md.
   - The docstrings in openhal/client/sync.py and openhal/client/aio.py that lean on "it", then regenerate website/src/content/generated/python-api.json with `uv run python -m tests.website.python_api`.
   - The mock driver's description in drivers/catalog.json.
   - FLOW_DESC in scripts/diagrams.py, then rebuild with scripts/build-diagrams.
   - NEEDS_HUMAN.md.
2. **The Playground mirror.** website/src/lib/kernel/ and website/src/lib/protocol.ts repeat the hub's messages. Change them to match, and regenerate website/tests/kernel-parity/expected.json with `uv run python -m tests.website.kernel_parity`.
3. **The spec.** spec/2026-10-24/basic/messages.md shows the old message in an informative example (about lines 277 to 279). Update the example. Normative sentences such as "Only a human Principal may approve" stay, because a dated spec's normative text never changes. If ADR 0015 or the spec fixes an error's exact message text normatively, stop and say so in your report instead of changing the message.
4. **Tests.** Every test that pins one of these messages follows the new words.

## Gates

COMMON.md's gates, plus `pnpm build` and vitest in website/, the kernel parity test, and the Playground's Playwright tests in Chromium and Firefox. Run one suite at a time, because the machine is shared with the speed round.

## Files you own

The files and lines listed above, the tests that pin them, website/src/lib/kernel/, website/src/lib/protocol.ts, website/tests/kernel-parity/, tests/website/kernel_parity.py, the two generated website files, library/README.md, the rebuilt files in docs/diagrams/ and NEEDS_HUMAN.md.

## Not yours

Any behavior, check, error name or data field. examples/print-babysitter/printer.hal.yaml, whose action descriptions are covered by the confirmation hash, so rewording them needs the owner to confirm the file again. The rest of website/, where the speed round is working. docs/DESIGN.md.
