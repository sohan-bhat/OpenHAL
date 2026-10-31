# Brief: the sidebar flush to the window's left edge with its own toggle button, and one striking accent color

Read docs/agents/COMMON.md first, then docs/DESIGN.md (Layout, "The sidebar", the header, Color and Motion), then website-17's sidebar: website/src/components/ui/sidebar.tsx, website/src/components/islands/SidebarNav.tsx, website/src/components/starlight/Sidebar.astro and Header.astro, website/src/lib/sidebar.ts, website/src/styles/starlight.css and global.css, design/tokens.css and the sidebar tests in website/tests/e2e/.

## What the owner said

On 2026-10-31 the owner sent a screenshot of the spec page in the dark theme on a wide window and wrote:

> the left sidebar has so much empty space all the way to the left, and also have a button as well but there are some padding or maargin issues going on the left side of the screen. Furthermore, for the colors u have blue and black but also have a visiually striking accent color that really draws the users in but no gradients

The owner's palette rule for every site is a two color harmony plus one visually striking accent, used sparingly, with no gradients and no glow.

## What we measured on the live site

The whole frame is centered in a maximum width, so the sidebar's container starts at the window's edge while its rows start far to the right.

| Window width | Sidebar container | First row starts at | Wordmark starts at |
|---|---|---|---|
| 1280 px | 0 to 300 px | 33 px | 16 px |
| 1728 px | 0 to 484 px | 217 px | 200 px |
| 2560 px | 0 to 900 px | 633 px | 616 px |

## Goal

1. **The sidebar flush to the left edge.** From 800 px up, the sidebar starts at the window's left edge at every width and keeps its width (about 280 to 300 px). Its rows start 16 to 24 px from the window's edge.
   - The header's left group (the new button, then the wordmark) lines up with the sidebar's rows.
   - The reading column (772 px at most) and the "On this page" outline sit in the space to the right of the sidebar. Choose whether the reading column is left-aligned or centered in that space, whichever reads better at 1728 and 2560 px, and record why.
   - No empty band appears to the left of the sidebar or the wordmark at 1280, 1440, 1728, 1920 or 2560 px, with the sidebar shown or collapsed.
   - Audit every left edge: the header, group labels, rows, sub-rows, the guide lines of nested groups, borders, the rail and the phone menu. Put them on one clear grid, so no row, label or line sits a few pixels off another.
2. **A toggle button from the component.** Add shadcn/ui's own SidebarTrigger, from the same sidebar.tsx, in the header at the far left before the wordmark, from 800 px up. Phones keep the menu button.
   - The button shows the component's PanelLeft icon, because the control has no word, with an accessible name, `aria-expanded` and `aria-controls`.
   - Hovering or focusing the button shows shadcn/ui's Tooltip, "Hide sidebar" or "Show sidebar" with the Command or Control and B key hint.
   - The button stays in the same place in both states and never floats over the content. Nothing peeks.
   - The rail and the shortcut stay. The first press works before React has loaded, because client:intent replays it.
3. **One striking accent, magenta, flat.** Keep the neutrals and the blue as the harmony, and add one token, `--spark`, to design/tokens.css.
   - **Colors.** Light #cc1475 and dark #ff4fa3.
   - **Contrast.** On the page background, light reaches 5.2:1 and dark 6.3:1. White text on the light value reaches 5.35:1, and the page's near black on the dark value reaches 6.3:1. Tune the values only if a check fails, and keep AA for every use.
   - **Subject.** The color ties to the subject: the magenta trace of an oscilloscope's third channel, and the pink and raspberry of maker hardware.
   - **Not a status color.** Never use magenta for success, blocked or pending, and keep red for danger only.
   - **Use it sparingly, at most two uses per screen.**
     - **Primary buttons.** The primary action button is filled magenta. That covers Get started on the home page and the site's other primary buttons.
     - **Current-location marker.** The header's current section and the sidebar's current page carry a 2 px magenta bar, while blue stays for links and the highlight.
     - **One more use.** You may add one more use if it clearly helps a visitor, and explain it.
   - **No gradients or glows.** No gradients, no glow, no tinted boxes.
   - **Brand stays.** The wordmark, the favicon and the social images stay as they are.
4. **Propose the design text.** Propose new wording for docs/DESIGN.md's Layout ("The sidebar" and the header bullet) and its Color section, with the accent's uses, in your report. Don't edit DESIGN.md.

Load and use every installed skill that fits: vercel:shadcn, ui-ux-pro-max:ui-ux-pro-max, ui-ux-pro-max:ui-styling, frontend-design:frontend-design, design-taste-frontend, web-design-guidelines, playwright-cli and chrome-devtools-mcp:a11y-debugging. Use the context7 tools for shadcn/ui's Sidebar and Tooltip documentation. List in your report what you used and for what.

## Gates

Run Playwright and pytest one at a time, with at most 3 Playwright workers.

- `pnpm build` with zero warnings, and vitest.
- Playwright in Chromium and Firefox, with axe at 0 violations with the sidebar shown and collapsed, the tooltip open and the phone menu open.
- The budget test. Set new baselines only where the change needs them, and explain each one.
- Lighthouse three times each, on mobile and desktop, for home, docs, a spec page and the Playground. Mobile scores 98 or more, desktop scores 100, and there is no layout shift.
- Screenshot the spec page and the docs index at 1280, 1440, 1728 and 2560 px, light and dark, with the sidebar shown and collapsed. Screenshot both pages at 390 px with the phone menu open, and the home hero at 1440 and 390 px in both themes.
- Look at every screenshot before you report. Save them to qa/after/website-18/ and keep scratch in docs/design-rounds/website-18/.

## Files you own

website/ except website/src/content/generated/, plus design/tokens.css for the new `--spark` token only. Don't change existing token values.

## Not yours

openhal/, spec/, dashboard/, docs/ other than your scratch folder, and docs/DESIGN.md (propose).
