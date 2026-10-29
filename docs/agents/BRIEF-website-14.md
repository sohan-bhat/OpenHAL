# Brief: no icons in the pickers, smooth animation from a proven library, and thicker control outlines

Read docs/agents/COMMON.md first, then docs/DESIGN.md (Layout, including the new rules on outlines and pickers, and Motion pattern 9) and website/ with its tests. Load the skills frontend-design:frontend-design, design-taste-frontend, web-design-guidelines and playwright-cli before UI work, and use the context7 tools for current library documentation.

## What the owner said

About the header's version and theme pickers: "No icons here please. Also when I click on them it should do a clean smooth animation. Use a nice animation library for most things, like the search bar, these dropdowns and most interactive things." About the search field's outline: "For all elements that have this type of outline, thicken it up a tad bit."

## Goal

1. **No icons in the pickers.** The version picker and the theme picker in the header show their word and a chevron only, with no book icon and no screen icon. The same goes for every other picker or menu on the site.
2. **Smooth animation from a proven library.** Choose a popular, maintained animation library and record its downloads, stars and last release. Motion (motion.dev, the vanilla `animate` API) is the default choice, and GSAP is the alternative. Use the library for:
   - the search dialog opening and closing
   - the version, theme and section pickers
   - the phone menu
   - the sidebar's groups opening and closing
   - the information marks' popovers
   - the Copy buttons' confirmation
   - other controls that open or change state
   Each animation runs 150 to 250 ms with an ease out or a soft spring that never bounces past its end. Only transforms, opacity and a disclosure's height move. With reduced motion every part opens at once. Load the library only on pages and moments that need it, for example with a dynamic import on the first interaction, so the budgets hold.
3. **Pickers that can animate.** A native select's list can't animate in every browser. Turn the version and theme pickers into accessible menu buttons that open a list, built on the native popover attribute, positioned with a proven library such as Floating UI where CSS anchoring isn't available, and animated with the library from goal 2. Each picker needs:
   - Enter, Space and the arrow keys
   - Escape and a click outside to close
   - focus returning to the button
   - the current choice on the nav's blue highlight
   The theme picker keeps Starlight's Auto, Light and Dark and its stored choice. The version picker keeps its links to the same section in each version.
4. **Thicker control outlines.** Every control with an outline draws the outline at 1.5 px instead of 1 px. That covers the search field and its shortcut key, inputs, pickers and outlined buttons such as the menu button and Copy, the drivers and library filters, and the Playground's fields. Rules, dividers and table borders stay at 1 px. Put the width in a token so one change moves every control.

## Gates

`pnpm build` with zero warnings, vitest, Playwright in Chromium and Firefox with axe at 0 violations (with each picker, the phone menu and the search dialog open), the budget test, and Lighthouse three times each on mobile and desktop on home, docs and a spec page: 98 or more on mobile, 100 on desktop and no layout shift. Record short videos of the search dialog, both pickers and the phone menu opening and closing at 1440 and 390 px, and screenshot the header and a page with inputs in light and dark. Look at every shot and video before you report, and keep them in docs/design-rounds/website-14/ inside your worktree.

## Files you own

website/ except what website-13 owns (BRIEF-website-13.md): the schema reference page, its outline and the home hero's small diagram. Also docs/verification/ui.md, apart from website-13's rows.

## Not yours

openhal/, spec/, dashboard/ and docs/DESIGN.md (propose).
