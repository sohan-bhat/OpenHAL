# Brief: the Inspector for the 3D print babysitter

Read docs/agents/COMMON.md first, then docs/DESIGN.md ("Canonical demo scenario" and "The Inspector") and dashboard/ with its tests. Load the skills frontend-design:frontend-design, design-taste-frontend, web-design-guidelines and playwright-cli before UI work.

## What changed

The owner wants the main example to be a task only an agent can do, so the 3D print babysitter replaces the plant waterer (DESIGN.md). A scenario round added examples/print-babysitter/ (a Klipper printer through Moonraker and its webcam through the `http` driver) and made camera reads return the image. An image Reading's value is `{ mimeType, bytes, width, height, data }`, where `data` is base64 and comes only with an explicit read. Live events and the audit log carry the description without `data`. Start by merging the branch and commit the orchestrator gives you.

## Goal

1. **Camera frames.** An image channel shows its latest frame in the device view at a size a person can judge, with its format and size in small mono, and a "Read frame" control that reads it again. The message log shows an image result as its description, never a wall of base64. Treat a frame as device data from an untrusted source, so it is never a link target and nothing on the page acts on its content.
2. **The person's question.** The scenario ends with `cancel` pending for a person. In Confirmations, make the cancel request clear for someone who just woke up: what the agent asked, why it waits (it can't be undone), and Approve and Reject. If it fits the design, show the camera's latest frame beside the request so the person can see the print before deciding, and propose any API or device file link this needs instead of inventing one.
3. **Demo data and tests.** dashboard/src/lib/fixtures and dashboard/e2e use the printer and camera wherever the plant waterer stood in as the example. Keep the plant waterer where a test is about firmware or the driver writer.
4. **Captures.** Retake the website's Inspector screenshots with a hub running the print babysitter devices on their simulators (website/scripts/inspector-captures.mjs), so the website's Inspector page shows the printer, its camera frame and the pending cancel. Never contact real hardware.
5. **Keep** the theme, no status dots, the text wordmark, light and dark, 1440 and 390 px. Say "agent", not "AI".

## Gates

`pnpm build` and the build into openhal/hub/static, vitest, Playwright in Chromium and Firefox with axe at 0 violations in both themes at 1440 and 390, Lighthouse on the Inspector where docs/verification/ui.md records it, and COMMON.md's Python gates. Screenshot every view you change, look at the shots, fix and repeat, and name the full absolute paths in your report.

## Files you own

dashboard/, openhal/hub/static/ (built output only), website/scripts/inspector-captures.mjs, website/public/captures/ and website/src/data/inspector-captures.json.

## Not yours

openhal/ Python code (propose API changes), examples/, docs/ (propose), README.md and the rest of website/.
