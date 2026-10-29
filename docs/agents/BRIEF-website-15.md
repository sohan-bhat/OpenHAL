# Brief: the home page, simple and clean, and the full example on its own page

Read docs/agents/COMMON.md first, then the owner's brief, docs/agents/OWNER-BRIEF-2026-10-29.md, which is the contract for this work, then docs/DESIGN.md and website/ with its tests.

## Your part of the owner's brief

- Section 0.2 for your pages: before screenshots of the home page (full page), the docs index, a spec page and the Playground at 1440×900 and 390×844 in light and dark, saved to qa/before/.
- Section 0.3: read the design tokens and components first and reuse them.
- Sections 2, 3 and 4 in full: the hero with readable labels and no diagram, the deleted H, A and L sections, "How it works" in three steps with the owner's captions exactly as written, Safety model, What OpenHAL works with, Run the demo, Read more and the footer, then the new page /docs/examples/3d-print-watch/ with the nine-step story, printer.hal.yaml, every JSON-RPC message and the audit log entries, linked from the home page and the Quickstart. Add "What the name means" to docs/guide/concepts.md.
- Section 5.4 for your content: the deleted letter sections and the old nine-step home demo must not appear in the search index, and the new example page's code must not land in search snippets.
- Section 5.5: the Playground and the Run the demo link to the Playground still work.
- Sections 6 and 7 for everything you write or touch, and section 8 for your pages, with screenshots in qa/after/. The home page is 4 to 5 screens tall at 1440×900.
- Record the hero layout choice in DECISIONS.md.

The owner's own words: "Literally don't do anything crazy on the landing page, keep as simple and clean as possible." Every section of the home page must be plain, quiet and obvious at a glance. The "How it works" animation follows the scroll, uses Motion (Framer Motion, already in website/package.json), never traps the scroll, and does nothing showy.

## Working beside website-16

website-16 (BRIEF-website-16.md) runs at the same time. It owns the docs frame, the header, the search, the sidebar, the pickers and the stack setup (Tailwind, React islands, shadcn/ui and Motion for those parts). Stay out of those. If website-16 sends you a commit with Tailwind set up, you may use Tailwind classes for the home page's new sections, but you don't have to.

## Gates

`pnpm build` with zero warnings, vitest, Playwright in Chromium and Firefox with axe at 0 violations, the budget test (new baselines only where the change needs them, explained), `uv run pytest tests/docs tests/website tests/demo`, the build under /OpenHAL/, and Lighthouse three times on mobile and desktop for home and the example page. Run Playwright and pytest one at a time.

## Files you own

website/src/pages/index.astro, website/src/components/landing/, website/src/lib/story/, website/src/styles/story.css, the new example page and its components, docs/guide/concepts.md, docs/guide/quickstart.md (the link only), DECISIONS.md (the hero entry), the home page's and the example page's tests, qa/ and the landing rows of docs/verification/ui.md.

## Not yours

The header, the search, the sidebar, the pickers, Starlight overrides other than the example page's content, astro.config.mjs (ask website-16 through the orchestrator for config changes), openhal/, spec/ and dashboard/.
