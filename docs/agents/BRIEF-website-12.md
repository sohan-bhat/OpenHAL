# Brief: the docs on Astro Starlight, with a proven sidebar, version picker and header

Read docs/agents/COMMON.md first, then docs/DESIGN.md and website/ with its tests. Load the skills frontend-design:frontend-design, design-taste-frontend, web-design-guidelines and playwright-cli before UI work.

## What the owner said

About the hand-built collapsible sidebar: "You need to find an online third party thing that is popular for this type of sidebar, since making this from scratch does not feel nice, like it comes out too much when it is expanded." About the version picker: "Same for this versioning toolkit. Also for versioning don't use date, use v.XX or whatever the format is." About the header: "Same thing for this whole top bar honestly. Learn how to steal from the best and invent the rest."

## Goal

1. **Starlight as the base.** Rebuild the documentation, specification, drivers, library, SDK and Playground pages on Astro Starlight, the most widely used docs framework for Astro, at its latest stable release. Starlight's header, sidebar, table of contents, search (Pagefind), pagination and mobile menu become the base, themed with design/tokens.css and DESIGN.md. Keep the text wordmark with no logo, Atkinson Hyperlegible Next and Mono, cool neutrals with the cobalt accent and the dulled status colors. Allow no status shapes, no tinted or color-bordered status boxes and no shadows. Remove the hand-built sidebar collapse, version picker and header.
2. **One header on every page.** The home page uses the same header as every Starlight page, through Starlight's splash template or its header component, so nothing moves between pages. Keep the top-level sections (Overview, Docs, Specification, Playground, Drivers, Device Library and GitHub) in the header, arranged the way the best docs top bars do it. Look at Starlight sites such as the Astro, Cloudflare and Biome docs, and at Docusaurus, Vercel and Stripe docs, then keep the current section highlighted.
3. **The sidebar.** Use Starlight's sidebar with collapsible groups. To hide the whole sidebar, use a maintained Starlight plugin if a popular one exists. Check npm downloads, GitHub stars and the last release, and record what you found. If none is solid, ship Starlight's standard sidebar without whole-sidebar hiding, because a proven sidebar beats the hand-built one the owner rejected.
4. **The version picker.** Show semantic versions only, such as v0.1. Use the most popular maintained Starlight versioning plugin (starlight-versions) if it fits. Otherwise use a widely used pattern such as Docusaurus's version dropdown. The picker sits in the header. The spec's versions come from spec/versions.json, which a parallel round (spec-semver, BRIEF-spec-semver.md) changes from 2026-10-24 to 0.1. Merge its commit when the orchestrator sends it. Old /spec/2026-10-24/ URLs redirect to the matching v0.1 pages.
5. **Keep** the home page's own content and behavior (the hero, the wordmark sequence, the landing story and the sections), the Playground's Svelte island inside a Starlight page, every existing URL (with redirects where a page moves), search snippets without code, reduced motion and accessibility. Keep the page transition and the nav highlight slide if they fit Starlight cleanly. If they don't, Starlight's behavior wins, so say so.
6. **Copy** follows Copy voice. Starlight's own interface strings, such as "On this page", "Next" and "Previous", are fine. Starlight's asides must not be tinted or color-bordered, so style them neutral or avoid them.

## Gates

`pnpm build` with zero warnings, vitest, Playwright in Chromium and Firefox with axe at 0 violations, the budget test (set new baselines honestly and explain each one), the build under /OpenHAL/ the way the Pages workflow builds it, and Lighthouse three times each on mobile and desktop on the home page, docs, a spec page, drivers, the Playground and the Python reference: 98 or more on mobile, 100 on desktop and no layout shift. Screenshot the header, the sidebar, the version picker open and the home page at 1440, 1024 and 390 px in light and dark, and record a short video of the sidebar and the picker. Look at every shot before you report. Keep them in docs/design-rounds/website-12/ inside your worktree. Run Playwright and pytest one at a time.

## Files you own

website/ and docs/verification/ui.md.

## Not yours

openhal/, spec/ (the spec-semver round changes it), dashboard/ and docs/DESIGN.md (propose new wording for Layout, the header, the sidebar, the version picker and Motion).
