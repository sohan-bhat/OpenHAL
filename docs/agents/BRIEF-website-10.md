# Brief: a steady header and a collapsible sidebar

Read docs/agents/COMMON.md first, then docs/DESIGN.md ("Layout", "Motion" and "Copy voice") and website/ with its tests. Load the skills frontend-design:frontend-design, design-taste-frontend, web-design-guidelines and playwright-cli before UI work.

## What the owner said

1. "There is a weird bug where if I click on the Overview button it shifts all header elements to the center, like it squeezes them in a bit." The header uses the 1360 px `.wrap` container on every page except the home page, where Header.astro and Footer.astro switch to the 1200 px `.home-width` column (commit aea7f2c). At 1440 px the wordmark moves from 56 px to 136 px and the nav moves 80 px inward on the home page.
2. "Make this left hand side sidebar able to be collapsible with a clean fast animation, and all the other elements on the right side get shifted over to match up with it. This should happen for all pages. If the sidebar is collapsed and the user hovers near the left side of the screen, then the sidebar should temporarily appear on that side and then go away after the hover is gone." The owner's reference is a browser's vertical tab sidebar, which collapses and slides back in as an overlay while the pointer is near the left edge.

## Goal

1. **One header on every page.** The header and footer use the same container on every page, so nothing in the header moves when a person goes to Overview or anywhere else. The home page's content lines up with the header by using that same container, so change `.home-width` to match `.wrap` instead of changing the header. Add a test that the wordmark, search, nav items and footer sit at the same positions on /, /docs/ and a spec page at 1440, 1280 and 1024 px.
2. **A collapsible sidebar** on every page that has the left sidebar (DocShell).
   - A small button at the top of the sidebar hides the sidebar, and the same control, still visible near the page's left edge, shows the sidebar again. Name the button in plain words ("Hide the sidebar", "Show the sidebar") with aria-expanded and aria-controls.
   - The sidebar slides out and the content and the "On this page" outline move left to use the space, in one clean animation of about 200 ms with an ease out. The reading column keeps its width.
   - While the sidebar is hidden, a pointer near the left edge of the window, below the header, slides the sidebar in as an overlay above the content. The sidebar leaves again a moment after the pointer leaves the sidebar, without flicker. Pressing the button while the sidebar is showing this way keeps the sidebar open.
   - The overlay follows the theme. It uses the page background and a 1 px `--border` rule, with no shadow, glow or blur.
   - The browser remembers the choice in localStorage, read in an inline script in the head so the first paint already has the right layout, with every storage call wrapped in try and catch. A page change keeps the state without replaying the animation, and the page transition still plays.
   - Keyboard. The button works with Enter and Space. While the sidebar is hidden, the sidebar's links leave the tab order, and moving focus into the sidebar from the button shows the sidebar.
   - Under `prefers-reduced-motion` the sidebar shows and hides without sliding.
   - At the widths where the sidebar is already a menu, nothing changes.
3. **Keep** the nav highlight slide, the page transition, the search dialog, the theme switch and the outline working in both sidebar states, with no layout shift on load.

## Gates

`pnpm build` with zero warnings, vitest, Playwright in Chromium and Firefox with axe at 0 violations with the sidebar shown and hidden, the budget test, and the build under /OpenHAL/. Record a short video of the sidebar hiding, showing, and appearing on hover at 1440 px in both themes, and screenshot the header on /, /docs/ and a spec page at 1440, 1280 and 1024 px. Keep them in docs/design-rounds/website-10/ inside your worktree and name the full absolute paths in your report. Run Playwright and pytest one at a time.

## Files you own

website/src/components/Header.astro and Footer.astro (layout and markup), website/src/layouts/DocShell.astro and Base.astro (the sidebar and the inline head script), the container, header, footer and sidebar rules in website/src/styles/global.css (including `.wrap` and `.home-width`), website/tests/e2e/layout.spec.ts and new tests for the sidebar.

## Not yours

The home page body and the landing story (website-9, BRIEF-website-9.md), page copy and the nav data files (site-copy, BRIEF-site-copy.md), docs/, openhal/ and dashboard/. Propose changes to docs/DESIGN.md ("One left edge" and Motion) in your report.
