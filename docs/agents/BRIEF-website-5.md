# Brief: the landing page, for people

Read docs/agents/COMMON.md first, then docs/DESIGN.md and website/. Load the skills frontend-design:frontend-design, design-taste-frontend, web-design-guidelines and playwright-cli before UI work.

## What the owner said

"Right now the landing page is built like if an AI bot is going through it. It is like a word soup. You need to present the information as to a consumer, imagine you." And "as you are scrolling through the landing page it should animate smoothly, not text appearing animations but like how Apple does it, kind of what you did for Taro."

## Goal

Rebuild the landing page (website/src/pages/index.astro and what it uses) for a person seeing OpenHAL for the first time. Every other page stays as it is.

1. **One idea per screen, few words.** The hero is the wordmark, the one-line description ("An open-source protocol for AI agents to control hardware.") and one call to action. After that each section says one thing in a short sentence and shows it. No walls of JSON, no lists of nouns, no paragraph that explains what a picture already shows. Plain words a maker would use. Defined protocol terms can wait for the docs.
2. **A scroll story, the centerpiece.** A pinned stage plays the plant waterer story as the visitor scrolls, the way Apple product pages and the Taro landing page do. Read ~/code/taro/apps/web/src/components/landing/story.tsx and its scene/ folder (the owner's own code, so reuse the ideas freely). A sticky stage stays put while scroll position drives story time, a camera moves and zooms across a scene, and pieces change with that time through a CSS variable. Write it for this site in Astro with a small script or a Svelte island.
   - The story is the trace in docs/demo/scenario.yaml, told visually. An AI asks to water for 120 s. The safety kernel stops it, because the confirmed limit is 30 s. The tank reads empty, and the kernel holds the pump. The tank is refilled, the plant gets 20 s, and soil moisture climbs from 31 % to 46 % on a live readout.
   - The camera travels along the real path: AI client, hub, safety kernel, driver, then the Arduino plant waterer. Show each step with the real words from the scenario (LIMIT_EXCEEDED, INTERLOCK_BLOCKED, done) in small mono where they help, never as JSON blocks.
   - Motion is tied to scroll and is smooth (transforms and opacity, requestAnimationFrame, no layout thrash). No fade-up-as-you-scroll text effects, no parallax gimmicks and no particles.
   - With prefers-reduced-motion, or without the script, it is a clean static sequence of the same steps. It works on phones, where the stage fits the screen.
   - Numbers come from docs/demo/scenario.yaml through the existing scenario helpers, so tests/docs/test_scenario_docs.py and the site's tests keep holding.
3. **Then only what a person needs next.**
   - Try it: the three commands from the README quickstart and a link to the Playground.
   - What it works with: device families in a compact form, with a link to the full drivers page.
   - Why it's safe: three short points at most (limits a person confirmed, one STOP, everything logged).
   - Links to the spec and the docs.
   Drop anything that repeats.
4. **Keep the theme.** The protocol theme in docs/DESIGN.md, the tight text wordmark (no logo), Atkinson Hyperlegible Next and Mono, cool neutrals with one cobalt accent, red only for blocked. No green status dots anywhere. Light and dark.

## Gates

`pnpm build` with zero warnings, vitest, Playwright in Chromium and Firefox with axe at 0 violations, and Lighthouse on the landing page at 100 for accessibility, best practices and SEO and 95 or more for performance on mobile, with no layout shift. Also `uv run pytest tests/docs tests/website tests/demo` (use `export PATH="$HOME/Library/Python/3.13/bin:$PATH"`). Screenshot the landing page at 390, 768 and 1440 px in both themes, and record a short scroll-through video of the story at 1440 and 390 with playwright-cli. Put them in your scratch folder and name the paths in your report.

## Files you own

website/src/pages/index.astro, new components for the landing page, website/src/styles/ where the landing page needs it, the landing page's tests, and docs/verification/ui.md.

## Not yours

Every other page, docs/DESIGN.md (propose changes to its Motion section in your report, since the owner asked for this scroll motion), the README and everything else.
