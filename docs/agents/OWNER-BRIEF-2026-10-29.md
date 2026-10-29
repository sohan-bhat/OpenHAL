# The owner's brief of 2026-10-29, verbatim

The owner's own words, sent with the brief below: "Literally don't do anything crazy on the landing page, keep as simple and clean as possible. Also you still didn't make the collapsable thingy. Also you are not using the plugins I gave you, use all plugins installed, search up how to make good collapsable side bar."

Then, in a second message about Starlight's search dialog: "For almost every element use a framework or third party plugin. This whole search window is very bad. There should also be some animation for the search bar, use third party, like framer motion for animations and tailwind or something."

---

# OpenHAL website: restructure the home page and fix everything outstanding

## What to build

Rebuild the OpenHAL home page so it explains the product once, clearly, in about 4 to 5 screens. The finished home page has exactly these sections, top to bottom:

1. **Hero:** the big "OpenHAL" wordmark with readable `[hardware] [abstraction] [layer]` labels under the H, A and L, the tagline "An open-source protocol for AI agents to control hardware.", one plain sentence saying what it does, and a Get started button. No diagram.
2. **How it works:** a 3-step scroll section on one simple Agent → OpenHAL hub → Printer diagram. In step 1 a request goes through, in step 2 a request is refused, and in step 3 a request waits for a person to approve it.
3. **Safety model:** the existing three rows.
4. **What OpenHAL works with:** the existing driver list.
5. **Run the demo:** the existing install commands.
6. **Read more:** the existing spec and docs links.

Also:
- Move the current 9-step 3D print story to a new docs page, "Example: an agent watching a 3D print", and link to it from the home page.
- Delete the three full-screen H / A / L sections.
- Fix the deploy pipeline (the last round of changes never reached the live site), the one-item version dropdown, the one-item "On this page" rails, the numbered spec title and the YAML in search snippets.

The rest of this prompt gives the details for each part. Work autonomously through every section below, in order. Don't ask me questions you can answer by reading the code, running the site or looking at screenshots. Commit after each section with a clear message.

## Context

You're working on the OpenHAL documentation site (Astro), deployed to GitHub Pages at https://sohan-bhat.github.io/OpenHAL/. OpenHAL is an open-source protocol for AI agents to control hardware. OpenHAL stands for **Open Hardware Abstraction Layer**. Most visitors won't know what "HAL" means, so the home page has to spell it out.

---

## 0. Before you change anything

1. **Check the deploy pipeline.** A previous round of home page changes never reached the live site. Before editing, find out why:
   - Run `git status` and `git log -5` and compare against `origin`. Are there unpushed or uncommitted changes?
   - Check the GitHub Actions runs for the Pages workflow (`gh run list --workflow <pages workflow> -L 5`). Did the last run fail or never trigger?
   - Fetch the live home page HTML and compare it against the local build output for the same page.
   - Write what you find in `DEPLOY_NOTES.md`, and fix the pipeline so a push to the main branch reliably updates the live site.
2. **Take "before" screenshots** with Playwright of the home page (full page), the docs index, the spec page and the Playground at 1440×900 and 390×844, in both light and dark. Save them to `qa/before/`.
3. **Read the site's current design tokens and components** so your changes reuse existing styles. Don't introduce a new look.

---

## 1. Fixed decisions (don't change these)

- **Wordmark only.** The nav shows the "OpenHAL" wordmark with no logo mark, like the GitHub README. Don't add an icon.
- **Name.** HAL means Hardware Abstraction Layer. Never relabel the letters as anything else.
- **HAL labels stay.** The `[hardware] [abstraction] [layer]` labels under the H, A and L in the hero wordmark are required, because most people don't know what HAL stands for. Don't remove them.
- **Tagline.** "An open-source protocol for AI agents to control hardware."
- **Theme.** Keep the current formal, MCP-style protocol theme: the same type, colors, spacing and dark/light handling.
- **Nav layout.** Keep the new layout: links on the left, search in the middle, then GitHub icon, version and theme switch on the right.
- **The example.** Keep the 3D printer example and its numbers: bed limit 110 °C, nozzle limit 260 °C, the agent asks for 70 °C bed (allowed) and 300 °C nozzle (refused), and cancel needs a person's approval.
- **Driver count.** 34 drivers everywhere, unless the drivers directory actually contains a different number, in which case use the real count everywhere and tell me.

---

## 2. The problem with the home page

The home page explains how OpenHAL works four times:
1. A full 9-step sequence diagram in the hero, which gives away the demo directly below it.
2. Three full-screen sections defining H, A and L letter by letter.
3. A 9-step scroll demo that ends with 14 arrows, a webcam, a printer panel and two-line captions.
4. A "Safety model" section that repeats what the demo showed.

The page is about 9 screens tall at 1440px, and a visitor gets the idea in the first two. Everything after that is repetition, and the repeated explanations compete with each other.

**OpenHAL has exactly three ideas worth showing on the home page:**
1. A request inside your limits goes through.
2. A request outside your limits is refused.
3. A request that can't be undone waits for a person.

Everything else (webcam reads, pause, audit counts, the meaning of each letter) supports those ideas and belongs on other pages.

---

## 3. New home page (rebuild to this exact structure)

Target: about 4 to 5 screens tall at 1440×900. Every section must earn its place.

### 3.1 Hero
- The large "OpenHAL" wordmark.
- **Keep the `[hardware]`, `[abstraction]` and `[layer]` labels directly under the H, A and L.** They're currently too small and faint to notice. Make them clearly readable: at least 14px on desktop and 12px on mobile, muted but passing WCAG AA contrast, and each centered under its letter. At 390px wide they must still line up with their letters and not wrap or overlap.
- The tagline as the main sentence.
- One supporting sentence, exactly: "Agents send requests to the OpenHAL hub, which checks each one against limits you set before anything reaches the device."
- Two actions: **Get started** (primary, links to the quickstart) and **Read the specification** (secondary, text link or quiet button).
- **Remove the hero sequence diagram.** The hero must not preview the demo.
- Layout: the hero currently has a big empty right half. Either center the hero block in the content column, or keep it left-aligned and size it so there's no large dead area. Pick whichever looks more deliberate, and record the choice in `DECISIONS.md`.

### 3.2 Delete the full-screen H / A / L sections (keep the hero labels)
- Remove the three full-screen letter sections that scroll after the hero and the animation that highlights each letter, including the duplicated markup. The hero labels from 3.1 already say what HAL stands for, so these sections only add length.
- Move their longer explanations to the docs Concepts page under a heading "What the name means" if they aren't already there.

### 3.3 "How it works": 3 steps instead of 9
Replace the 9-step scroll demo with a 3-step scroll section on **one simple diagram**.

**Diagram:** three columns, left to right: **Agent → OpenHAL hub → Printer**. No Owner lifeline, no webcam, no audit step. A small printer panel shows three values: Nozzle, Bed, State.
- The hub column shows the relevant limit from `printer.hal.yaml` when it applies (for example "Bed ≤ 110 °C").
- Requests are solid arrows and replies are dashed arrows back to the Agent.
- Status colors: green for success, red for refused, amber for waiting. Use the existing semantic colors.

**Steps (use these captions exactly):**
1. "The agent sets the bed to 70 °C. Your limit is 110 °C, so the hub passes the request to the printer."
   - The arrow goes Agent → hub → Printer, `done` returns to the Agent, and the printer panel's Bed changes from 60 °C to 70 °C.
2. "The agent asks for a 300 °C nozzle. Your limit is 260 °C, so the hub refuses the request."
   - The arrow stops at the hub, `LIMIT_EXCEEDED` returns to the Agent, and the printer panel doesn't change.
3. "The agent tries to cancel the print. Cancelling can't be undone, so the hub waits for you to approve."
   - The arrow stops at the hub as `pending` (amber). Then an **Approve** label or button appears at the hub, the cancel continues to the printer, `done` returns, and State changes to `cancelled`.

**Behavior:**
- Sticky scroll section with a step counter ("1 / 3"), a "Skip" link, and the existing smooth scrolling toggle.
- Caption sits in a fixed-height slot so the diagram never jumps between one-line and two-line captions.
- The diagram fills the sticky area with no large empty band below it.
- `prefers-reduced-motion`: show all three steps as static, stacked panels with no scroll-driven animation.
- Below step 3, add a text link: "See the full example: an agent watching a 3D print overnight".

### 3.4 Safety model
Keep the three rows (Limits a person confirmed, One STOP, Everything logged) as they are. They now summarize what the visitor just watched, so the repetition is fine.

### 3.5 What OpenHAL works with
Keep as is. The driver count must match the real number of drivers.

### 3.6 Run the demo
Keep as is. The code block works; keep it working (three separate lines, and Copy copies all three).

### 3.7 Read more
Keep the two links (specification, docs).

### 3.8 Footer
Keep as is.

---

## 4. New page: the full 3D print example

Create a docs page at `/docs/examples/3d-print-watch/`, titled "Example: an agent watching a 3D print", and add it to the docs sidebar under a new "Examples" group.

- Move the full 9-step sequence diagram here (Agent, Owner, OpenHAL hub, Printer lifelines, with reply arrows, the webcam frame with its "Seen:" labels, and the printer panel). It can be a static, fully drawn diagram, or keep the step-through interaction with Previous/Next buttons instead of scroll-driven animation.
- Add a short intro (2 to 3 sentences), the `printer.hal.yaml` file used in the example as a code block, the full list of JSON-RPC messages exchanged (`hal/read`, `hal/write`, `hal/action`, with the actual request and response objects), and the final audit log entries.
- Keep the step captions from the current home page demo (they're good), but drop any that repeat.
- Link to it from the home page (section 3.3) and from the Quickstart.

---

## 5. Other pages and components

### 5.1 Version picker
- The dropdown has one item (v0.1). A dropdown with one option looks unfinished.
- Show "v0.1" as a plain label (or a link to the spec's Versions section) while only one version exists. Make it a dropdown automatically once `spec/versions.json` lists two or more versions.

### 5.2 Docs "On this page" rail
- On the docs index, the right rail lists only "Overview". Hide the right rail on any page with fewer than 2 headings at h2 level, and let the content column use the space.

### 5.3 Spec page heading numbers
- The page title reads "1 OpenHAL specification" and the first section is "1.1 Introduction". Remove the number from the page title (h1) so numbering starts at the sections. Check that the sidebar numbering still matches the section numbers.

### 5.4 Search
- Search results for the Playground and Concepts pages show flattened YAML and code in their snippets (for example `provenance: { source: hand-written, by: ...`).
- Exclude code blocks and the diagram's text from the search index, or use the page description as the snippet when the match is inside code.
- Make sure the deleted letter sections and the 9-step home page demo no longer appear in the index.

### 5.5 Playground
- Make sure the Playground still works after the home page changes, and that the "Send the requests in your browser" link from the Run the demo section still lands on it.

---

## 6. Writing rules (apply to every word you write or touch)

- Write like technical documentation, not ad copy.
- Don't write sequences of short punchy fragments ("OpenHAL says no. You set 260 °C."). Connect related ideas in one natural sentence.
- Don't start every sentence the same way. In particular, don't start more than one sentence per section with "Because" or "When".
- Don't personify software ("the hub says no", "the kernel steps in"). Say what it does: refuses, returns, holds, passes.
- Be precise with units and nouns: "a nozzle temperature of 300 °C", "the bed target".
- No em dashes. Use commas, parentheses or separate sentences.
- No marketing words: unlock, empower, seamless, revolutionary, cutting-edge, robust (as filler), leverage, delve.
- Read every caption aloud. If it sounds like a movie trailer, rewrite it.

---

## 7. Banned patterns (don't introduce these anywhere)

- Logo marks or icons next to the wordmark
- Gradient backgrounds, glowing elements, glassmorphism, starfields
- Emoji used as icons
- Feature card grids with icons in circles
- Fake stats, testimonials or "trusted by" logos
- Any new color, font or spacing scale outside the existing design tokens
- Scroll-jacking that traps the user. The Skip link must always work and normal scrolling must still reach the rest of the page.

---

## 8. QA (required before you report)

Use Playwright for all of this. Save screenshots to `qa/after/`.

1. **Every page, both themes, both widths.** Screenshot the home page (full page and each section), the new example page, docs index, Concepts, spec and Playground at 1440×900 and 390×844, in light and dark.
2. **Each step of "How it works."** Screenshot steps 1, 2 and 3 separately (mid-scroll positions) at both widths. Check that each caption matches the diagram state, the printer panel values are right, and nothing overlaps or clips.
3. **Look at every screenshot yourself.** Check alignment, empty space, clipped text, overlapping elements, contrast, and whether the first screen explains the product on its own.
4. **Page height.** Report the home page's total height at 1440×900. Target: 4 to 5 screens. If it's over 6, cut more.
5. **Console and network.** No console errors or warnings and no failed requests on any page.
6. **Accessibility.** Run axe-core on the home page, the example page and the spec, and fix every violation. Check keyboard navigation through the nav, the version label, the theme switch, search, the Skip link and the Copy button.
7. **Reduced motion.** Emulate `prefers-reduced-motion: reduce` and confirm the How it works section shows static stacked panels.
8. **Search.** Search for "babysit", "LIMIT_EXCEEDED", "abstraction" and "provenance", and screenshot the results. No YAML snippets, no removed sections.
9. **Links.** Crawl every internal link on the site and fix any 404s.
10. **Live check.** After pushing, wait for the Pages deploy to finish, then repeat steps 1 and 4 against the **live** URL, not localhost. The task isn't done until the live site shows the changes.

---

## 9. Definition of done

- [ ] Deploy pipeline fixed and explained in DEPLOY_NOTES.md
- [ ] Home page: hero with readable [hardware] [abstraction] [layer] labels and no diagram, no full-screen H/A/L sections, 3-step How it works, Safety model, Works with, Run the demo, Read more
- [ ] Home page is 4 to 5 screens tall at 1440×900
- [ ] Full 9-step example lives on its own docs page, linked from home and Quickstart
- [ ] "What the name means" on Concepts says Hardware Abstraction Layer
- [ ] Version label instead of a one-item dropdown
- [ ] No one-item "On this page" rails
- [ ] Spec h1 unnumbered
- [ ] Search snippets clean, removed content not indexed
- [ ] All copy follows the writing rules
- [ ] QA complete: screenshots, axe, console, links, reduced motion
- [ ] Changes verified on the live site

When you're done, send me a short report: what changed (one line per section), the home page height before and after, the deploy issue you found, and anything you couldn't do and why. Include the paths to the before and after screenshots.
