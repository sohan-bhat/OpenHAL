# Brief: the Inspector on shadcn-svelte, with no hand-written control

Read docs/agents/COMMON.md first, then docs/DESIGN.md (The Inspector, Color, Layout, Motion, Banned), design/tokens.css, dashboard/src/app.css and every file in dashboard/src/components/ and dashboard/src/views/, and the Inspector's tests in dashboard/ and tests/inspector/.

## What the owner said

On 2026-11-01 the owner wrote, word for word.

> for these use the react dropdowns or whatever, yk what just use react components for everything or third party libraries, there should be no component that is self written

The owner's standing rule is to use proven libraries for almost every element and to build what no plugin covers from those libraries. The website uses shadcn/ui on Radix. The Inspector is Svelte 5, so its counterpart is shadcn-svelte on bits-ui.

## Goal

1. **Library controls.** Set up shadcn-svelte on bits-ui in dashboard/ with Tailwind 4 through its Vite plugin, without Preflight, mapped to the tokens in design/tokens.css the way website/src/styles/global.css maps them. Replace every hand-written control with its component. Buttons are Button, text fields Input and Textarea, selects Select, checkboxes Checkbox, switches Switch, sliders Slider, tabs Tabs, dialogs and confirmations Dialog or AlertDialog, tooltips Tooltip, menus DropdownMenu and data tables Table. That covers at least ActionControl, WriteControl, StopControl, LimitScale, MessageLog, Header, DeviceList, CameraFrame and every view (Audit, Confirmations, Device, Pair, Routines, Settings, Writer).
2. **Safety first.** STOP, UNLOCK, approve and reject keep exactly the behavior, wording, focus order, confirmation steps and keyboard reach they have today. The STOP control stays reachable from every view in one key press or click. Never weaken a safety requirement (Part 7) to fit a component. Where a component can't hold a safety behavior, keep the behavior and report the gap.
3. **Content renderers.** The message log's traces, the JSON view, the camera frame and the status words are the Inspector's own content. Build each one on library primitives where one fits and keep a hand-built renderer only where no library draws it. List each one you keep in your report with the libraries you tried and why each falls short.
4. **Looks.** Flat, no shadows, no gradients, 1.5 px control outlines, `--accent` focus rings, primary actions on `--accent-fill` with `--on-accent` text, selected rows on `--surface`, blue only for pending, green for done and red for blocked. Use token names only, never hex values. The orchestrator is changing the accent's hue to pink in design/tokens.css at the same time, with the same token names.
5. **The bundle.** After your last change run `cd dashboard && pnpm build`, which writes the bundle into openhal/hub/static/, and commit the bundle as its own commit.
6. **Propose the design text.** Propose DESIGN.md wording for The Inspector in your report. Don't edit DESIGN.md.

Load and use every installed skill that fits, at least ui-ux-pro-max:ui-styling, frontend-design:frontend-design, design-taste-frontend, web-design-guidelines, playwright-cli and chrome-devtools-mcp:a11y-debugging. Use the context7 tools for shadcn-svelte, bits-ui, Svelte 5 and Tailwind 4 documentation. List in your report what you used and for what.

## Gates

Run Playwright and pytest one at a time, with at most 3 Playwright workers, and use ports 4421 to 4429 only for any server you start. The machine is often under heavy load, so rerun a failure alone before you treat it as real.

- `pnpm build` in dashboard/ (svelte-check with warnings as errors, then Vite) and its vitest.
- The Inspector's end-to-end and axe tests in Chromium and Firefox, with axe at 0 violations in both themes, with a dialog, a select and a tooltip open.
- `uv run pytest tests/inspector tests/hub` and the full gates in COMMON.md.
- Keyboard checks for every control, STOP and UNLOCK first.
- Screenshots of every view at 1440 and 390 px in light and dark, plus STOP, an approval dialog and an open select. Look at every one before you report. Save them by absolute path to /Users/sohanb/code/projects/openhal/qa/after/inspector-6/ so they outlive your worktree, and keep scratch in docs/design-rounds/inspector-6/.

## Files you own

dashboard/, openhal/hub/static/ (the built bundle only) and tests/inspector/.

## Not yours

website/, design/tokens.css (orchestrator), openhal/ other than the bundle, spec/, docs/ other than your scratch folder, and docs/DESIGN.md (propose).
