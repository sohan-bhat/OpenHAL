# Brief: the top of the home page, and the drop into the wordmark sequence

Read docs/agents/COMMON.md first, then docs/DESIGN.md ("The wordmark sequence", "The landing story", Motion patterns 4 and 7, "Copy voice") and website/ with its tests. Load the skills frontend-design:frontend-design, design-taste-frontend, web-design-guidelines and playwright-cli before UI work.

## What the owner said

"If I am scrolled all the way to the top it should still show this [the demo's opening: the row with 9 steps, Skip the demo and the Smooth scrolling switch, the title 'An agent watches a 3D print through the OpenHAL hub.' and the start of the lifelines], but right when the user scrolls it should drop down and start the transition into [the large wordmark alone, pinned, the first frame of the wordmark sequence]."

Before the wordmark sequence existed, the top of the home page showed the hero and, under the hero, the demo's opening, so a visitor saw the demo and its controls without scrolling. The sequence now sits between the two, so the top shows the hero and empty space.

## Goal

1. **At the very top**, the first screen shows the hero (the wordmark with its [hardware], [agent] and [layer] labels, the one-line description and Get started) and, under the hero, the demo's opening as far as the screen allows: the row with the step count, Skip the demo and the Smooth scrolling switch, the title and the lifeline names. The switch works from this first screen.
2. **The moment the visitor scrolls**, the demo's opening drops down and out of view while the description, Get started and the labels fade and the wordmark drops into the pinned stage. Then the H, A and L steps play as they do now. After L the stage releases, the demo's opening comes back into place, and the story plays from step 1. Everything follows the scroll, nothing moves on its own, and scrolling back up plays all of it in reverse until the first screen looks exactly as it did on load.
3. **Scrolling back to the top lands at 0.** With smooth scrolling on, wheel and trackpad scrolling up past the top currently stops at about 3 px and leaves the description at about 96 % opacity. The page must land at 0 with every hero element at full opacity.
4. **Keep** everything else in the sequence and the story as it is, including the briefs, the captions, the nine steps, the reduced-motion list, the HAL labels test and the 1360 px home column that website-10 is introducing. With reduced motion or no script, the top shows the hero, then the three briefs, then the demo as a list, with nothing animating.

## Gates

`pnpm build` with zero warnings, vitest, Playwright in Chromium and Firefox with axe at 0 violations, the scroll smoothness check from docs/verification/ui.md, the budget test, the build under /OpenHAL/ and `uv run pytest tests/docs tests/website tests/demo`. Lighthouse on the home page, three runs each on mobile and desktop, no worse than main, with no layout shift. Screenshot the first screen at 1440x900, 1366x768, 1280x720 and 390x844 in light and dark, plus frames 40, 150 and 400 px into the scroll at 1440 and 390, and record a scroll video from the top through L and into step 1 and back up to the top. Keep them in docs/design-rounds/website-11/ inside your worktree and name the full absolute paths in your report. Run Playwright and pytest one at a time.

## Files you own

website/src/pages/index.astro, website/src/components/landing/, website/src/lib/story/, website/src/styles/story.css, the home page's tests and the landing section of docs/verification/ui.md.

## Not yours

Header.astro, Footer.astro, Base.astro, DocShell.astro, VersionSwitcher.astro and global.css, which website-10 owns, every other page, docs/, openhal/ and dashboard/.
