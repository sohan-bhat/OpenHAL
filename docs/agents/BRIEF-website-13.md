# Brief: the schema reference's speed on phones, and the home page at 1024 px

Read docs/agents/COMMON.md first, then docs/DESIGN.md (Layout, which now describes the Starlight frame) and website/ with its tests, starting with the website round 12 notes in docs/verification/ui.md.

## What needs fixing

1. **The schema reference on a phone.** /spec/v0.1/schema/ is the largest page on the site, with 4,685 elements, 69 tables and 72 outline entries. After the move to Starlight it scores 82 to 85 on a phone in Lighthouse, against 99 before, with a median blocking time of 626 ms against 15 ms. A trace with the CPU slowed 4x showed two causes. The first style and layout pass takes 2.2 s against 0.7 s, and Starlight's outline script scans the page when idle, about 0.5 s each for the desktop and phone outlines.
2. **The home page at 1024 px.** The hero's small sequence diagram has its lifeline names cut off at the top, under the row with the step count. The cut-off predates Starlight.

## Goal

1. **Bring the schema reference back to 98 or more on a phone**, with no layout shift and nothing lost for a reader. Choose the fix that serves readers best and stays within the owner's preference for proven parts over hand-built ones. Measure before you choose.
   - One fix is splitting the generated schema reference into a page per part, such as methods, notifications, results and types. That changes the generator and the spec's draft structure, which the draft allows, and the website's sidebar, so keep every anchor working through redirects.
   - Another is a lighter outline for that page through a Starlight component override, such as one that lists only the top headings.
   - A third is cutting the first layout's cost, with content-visibility on the tables or simpler table styles.
2. **Show the small diagram's lifeline names in full at every width** from 1024 to 1199 px. Check 1024, 1100 and 1199 px in light and dark.

## Gates

`pnpm build` with zero warnings, vitest, Playwright in Chromium and Firefox with axe at 0 violations, the budget test, and Lighthouse three times each on mobile and desktop for the schema reference, a spec page and home: 98 or more on mobile, 100 on desktop and no layout shift. If you change the generator or the spec, run COMMON.md's Python gates too. Screenshot the schema reference at 1440 and 390 px and the home page's first screen at 1024, 1100 and 1199 px, look at each one before you report, and keep them in docs/design-rounds/website-13/ inside your worktree.

## Files you own

website/, docs/verification/ui.md and, if you split the schema reference, the schema generator in openhal/protocol/, the generated spec/v0.1/ schema files and the tests that pin them.

## Not yours

The rest of spec/, the hub's behavior, dashboard/ and docs/DESIGN.md (propose).
