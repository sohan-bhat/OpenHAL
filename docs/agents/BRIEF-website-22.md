# Brief: phones that work, a steady tab highlight, a neutral beside the pink and a hint of green in the black

Read docs/agents/COMMON.md first, then docs/DESIGN.md (Color, Layout, Motion, Banned), design/tokens.css, website/src/styles/global.css, starlight.css, how.css and story.css, website/src/components/starlight/Header.astro and the header's islands, website/src/components/landing/Hero.astro, website/src/lib/markdown/mermaid.mjs, website/src/lib/og.ts, docs/diagrams/theme-light.d2 and theme-dark.d2, and the Playwright specs that check color, layout and motion.

## What the owner said

On 2026-11-01 the owner wrote, word for word.

> on the openhal website the mobile version is cooked. also on the computer version when going between the different tabs the tab transition between [screenshot of the header's Overview tab with its highlight box and pink bar] like docs and overview for example turns the box outline to what tab it is currently on completely opaque and not transparent. also add back in like a nuetral color because having one visually striking color is bad you want to balance it with a nuetral color that fits black pink and whatever the other color is, dont go back to blue doesnt fit with pink

> also instead the black color make the background have a ever so hint of very very military grade very very dark dark dark green ever so tiny hint

> [screenshot of the phone menu button] on mobile this isnt centered

The owner's palette rule for every site is a two color harmony plus one striking accent, used sparingly, with no gradients and no glow.

> use 3rd party libraries for this as well

The owner's standing rule is that nothing is self written. Every fix comes from a proven library.

## What we saw on the live site

At 390 px in headless Chromium, the menu button's three lines sit off the center of its box, the hero wordmark runs nearly edge to edge with its labels against the right edge, and the Drivers table headers extend past the screen inside their scroller. Nothing scrolls the page sideways, so the rest of "cooked" has to be found on a phone's own engine.

## Goal

1. **Phones.** Audit every page at 375, 390 and 430 px in WebKit, the engine of Safari on iPhone, and in Chromium, in both themes, at rest and while using each part: the header and its menu, the phone menu, search, the hero, How it works while scrolling through all three steps, the example's walkthrough, the catalog filters with a Select open, tables, code blocks, the Playground and the footer. Fix everything that is off, cut, crowded, misaligned, too small to tap (24 px at least, 44 px for main controls) or jumpy. Start with the owner's two findings, the menu button's icon centered in its box both ways, and the hero wordmark with room on both sides. List every problem you found and its fix in your report.
2. **The tab highlight.** Reproduce the desktop header's highlight going fully opaque when moving between sections, such as Docs to Overview, by capturing frames through the page transition and the highlight's own motion in Chromium, Firefox and WebKit. Fix it so the highlight keeps the same look before, during and after every move, then add a test that samples the highlight's computed background and opacity through the transition.
3. **A neutral beside the pink.** Add one neutral color to the harmony so the pink stays rare and the page has a calm second color. It fits the near-black, the pink and the new green hint, and it is not blue and not a gray that reads as blue. Choose its roles yourself, for example links, the highlight behind the current section and row, the step counter or secondary marks, and keep the pink for primary actions, the current location bar, the request arrow being drawn and focus. Record the roles. Blue stays only for pending.
4. **A hint of military green in the black.** Tint the dark theme's background and surfaces with the faintest dark military green, so the page still reads as near-black and the green shows only beside pure black. Give the light theme's background and surfaces a matching faint tint that keeps the page reading as off-white. The tint never touches the status green's meaning, so check that done green stays clearly apart from the background and the neutral.
5. **Everywhere the palette lives.** Update design/tokens.css, the Tailwind mapping, Mermaid's theme, the social images in og.ts, the D2 diagram themes and their built SVGs through scripts/build-diagrams, and the theme-color meta tags. The Inspector imports design/tokens.css, so it follows. Don't edit dashboard/ (setup-1 owns it), and note anything there that looks wrong.
6. **Third-party libraries for all of it.**
   - **Palette.** Build it from a maintained palette library instead of hand-picked hex values. Radix Colors fits the site's shadcn/ui on Radix stack: its olive gray scale is a near-black with a faint green hint, and its sand and mauve scales are candidates for the neutral, beside its pink or crimson scale for the accent. Use the library's steps as published, or say which step you adjusted and why.
   - **Checks.** Run contrast and color blind checks with a color library such as Color.js or culori, not your own math.
   - **Motion.** The tab highlight's motion stays on Motion, for example its shared layout animation.
   - **Phone controls.** Any phone control you add or rebuild comes from shadcn/ui on Radix or Starlight, never hand-written markup.
   - **Records.** List every library, with its version, in your report and in docs/DEPENDENCIES.md.
7. **Checks.** AA contrast for every pair, with a table in your report. Color blind distances between the pink, the neutral, the background and the three status colors under protanopia, deuteranopia and tritanopia, with the method used in DESIGN.md. Then propose DESIGN.md's Color text in your report and don't edit DESIGN.md.

Load and use every installed skill that fits, at least frontend-design:frontend-design, design-taste-frontend, web-design-guidelines, ui-ux-pro-max:ui-ux-pro-max, ui-ux-pro-max:ui-styling, humanizer, playwright-cli and chrome-devtools-mcp:a11y-debugging. List in your report what you used and for what.

## Gates

Run Playwright and pytest one at a time, with at most 3 Playwright workers, and use preview ports 4451 to 4459 only (`OPENHAL_PREVIEW_PORT`). The machine is sometimes under heavy load, so rerun a failure alone before you treat it as real.

- `pnpm build` with zero warnings, and vitest.
- Playwright in Chromium, Firefox and WebKit for every spec your change touches, with axe at 0 violations in both themes, and the design-rules, scrollbar, how, chrome, controls, site and budget specs passing.
- `uv run pytest tests/website tests/docs`.
- Screenshots of every page at 375, 390 and 430 px in WebKit and at 1440 px in Chromium, in light and dark, plus the frames of the tab highlight through a move. Look at every one before you report. Save them by absolute path to /Users/sohanb/code/projects/openhal/qa/after/website-22/ and keep scratch in docs/design-rounds/website-22/.

## Files you own

website/ except the pages and tests setup-1 owns (the quickstart, install and CLI pages and their tests), design/tokens.css, docs/diagrams/ theme files and built SVGs, scripts/diagrams.py for colors only, and docs/DEPENDENCIES.md.

## Not yours

dashboard/ and openhal/ (setup-1 is changing both), the docs and pages setup-1 owns, firmware/, spec/, docs/DESIGN.md (propose), and docs/ other than your scratch folder and the diagram files above.
