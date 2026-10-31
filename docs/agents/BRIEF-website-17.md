# Brief: the documentation sidebar on shadcn/ui's Sidebar, with no show sidebar button and no peek

Read docs/agents/COMMON.md first, then docs/DESIGN.md (Layout from "Third-party first", "The sidebar", and Motion pattern 8), then the current sidebar: website/src/components/starlight/Sidebar.astro, website/src/components/islands/SidebarControls.tsx, website/src/lib/sidebar.ts, the sidebar rules in website/src/styles/starlight.css, website/src/components/starlight/Head.astro, website/src/directives/ and the sidebar tests in website/tests/e2e/.

## What the owner said

On 2026-10-30 the owner sent a screenshot of the spec page with the sidebar hidden and its hover panel open over the content, cutting off the start of every line, and wrote: "sidebar poor, remove that show sidebar button AND USE AN EXTERNAL SIDEBAR THING FROM BOOTSTRAP OR REACT". Earlier the owner asked for a collapsible sidebar ("u still didnt make the collapsable thingy") and rejected hand-built ones twice ("making this from scratch does not feel nice, it comes out too much when it is expanded").

## Goal

1. **Remove the hand-built parts.** Delete the Hide sidebar and Show sidebar buttons (SidebarControls.tsx), the hover peek panel, the left-edge dwell logic in lib/sidebar.ts, their CSS, the parts of the head script that only serve them, and their tests. No button anywhere shows or hides the sidebar.
2. **Build the sidebar on shadcn/ui's Sidebar.** Add shadcn/ui's Sidebar component (React, on Radix) with the shadcn CLI, the way website/src/components/ui/ already holds Button, Dialog and the rest (components.json is set up). Add shadcn's Collapsible for the groups, pin exact versions, and record the component's popularity and last release. Use the component's own structure and behavior: SidebarProvider, Sidebar, SidebarContent, SidebarGroup, SidebarMenu, SidebarMenuItem, SidebarMenuButton, SidebarMenuSub and SidebarRail.
   - **Theme.** Map the component's sidebar CSS variables onto design/tokens.css so the sidebar reads like the site in both themes. Rows show words only, with no icons except a group's chevron. The current page sits on the nav's blue highlight, and the type sizes and spacing match the current sidebar.
   - **Collapse.** Use the component's own off-canvas collapse, toggled by its SidebarRail and by its Command or Control and B shortcut. The rail is the thin hit area on the sidebar's edge that shows a line and a resize cursor on hover, and it stays at the window's left edge while the sidebar is collapsed. Don't use SidebarTrigger or any other button.
     - The content and the outline move over to use the space, and the browser keeps the choice.
     - The state applies before the first paint, with no layout shift.
     - With reduced motion, nothing slides.
   - **Never cover the content.** The sidebar never covers the content at any width, and nothing peeks or floats over text.
   - **Phone menu.** Under 800 px the phone menu works as it does now, with the sections first, then the section's pages, then the version and the theme at its foot. Keep Starlight's phone menu or use the component's own mobile Sheet, whichever reads better, and say why.
   - **Keep Starlight's frame.** The header, outline, search and pagination stay Starlight's.
     - The sidebar's links come from the same Starlight route data as now, so every page keeps the same items, order, numbers, badges and current-page state.
     - Pages without a sidebar still have none.
   - **Without JavaScript and loading.** Links work without JavaScript. Load React for the sidebar as late as its use allows. The existing client:intent directive replays a press that arrives while an island loads, and the shortcut has to work on the first press.
3. **Study first.** Look at how shadcn's own docs and blocks (sidebar-01 and sidebar-07, for example) use the rail and the shortcut, and record what you chose and why.
4. **Propose the design text.** Propose new wording for docs/DESIGN.md's sidebar paragraph (Layout, "The sidebar") and Motion pattern 8 in your report. Don't edit DESIGN.md.

Load and use every installed skill that fits: vercel:shadcn, ui-ux-pro-max:ui-styling, frontend-design:frontend-design, design-taste-frontend, web-design-guidelines, playwright-cli and chrome-devtools-mcp:a11y-debugging. Use the context7 tools for shadcn/ui's Sidebar documentation. List in your report what you used and for what.

## Gates

Run Playwright and pytest one at a time.

- `pnpm build` with zero warnings, and vitest.
- Playwright in Chromium and Firefox, with axe at 0 violations with the sidebar expanded, with the sidebar collapsed and with the phone menu open.
- The budget test. Set new baselines only where the change needs them, and explain each one.
- Lighthouse three times each, on mobile and desktop, for docs, a spec page and the Playground. Mobile scores 98 or more, desktop scores 100, and there is no layout shift.
- Screenshot the docs index and a spec page at 1440 and 390 px, in light and dark, with the sidebar expanded and collapsed. Record a short video of the collapse and the expand at 1440 px.
- Look at every screenshot and video before you report.
- Save screenshots to qa/after/sidebar/ and keep scratch in docs/design-rounds/website-17/.

## Files you own

website/ except website/src/content/generated/. That covers the shadcn components, the sidebar, the Starlight overrides, the head script, the styles and the website's tests.

## Not yours

openhal/, spec/, dashboard/, docs/ other than your scratch folder, and docs/DESIGN.md (propose).
