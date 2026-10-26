# Brief: the landing story and site for the 3D print babysitter

Read docs/agents/COMMON.md first, then docs/DESIGN.md (above all "Canonical demo scenario", "The landing story" and Motion pattern 4) and website/. Load the skills frontend-design:frontend-design, design-taste-frontend, web-design-guidelines and playwright-cli before UI work.

## What the owner said

"Instead of a basic watering plant example use a more complex example. Like I can use Arduino IoT to water the plant as well without an agent. Do a task only an agent can do." The owner chose the 3D print babysitter. The earlier landing round's bar still holds: a page for a person, not word soup, with a pinned scroll story where scroll drives a camera across one scene.

## How this round starts

A scenario round is writing the new example and docs/demo/scenario.yaml on its own branch. Until it lands, design and build the scene from the story in DESIGN.md. When the orchestrator sends you a branch and commit, merge it and wire every word and number to the real record. Until then the build may fail where it reads the old scenario.

## Goal

1. **The landing story, retold.** Keep the engine in website/src/components/landing/ (pinned stage, scroll-driven camera, a piece leaves before the next arrives, reduced-motion static list) and change the scene and shots.
   - Stations along the real path: AI client, OpenHAL hub with `printer.hal.yaml`, Safety kernel, Driver (`moonraker`), the 3D printer, with the camera beside the printer.
   - The camera panel matters most. It shows what the agent sees, a plain line drawing of the print, first with a lifted corner and then come loose. Match the demo frames the scenario round draws for the camera simulator, in the house style. No photos, no 3D renders, no glow.
   - Beats from DESIGN.md. A long print starts and someone asks the AI to watch it. The camera shows a corner lifting. The AI warms the bed from 60 °C to 70 °C and it happens. It asks for a 300 °C nozzle and the kernel says no, because a person set 260 °C. The print comes loose. The AI pauses it at once. Cancelling can't be undone, so it waits for the person, who wakes up to a paused print and one question.
   - Short captions a maker would say. Real codes (LIMIT_EXCEEDED, done, pending) in small mono where they help.
   - Every word and number from docs/demo/scenario.yaml and printer.hal.yaml through website/src/lib/story/, with the test that changes the record and checks the story follows.
2. **The rest of the site.** Every page that shows the main example moves to the printer: the Playground (cases in tests/website/kernel_parity.py and the playground page), social images, the Inspector page's words (not its images), docs navigation labels and the blog post. Pages about Arduino, firmware or the driver writer keep the plant waterer.
3. **Keep** the theme, the text wordmark, no status dots, the one left edge, nothing under 13 px, light and dark.

## Gates

`pnpm build` with zero warnings, vitest, Playwright in Chromium and Firefox with axe at 0 violations, Lighthouse on the landing page at 100 for accessibility, best practices and SEO and 95 or more for performance on mobile with no layout shift, the scroll smoothness check from docs/verification/ui.md, and `uv run pytest tests/docs tests/website tests/demo` (use `export PATH="$HOME/Library/Python/3.13/bin:$PATH"`). Check the build under /OpenHAL/ the way the earlier landing round did. Screenshot the story at 1440, 768 and 390 px in both themes, record scroll videos at 1440 and 390, look at them, fix and repeat. Name the full absolute paths in your report.

## Files you own

website/ except the Inspector captures (website/scripts/inspector-captures.mjs, website/public/captures/ and website/src/data/inspector-captures.json), tests/website/kernel_parity.py and website/tests/kernel-parity/, and docs/verification/ui.md.

## Not yours

openhal/, examples/, docs/ outside docs/verification/ui.md, README.md, dashboard/ and the Inspector captures. Propose changes in your report.
