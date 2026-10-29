# Brief: the docs frame on a proven component stack, a good collapsible sidebar and a good search

Read docs/agents/COMMON.md first, then the owner's brief, docs/agents/OWNER-BRIEF-2026-10-29.md, including the owner's two notes at its top, then docs/DESIGN.md (Layout starts with "Third-party first") and website/ with its tests.

## What the owner said

"You still didn't make the collapsable thingy. Also you are not using the plugins I gave you, use all plugins installed, search up how to make good collapsable side bar." Then: "For almost every element use a framework or third party plugin. This whole search window is very bad. There should also be some animation for the search bar, use third party, like framer motion for animations and tailwind or something."

## Goal

1. **Deploy pipeline (owner's brief, section 0.1).** Check git against origin, the Pages workflow's last runs, and the live home page's HTML against a local build. Write what you find in DEPLOY_NOTES.md at the repository root. If the pipeline works and the owner saw an old page, say so plainly, find the cause (for example GitHub Pages' 10 minute cache, a prerendered page or a stale tab), and add whatever makes a fresh deploy show up reliably.
2. **The stack.** Add Tailwind CSS through Starlight's official Tailwind integration, React through @astrojs/react, and shadcn/ui components (Radix primitives, copied into the repository the way shadcn/ui works) themed with design/tokens.css. Use Motion's React API (Framer Motion) for their animation. Tailwind's base layer must not change how any existing page looks, so compare screenshots before and after. Pin exact versions and check each library's popularity and maintenance first.
3. **A good search.** Replace Starlight's search dialog with a command palette built on cmdk (shadcn/ui's Command and Dialog), querying the site's Pagefind index through Pagefind's JavaScript API. It needs:
   - result groups by section
   - highlighted matches
   - the keyboard flow of the best palettes (Cmd or Ctrl K, the arrow keys, Enter and Escape)
   - recent searches
   - an empty state
   - an animated open and close with Motion
   Look at the search palettes of Vercel, Linear, Raycast and the shadcn/ui docs first. Snippets never show code or YAML (owner's brief, section 5.4).
4. **A good collapsible sidebar.** Search the web for how the best products build one, such as shadcn/ui's Sidebar (offcanvas collapse, the rail, Cmd or Ctrl B, the persisted state), Fumadocs' collapsible sidebar with a hover peek, Arc, Linear and Notion. Then build the documentation sidebar's collapse the best way you find, from those components and Motion, inside Starlight's frame.
   - The sidebar hides and shows with a quick, smooth animation, and the content moves over to use the space.
   - While the sidebar is hidden, a pointer resting at the left edge brings the sidebar in temporarily, and the sidebar leaves when the pointer does. The owner said the last hand-built version "comes out too much when it is expanded", so make the peek feel light, for example a narrower inset panel that opens after a short dwell.
   - The choice persists, the keyboard works, and with reduced motion nothing slides.
   Record what you studied and why you chose your design.
5. **Pickers and the theme switch.** While spec/versions.json lists one version, the version shows as a plain label "v0.1" linking to the spec's Versions section, and it becomes a dropdown on its own once two versions exist (owner's brief, section 5.1). The theme switch and any remaining picker use shadcn/ui's dropdown (Radix) with Motion. Replace the hand-written Picker.astro and the vanilla motion code from round 14 with these components.
6. **The rest of the owner's brief section 5.**
   - Hide the "On this page" rail on pages with fewer than two h2 headings, and let the content use the space (5.2).
   - Remove the number from the spec page's h1, and check the sidebar's numbers still match the sections (5.3).
   - Search snippets carry no code or YAML, and the Playground and Concepts results are clean (5.4).
7. **Use the installed tools.** Load and use every installed skill that fits:
   - frontend-design:frontend-design
   - design-taste-frontend
   - web-design-guidelines
   - ui-ux-pro-max:ui-ux-pro-max
   - ui-ux-pro-max:ui-styling
   - ui-ux-pro-max:design-system
   - vercel:shadcn
   - playwright-cli
   - chrome-devtools-mcp:a11y-debugging
   - chrome-devtools-mcp:debug-optimize-lcp
   Use the context7 tools for current library documentation and WebSearch for the sidebar and search research. List in your report which ones you used and for what.

## Gates

`pnpm build` with zero warnings, vitest, Playwright in Chromium and Firefox with axe at 0 violations with the palette, the sidebar peek and each menu open, the budget test (set new baselines honestly and explain each), the build under /OpenHAL/, and Lighthouse three times on mobile and desktop for docs, a spec page and the Playground: 98 or more on mobile, 100 on desktop, no layout shift. Load the React islands as late as their use allows. Record videos of the search palette, the sidebar's collapse and peek and the pickers at 1440 and 390 px, screenshot the header and a docs page in light and dark, and look at every one before you report. Save screenshots to qa/after/ (the docs frame) and keep scratch in docs/design-rounds/website-16/. Run Playwright and pytest one at a time.

## Files you own

website/ except what website-15 owns (BRIEF-website-15.md): the home page, the landing components, the story library and styles, and the new example page. You also own astro.config.mjs, website/package.json, the Starlight overrides, the search, the sidebar, the pickers, DEPLOY_NOTES.md, .github/workflows/pages.yml if the deploy needs a fix, and the docs frame rows of docs/verification/ui.md.

## Not yours

The home page and the example page (website-15), openhal/, spec/, dashboard/ and docs/DESIGN.md (propose).
