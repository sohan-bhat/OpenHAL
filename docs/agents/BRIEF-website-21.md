# Brief: the Playground in React on shadcn/ui, with no hand-written control

Read docs/agents/COMMON.md first, then docs/DESIGN.md (Signature elements, Theme mapping, Layout, Color, Banned), website/components.json, every file in website/src/components/ui/, website/src/components/playground/ (Playground.svelte, TraceList.svelte, InfoMark.svelte), website/src/pages/spec/playground.astro, the Playground's library code and its tests in website/tests/.

## What the owner said

On 2026-11-01 the owner wrote, word for word.

> for these use the react dropdowns or whatever, yk what just use react components for everything or third party libraries, there should be no component that is self written

The owner's standing rule is to use proven libraries for almost every element, Starlight, Tailwind, shadcn/ui on Radix, cmdk and Motion, and to build what no plugin covers from those libraries. The rest of the site is already React islands on shadcn/ui, and the Playground is the one Svelte island left.

## Goal

1. **One stack.** Port the Playground from Svelte to a React island built from shadcn/ui on Radix. Every control is a library component, the client picker a Select or DropdownMenu, Send a Button, the information marks Popover or HoverCard, any tabs Tabs and every text field Input or Textarea. The primitives are already in website/src/components/ui/. Add more with `pnpm dlx shadcn@latest add`, and fix any import the CLI writes as `from "cn"` to `from "@/lib/utils"` and remove a `cn` package it adds.
2. **The editor.** The request editor uses a proven editor library, such as CodeMirror 6 through a maintained React wrapper, with JSON highlighting in the house syntax theme (DESIGN.md, Syntax theme) built from the tokens, line numbers off unless the current Playground shows them, and the same keyboard behavior a text field has today (Tab leaves the editor, so a keyboard user never gets trapped). Keep the bundle lean and load the editor only on the Playground.
3. **Same behavior.** Everything the Playground does today still works the same way, the simulated hub, the trace list with its inline SVG arrows, the kernel's answers, the demo labels, the recorded examples and every message, word for word. Keep the Playground's look. Move the trace list onto library primitives where one fits, and list in your report anything you keep hand-built with the libraries you tried and why each falls short.
4. **No Svelte left on the website.** Remove @astrojs/svelte, svelte and the Svelte config from website/ once nothing uses them. The Inspector in dashboard/ stays Svelte and is not yours.
5. **Looks.** Flat, no shadows, no gradients, 1.5 px control outlines, `--accent` focus rings and the primary Send button on `--accent-fill` with `--on-accent` text. Use token names only, never hex values. The orchestrator is changing the accent's hue to pink in design/tokens.css at the same time, with the same token names.
6. **Propose the design text.** Propose any DESIGN.md wording in your report. Don't edit DESIGN.md.

Load and use every installed skill that fits, at least vercel:shadcn, vercel:react-best-practices, ui-ux-pro-max:ui-styling, frontend-design:frontend-design, design-taste-frontend, web-design-guidelines, playwright-cli and chrome-devtools-mcp:a11y-debugging. Use the context7 tools for shadcn/ui, Radix, CodeMirror and Astro islands documentation. List in your report what you used and for what.

## Gates

Run Playwright and pytest one at a time, with at most 3 Playwright workers, and use preview ports 4411 to 4419 only (`OPENHAL_PREVIEW_PORT`). The machine is often under heavy load, so rerun a failure alone before you treat it as real.

- `pnpm build` with zero warnings, and vitest, with the Playground's unit tests ported.
- Playwright in Chromium and Firefox for the Playground and every spec that loads it (design-rules, a11y, interactions, budget), with axe at 0 violations in both themes. Set a new budget baseline only where the change needs it and explain it.
- Keyboard checks for every control and for leaving the editor with Tab.
- `uv run pytest tests/website tests/docs`.
- Screenshots of the Playground before and after a Send, with a picker open and with an information mark open, at 1440 and 390 px in light and dark. Look at every one before you report. Save them by absolute path to /Users/sohanb/code/projects/openhal/qa/after/website-21/ so they outlive your worktree, and keep scratch in docs/design-rounds/website-21/.

## Files you own

website/src/components/playground/ (replace it with the React version), website/src/pages/spec/playground.astro, the Playground's library code and tests, new files in website/src/components/ui/, and website/package.json, pnpm-lock.yaml and astro.config.mjs for the editor and the Svelte removal only.

## Not yours

Every other page and component on the website (website-20 is moving them onto library components at the same time), dashboard/, design/tokens.css, the scrollbar rules at the end of website/src/styles/global.css, openhal/, spec/, docs/ other than your scratch folder, and docs/DESIGN.md (propose).
