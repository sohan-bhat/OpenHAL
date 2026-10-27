# Website and Inspector quality

Measured on 2026-10-25 by the quality workstream, at commit b29aa75 on branch worktree-agent-a93add9689c8b7b2f, on an Intel Core i7-8750H Mac with macOS 15.5. The website rows were measured again the same day by the website round 4 workstream, at commit acadaf4 on branch worktree-agent-aa39233d21696be73, on the same Mac, after the site search, the wrapped code blocks and the stacked tables landed. They were measured a third time by the website round 5 workstream, at commit 589b7d8 on branch worktree-agent-aa06f02640ce4c4c4, on the same Mac, after the house-style diagrams, the numbered spec sections, the shared left edge and the owner's text wordmark landed. The Overview row and the landing story section were measured by the landing page round, at commit 6ef60a6 on branch worktree-agent-a39e9445429fca114, on the same Mac, after the landing page was rebuilt around the scroll story. The Overview and Playground rows, the website axe rows, the layout and search lines and the landing story section were measured again by the website round 6 workstream, at commit 09c7812 on branch worktree-agent-a1c88bf95caf4733d, on the same Mac, after the story was retold around the 3D print babysitter and the Playground was rebuilt around its requests. The Inspector rows were measured again by the Inspector round 5 workstream, at commit 6c815d7 on branch worktree-agent-abb87dd02b08d1eaf, on the same Mac, on a test hub with the print babysitter's simulators, after camera frames, the pending cancel and status words with no shapes landed.

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

The Inspector, from the build the hub serves, on a test hub with the simulated printer and its camera beside the plant waterer, the curing heater and the bench lamp.

```text
cd dashboard
pnpm build
cd ..
PYTHONPATH=. uv run python dashboard/e2e/print_hub.py --port 7492 --state STATE.json
cd dashboard
node scripts/lighthouse.mjs LIGHTHOUSE_BIN STATE.json "#/devices/printer,#/confirmations" mobile,desktop OUTDIR
```

Both scripts print each score and the audits that lost points. The Inspector script signs in with the human token from the state file. The pairing page was measured with a state file whose token is not a session.

The page weight budgets, from a production build. The spec loads one page of each template in Chromium and prints what each sends.

```text
cd website
pnpm build
pnpm exec playwright test tests/e2e/budget.spec.ts --project=chromium
```

When the budget spec says a font subset lacks a character, list the characters the build shows and cut the subsets again, then rebuild.

```text
cd website
pnpm build
node scripts/glyphs.mjs dist
cd ..
uv run --no-project --with fonttools==4.67.0 --with brotli python website/scripts/fonts.py
```

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

Mobile performance moves by a point or two between runs on this Mac. Pages that scored under 100 on the first run were measured three or four times, and the table shows the median. The rebuilt Overview scored 100 on four mobile runs, with a layout shift of 0, first contentful paint at 1.0 s, largest contentful paint at 1.4 to 1.5 s, no blocking time and 74 KB in all. Before the rebuild it scored 99, 99, 99 and 100. In round 6 the Overview scored 100 in every category on three mobile and three desktop runs, with a layout shift of 0, first contentful paint at 1.10 to 1.13 s, largest contentful paint at 1.51 to 1.59 s, no blocking time and 81 KB in all on a phone. The Playground scored 100 in every category on all six runs, with 79 KB on a phone, since its kernel loads only when a person first uses it. Messages scored 96, 100 and 99, Schema reference 99, 100 and 99, and Drivers 99, 100 and 100. The points they lose are first contentful paint at 1.1 to 1.5 s and blocking time of 70 to 210 ms under the simulated slow phone.

Gzipped, the home page's HTML is 14.7 KB, which holds 3.5 KB of inline script and 1.3 KB of inline style, its two stylesheets are 7.8 KB and the story script is 2.3 KB. The smooth scrolling code adds 0.6 KB once the page is idle. The Playground's HTML is 16.6 KB and its three stylesheets are 6.8 KB, and its kernel, 98 KB with the Svelte runtime, loads the first time a person uses the page, which then replays that first click. The speed round's weights are under Website speed below.

## Website speed

Measured by the website round 7 workstream, the speed round, on the same Mac. Before is the starting commit 2aa54f2. After is the round's last commit. Both were built the same way and served the same way in one session, one before run and one after run in turn, so a busy moment on the shared Mac hits both. Live is https://sohan-bhat.github.io/OpenHAL/ serving 2aa54f2, measured from this Mac on 2026-10-26. Each value is the median of three runs, times in ms and weights in KB as Lighthouse counts them.

### Where the bytes went

| Template | Page | Before, HTML + CSS + JS + fonts | After, HTML + CSS + JS + fonts |
|---|---|---|---|
| Home | `/` | 77.4 KB | 53.4 KB |
| Docs index | `/docs/` | 64.8 KB | 30.9 KB |
| Guide page | `/docs/quickstart/` | 85.1 KB | 47.7 KB |
| Page with diagrams | `/docs/architecture/` | 125.1 KB | 51.9 KB |
| Spec page | `/spec/2026-10-24/basic/messages/` | 76.2 KB | 51.7 KB |
| Drivers | `/drivers/` | 70.3 KB | 46.0 KB |
| Playground | `/spec/playground/` | 75.3 KB | 51.0 KB |
| Python reference | `/sdks/python/reference/` | 71.8 KB | 47.3 KB |
| Inspector page | `/inspector/` | 65.1 KB | 41.3 KB |

HTML, CSS and JavaScript are gzipped the way GitHub Pages serves them, fonts are their WOFF2 bytes. The Inspector page's screenshots come on top, 241 KB before on a phone and on a desktop, 53 KB after on a phone and 102 KB on a desktop.

- **Fonts.** website/scripts/fonts.py cuts the two faces to the characters a build shows and the weights the styles use, 400 to 800 for the text face, 400 to 700 for the mono face and 400 for the mono italic. The text face went from 34.0 KB to 16.7 KB, the mono face from 17.8 KB to 9.7 KB and the mono italic from 19.1 KB to 6.0 KB. A static instance came out at 7.0 to 7.5 KB a weight, more than the narrowed variable face once a page uses three weights, so the subsets stay variable apart from the mono italic, which the site sets only at 400. Each subset keeps its face's family, style and weight range, so its rule joins the full face's rule in design/tokens.css, and a character a subset lacks still renders in the full face. Both subsets are preloaded. The mono face shows in the first screen of 101 of 115 pages at 1440 px and 75 at 390 px, and its fallback is about 9 % narrower than the face, so a mono font that arrives after the first paint moves text. The docs index shows no mono text and preloads only the text face. Body text renders the same, apart from anti-aliasing in under 0.2 % of a page's pixels.
- **Diagrams.** A page inlines each D2 diagram once. D2's embedded fonts go, the diagram's text uses the page's faces at the weights D2 drew with and without kerning, as D2's fonts have none, and every color that differs between the light and dark files becomes a design token or a property the SVG sets for each theme. docs/architecture went from 321 KB of HTML to 98 KB, and from 68 KB to 17 KB gzipped. The diagrams render as before in both themes in Chromium and Firefox, apart from anti-aliasing in 0.4 to 2.2 % of their pixels. The files in docs/diagrams are unchanged.
- **Inspector screenshots.** The build cuts each crop out of its capture with sharp, from the crop website/src/data/inspector-captures.json records, as AVIF with a WebP fallback in both themes. Each crop comes at its recorded width and at 85 %, the narrowest the page draws it, with its width and height set and loaded lazily, since the first one starts 1,099 px down at 1440 px and 1,948 px down at 390 px. Open the whole screen still links the full capture.
- **Scripts.** The copy buttons, the scrolling regions, the search dialog and the prefetch for browsers without speculation rules ship as one module, 7.3 KB, 3.0 KB gzipped, cached across pages. The Pagefind index loads only when a person points at the search or opens it. The page turn script stays inline in the head and is minified, 2.5 KB down to 1.2 KB. The story and smooth scrolling load only on home and the Playground's kernel only on its first use, as before. A CSS coverage pass over every page in both themes at 1440 and 390 px found no dead rules beyond the full faces kept as the subsets' fallback, the dark rules for data-theme that the Inspector uses, and the two-copy diagram rules kept for a diagram with no redraw.
- **Search snippets.** The owner asked that a result never show YAML or code. The index leaves code blocks, YAML and message traces out of what it reads, and a snippet that still reads as code shows the page's description, which is also the snippet when a result has none.

### Page turns and prerendering

Every page carries speculation rules that prerender a same-site page after a short hover or on pointer down, and only prefetch the Playground, whose kernel still waits for the first click. Search files, captures and social images are never fetched ahead. tests/e2e/navigation.spec.ts checks the rules on four pages, that pointing at Drivers and the Playground fetches their pages in Chromium without the Playground's script, and that Firefox, which has no speculation rules, prefetches with Astro's prefetch on hover and on focus. Chrome turns prerendering off while DevTools drives it, so those tests see a prefetch. A self-driving page checked the prerendered path in Chrome for Testing with nothing attached. The Device Library page was prerendered, then activated 3.8 s after its prerender began, its pagereveal event carried the view transition with the type forward, and the page turned forward as the navigation goes. Under /OpenHAL/ the rules' pattern reads /OpenHAL/* and every request stayed under /OpenHAL/ in Chromium and Firefox.

### A first frame that waits a second

In some Lighthouse runs on a phone, Chrome draws nothing for about a second after the page has loaded, and sometimes two. The trace shows the load event near 200 ms, no main frame until a tick near 1.16 s, and the first contentful paint near 1.2 or 2.2 s. Lighthouse's Speed Index weighs the paint it saw by 1.4, so such a run reads about 2.0 s instead of the first paint's 1.1 s, and its blocking time rises when the late frame lands after the simulated first paint. The delay happened in 6 of 24 phone runs of the starting commit and never on a desktop. The delay still happened with the view transition rule, the font preloads, the head script, every script or every stylesheet removed, and with the reference's sections hidden by content-visibility. The delay did not happen on a page with a small main column or on a plain test page. The delay reads as a headless Chrome frame scheduling issue that larger pages meet more often, not something a page asks for. The tables give the median of three runs, as the brief asks, so one such run doesn't set a median.

## Lighthouse, Inspector

| Page | Path | Mobile perf | Mobile a11y | Mobile best practices | Mobile SEO | Desktop perf | Desktop a11y | Desktop best practices | Desktop SEO |
|---|---|---|---|---|---|---|---|---|---|
| Device, printer | `#/devices/printer` | 96 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| Device, printer camera | `#/devices/printer-cam` | 97 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| Device, plant waterer | `#/devices/plant-waterer` | 98 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| Device, curing heater | `#/devices/curing-heater` | 97 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| Device, read-only bench lamp | `#/devices/bench-lamp` | 98 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| Confirmations, with the pending cancel | `#/confirmations` | 93 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| Audit log | `#/audit` | 98 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| Routines | `#/routines` | 95 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| Routine detail | `#/routines/water-when-dry` | 98 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| Driver writer | `#/writer` | 98 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| Settings | `#/settings` | 98 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| Pairing page | `#/pair` | 99 | 100 | 96 | 100 | 100 | 100 | 96 | 100 |

Confirmations scored 94, 93 and 93 over three runs on a phone, and the table gives the median.

## What was fixed

- **Inspector layout shift.** The device list, the main pane and the message log each grew as their data arrived, a layout shift of 0.58 on a phone and 0.53 on desktop. The Inspector now fetches its first data in parallel with the session check and draws the layout once that data and the routed view's own data are in. Shift is 0 on every view.
- **Inspector main thread.** A size binding and a scroll reset on mount each forced a full layout during the first render, and sorting names started the ICU collator. These are gone, log rows draw after the first paint, and an answer or reading that changes nothing no longer re-renders. Blocking time on a phone is about 90 ms, down from 170 ms.
- **Inspector bundle.** Views other than Devices load on demand, so the first load is 123 KB instead of 160 KB, and the two upright fonts are preloaded.
- **Inspector accessibility and SEO.** Control and action names were h4 under an h2. The page had no meta description.
- **Inspector before.** The plant waterer view scored 69 for performance, 99 for accessibility, 100 for best practices and 90 for SEO on mobile, and 78, 99, 100 and 90 on desktop.

## What is left, and why

- **Inspector performance on a phone is 93 to 99.** Confirmations with a pending cancel is the lowest view at 93, and Routines is next at 95. The hub now gzips the Inspector and caches its hashed assets, which lifted most views from 93 to 95 into the high 90s.
- **The pairing page scores 96 in best practices.** The hub answers `/v1/whoami` with 401 when a browser is not paired, and Chrome logs every 401 as a console error. Answering 200 with a paired flag would clear it, also in openhal/hub.
- **The 404 was measured at /404.html.** An unknown address answers with status 404, which Lighthouse's SEO category counts against any page by design.

## axe

Rules from the tags wcag2a, wcag2aa, wcag21a and wcag21aa, with axe 4.14.0.

| Surface | What is checked | Violations |
|---|---|---|
| Website | Every page in the sitemap (114 pages), /spec/latest/ and the 404, in the light and dark themes, at 1280 by 720 in Chromium | 0 |
| Website | At 390 px in both themes, the open phone menu, the open section menu and version switcher, the playground after a refused write with an information mark and the request builder open, empty driver and library filters, the landing story halfway through its scroll and as the list reduced motion shows, and the site search opened from its icon button with results | 0 |
| Website | At 1280 by 800 in both themes, the site search dialog opened with Ctrl K and showing results for LIMIT_EXCEEDED | 0 |
| Inspector | At 1440 and 390 px in both themes, in Chromium, and at 1440 px in Firefox. Each device (the printer, the printer camera with its frame, the plant waterer, the curing heater, the read-only bench lamp), confirmations with the pending cancel and its camera frame, the message log with an expanded frame result, the audit log, routines and a dry run, the driver writer and its limits interview, settings, the hidden log, the stopped state, the UNLOCK dialog, pairing and the offline page | 0 |

Round 5 ran the website rows again on its own build, with the house-style diagrams, the Inspector crops and the text wordmark, and found 0 violations in 239 checks. The landing page round ran them again on its own build and found 0 violations in 239 checks. Round 6 ran them on its own build and found 0 violations in 236 axe runs, the 116 pages in both themes and the phone and search dialog states.

The Inspector's status test, dashboard/e2e/status.spec.ts, fails when a status word has an icon, glyph or shape beside it, or when anything other than STOP has a status colored border or background. It runs on every view in both themes, in Chromium and Firefox. The website's design rules test, website/tests/e2e/design-rules.spec.ts, checks the same on eight pages that show statuses, the home page, the Playground, the drivers and library pages, the error codes, the quickstart, the Inspector page and the Moonraker driver.

The sweep found and fixed these.

- Wide tables on the CLI reference, the safety page and the esphome, homeassistant and opcua driver pages scrolled sideways but could not be reached from the keyboard (`scrollable-region-focusable`). A table wrapper that overflows is now a named region in the tab order, and stops being one when it fits.
- The driver writer's Use suggested buttons had a name that did not contain their visible text (`label-content-name-mismatch`).

The tests are website/tests/e2e/a11y.spec.ts and dashboard/e2e/axe.spec.ts.

## Website layout and search

- **No sideways scrolling at 390, 768 and 1440 px.** A scan of every sitemap page and the 404 at those widths found no page wider than the window. At 390 px the architecture and sequence diagrams and the Inspector screenshot crops scroll inside their own frame, which becomes focusable only while it overflows. At 1440 px only the components diagram (814 px) and the life of a command (1105 px) are wider than the 772 px reading column. tests/e2e/site.spec.ts checks the SDK pages, the playground, the messages page and a library page at 1280 px.
- **One left edge.** On every page but home the title starts at 344 px at 1440 and at 304 px from 1024 to 1360, the column the documentation sidebar leaves. The blog, the 404 and the playground use the same column. Since round 6 home keeps its sections in one centered column at most 1200 px wide, as the owner asked, so its headings start at 136 px at 1440 and at 16 px up to 1232. The story's column layout, used below 1200 px, is at most 600 px wide and centered in it.
- **No text under 13 px.** A scan of every text node on every page at 390, 768 and 1440 px, inline SVG labels included, found none smaller than the 13 px legend size.
- **Diagrams in the house style.** The seven Mermaid diagrams of docs/ARCHITECTURE.md and the sequence diagram of the spec's architecture section are redrawn in D2 in docs/diagrams and shown at full size in light and dark. tests/unit/diagrams.test.ts fails when a Mermaid block on the site has no current redraw.
- **Search under /OpenHAL/.** A build was copied into a folder served as /OpenHAL/, checked for links, rebased with scripts/rebase.mjs and indexed with `node scripts/search-index.mjs DIR /OpenHAL`, as the Pages workflow does. Searching for LIMIT_EXCEEDED and for plant waterer in Chromium and Firefox found 7 and 22 pages, every result link started with /OpenHAL/, and Enter opened the first result. Round 5 repeated it on its own build, where the dialog listed 7 and 8 results with every link under /OpenHAL/ and Enter opened /OpenHAL/docs/quickstart/ and /OpenHAL/library/openhal-firmware-openhal-plant-waterer/. Round 6 repeated it, and in Chromium and Firefox the dialog listed 6 results for LIMIT_EXCEEDED and 4 for print babysitter, every link under /OpenHAL/, and Enter opened /OpenHAL/docs/quickstart/#run-the-demo and /OpenHAL/spec/playground/#pg-editor-title. The script fails when any page would load the index from outside the base.

## Landing page story

Round 6 retold the story around the 3D print babysitter. The whole diagram stays in view at one size, from the agent through the hub, the kernel and the drivers to the printer and its webcam, and each of nine steps lights the stations it is about.

- **A caption and its state change together.** tests/e2e/story.spec.ts stops at the first, middle and last scroll position of every step and checks the caption, the count, the lit stations and the state the caption describes in one pass, in Chromium and Firefox. Another test reads the trace under the diagram in the hub's own words, LIMIT_EXCEEDED with its code for the hot nozzle and pending for the cancel.
- **Scroll drives it, and it stays smooth.** A scripted 10 s scroll through the whole story in Chromium, with the CPU slowed 4 times, drew 601 to 603 frames with a 95th percentile of 16.7 to 16.8 ms and none over 25 ms at 1440 by 900, at 390 by 844 and, where the short stage plays, at 390 by 664 and 1366 by 641. The first 390 by 844 run had one frame of 33 ms and two reruns had none. Scrolling it with the mouse wheel at 1440 by 900, with smooth scrolling on, drew no frame over 16.8 ms. Chromium counted 0 layouts in every run, since a step changes only opacity and a wire only its transform.
- **Where it plays.** The whole stage plays where it fits under the header, at 1440 by 900, where it is 657 px tall, and at 1920 by 1080, 1536 by 730, 1366 by 768, 1280 by 720, 1100 by 900, 768 by 1024, 412 by 823, 390 by 844 and 375 by 812. Where it does not fit, the short stage drops the trace on a phone and sets the caption on one line with a smaller webcam on a laptop. It plays at 1366 by 641, 1024 by 768, 430 by 740, 393 by 659, 375 by 667 and 390 by 664, the size of an iPhone 13 with Safari's toolbars showing. At 360 by 700, 375 by 629, 1024 by 700 and under 600 px tall the story is the list. The fit is read from a 100svh probe before the first paint, so a phone that hides its toolbars while scrolling never switches between the two, and nothing scrolls sideways at any point.
- **Reduced motion and no script.** The stage gives way to a list of the nine steps, each with its caption, its trace and the station it is about at that moment, in Chromium and Firefox. The story also turns into that list on a screen too short for the short stage.
- **Text and edges.** No text on the stage is under 13 px at 1440 by 900, 1366 by 641, 390 by 844 and 390 by 664, and no word leaves its card at any step at 1440 by 900, 1366 by 641, 1200 by 800, 1100 by 900, 768 by 1024, 390 by 664 and 375 by 667, in Chromium and Firefox. Skip the demo lands on the next section, which starts less than 120 px under the stage after the last step.
- **Page turns and the nav highlight.** A link in the main navigation turns the page with a 24 px slide and a wipe, forward or back in the order of the navigation, and the highlight slides to the new item in 240 ms. Both are cross-document view transitions, with no router. A browser without them opens the page as usual, and reduced motion turns them off. tests/e2e/controls.spec.ts checks the direction in Chromium and that only navigation links turn the page.
- **Smooth scrolling.** The home page has a Smooth scrolling switch, on unless reduced motion is set, and the choice is kept in the browser. It eases the mouse wheel and leaves keys, anchors, the scroll bar and inner scrolling alone. Its code is 626 B gzipped and loads once the page is idle.
- **Under /OpenHAL/.** A build for sohan-bhat.github.io was checked for links, rebased and indexed as the Pages workflow does, then served as /OpenHAL/. In Chromium and Firefox the story's script loaded from /OpenHAL/_astro/, every link and request stayed under /OpenHAL/, all ten steps played with no console errors, and Chromium counted 0 layouts while it played. A click on Drivers turned the page forward.

## Browsers

Every browser test ran in Chromium and Firefox. WebKit page loads stall on this Mac, so WebKit was skipped, as the brief says.
