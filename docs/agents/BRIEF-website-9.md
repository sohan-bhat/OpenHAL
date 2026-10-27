# Brief: the landing story without boxes

Read docs/agents/COMMON.md first, then docs/DESIGN.md ("The landing story", which is the new contract, "Copy voice" with the owner's writing rules, "Canonical demo scenario" and Motion pattern 4) and website/ with its tests. Load the skills frontend-design:frontend-design, design-taste-frontend, web-design-guidelines and playwright-cli before UI work.

## What the owner said

"Again use a different method, right now it's just boxes, very confusing, lots of text within each box. Remove the boxes entirely, communicate in another way." The owner also set writing rules for all site copy, now in DESIGN.md under Copy voice.

## Goal

1. **A sequence diagram drawn with lines and text.** Rebuild the scene in website/src/components/landing/ as DESIGN.md's landing story describes.
   - Thin vertical lifelines for the person, the agent, the OpenHAL hub and the devices, each labeled in plain text at the top. The printer and its webcam may share one lifeline or have two, whichever reads more clearly at 390 px.
   - One arrow per request, labeled in short mono with the record's values, for example "read frame", "bed_target 70 °C", "extruder_target 300 °C", "pause", "cancel" and "approve". The result sits at the arrow's end as a word in its status color, such as done, LIMIT_EXCEEDED, waiting for approval or approved. No glyph, dot or mark sits beside a status word.
   - A refused request stops at the hub's lifeline. The held cancel stops there in amber until step 8, when the owner's approval arrives from the person's lifeline and the cancel continues to the printer.
   - Earlier arrows settle into a quieter color, so step 9 shows the whole exchange, with the audit log's counts (6 requests, 1 refused, 1 approved by a person) in the caption sentence.
   - The webcam's line drawing, from the same demo frames, sits beside the lifelines with no frame or border and changes with the print. The printer's nozzle temperature, bed target and state sit beside the drawing as plain text.
   - Nothing in the story has a border, card, panel or tinted background. The kernel's individual checks and the drivers leave the landing page, since the Playground and the docs already show them.
2. **Captions.** Write one sentence per step to the owner's rules: technical documentation, the cause before the effect, no personified software and precise nouns. Two examples of the register, to adapt to the record's words:
   - "Because the owner set a nozzle limit of 260 °C in printer.hal.yaml, the hub refuses the agent's request for a nozzle temperature of 300 °C and returns LIMIT_EXCEEDED."
   - "Because a cancelled print can't be resumed, the hub holds the agent's cancel request until a person approves or rejects the request."
3. **Keep** the nine steps, the step count text, Skip the demo, the Smooth scrolling switch and its behavior, the pinned stage with no pan or zoom, the reduced-motion and short-screen list, and the HAL labels under the hero exactly as they are. Every word and number still comes from docs/demo/scenario.yaml through website/src/lib/story/, with tests that change the record and check the story follows.
4. **The rest of the home page** follows the writing rules too: the safety model points, What OpenHAL works with, Run the demo and Read more. The one-line description "An open-source protocol for AI agents to control hardware." stays exactly as it is.

## Gates

`pnpm build` with zero warnings, vitest, Playwright in Chromium and Firefox with axe at 0 violations, the scroll smoothness check from docs/verification/ui.md (as an A/B against main's build if the machine is loaded), the budget test in website/tests/e2e/budget.spec.ts (reset the home row only if the new scene needs it, and say why), `uv run pytest tests/docs tests/website tests/demo` and the build under /OpenHAL/. Lighthouse on the home page, three runs each on mobile and desktop, no worse than main's 99 on mobile and 100 on desktop, with no layout shift. Screenshot every step from 1 to 9 at 1440 and 390 px in light and dark, look at each shot and confirm the caption, the arrows and the drawing agree. Keep screenshots in docs/design-rounds/website-9/ inside your worktree and name the full absolute paths in your report. Run Playwright and pytest one at a time.

## Files you own

website/src/components/landing/, website/src/lib/story/, website/src/styles/story.css, website/src/pages/index.astro, the home page's tests (the story, first paint, the home page's design rules and the home row of the budget test) and the landing story section of docs/verification/ui.md.

## Not yours

Every other page and its copy, which a site copy round rewrites at the same time (BRIEF-site-copy.md), website/src/components/playground/, the header and footer, docs/, openhal/ and dashboard/.
