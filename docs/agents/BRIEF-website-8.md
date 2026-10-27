# Brief: the story resolves, and the site's details

Read docs/agents/COMMON.md first, then docs/DESIGN.md ("Canonical demo scenario" with its new step 6, "The landing story", "Copy voice" and Motion pattern 4) and website/ with its tests. Load the skills frontend-design:frontend-design, design-taste-frontend, web-design-guidelines and playwright-cli before UI work.

## What the owner asked

Fix the landing page scroll demo and a few site details. Keep the theme, the nine steps and the camera behavior (the whole diagram in view at one size).

1. **Resolve the story.** Step 8 shows the owner approving the cancel. The hub shows the approval in the record's words (for example "approved by owner"), the kernel's Confirmation row turns green, the grant flows to the driver, and the printer's state reads cancelled. Step 9 keeps "Every command to every device takes this path." and replaces the log with the last few audit log lines from the record (the requests, the refusal and the person's approval), so the ending shows something new instead of repeating step 8.
2. **Step 4** gets a "#" reason line in the log like every other step, from the record. The printer panel gets a Nozzle row, so the 260 °C limit has something to protect.
3. **Step 5's read path.** Reads pass through the kernel. The kernel checks the channel and the device, needs no grant and logs the read. Show the kernel allowing the read and the driver reading the frame, never "Waiting for a grant" on a read.
4. **Light the hub box** on every step where a request passes through the hub, not only when a rule row applies.
5. **Log colors.** Green only for success, amber for pending or confirmation required, red for errors. Step 7's pending result is amber.
6. **A fixed two-line caption slot**, aligned to the top, so a one-line caption doesn't move the diagram down.
7. **No blank band** between the nav and the step counter. Fill or tighten the empty area under the log beside the webcam, for example by making the log as tall as the webcam panel.
8. **The nav and footer content** line up with the home page's content container. Check that the docs templates keep their own alignment (One left edge in DESIGN.md).
9. **Copy rules** (DESIGN.md, Copy voice) on every website page. Name the subject instead of "it" or "them". Never write a contrast like "An agent can't loosen them. Only a person editing the device file can." No vague wrap-ups like "That fixes it." Start with the home page's three safety points, the story captions, the Playground ("Any client may stop. Only a person may lift it."), website/src/lib/safety.ts and the Inspector page, then read every other page. Leave the kernel and protocol messages in website/src/lib/kernel/ and website/src/lib/protocol.ts as they are, since they mirror the hub.

The owner's list also asked for a logo mark beside the nav wordmark. Don't add one. The owner chose a text wordmark with no logo, and the orchestrator is asking the owner about it.

## How this round starts

A scenario round is adding the approval, the reason line, the nozzle readings, the read path and the audit lines to docs/demo/scenario.yaml on its own branch (BRIEF-scenario-approval.md). Until the record lands, build the scene from the shape described here. When the orchestrator sends a branch and commit, merge it and wire every word and number to the record through website/src/lib/story/, with tests that change the record and check the story follows.

## Working beside the speed round

website-7, the speed round, runs on website/ at the same time. It stays out of the story, the home page body, the header and footer, and the Playground, and it owns the search dialog, fonts, images, prefetch and budgets. Keep your changes to Base.astro and global.css small and limited to the header and footer container, because the speed round edits the page head. Don't edit docs/verification/ui.md, which the speed round owns. Put your numbers in your report.

## Gates

`pnpm build` with zero warnings, vitest, Playwright in Chromium and Firefox with axe at 0 violations, the scroll smoothness check from docs/verification/ui.md, `uv run pytest tests/docs tests/website tests/demo` (use `export PATH="$HOME/Library/Python/3.13/bin:$PATH"`) and the build under /OpenHAL/ the way the Pages workflow builds it. Screenshot every step from 1 to 9 at 1440 and 390 px in light and dark, look at each shot, and confirm the caption, the lit stations and the log lines agree on every step. Keep screenshots in docs/design-rounds/website-8/ inside your worktree, which is gitignored, and name the full absolute paths in your report with a list of what changed. Run Playwright and pytest one at a time, never together, because the machine is shared.

## Files you own

website/src/components/landing/, website/src/lib/story/, website/src/styles/story.css, website/src/pages/index.astro (keep the HAL label script's behavior and its test), the header and footer components and their styles, website/src/components/playground/, website/src/lib/safety.ts, website/src/pages/inspector.astro, the copy on every other website page, the website tests for all of these, tests/website/kernel_parity.py and website/tests/kernel-parity/.

## Not yours

openhal/, docs/ (propose changes), dashboard/, the search dialog and the speed round's areas (fonts, images, prefetch, budgets, docs/verification/ui.md).
