# Brief: safety yellow as the site's one accent, with blue kept for pending only

Read docs/agents/COMMON.md first, then docs/DESIGN.md (Color, Layout, Motion and Banned), then design/tokens.css, website/src/styles/global.css, starlight.css, code.css, story.css and prose.css, website/src/components/ui/button.tsx, command.tsx and dropdown-menu.tsx, website/src/components/starlight/Header.astro, Sidebar.astro and Footer.astro, website/src/components/islands/SearchPalette.tsx, website/src/lib/markdown/mermaid.mjs, website/src/lib/og.ts, dashboard/src/app.css and the color checks in website/tests/e2e/design-rules.spec.ts.

## What the owner said

On 2026-11-01 the owner asked for this, word for word.

> Change the site's accent color from pink and blue to safety yellow, used as the single accent.
>
> Tokens
> - Dark mode accent #FFD60A. Text on yellow is always near-black (#0d0f12).
> - Light mode: yellow only as a fill (#FFD60A with black text). For accent-colored text and links in light mode, use a dark mustard (around #7A5C00) that passes WCAG AA on white.
> - Status colors: done = green, refused = red, pending = blue (move pending off amber so it can't be confused with the accent). Nothing else may use these colors.
>
> Apply the accent to
> - The Get started button (yellow fill, black text, 600 weight, a subtle brighten and 1px lift on hover)
> - The active nav underline (.nav-mark)
> - Links (yellow in dark mode, mustard in light mode, underlined)
> - The active step in How it works: the current request arrow and the step counter
> - Focus rings, ::selection, and the Smooth scrolling toggle when on
> - Remove all pink (#FF4FA3) and all blue accent uses.
>
> Keep it rare: yellow should mark what's important or interactive, never backgrounds of large areas or body text.
>
> Check contrast for every pair, then screenshot the hero, How it works (all 3 steps), the docs and the spec in light and dark mode. Make sure the yellow button is the first thing your eye goes to, and that pending, refused and done are still easy to tell apart.

## Tokens, decided

Use these names in design/tokens.css so the orchestrator's How it works work lines up with yours.

| Token | Light | Dark | Use |
|---|---|---|---|
| `--accent` | #7A5C00 | #FFD60A | Accent text, links and thin marks under 4 px, such as the nav underline, the sidebar's current page bar and focus rings |
| `--accent-fill` | #FFD60A | #FFD60A | Fills, such as the primary button, ::selection and a switch that is on |
| `--accent-fill-hover` | your choice | your choice | The primary button's subtle brighten on hover |
| `--on-accent` | #0d0f12 | #0d0f12 | Text and marks on a yellow fill |
| `--confirm` | #1d5fb4 | #7db2f0 | Pending, and nothing else |
| `--ok`, `--blocked` | unchanged | unchanged | Done and blocked, and nothing else |

Remove `--spark` and every use of it. Tune #7A5C00 only if a check fails, and keep AA (4.5:1 for text, 3:1 for marks and control edges) for every pair.

## Goal

1. **One accent.** Apply the owner's list above everywhere on the site, the docs, the spec, the blog, the Playground, the drivers and the Device Library pages, the 404 and the search palette.
   - The Get started button and the site's other primary buttons use the fill with `--on-accent` text at weight 600. On hover the fill brightens a little and the button lifts 1 px. No glow, no gradient and no shadow. With reduced motion, nothing lifts.
   - Links are underlined. Nav rows, sidebar rows, buttons and the search palette's rows are not links in this sense and stay in the text color.
   - Choose how a light mode yellow fill keeps a visible edge on the near white page (3:1 for the control's edge), and say why.
2. **No blue or pink outside pending.** Blue now means pending only.
   - Replace every blue use that isn't pending, including the nav's blue highlight behind the header's current section and the sidebar's current page, the search palette's and the dropdown's selected rows, hover rings on controls, code syntax colors, Mermaid's link color and the method color in the social image renderer.
   - Highlights and selected rows use a neutral surface, never a yellow tint. Syntax colors use the neutrals only, and errors keep `--blocked`.
   - The story diagram on the 3D print example page (story.css and website/src/lib/story/) follows the same rule as How it works. The request arrow being drawn is in `--accent`, earlier requests turn to `--text-2`, replies keep their status colors and pending is blue.
3. **Status colors.** Done is green, blocked is red and pending is blue, and nothing else uses these three colors. Check that the three stay easy to tell apart from each other and from the yellow, in both themes and for color blind readers (protanopia, deuteranopia and tritanopia simulations), and record the check.
4. **The dashboard.** dashboard/ imports design/tokens.css, so the token change reaches it. Fix only what the change breaks there, such as light text on a yellow fill or blue used for something other than pending, and keep its tests green.
5. **Propose the design text.** Propose new wording for docs/DESIGN.md's Color section, with the token table, the accent's uses and the status colors, in your report. Don't edit DESIGN.md.

Load and use every installed skill that fits, at least frontend-design:frontend-design, design-taste-frontend, web-design-guidelines, ui-ux-pro-max:ui-ux-pro-max, ui-ux-pro-max:ui-styling, vercel:shadcn, playwright-cli and chrome-devtools-mcp:a11y-debugging. List in your report what you used and for what.

## Gates

Run Playwright and pytest one at a time, with at most 3 Playwright workers. The machine is sometimes under heavy load from other sessions, so rerun a failure alone before you treat it as real.

- `pnpm build` with zero warnings, and vitest.
- Playwright in Chromium and Firefox for the specs your change touches, design-rules.spec.ts and the axe checks, with axe at 0 violations in both themes.
- The dashboard's own build and tests.
- `uv run pytest tests/website tests/docs`.
- A contrast table in your report with every pair you use, its ratio and its threshold, in both themes.
- Screenshots of the hero, the docs index, a spec page, the blog and the Playground at 1440 and 390 px in light and dark. Look at every screenshot before you report. Save them to qa/after/website-19/ and keep scratch in docs/design-rounds/website-19/.

## Files you own

website/ and design/tokens.css, plus dashboard/ for the fallout in Goal 4.

## Not yours

The orchestrator is changing How it works at the same time. Don't touch website/src/components/landing/HowItWorks.astro, website/src/components/landing/how-runtime.ts, website/src/styles/how.css, website/src/lib/story/how.ts, website/tests/unit/how.test.ts or website/tests/e2e/how.spec.ts. The orchestrator applies the accent there with the tokens above.

Also not yours are openhal/, spec/, docs/ other than your scratch folder, docs/DESIGN.md (propose) and website/src/content/generated/.
