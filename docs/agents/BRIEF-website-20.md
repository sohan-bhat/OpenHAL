# Brief: every control on the website from a library, starting with the catalog filters

Read docs/agents/COMMON.md first, then docs/DESIGN.md (Layout, Color, Motion, Banned), website/src/styles/global.css, starlight.css and how.css, website/components.json, every file in website/src/components/ui/, and the pages and components listed under Files you own.

## What the owner said

On 2026-11-01 the owner sent a screenshot of the Drivers page filters (a Filter text field and the Tier, Conformance and Hazard selects) and wrote, word for word.

> for these use the react dropdowns or whatever, yk what just use react components for everything or third party libraries, there should be no component that is self written

The owner's standing rule is to use proven libraries for almost every element, Starlight, Tailwind, shadcn/ui on Radix, cmdk and Motion, and to build what no plugin covers from those libraries.

## Goal

1. **The catalog filters.** The Drivers page (website/src/pages/drivers/index.astro) and the Device Library page (website/src/pages/library/index.astro) filter with a React island built from shadcn/ui's Input, Label and Select on Radix. The Select's trigger, list, check mark and keyboard behavior come from the component. The rows still filter as they do now, the result count still reads "34 drivers." and announces in a live region, and the choices still sit in the URL so a filtered view can be shared. With no JavaScript the full table shows and nothing breaks.
2. **No hand-written control anywhere on the site.** Audit every page and component you own and replace each hand-written control with a library component.
   - Buttons are shadcn/ui's Button, inputs Input, selects Select, switches Switch, tabs Tabs, disclosures Collapsible, overlays Popover, HoverCard, Tooltip or Dialog, menus DropdownMenu, and data tables shadcn/ui's Table. The primitives are already in website/src/components/ui/. Add more with `pnpm dlx shadcn@latest add`, and fix any import the CLI writes as `from "cn"` to `from "@/lib/utils"` and remove a `cn` package it adds.
   - That covers at least the catalog filters and tables, the Smooth scrolling switch and the Skip link's control in How it works (keep the switch's behavior, its stored choice and its reduced motion rule), Previous and Next on the 3D print example, the verification badge, the Inspector screenshots' controls, the version, theme and section pickers' server-rendered fallbacks and every native `<select>`, `<input>`, `<button>`, `<details>` and `<dialog>` outside components/ui.
   - The Playground is not yours. website-21 is moving it to React at the same time.
3. **Content renderers.** The message trace, the How it works diagram, the example's sequence diagram and webcam frame and the hero are OpenHAL's own content, not controls. Build each one on library primitives where one fits, such as Expressive Code for a code block or Motion for movement, and keep a hand-built renderer only where no library draws it. List each one you keep in your report with the libraries you tried and why each falls short. Don't change how any of them looks or moves.
4. **Looks.** The new components take the site's tokens and look like the site, flat, no shadows, no gradients, 1.5 px control outlines, `--accent` focus rings and selected rows on `--surface`. A Select's open list matches the pickers' lists (DESIGN.md, Layout). Use token names only, never hex values. The orchestrator is changing the accent's hue to pink in design/tokens.css at the same time, with the same token names.
5. **Propose the design text.** Propose DESIGN.md wording for the components in your report. Don't edit DESIGN.md.

Load and use every installed skill that fits, at least vercel:shadcn, ui-ux-pro-max:ui-styling, frontend-design:frontend-design, design-taste-frontend, web-design-guidelines, playwright-cli and chrome-devtools-mcp:a11y-debugging. Use the context7 tools for shadcn/ui, Radix and Astro islands documentation. List in your report what you used and for what.

## Gates

Run Playwright and pytest one at a time, with at most 3 Playwright workers, and use preview ports 4401 to 4409 only (`OPENHAL_PREVIEW_PORT`). The machine is often under heavy load, so rerun a failure alone before you treat it as real.

- `pnpm build` with zero warnings, and vitest.
- Playwright in Chromium and Firefox for every spec your change touches, with axe at 0 violations in both themes, including a Select open and a filtered table.
- Keyboard checks for every new control (Tab order, Enter, Space, the arrow keys and Escape).
- `uv run pytest tests/website tests/docs`.
- Screenshots of the Drivers page with a Select open, the Device Library page, How it works, the example's Previous and Next and every other page you changed, at 1440 and 390 px in light and dark. Look at every one before you report. Save them by absolute path to /Users/sohanb/code/projects/openhal/qa/after/website-20/ so they outlive your worktree, and keep scratch in docs/design-rounds/website-20/.

## Files you own

website/, except the Playground (website/src/components/playground/, website/src/pages/spec/playground.astro and the Playground's tests), design/tokens.css, the scrollbar and scroll lock rules at the end of website/src/styles/global.css, website/src/lib/markdown/mermaid.mjs and website/src/content/generated/.

## Not yours

The Playground (website-21), dashboard/ (inspector-6), design/tokens.css and the scrollbar rules (orchestrator), openhal/, spec/, docs/ other than your scratch folder, and docs/DESIGN.md (propose).
