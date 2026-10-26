# Website and Inspector quality

Measured on 2026-10-25 by the quality workstream, at commit b29aa75 on branch worktree-agent-a93add9689c8b7b2f, on an Intel Core i7-8750H Mac with macOS 15.5. The website rows were measured again the same day by the website round 4 workstream, at commit acadaf4 on branch worktree-agent-aa39233d21696be73, on the same Mac, after the site search, the wrapped code blocks and the stacked tables landed. The Inspector rows are from the first run.

## Tools

| Tool | Version |
|---|---|
| Lighthouse | 13.5.0, run with `pnpm dlx lighthouse@13.5.0` |
| Chromium | Chrome for Testing 156.0.8078.4, from Playwright 1.64.1 |
| axe | @axe-core/playwright 4.14.0 |
| Node | 22.17.1 |

Lighthouse ran headless with its default mobile settings (simulated slow 4G and a 4x slower CPU) and with `--preset=desktop`, against loopback servers started for the run. Port 4000 was never used.

## How to run it

`LIGHTHOUSE_BIN` is the `lighthouse` binary that `pnpm dlx lighthouse@13.5.0` installs. Start each server in the background and stop it by its PID afterwards.

The website, from a production build.

```text
cd website
pnpm build
pnpm exec astro preview --host 127.0.0.1 --port 4391
OPENHAL_PREVIEW_URL=http://127.0.0.1:4391 node scripts/lighthouse.mjs LIGHTHOUSE_BIN "/,/spec/playground/" mobile,desktop OUTDIR
```

The Inspector, from the build the hub serves, on the mock hub with the simulated plant waterer.

```text
cd dashboard
pnpm build
cd ..
uv run python -m tests.inspector.serve --port 7492 --state STATE.json
cd dashboard
node scripts/lighthouse.mjs LIGHTHOUSE_BIN STATE.json "#/devices/plant-waterer,#/settings" mobile,desktop OUTDIR
```

Both scripts print each score and the audits that lost points. The Inspector script signs in with the human token from the state file. The pairing page was measured with a state file whose token is not a session.

## Lighthouse, website

| Page | Path | Mobile perf | Mobile a11y | Mobile best practices | Mobile SEO | Desktop perf | Desktop a11y | Desktop best practices | Desktop SEO |
|---|---|---|---|---|---|---|---|---|---|
| Overview | `/` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| Spec page (Messages) | `/spec/2026-10-24/basic/messages/` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| Schema reference | `/spec/2026-10-24/schema/` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| Playground | `/spec/playground/` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| Drivers | `/drivers/` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| Driver page (mock) | `/drivers/mock/` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| Device Library | `/library/` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| Library device (Rigol DP832) | `/library/scpi-rigol-dp832/` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| Guide page (Quickstart) | `/docs/quickstart/` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| Python reference | `/sdks/python/reference/` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| Inspector docs | `/inspector/` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| Blog | `/blog/` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| 404 | `/404.html` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |

## Lighthouse, Inspector

| Page | Path | Mobile perf | Mobile a11y | Mobile best practices | Mobile SEO | Desktop perf | Desktop a11y | Desktop best practices | Desktop SEO |
|---|---|---|---|---|---|---|---|---|---|
| Device, plant waterer | `#/devices/plant-waterer` | 95 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| Device, curing heater | `#/devices/curing-heater` | 95 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| Device, read-only bench lamp | `#/devices/bench-lamp` | 95 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| Confirmations | `#/confirmations` | 93 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| Audit log | `#/audit` | 94 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| Routines | `#/routines` | 94 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| Routine detail | `#/routines/water-when-dry` | 94 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| Driver writer | `#/writer` | 93 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| Settings | `#/settings` | 93 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| Pairing page | `#/pair` | 95 | 100 | 96 | 100 | 100 | 100 | 96 | 100 |

## What was fixed

- **Inspector layout shift.** The device list, the main pane and the message log each grew as their data arrived, a layout shift of 0.58 on a phone and 0.53 on desktop. The Inspector now fetches its first data in parallel with the session check and draws the layout once that data and the routed view's own data are in. Shift is 0 on every view.
- **Inspector main thread.** A size binding and a scroll reset on mount each forced a full layout during the first render, and sorting names started the ICU collator. These are gone, log rows draw after the first paint, and an answer or reading that changes nothing no longer re-renders. Blocking time on a phone is about 90 ms, down from 170 ms.
- **Inspector bundle.** Views other than Devices load on demand, so the first load is 123 KB instead of 160 KB, and the two upright fonts are preloaded.
- **Inspector accessibility and SEO.** Control and action names were h4 under an h2. The page had no meta description.
- **Inspector before.** The plant waterer view scored 69 for performance, 99 for accessibility, 100 for best practices and 90 for SEO on mobile, and 78, 99, 100 and 90 on desktop.

## What is left, and why

- **Inspector performance on a phone is 93 to 95.** The hub serves the Inspector uncompressed and with `cache-control: no-store` on hashed assets, which is in openhal/hub, not in the Inspector. Behind a gzip proxy on loopback the same build scores 99 on the device, settings and writer views. The fix proposed for the hub is Starlette's `GZipMiddleware` and a long cache lifetime for `/assets/`.
- **The pairing page scores 96 in best practices.** The hub answers `/v1/whoami` with 401 when a browser is not paired, and Chrome logs every 401 as a console error. Answering 200 with a paired flag would clear it, also in openhal/hub.
- **The 404 was measured at /404.html.** An unknown address answers with status 404, which Lighthouse's SEO category counts against any page by design.

## axe

Rules from the tags wcag2a, wcag2aa, wcag21a and wcag21aa, with axe 4.14.0.

| Surface | What is checked | Violations |
|---|---|---|
| Website | Every page in the sitemap (114 pages), /spec/latest/ and the 404, in the light and dark themes, at 1280 by 720 in Chromium | 0 |
| Website | At 390 px in both themes, the open phone menu, the open section menu and version switcher, a playground trace, empty driver and library filters, a focused flow part, and the site search opened from its icon button with results | 0 |
| Website | At 1280 by 800 in both themes, the site search dialog opened with Ctrl K and showing results for LIMIT_EXCEEDED | 0 |
| Inspector | At 1440 and 390 px in both themes, in Chromium, and at 1440 px in Firefox. Each device (the plant waterer, the curing heater, the read-only bench lamp), confirmations with a pending request, the audit log, routines and a dry run, the driver writer and its limits interview, settings, the hidden log, the stopped state, the UNLOCK dialog, pairing and the offline page | 0 |

The sweep found and fixed these.

- Wide tables on the CLI reference, the safety page and the esphome, homeassistant and opcua driver pages scrolled sideways but could not be reached from the keyboard (`scrollable-region-focusable`). A table wrapper that overflows is now a named region in the tab order, and stops being one when it fits.
- The driver writer's Use suggested buttons had a name that did not contain their visible text (`label-content-name-mismatch`).

The tests are website/tests/e2e/a11y.spec.ts and dashboard/e2e/axe.spec.ts.

## Website layout and search

- **No sideways scrolling at 1280 px.** A scan of every sitemap page and the 404 at 1280 by 900 found no code block, table, trace or editor that scrolls sideways, and the page itself never does. At 390 px only the wide architecture diagrams scroll inside their own focusable frame. tests/e2e/site.spec.ts checks the SDK pages, the playground, the messages page and a library page.
- **Search under /OpenHAL/.** A build was copied into a folder served as /OpenHAL/, checked for links, rebased with scripts/rebase.mjs and indexed with `node scripts/search-index.mjs DIR /OpenHAL`, as the Pages workflow does. Searching for LIMIT_EXCEEDED and for plant waterer in Chromium and Firefox found 7 and 22 pages, every result link started with /OpenHAL/, and Enter opened the first result. The script fails when any page would load the index from outside the base.

## Browsers

Every browser test ran in Chromium and Firefox. WebKit page loads stall on this Mac, so WebKit was skipped, as the brief says.
