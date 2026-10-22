# Brief: website (M8)

## Goal

Build the OpenHAL website in `website/` as a static Astro site, to the spec below. The website is top priority, equal to the core. It must look like a strong studio made it for this exact product, and every fact on it must come from the repository.

Read first, in this order. docs/DESIGN.md (binding), design/tokens.css and design/fonts/ (frozen, import them, don't fork them), docs/adr/0009 (Astro), docs/research/OPENHAL_RESEARCH.md (positioning), spec/SPEC.md, docs/SAFETY.md, docs/ARCHITECTURE.md, docs/interfaces/CLI.md, docs/interfaces/MCP.md, docs/interfaces/PYTHON.md, drivers/catalog.json, openhal/kernel/kernel.py and openhal/kernel/checks.py (for the TypeScript port).

Load the design skills before any UI work. Use `frontend-design:frontend-design`, `design-taste-frontend`, `web-design-guidelines` and `playwright-cli`.

## Pages and features

1. **Landing page.**
   - The one-line pitch.
   - A hero that shows the real product blocking an unsafe command. Until the dashboard exists (another workstream builds it in parallel), the hero is a live limit line demo driven by your TypeScript kernel port, using the desk fan from spec/examples. It shows a real block message, labeled as an in-browser demo. Build the hero so a dashboard capture can replace or sit beside it later. Captures will be PNG and WebM files at `website/public/captures/`, and the orchestrator supplies them.
   - The 30-second demo as a scroll-driven storyboard. Its steps are data in `website/src/content/demo/steps.json`, each with a caption, the real CLI or MCP text for that step, and an optional capture path. Generate the text from the real CLI against an embedded mock hub (see Tested snippets). Leave the capture paths empty until captures exist, and render text-only frames meanwhile.
   - How it works, in three steps.
   - The safety model in plain language.
   - Supported devices (from the catalog).
   - How it relates to MHS. Say it in this voice, as separate sentences. "MHS is for labs, in a closed preview. OpenHAL is open and works today. We plan to be compatible." Facts about MHS come from docs/research only.
   - A quickstart with real commands.
   - No fake stats, testimonials or logos.
2. **Device file playground.**
   - Edit a `.hal.yaml` in the browser and validate it live against `spec/schema/device-file.schema.json`, imported at build time and never copied by hand.
   - Preview the generated dashboard controls, with the limit line drawn on every limited control.
   - A "try to break the limits" panel where the visitor sends write commands and watches the kernel's rules block unsafe ones, with the same codes and messages as the real hub. Label it clearly as a demo that runs in the browser.
   - One Svelte island. Keep its JavaScript lazy and out of every other page.
3. **TypeScript kernel port**, in `website/src/lib/kernel/`. A faithful port of the checks that apply without hardware. That means shape, read-only file, units (a small table that covers the units in spec/examples), type, range, step, rate of change, interlocks and requires (three-valued, where unknown never passes), confirmation tiers and the stop lock. Messages must match the Python kernel character for character.
   - Parity test. A fixture file `website/tests/kernel-parity/cases.json` with at least 40 commands across the example device files, covering every block code the port implements.
   - `tests/website/test_kernel_parity.py` runs every case through the real Python kernel (mock driver, fixed clock) and writes or compares `expected.json`. A vitest suite runs the same cases through the TS port and requires identical status, code and message.
   - Both run in the normal test commands.
4. **Supported devices**, searchable and filterable by tier, status and hazard. Built from `drivers/catalog.json` at build time, and from docs/drivers/COVERAGE.md for prose. The catalog grows as driver workstreams merge, so nothing may be hard-coded.
5. **Device library browser.** It is generated from `library/**/*.hal.yaml` with a page per device and verification badges. `library/` does not exist yet (it lands at M12). Build the collection so it reads whatever is there. With no files, show an honest empty state that explains how to contribute. Use a fixture directory in tests.
6. **Docs.**
   - Render the repository's Markdown at build time, so nothing drifts. That covers spec/SPEC.md, docs/SAFETY.md, docs/ARCHITECTURE.md, docs/drivers/*.md, docs/interfaces/*.md, spec/FIRMWARE-PROTOCOL.md and firmware/arduino/OpenHAL/README.md.
   - Write the missing guides as Markdown in `docs/guide/` (you own that folder): quickstart, concepts, conformance suite, contributing a device file, FAQ.
   - The driver writer guide is `docs/guide/driver-writer.md` and the orchestrator writes it. Render it if present and leave a clean gap if not.
7. **Spec page** with a version selector (versions from spec/CHANGELOG.md, currently only 0.1) and the changelog.
8. **Blog layout** with one launch post draft, "Why we built OpenHAL". Mark it draft so it is excluded from production builds unless `OPENHAL_SHOW_DRAFTS=1`.
9. **Site basics.** A 404 page. Open Graph images generated at build time for every page, from the design system and never stock art. A favicon set, sitemap and robots.txt.

## Quality bar

- Lighthouse 95+ on performance, accessibility, best practices and SEO for the landing page on mobile, and 90+ on every other page. Record the scores in your report.
- WCAG AA everywhere. Keyboard navigable, visible focus, and status never shown by color alone.
- Playwright tests pass in Chromium, Firefox and WebKit. Headless only, always.
- No layout shift. Images optimized and sized. Minimal JavaScript outside the playground.
- **Tested snippets.** Every command and code snippet on the site is tested against the real CLI and library. Mark snippets in content (for example a `tested` fence attribute). `tests/website/test_snippets.py` extracts them and runs them against an embedded hub with the mock devices in a temporary `OPENHAL_HOME`. It never touches real hardware or the user's `~/.openhal`.
- `pnpm build` (or npm) with zero warnings.
- The site URL is one constant in the website config. The domain is not bought yet (NEEDS_HUMAN item 2), so use `https://openhal.dev` as the placeholder and say so in your report. Product names come from one website config file that mirrors openhal/_brand.py, and a test checks they match.

## Design

- docs/DESIGN.md is binding. The signature is the limit line. The stop bar and limit line are what a visitor should remember.
- Run the three generic-ness tests on every page.
- The banned list in DESIGN.md is absolute.
- Copy rules
  - Precise, plain and a little dry.
  - No em or en dashes. No colons or semicolons in running prose (headings, labels, tables and code are fine).
  - No exclamation marks.
  - None of the banned words.
- Never use Inter or an Inter-like system stack.

## Design critique loop (at least 3 rounds)

You can't start subagents, so the orchestrator runs the independent reviewer. When the site is feature complete, and again after each round of fixes, do these steps.

1. Take Playwright screenshots of every page at 390, 768, 1024 and 1440 px, in light and dark. Save them to `docs/design-rounds/round-N/` (N = 1, 2, 3).
2. Commit, then stop and hand back with a short note that round N is ready.
3. The orchestrator sends you the reviewer's scores and the 5 weakest things. Fix them, then repeat.

Before round 1, do your own critique pass against DESIGN.md and fix what you find.

## Files you own

- `website/` (everything, including its package.json, lockfile, tests and config)
- `docs/guide/`
- `docs/design-rounds/`
- `tests/website/`

Read anything else. Change nothing else. If you need a contract change (an API field, a schema export, a kernel message), propose it in your report.

## Ports and processes

- Astro dev on 4321 and the preview server on 4322. Never use port 4000.
- Start servers in the background and stop them by their exact PID. Never pkill by pattern.
- Headless browsers only.

## What you must not do

- Don't deploy, push, publish packages, buy domains, create accounts or post anything.
- Don't start subagents.
- Never send anything to real hardware. Never weaken a safety rule.
- Don't put secrets or personal data in the repo.

## Working setup

- You work in your own git worktree on your own branch.
- Python: `export PATH="$HOME/Library/Python/3.13/bin:$PATH"`, then `uv sync --all-extras`.
- Website: run `pnpm install` in website/.
- All of these must pass before every hand-back: `uv run pytest`, `uv run ruff check openhal tests`, `uv run ruff format openhal tests`, `uv run mypy openhal`, and the website's build and test scripts.
- Commit in small logical commits of roughly 50 to 450 lines, with conventional commit messages, authored by the existing global git identity. Never set git config, never pass --author, and add no trailers of any kind.
- Keep at least 2.5 GB of disk free. Playwright browsers and node_modules are fine. Don't delete anything you didn't create.

## Report

The harness may block you from writing report files. If so, put the full report in your final message. It should cover files, pages, tests, Lighthouse scores per page, dependencies with versions and licenses, open issues, decisions, and contract change proposals. The target is `docs/agents/REPORT-website.md`.
