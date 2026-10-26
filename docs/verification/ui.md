# Website and Inspector quality

Measured on 2026-10-25 by the quality workstream, at commit b29aa75 on branch worktree-agent-a93add9689c8b7b2f, on an Intel Core i7-8750H Mac with macOS 15.5. The website rows were measured again the same day by the website round 4 workstream, at commit acadaf4 on branch worktree-agent-aa39233d21696be73, on the same Mac, after the site search, the wrapped code blocks and the stacked tables landed. They were measured a third time by the website round 5 workstream, at commit 589b7d8 on branch worktree-agent-aa06f02640ce4c4c4, on the same Mac, after the house-style diagrams, the numbered spec sections, the shared left edge and the owner's text wordmark landed. The Overview row and the landing story section were measured by the landing page round, at commit 6ef60a6 on branch worktree-agent-a39e9445429fca114, on the same Mac, after the landing page was rebuilt around the scroll story. The Inspector rows are from the first run.

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
| Spec page (Messages) | `/spec/2026-10-24/basic/messages/` | 99 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| Schema reference | `/spec/2026-10-24/schema/` | 99 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
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
| Documentation index | `/docs/` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| Architecture, with seven diagrams | `/docs/architecture/` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| Errors | `/spec/errors/` | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |

Mobile performance moves by a point or two between runs on this Mac. Pages that scored under 100 on the first run were measured three or four times, and the table shows the median. The rebuilt Overview scored 100 on four mobile runs, with a layout shift of 0, first contentful paint at 1.0 s, largest contentful paint at 1.4 to 1.5 s, no blocking time and 74 KB in all. Before the rebuild it scored 99, 99, 99 and 100. Messages scored 96, 100 and 99, Schema reference 99, 100 and 99, and Drivers 99, 100 and 100. The points they lose are first contentful paint at 1.1 to 1.5 s and blocking time of 70 to 210 ms under the simulated slow phone.

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
| Website | At 390 px in both themes, the open phone menu, the open section menu and version switcher, a playground trace, empty driver and library filters, the landing story halfway through its scroll and as the list reduced motion shows, and the site search opened from its icon button with results | 0 |
| Website | At 1280 by 800 in both themes, the site search dialog opened with Ctrl K and showing results for LIMIT_EXCEEDED | 0 |
| Inspector | At 1440 and 390 px in both themes, in Chromium, and at 1440 px in Firefox. Each device (the plant waterer, the curing heater, the read-only bench lamp), confirmations with a pending request, the audit log, routines and a dry run, the driver writer and its limits interview, settings, the hidden log, the stopped state, the UNLOCK dialog, pairing and the offline page | 0 |

Round 5 ran the website rows again on its own build, with the house-style diagrams, the Inspector crops and the text wordmark, and found 0 violations in 239 checks. The landing page round ran them again on its own build and found 0 violations in 239 checks.

The sweep found and fixed these.

- Wide tables on the CLI reference, the safety page and the esphome, homeassistant and opcua driver pages scrolled sideways but could not be reached from the keyboard (`scrollable-region-focusable`). A table wrapper that overflows is now a named region in the tab order, and stops being one when it fits.
- The driver writer's Use suggested buttons had a name that did not contain their visible text (`label-content-name-mismatch`).

The tests are website/tests/e2e/a11y.spec.ts and dashboard/e2e/axe.spec.ts.

## Website layout and search

- **No sideways scrolling at 390, 768 and 1440 px.** A scan of every sitemap page and the 404 at those widths found no page wider than the window. At 390 px the architecture and sequence diagrams and the Inspector screenshot crops scroll inside their own frame, which becomes focusable only while it overflows. At 1440 px only the components diagram (814 px) and the life of a command (1105 px) are wider than the 772 px reading column. tests/e2e/site.spec.ts checks the SDK pages, the playground, the messages page and a library page at 1280 px.
- **One left edge.** On all 115 pages the title starts at 344 px at 1440 and at 304 px from 1024 to 1360, the column the documentation sidebar leaves. Home, the blog, the 404 and the playground use the same column.
- **No text under 13 px.** A scan of every text node on every page at 390, 768 and 1440 px, inline SVG labels included, found none smaller than the 13 px legend size.
- **Diagrams in the house style.** The seven Mermaid diagrams of docs/ARCHITECTURE.md and the sequence diagram of the spec's architecture section are redrawn in D2 in docs/diagrams and shown at full size in light and dark. tests/unit/diagrams.test.ts fails when a Mermaid block on the site has no current redraw.
- **Search under /OpenHAL/.** A build was copied into a folder served as /OpenHAL/, checked for links, rebased with scripts/rebase.mjs and indexed with `node scripts/search-index.mjs DIR /OpenHAL`, as the Pages workflow does. Searching for LIMIT_EXCEEDED and for plant waterer in Chromium and Firefox found 7 and 22 pages, every result link started with /OpenHAL/, and Enter opened the first result. Round 5 repeated it on its own build, where the dialog listed 7 and 8 results with every link under /OpenHAL/ and Enter opened /OpenHAL/docs/quickstart/ and /OpenHAL/library/openhal-firmware-openhal-plant-waterer/. The script fails when any page would load the index from outside the base.

## Landing page story

- **Scroll drives it, and it stays smooth.** A scripted 10 s scroll through the whole story in Chromium drew 602 frames with a 95th percentile of 16.7 ms and none over 25 ms, at 1440 by 900 and at 390 by 844 with the CPU slowed 4 times. Chromium counted 0 layouts during the scroll, since only transforms and opacity change. tests/e2e/story.spec.ts checks the layout count, the pinned stage, and the kernel's and the client's answers at their moments.
- **Reduced motion and no script.** The stage gives way to a list of the same ten steps, each with its station drawn at that moment, in Chromium and Firefox.
- **Phones and tablets.** At 390 by 844 the stage fills the screen under the header and nothing scrolls sideways at any point of the story. At 1024 by 768 the three-station shots fit without cropping. The story was also checked at 768 by 1024 and 1920 by 1080.
- **Text and edges.** No text node on the landing page is under 13 px at 390, 768 and 1440 px, with motion or without. Every heading starts at 344 px at 1440. The wordmark's box starts 0.04 em to the left of that, so its O lines up with the text under it.
- **Under /OpenHAL/.** A build for sohan-bhat.github.io was checked for links, rebased and indexed as the Pages workflow does, then served as /OpenHAL/. The story's script loaded from /OpenHAL/_astro/, every link stayed under /OpenHAL/, the camera ran in Chromium and Firefox with no console errors, and Chromium counted 0 layouts while it played.

## Browsers

Every browser test ran in Chromium and Firefox. WebKit page loads stall on this Mac, so WebKit was skipped, as the brief says.
