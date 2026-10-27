# Brief: Inspector round 4, the final critique's fixes

Read docs/agents/COMMON.md first, then docs/DESIGN.md and dashboard/ with its tests. Load the skills frontend-design:frontend-design, design-taste-frontend, web-design-guidelines and playwright-cli before UI work. A fresh critic scored the Inspector 4 of 5 from screenshots. Fix what it found.

## The critic's findings

1. **Settings on phones.** The token table overflows at 390 px, so Id truncates and Created, State and Revoke fall off screen. On desktop the row dividers stop short of the Revoke column, and the selects and checkbox are native and unstyled.
2. **Audit log on phones.** Stacked values have no labels (writer_answer, human:owner, c8cd4cfe). Rows style inconsistently, so the confirmation row's code wraps in plain text while blocked rows are bold red. "Done. water ran." starts a sentence in lowercase.
3. **The mobile header.** The hub and connection labels are dropped, and protocol and conformance turn into lowercase fragments on a misaligned row.
4. **Numbers with no units**, which DESIGN.md bans. Slider midpoints such as "16", "11", "30" and "40", and the power "0", need their unit. The power slider has no min bar where action sliders do.
5. **Agent and human markers.** lab-script log entries have no dashed agent rule. Blocked agent rows in the audit log swap the dashed agent rule for a solid red one, the same solid treatment human rows get. An agent stays dashed whatever its status.
6. **The dashed outline means too many things.** It marks unverified, agent entries, the DEMO DATA box, the "simulated" chip, "shown as data" fields, empty states, the disabled Pair button and more. Keep dashed for unverified and for agents, as DESIGN.md says, and give the rest another treatment. The disabled Pair button must not look like an unverified chip.
7. **Device views.**
   - The "reads tested, commands unverified" chip wraps to two lines and stretches across the card.
   - The "limits not confirmed" badge stretches the full width of its box.
   - On a read-only device the slider and input look live while their Set buttons are disabled.
   - A device action named stop gets a blue "Run stop" primary button, too close in meaning to the global STOP. Keep the global STOP the only stop-looking control.
   - "Run vent" looks the same as a button that runs at once, even when the action needs a confirmation.
8. **Text that breaks mid-token.** For example "agent:bench-agent" in the routines list and "desk-/fan" in the writer's detected fields. "every 1800 s" sits next to source that says "every: 30 min".
9. **The driver writer.** The detected view is a grid of equal-weight dashed boxes, and it repeats "shown as data" six times. The review view uses the granted green for diff additions, and the sha256 line is clipped on phones.
10. **Pair and offline.** These screens have no STOP control. Keep STOP reachable wherever the hub is reachable, and say plainly why it isn't when it isn't.
11. **Small things.** The confirmations count badge uses amber with no shape. The "Message log" toggle shows its state by weight alone. An empty circle is used for planned, disabled, no confirmation and started, which goes beyond DESIGN.md's four status shapes.
12. **The test harness** (tests/inspector/harness.py) reports its simulated unknown board as `firmware.product desk-fan`, so the writer views show fan_speed questions. Make it a board in the plant waterer's family that isn't already registered, so the screens stay on the canonical example.
13. **The port.** The screenshots show 7432 while the docs say 7420. Capture the screenshots the website uses (website/scripts/inspector-captures.mjs) with the hub shown at 127.0.0.1:7420. Keep the harness on a free port and show 7420 in the header, or run the capture hub on 7420 when it's free.

Keep the website round's work in mind. Another agent is changing the message log's narration lines to `#` comments, muted and italic, in dashboard/src/components/MessageLog.svelte. Leave that file's narration rendering to it.

## Gates

svelte-check with zero errors and warnings, `pnpm build`, vitest and Playwright in Chromium and Firefox in dashboard/, with axe at 0 violations in both themes at 1440 and 390, and `uv run pytest tests/inspector tests/website` (use `export PATH="$HOME/Library/Python/3.13/bin:$PATH"`). Rebuild openhal/hub/static with each change. Save screenshots of every view and state at 1440 and 390, light and dark, in your scratch folder.

## Files you own

dashboard/ except the narration rendering in MessageLog.svelte, openhal/hub/static/, tests/inspector/, and website/scripts/inspector-captures.mjs with the captures it writes.

## Not yours

website/ apart from those captures, the hub's Python code (propose changes in your report), docs/DESIGN.md (propose changes) and everything else.
