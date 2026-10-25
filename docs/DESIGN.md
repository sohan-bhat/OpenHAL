# Design

OpenHAL has exactly one theme: a formal open protocol. Everything (website, Inspector, README, diagrams, CLI output, error messages, social images) looks and reads like a well-run modern protocol: precise, versioned, calm, trustworthy.

The tokens live in `design/tokens.css`, and every surface imports them. If something needs a value this document doesn't define, add it here first.

Theme rules.
1. The theme lives in structure, components, typography, terminology and copy, never in illustrations or decoration.
2. Clarity beats theme. A term a newcomer may not know links to the glossary on first use.
3. Everything is themed, including every empty state, error, 404, loading state, favicon, social image and README.
4. Every visual element comes from a real part of the system. Before a surface ships, list its elements and remove any that come from nowhere.
5. Every piece of UI chrome works, or it isn't drawn.

## Subject and job

OpenHAL is an open protocol for AI agents to discover, read and control hardware safely. The reader is an engineer deciding whether to implement or adopt it. The site's job is to make the protocol legible: what a client sends, what the hub answers, and why a write is refused. The Inspector's job is to show every device and every message, and stop anything in one click.

## Signature elements

Two elements carry the identity.

### The animated flow diagram

A clean flowchart of one command, left to right. AI client, then OpenHAL hub (with the Device files that feed the kernel), then Safety kernel, then Driver, then Arduino plant waterer. A branch from the kernel goes down to a Blocked node, `INTERLOCK_BLOCKED: tank empty`. Connector labels in the mono face read `hal/action`, `check`, `grant` and `command`, and a thin return line reads `reading`.

- Rounded rectangles with 1.5 px strokes, equal heights and consistent widths on a grid. Orthogonal connectors with right-angle turns only, one arrowhead style, no crossings.
- One neutral for nodes and wires, the accent for the active path, red only for the Blocked node and its connector.
- Only the wires move. A dash flows along each connector in the direction data travels, 2 to 3 s per loop, staggered from client to device. The blocked branch flows to Blocked, then pauses. `prefers-reduced-motion` stops all of it.
- Source `docs/diagrams/flow.d2`, built with `scripts/build-diagrams` into `docs/diagrams/flow-light.svg` and `flow-dark.svg`. The README hero and the website home hero use these files.

### The message trace

A two-column trace of a request and the hub's answer, the way a protocol spec shows an exchange. It appears below the hero on the website, in the README as a code block, in the spec and docs, in the Inspector's message log and in social images.

```
→ hal/action  { "device": "plant-waterer", "action": "water",
                "args": { "duration": { "value": 120, "unit": "s" } } }
← error -32010 LIMIT_EXCEEDED
  water duration 120 s exceeds the limit of 30 s
  (plant-waterer.hal.yaml, confirmed by sohan 2026-10-24)
```

- **Direction column.** An arrow pointing right for client to hub, left for hub to client, and a dashed left arrow for notifications, in the text color. Atkinson Hyperlegible Mono has no arrow glyphs, so the arrows are drawn as small inline SVGs in the house diagram style (1.5 px stroke, 6 px filled head), never typed characters. Plain text renditions in a font that has arrows, such as the README code block, use `→` and `←`. CLI output uses `->` and `<-`.
- **Method or outcome column.** The method name in the accent color. `error` plus the numeric code and the registry name in the blocked red. `result` in the granted green. Each is paired with its word, never color alone.
- **Payload.** JSON in the mono face with the house syntax theme. Reasons as plain mono text on their own line.
- Method names, codes and names match ADR 0015 and the generated schema exactly, everywhere.

## Canonical demo scenario

Every example value in the README, website, Inspector screenshots, docs and social images comes from one file, `docs/demo/scenario.yaml`, written by `uv run openhal demo --record docs/demo/scenario.yaml` from a real run of the hub against the plant waterer mock (examples/plant-waterer/). The device is an Arduino plant waterer with `soil_moisture` and `tank` readings and one action, `water(duration)`, limited to 30 s, 3 runs per hour and never while the tank is empty. The trace has three exchanges. Watering for 120 s gets `LIMIT_EXCEEDED`. Watering for 20 s with the tank empty gets `INTERLOCK_BLOCKED`. After a refill, watering for 20 s is done and soil moisture rises from 31 % to 46 %. Tests check that the file is still what the hub answers and that every surface matches it. The desk fan stays only as a secondary example in spec/examples/. Demo values are labeled as demo data where shown.

## Theme mapping

| Surface, feature or state | How the theme expresses it |
|---|---|
| Home page | One sentence, the flow diagram, the message trace, a three-command quickstart, device families from the catalog, two sentences on MHS, links into the spec |
| Spec pages | Dated version in the URL and a switcher, numbered sections, MUST, SHOULD and MAY, outline, anchors, previous and next, "Edit on GitHub" |
| Schema reference | Generated tables of every message, type and field, monospace names |
| Error codes | The registry table, the message trace with `error`, code and name in the blocked red with its shape |
| Granted write | `result` in the granted green with its shape |
| Confirmation required | Amber with the half-circle shape and the words "confirmation required" |
| Stopped | The blocked red, the word "stopped", the STOP control turning into UNLOCK |
| Unverified driver or device | Gray with a dashed outline and the word "unverified" |
| Drivers and Device Library | Datasheet-style tables with conformance level, status and hazard default |
| Playground | A spec-style editor and the message trace for each attempted command, labeled as an in-browser demo |
| Inspector | Device list, device pane and message log as JSON-RPC traces |
| Empty states | One sentence that says what is missing and the command or link that fills it |
| 404 | A message trace of the request and `error -32004 UNKNOWN_TARGET` |
| Loading | The layout at its final size with values shown as an em space until they arrive, no spinners on loaded content |
| CLI output and errors | Plain text with `->` and `<-`, error name and code first, then the reason |
| Social images | The message trace on the page's title, in the house style |
| Favicon | The mark at 16 px |

Anything that doesn't map gets plain, neutral treatment, never a second metaphor.

## Color

Cool neutrals with one accent. Status colors only for meaning.

| Token | Light | Dark | Role |
|---|---|---|---|
| `--bg` | `#FCFCFD` | `#0D0F12` | Page background |
| `--surface` | `#F4F5F7` | `#15181D` | Code blocks, the trace, panels |
| `--border` | `#DADDE2` | `#2A2F36` | Rules and outlines |
| `--text` | `#15181C` | `#E7EAEE` | Body text and headings |
| `--text-2` | `#4F5661` | `#A0A7B1` | Secondary text, JSON keys |
| `--accent` | `#1D5FB4` | `#7DB2F0` | Links, active navigation, method names, the logo |

| Status | Light | Dark | Shape and word |
|---|---|---|---|
| ok, granted | `#1E7A44` | `#5BC58A` | filled circle, "granted" or "ok" |
| confirmation required | `#8A5A00` text on `#FFF3CC` | `#E8B341` | half circle, "confirmation required" |
| blocked, stopped | `#B42318` | `#F07068` | circle with bar, "blocked" or "stopped" |
| unverified | `#636A75` | `#8B93A0` | dashed outline, "unverified" |

Every pair passes WCAG AA for its text size. Status never appears as color alone.

### Syntax theme

One theme built from the palette, used on the site, in README images and in the Inspector. Keys `--text-2`, strings `--text`, numbers and booleans `--accent`, punctuation `--text-2`, method names `--accent` at weight 700, error names in the blocked red at weight 700, comments `--text-2` italic.

## Typography

Two faces from one family.

| Role | Face | Why |
|---|---|---|
| Text and headings | Atkinson Hyperlegible Next (OFL) | Designed by the Braille Institute for legibility. It tells 0 from O and 1 from l and I, which matters on pages full of identifiers, units and codes. It has character without being decorative, and it is not Inter or a system stack |
| Code, messages, method names, values | Atkinson Hyperlegible Mono (OFL) | The same family's monospace, with the same distinct letterforms, so prose and protocol read as one voice |

Scale, mobile then desktop. 13/13 legend, 15/15 secondary, 16/17 body with line height 1.65, 20/22 h3, 26/30 h2, 34/44 h1. Reading column at most 72 characters. Headings are sentence case. Short labels may use small caps through `font-variant-caps: all-small-caps`.

## Layout

- Documentation-first. Left sidebar navigation, a centered reading column, and an "On this page" outline on the right at 1280 px and wider.
- Breakpoints 390, 768, 1024, 1280. At 390 the sidebar becomes a menu and the outline moves above the content.
- Spacing scale 4, 8, 12, 16, 24, 32, 48, 64.
- Borders are 1 px `--border`, radius at most 6 px, no shadows.
- Every spec page has anchor links on headings, copy buttons on code, previous and next links, "Edit on GitHub", and the spec version in the URL.

## Logo

- **Wordmark.** "OpenHAL" in Atkinson Hyperlegible Next at weight 700, in `--text`.
- **Mark.** A request stroke ending at a vertical stop bar, above a return stroke pointing back. It reads as a request and an answer with a limit in between. It sits on a 16 px grid with 2 px strokes in `--accent`, and stays legible at 16 px. Built by tools/readme/build.py into docs/assets/mark-{light,dark}.svg, docs/assets/favicon.svg and the wordmarks, which the website reads, and drawn the same way in the Inspector header (dashboard/src/components/Mark.svelte).
- Original. It never imitates MCP's, Anthropic's or any other logo.

## Diagrams

One house style for sequence and architecture diagrams.
- 1.5 px lines in `--text-2`.
- Filled triangular arrowheads, 6 px.
- Labels and messages in the mono face.
- Participants as plain bordered boxes with sentence-case names.
- Light and dark variants, transparent backgrounds.
- Status colors only on arrows that carry a granted or blocked outcome.

## The Inspector

The dashboard is the OpenHAL Inspector, a protocol inspector.
- **Left pane.** Devices with their conformance level and verification.
- **Main pane.** The selected device's channels, limits and live values.
- **Bottom pane.** The live message log, every request, response, notification and error as formatted JSON-RPC, filterable.
- **Stop control.** Large and always visible in the header, in the blocked red with its word, never styled like other buttons.
- **Agent requests and human confirmations look different.** Agent entries carry the client's name and a dashed rule. Human decisions sit on a solid surface.

## Motion

Three patterns, nothing else.
1. The flowing connectors in the flow diagram.
2. A message appearing in the trace or log. A 120 ms fade, 4 px rise.
3. A status change. A 120 ms cross-fade.

With `prefers-reduced-motion: reduce`, nothing moves.

## Copy voice

- Formal and exact, like a good specification.
- Short declarative sentences.
- Defined terms capitalized on first use and linked to the glossary (Hub, Device File, Safety Kernel, Driver, Grant, Conformance Level).
- No hype. Marketing pages use the same voice as the spec.
- "Open protocol" and "specification", never "standard".
- State plainly that OpenHAL is not affiliated with Anthropic or MHS.
- No em dashes or en dashes, and no colons or semicolons in running prose.
- No exclamation marks.

## Banned

These rules apply to the website, the docs and the dashboard, and to every diagram and image in the repository. They come from the owner and override anything above that disagrees.

### Banned for the protocol theme

- Copying MCP's or any other protocol site's logo, colors, illustrations or exact layout. Using a docs framework's default theme unstyled, such as a stock Mintlify, Docusaurus or Starlight look.
- Hero illustrations, 3D objects, abstract network or "connection" graphics.
- Marketing sections on the home page, such as feature grids, testimonials, stats or logos.
- Calling anything a standard that isn't one.
- Inconsistent names. Method names, error codes and terms match the schema exactly everywhere.
- A failing CI badge. Show the CI badge only while CI passes.
- Demo GIFs or demo panel images as the README hero.

### Never, no exceptions

Honesty
- Fake stats, user counts, star counts, download numbers, "trusted by" logo strips, testimonials or quotes.
- Fake data presented as real. Screenshots come from the real product running on mocks, labeled as demo data where shown.
- Listing a device or driver as supported unless drivers/catalog.json has it with that status. Unverified things are labeled unverified.
- Lorem ipsum, "John Doe", placeholder avatars, stock photos of people.
- Pricing tables, "Book a demo", waitlist forms or "Enterprise" calls to action. There is nothing to sell.

Safety semantics
- Red used decoratively. Red means blocked, stopped or danger, and nothing else.
- Yellow and black hazard stripes or ISO 7010 symbols as decoration. They only appear next to real hazards.
- Status shown by color alone. Always pair it with an icon, a label or a shape.
- A stop control that is hidden, collapsed, small or styled like a normal button.
- Any UI where an agent action and a human confirmation look the same.

Accessibility
- Text contrast below WCAG AA, including gray on gray muted text and text over images or gradients.
- Body text under 16 px on the website or 14 px in the dashboard. Body weights under 400.
- Removing focus outlines without a visible replacement.
- Motion that ignores prefers-reduced-motion. Anything that flashes more than 3 times per second.
- Information only available on hover.

### Banned by default (only with a written justification in this file)

AI-slop visuals
- Purple, indigo, violet or blue-to-purple gradients. Aurora and mesh gradient backgrounds.
- Glassmorphism, frosted panels, backdrop blur as decoration.
- Neon glow, glowing orbs, light beams, spotlight effects that follow the cursor.
- 3D, clay or glossy rendered objects, isometric illustrations, floating decorative shapes.
- Grain or noise overlays, dot-grid or line-grid backgrounds used as filler.
- Animated gradient borders, shimmer effects, sparkle animations.
- The sparkles icon to mean AI.

Hardware and AI clichés
- Circuit-board trace patterns, glowing PCB backgrounds, chip icons as decoration.
- Robot mascots, robot hands, humanoid robots.
- Brains, neural network node diagrams, "digital DNA".
- Matrix code rain, cyberpunk neon, sci-fi HUD overlays.
- HAL 9000's red eye or 2001 references in the design. Jokes stay in copy, if anywhere.
- Terminal mockups with fake typing in the hero. Show real commands, static and copyable.

Layout templates
- Centered title, tagline, subtitle and badge row (the default README layout), on GitHub or the website.
- Centered hero, one-line subhead, two pill buttons and a product card on the right.
- Three icon feature cards in a row.
- Bento grids.
- Zigzag sections alternating text and screenshot all the way down the page.
- A stats strip of big numbers.
- Logo marquees and auto-playing carousels.
- FAQ accordions used as filler.
- Footers with columns of placeholder links.
- Every container as a rounded card with a soft drop shadow. Hover-lift on everything.

Typography
- Inter, Geist, Poppins, Roboto, Montserrat or system-ui as the only typeface.
- A serif headline with one italic or gradient-colored accent word.
- Gradient-filled text.
- All caps for anything longer than a short label.
- More than 3 typefaces.

Components and icons
- Stock shadcn, MUI, Chakra or Tailwind UI appearance. Restyle everything to our tokens.
- Lucide or Heroicons used as-is everywhere as decoration. Icons only where they add meaning, drawn consistently.
- Emoji as icons or in headings.
- Toasts for things that need attention. Blocks and stops get persistent, visible states.
- Modals for anything except confirmations and destructive actions.

Dashboard
- Donut or pie charts for single values. Decorative gauges that can't be read precisely.
- Rainbow chart palettes. More than 5 series colors.
- Numbers without units. Values that jump or shift layout when they update.
- Spinners on content that is already loaded. Skeleton screens that don't match the real layout.
- Charts without axes or labeled scales.

Motion and interaction
- Scroll-jacking, parallax, scroll-triggered fade-in on every section.
- Typewriter text effects, counting-up numbers.
- Custom cursors, cursor trails, magnetic buttons.
- More than 3 motion patterns sitewide. Any animation that doesn't communicate a state change.

Copy
- Banned words: unlock (except the literal control after a stop), seamless, supercharge, elevate, effortless, empower, revolutionary, next-generation, cutting-edge, game-changer, magic, harness, unleash, journey, "Welcome to", "the future of".
- "X for Y" taglines ("Stripe for hardware"), "Say goodbye to...", "Meet X", rhetorical questions as headlines.
- "It's not X, it's Y" constructions.
- Exclamation marks.
- Em dashes.
- Vague claims without specifics ("works with everything", "blazing fast", "enterprise-grade").

## README and diagrams

The repository README follows this structure, in this order, left-aligned.

1. The wordmark (SVG, light and dark) and one sentence. "An open-source protocol for AI agents to control hardware." No second sentence and no subtitle. The same sentence is the website subhead, the default OG description, the pyproject description and the GitHub repository description.
2. Two neutral badges, the license and CI.
3. The animated flow diagram, directly under the badges.
4. Quickstart. Three commands in one code block, then one line on what you'll see, generated from the scenario.
5. The message trace, the three exchanges of the canonical scenario, as a code block generated from the scenario (`uv run python -m openhal.demo.readme`).
6. "What it does", three bullets.
7. Supported devices. Status as a sentence, "v0.1, in development. Every driver passes the conformance suite on a simulator.", then a table generated from drivers/catalog.json with driver, devices covered, status and hazard default.
8. Safety model, at most five bullets, linking to docs/SAFETY.md.
9. Relationship to MHS, two sentences.
10. Contributing a driver or device file, then the license.

No demo GIF, no demo panel images, no emoji in headings, no rules between sections.

Images ship as SVG in light and dark variants through `<picture>` with a `prefers-color-scheme: dark` source, on transparent backgrounds, at most 900 px wide, with descriptive alt text. Text in SVGs is converted to paths or uses an embedded subset font, since GitHub loads no web fonts. No JavaScript and no external files inside SVGs.

All diagrams (flow, architecture, sequence, discovery, driver writer) use one D2 house style with light and dark variants.

Verify by rendering the README in GitHub's light and dark modes and at phone width. The animation plays, reduced motion shows static lines, nothing looks like a slab, all image text reads at 100 % zoom, and the diagram and quickstart are visible without scrolling at 1440 by 900.

## Generic-ness tests

Run these on every screen before calling it done.

1. **Swap.** Put another product's name on it. If it still fits, revise.
2. **Thumbnail.** Blur a screenshot to 200 px wide. It should still read as a specification with message exchanges.
3. **Memory.** What does a visitor remember ten minutes later? It should be the flow diagram's blocked branch and the message trace with LIMIT_EXCEEDED and INTERLOCK_BLOCKED.
