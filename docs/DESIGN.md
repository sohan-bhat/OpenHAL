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

Three elements carry the identity. The flow diagram heads the README, the message trace shows every exchange, and the landing story tells both as one scene on the website.

### The animated flow diagram

A clean flowchart of one command, left to right. Agent, then OpenHAL hub (with the Device files that feed the kernel), then Safety kernel, then Driver, then 3D printer (Klipper through Moonraker). A branch from the kernel goes down to a Blocked node, `LIMIT_EXCEEDED: nozzle 300 °C`. Connector labels in the mono face read `hal/write`, `check`, `grant` and `command`, and a thin return line reads `reading`.

- Rounded rectangles with 1.5 px strokes and 6 px corners, every node 112 by 88 on a grid, with every wire level. Orthogonal connectors with right-angle turns only, one arrowhead style, no crossings.
- The Safety kernel and Driver nodes each say what they do in a short line, and the blocked code sits under the Blocked node.
- One neutral for nodes and wires, the accent for the active path, red only for the Blocked node and its connector.
- Only the wires move. A dash flows along each connector in the direction data travels, 2 to 3 s per loop, staggered from client to device. The blocked branch flows to Blocked, then pauses. `prefers-reduced-motion` stops all of it.
- Source `docs/diagrams/flow.d2`, built with `scripts/build-diagrams` into `docs/diagrams/flow-light.svg` and `flow-dark.svg`, plus narrow variants for phones. The page picks the narrow one by the figure's width, not the viewport. The README hero uses these files.

### The message trace

A two-column trace of a request and the hub's answer, the way a protocol spec shows an exchange. It appears in the README as a code block, in the Playground, in the spec and docs, in the Inspector's message log and in social images.

```
→ hal/write   { "device": "printer", "channel": "extruder_target",
                "value": 300, "unit": "degC" }
← error -32010 LIMIT_EXCEEDED
  extruder_target 300 degC exceeds the limit of 260 degC
  (printer.hal.yaml, confirmed by owner 2026-10-24)
```

- **Direction column.** An arrow pointing right for client to hub, left for hub to client, and a dashed left arrow for notifications, in the text color. Atkinson Hyperlegible Mono has no arrow glyphs, so the arrows are drawn as small inline SVGs in the house diagram style (1.5 px stroke, 6 px filled head), never typed characters. Plain text renditions in a font that has arrows, such as the README code block, use `→` and `←`. CLI output uses `->` and `<-`.
- **Method or outcome column.** The method name in the accent color. `error` plus the numeric code and the registry name in the blocked red. `result` in the granted green. Each is paired with its word, never color alone.
- **Payload.** JSON in the mono face with the house syntax theme. Reasons as plain mono text on their own line.
- Method names, codes and names match ADR 0015 and the generated schema exactly, everywhere.

### The wordmark sequence

The owner's idea on 2026-10-27. Right after the hero, scrolling brings the large OpenHAL wordmark down into a pinned stage, while the one-line description and Get started scroll away, and the stage walks through the letters H, A and L in three steps. In each step the current letter keeps full strength and every other letter fades to a low opacity, and between letters the whole word slides left, so each current letter lands in the same place. Coming down, the word moves right so H stands where L stands at rest, so the slide never crosses the column's left edge, and on phones and narrow tablets the word shrinks while it comes down, just enough that the moved word fits the column. The hero's labels fade as the word comes down, the other letters fade to an opacity of 0.14, and a short brief in Copy voice says what the current part means, headed by the hero's label for the letter ([hardware], [abstraction] or [layer]). The brief sits under the current letter on a desktop and under the whole word below 1024 px. The h1 keeps its text for screen readers under an aria-hidden copy of the letters that moves. H is the hardware, the devices with device files whose limits a person confirmed. A is the abstraction, one interface for every device, so an agent uses the same few requests for a 3D printer, a bench power supply or an Arduino board while the device file and the driver handle the differences. L is the layer, the hub between the agent and the hardware, where the safety kernel checks every request against the limits before a driver sends a command. There are no boxes, the motion uses transforms and opacity only and follows the scroll, and with reduced motion or no script the three briefs are a static list under the wordmark. The print babysitter story follows the sequence.

### The landing story

The website's home page tells the canonical scenario as one pinned scene drawn with lines and text only. There are no boxes anywhere in the story, so no bordered cards, panels, tinted areas or framed images around a station, the log or the webcam frame. The owner asked for this on 2026-10-27. The scene is a sequence diagram with thin, evenly spaced vertical lifelines in the order Agent, Owner, OpenHAL hub and Printer, so the owner's arrows never cross the agent's lifeline, and the owner's lifeline breaks where an agent arrow passes over it. Each step adds one request as an arrow with a short mono label, and each answer returns as a dashed reply arrow to the sender in the outcome's color, so the refusal visibly returns to the agent. A request the hub forwards continues to the device and ends in the result, a refused request stops at the hub's lifeline with the error in red, and the held cancel stops at the hub's lifeline in amber until the person's approval arrives and the cancel continues to the printer. Earlier arrows stay in a quieter color, so the last step shows the whole exchange together with the audit log's counts. Beside the lifelines, the webcam's line drawing changes with the print and has no frame. The drawing shows a flat print until the agent's first read and then carries a line saying what the frame shows ("Seen: first layer corner lifting", then "Seen: print loose"). The printer's nozzle temperature, bed target and state sit beside the drawing as plain text, and after the cancel the nozzle cools from 215 °C to 155 °C and 113 °C as the record shows, while the target rows leave because the hub doesn't read the targets again after a cancel. Each step has the owner's caption for the step, at the top of a slot two lines tall on a desktop and a tablet and three on a phone. The answer words are the record's own, such as done, LIMIT_EXCEEDED and pending. The step count reads as text ("4 / 9") beside a Skip the demo link and the Smooth scrolling switch. Every word and number comes from docs/demo/scenario.yaml. On a screen too short for the scene, with reduced motion or with no script, the story shows the whole diagram as the story ends, followed by a static list of the same steps. The motion is pattern 4 under Motion. Source in website/src/components/landing/.

## Canonical demo scenario

The main example is a task that needs an agent. A timer or an IoT rule waters a plant on a schedule, but watching a print on a camera, judging what is going wrong and acting takes an agent, so the main example is the 3D print babysitter (examples/print-babysitter/). The owner chose the print babysitter on 2026-10-26.

Every example value in the README, website, Inspector screenshots, docs and social images comes from one file, `docs/demo/scenario.yaml`, written by `uv run openhal demo --record docs/demo/scenario.yaml` from a real run of the hub against simulated devices. There are two. `printer` is a Klipper 3D printer reached through Moonraker, with `state`, `extruder_temp`, `bed_temp` and `progress` readings, `extruder_target` limited to 260 °C and `bed_target` limited to 110 °C, both rate limited, and the actions `pause`, `resume` and `cancel`, where cancel waits for a person. `printer-cam` is the printer's webcam watching the bed, read as snapshots over HTTP the way crowsnest serves it on a Klipper printer (the `http` driver). The limits were confirmed by owner on 2026-10-24.

The story. Someone starts a long print and asks an agent to keep an eye on it.
1. The agent reads a camera frame, an image Reading (ADR 0015), and sees a corner of the first layer lifting.
2. The agent raises `bed_target` from 60 °C to 70 °C. The new target is inside the limit, so the write is done.
3. Because a hotter nozzle might help the corner stick, the agent requests a nozzle temperature of 300 °C, and the kernel refuses the request with `LIMIT_EXCEEDED` because the nozzle limit is 260 °C.
4. Later the camera shows the print has come loose. The agent pauses the print, which is done straight away.
5. The agent asks to cancel. Cancelling can't be undone, so `cancel` is `confirm-each-time`, and the hub queues the request and answers pending.
6. The owner approves the cancel within the hub's five minute window. The kernel checks every limit again and grants the cancel, the driver sends the cancel to the printer, and the printer's state reads cancelled. The printer's CANCEL_PRINT macro turns the heaters off, so the record then follows the nozzle as the nozzle cools for a minute. The hub's audit log then holds every request, the refusal and the person's approval.

Tests check that the file is still what the hub answers and that every surface matches it. Demo values are labeled as demo data where shown.

The Arduino plant waterer (examples/plant-waterer/) stays as the Arduino example. It runs the end-to-end demo (`openhal demo --full`, docs/demo/e2e.yaml), the driver writer tutorial and the first hardware test, since it is the lowest hazard. The desk fan stays only as a secondary example in spec/examples/.

## Theme mapping

| Surface, feature or state | How the theme expresses it |
|---|---|
| Home page | The text wordmark, the one sentence and Get started beside a small still copy of the whole sequence diagram, the wordmark sequence, the landing story of the print babysitter, the safety model in three points, device families from the catalog, the three-command quickstart with a link to the Playground, and links to the spec and the docs |
| Spec pages | The version, v0.1, in the URL and in the header's version picker, numbered sections, MUST, SHOULD and MAY, outline, anchors, previous and next, "Edit on GitHub" |
| Schema reference | Generated tables of every message, type and field, monospace names |
| Error codes | The registry table, the message trace with `error`, code and name in the blocked red as plain text |
| Granted write | `result` in the granted green |
| Confirmation required | The words "confirmation required" in amber |
| Stopped | The blocked red, the word "stopped", the STOP control turning into UNLOCK |
| Unverified driver or device | The word "unverified" in gray |
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

| Status | Light | Dark | How it shows |
|---|---|---|---|
| ok, granted | `#3C754F` | `#72B88E` | the word in green, "granted", "ok" or "connected" |
| confirmation required | `#8A5A00` | `#E8B341` | the words "confirmation required" in amber |
| blocked, stopped | `#A14034` | `#D57A72` | the word in red, "blocked" or "stopped" |
| unverified | `#636A75` | `#8B93A0` | the word "unverified" in gray |

Every pair passes WCAG AA for its text size on `--bg` and `--surface`. A status always shows as its word, so it never relies on color alone. No status has a dot, circle, shape or icon beside it, and a status, error code or verdict never sits in a box with a colored border or a tinted background. It is plain text, in mono for codes. The owner had the green and red dulled slightly on 2026-10-26. Neutral states (disabled, started, running, connecting, no confirmation) show their word in the text colors. Dashed rules mark an agent's entries, in the Inspector and in the Playground's log, and nothing else. Simulated devices, demo data, data blocks and empty states sit on a surface fill, and disabled controls are flat surface gray.

### Syntax theme

One theme built from the palette, used on the site, in README images and in the Inspector. Keys `--text-2`, strings `--text`, numbers and booleans `--accent`, punctuation `--text-2`, method names `--accent` at weight 700, error names in the blocked red at weight 700, comments `--text-2` italic.

## Typography

Two faces from one family.

| Role | Face | Why |
|---|---|---|
| Text and headings | Atkinson Hyperlegible Next (OFL) | Designed by the Braille Institute for legibility. It tells 0 from O and 1 from l and I, which matters on pages full of identifiers, units and codes. It has character without being decorative, and it is not Inter or a system stack |
| Code, messages, method names, values | Atkinson Hyperlegible Mono (OFL) | The same family's monospace, with the same distinct letterforms, so prose and protocol read as one voice |

Scale, mobile then desktop. 13/13 legend, 15/15 secondary, 16/17 body with line height 1.65, 20/22 h3, 26/30 h2, 34/44 h1. Reading column at most 72 characters. Headings and labels are sentence case. Table headers, form labels and captions carry meaning and stay, set in sentence case at the legend size or larger. Decorative eyebrows, corner tags and micro labels are not used.

## Layout

- Third-party first, the owner's rule from 2026-10-28 and 2026-10-29. Almost every interactive element comes from a popular framework or library rather than hand-written code: Starlight for the docs frame, Tailwind CSS (through Starlight's official Tailwind integration) for styling new components, shadcn/ui components on Radix primitives in React islands for menus, dialogs, the search palette and the sidebar's collapse, cmdk for the search palette over the site's Pagefind index, and Motion (Framer Motion) for animation. Each library is themed with design/tokens.css, so the protocol theme stays.
- Documentation-first, on Astro Starlight. On 2026-10-28 the owner asked for the documentation frame to come from a proven third-party base instead of hand-built parts. The header, sidebar, outline, search, pickers and previous and next links are Starlight's components themed with design/tokens.css, and anything Starlight lacks is an override of one of its components, never a second frame. A left sidebar, a 772 px reading column and an "On this page" outline on the right from 1152 px. When one of Starlight's components is too slow for a page, the fix is a small patch to that component in website/patches, kept until Starlight ships the same fix, never a hand-built copy. The outline carries one, which finds the elements the outline observes without testing every element of the page.
- Long pages. A page with more than 20 tables, today only the schema reference, renders each table after the first as the table nears the screen and holds about the table's height until then, so the page opens as fast as a short one. The outline's column takes no part in scroll anchoring, so a jump lands under the header where the jump would land with every table drawn, and print, find in page, screen readers and search see every table.
- One header on every page, the home page included, as the owner asked on 2026-10-27. The text wordmark, then Overview, Docs, Specification, Playground, Drivers and Device Library with the current section on the nav's blue highlight, then the search field with its shortcut, and at the right GitHub, a 1 px rule, the specification version picker and the theme picker. From 800 to 1023 px the sections become one Section picker, and from 1024 to 1139 px the search shows as its icon. Under 800 px the header holds the wordmark, the search icon and the menu button, and the menu lists the sections over the page's sidebar, with GitHub and both pickers at its foot. The header is 61 px tall over a 1 px `--border` rule, with no shadow.
- One left edge. The header, the sidebar and the outline share the 1360 px container, so nothing in them moves when a person changes pages, and the wordmark lines up with the sidebar's links and with the home page's column. Every page but home starts its title in the column the 300 px sidebar leaves, 364 px from the left at 1440 px, 324 px at 1280 and 1360 px and 316 px at 1024 px, and the blog and the 404 page, which have no sidebar, keep that column.
- The sidebar. Each section has its own sidebar, the docs in their groups, the specification's numbered sections under "Specification v0.1", the drivers by status, the device library and the SDKs. Every group collapses with a caret, the group that holds the current page is open, and the open groups and the scroll position carry over between pages. The current page shows in the accent at weight 700 on the nav's blue highlight. Nothing hides the whole sidebar, because no maintained Starlight plugin offers that, and the owner prefers a proven sidebar to a hand-built one.
- The specification version picker. A menu button in the header after GitHub that shows the version as v0.1 with a chevron and opens a list of every version. On a spec page each version opens the same section in that version, or that version's start when the section is missing, and on every other page the picker shows the latest version. Under 800 px the picker sits at the foot of the menu. The dated addresses and /spec/latest/ move to the matching v0.1 page and keep the anchor.
- The theme picker. A menu button after the version picker with Auto, Light and Dark, kept per browser in Starlight's own setting, where Auto follows the system.
- Every picker is a menu button on a native popover list, so a click outside closes the list and the button works before any script runs. Enter, Space and the arrow keys open a picker and move through the list, Home, End and a letter jump, Escape closes the list with focus back on the button, and Tab leaves the list closed. The list opens 4 px under its button, or above the button where the screen has no room, on the page background in a 1 px `--border` box with rows rounded inside its padding, the current choice on the nav's blue highlight and no shadow. CSS anchor positioning places the list, and Floating UI places the list in a browser without anchoring.
- Asides. A note, tip, caution or danger aside sits in a 1 px `--border` box on the page background with its title in `--text`, no icon and no tint.
- Breakpoints 800, 1024, 1140 and 1152. Under 800 px the sidebar is the menu, from 800 to 1023 px the sections are one picker, from 1024 to 1139 px the search is its icon, and under 1152 px the outline is an "On this page" disclosure under the header. Pages are checked at 390, 768, 1024, 1280 and 1440 px.
- Spacing scale 4, 8, 12, 16, 24, 32, 48, 64.
- Borders are 1 px `--border`, radius at most 6 px, no shadows. Controls with an outline, such as the search field and its shortcut key, inputs, selects and outlined buttons, draw the outline 1.5 px wide, the owner's request on 2026-10-28. Browsers round a border's width down to whole pixels, so the outline is a 1 px border with an inset 0.5 px ring in the same color, a solid line and not a shadow, set by one token. Rules, dividers, table borders, panels and the pickers' lists stay 1 px.
- Pickers and menus show words only, with a chevron where they open, and never an icon beside the word.
- Every spec page has anchor links on headings, copy buttons on code, previous and next links, "Edit on GitHub", and the spec version in the URL.

## Information marks

Pages show the one thing a person needs and keep the depth one tap away. A term or control that needs explaining gets a small information mark, a lowercase i in a 16 px circle in `--text-2`, right after it. Tapping or clicking it, or pressing Enter on it, opens a short popover of one to three sentences with an optional "Read more" link into the docs, and Escape or a click outside closes it. It is a real button with an accessible name ("About hazard"), never hover-only, and the popover keeps AA contrast in both themes. Use it instead of a paragraph above the control. At most one per row, and never on every label.

## Wordmark

- **Wordmark, no logo.** The brand is the name, OpenHAL, set in Atkinson Hyperlegible Next at weight 800 with tracking at -0.06 em, in `--text`. There is no logo shape. Where a square is needed (favicon, app icons) the initials OH are set the same way. Built by tools/readme/build.py into docs/assets/wordmark-{light,dark}.svg, mark-{light,dark}.svg (the initials) and favicon.svg, which the README and the website read. The Inspector sets the same wordmark in its header.
- **HAL spelled out, on the landing hero only.** Under the letters H, A and L of the large hero wordmark sit three small labels, written exactly `[hardware]`, `[abstraction]` and `[layer]` with their square brackets, for Open Hardware Abstraction Layer, lowercase in `--text-2`, growing with the word up to 17 px, each centered under its letter. The owner asked for the brackets on 2026-10-26. On a narrow phone a label that would touch its neighbor drops to a second row under its own letter. They are hidden from screen readers, which read OpenHAL, and the long name Open Hardware Abstraction Layer is in the page's metadata. The header wordmark, icons and the README stay plain.
- Original. It never imitates MCP's, Anthropic's or any other logo.

## Diagrams

One house style for sequence and architecture diagrams.
- 1.5 px lines in `--text-2`.
- Filled triangular arrowheads, 6 px.
- Labels and messages in the mono face.
- Participants as plain bordered boxes with sentence-case names. The landing story is the exception, with its lifelines named in plain text and no boxes.
- Light and dark variants, transparent backgrounds.
- Status colors only on arrows that carry a granted or blocked outcome, and amber on a request the hub holds for a person.
- A dashed line means a notification, such as `hal/value`, and in the landing story a reply. Every other line is solid, lifelines included.
- Diagrams show at their natural size. One wider than the reading column scrolls sideways in its own frame.
- The Mermaid blocks in docs/ARCHITECTURE.md and the spec stay the source on GitHub. The website shows the D2 redraw of each from docs/diagrams, matched through docs/diagrams/diagrams.json. If a block's text changes, the site falls back to Mermaid and a test fails until the redraw is updated.

## The Inspector

The dashboard is the OpenHAL Inspector, a protocol inspector.
- **Left pane.** Devices with their conformance level and verification.
- **Main pane.** The selected device's channels, limits and live values.
- **Bottom pane.** The live message log, every request, response, notification and error as formatted JSON-RPC, filterable.
- **Stop control.** Large and always visible in the header, in the blocked red with its word, never styled like other buttons.
- **Agent requests and human confirmations look different.** Agent entries carry the client's name and a dashed rule, which stays dashed whatever the outcome, red when blocked. Human decisions sit on a solid surface.
- **Commands say what a click does.** A command that needs a person's confirmation reads "Confirm and run X" or "Confirm and set X". A read-only device shows its limits without live controls. A device's own safe-state action is never a primary button, since STOP in the header covers every device.
- **Where STOP can't be sent** (an unpaired browser, a hub that is offline), a panel on the surface fill with no colored border takes STOP's place. Its title is in the blocked red, and it says why and what still keeps devices safe.
- **Buttons are controls, not status.** STOP keeps its solid blocked red fill. No other control has a red outline, so UNLOCK uses the standard secondary button with its word in the blocked red.
- **Kernel reasons outside the trace** read as prose, with identifiers and conditions set in mono.
- **Camera frames are device data.** An image channel shows its latest frame at its own size, labeled demo frame when it comes from a simulator, with its format, size and read time in small mono. A frame is never a link target and nothing on the page acts on what it shows. The message log and the audit log show an image result as its description, never its bytes.
- **A pending request shows the camera a person picks.** No Device File links a camera to the device it watches yet, so Confirmations shows a request's own camera when it has one and otherwise offers "Show a camera". The browser keeps that pick for the device.

## Motion

Nine patterns, nothing else.
1. The flowing connectors in the flow diagram.
2. A message appearing in the trace or log. A 120 ms fade, 4 px rise.
3. A status change. A 120 ms cross-fade.
4. The landing story. A stage pins under the header while the page scrolls normally, and the scroll position moves the story from step to step. The scene never pans or zooms. Each step's arrow draws along its lifelines with the scroll and earlier arrows settle into a quieter color, using transforms, opacity and stroke drawing only, and a caption finishes leaving before the next one arrives. Scrolling back plays it in reverse. Nothing moves on its own, so it is not scroll-jacking, parallax or fade-in on scroll. The bed target readout steps from 60 °C to 70 °C as a live reading, not a counter. The owner asked for this motion on 2026-10-25, and on 2026-10-26 for the whole diagram in view at one zoom level, which is its justification under Banned by default.
5. The nav highlight. The blue highlight behind the current top-level item slides to the item a person clicks, as one shape moving between positions, about 240 ms with an ease out. It never bounces or stretches.
6. The page transition. A page change moves the content sideways in the direction of travel through the nav, with the header and its highlight held still. Going to an item further right, the old content slides 24 px left and fades as the new content wipes in from the right with a clip-path, and going left mirrors it. About 260 ms in all. It is not a fade, a rise or a scale, so it stays distinct from the owner's other sites. Built on cross-document view transitions, so a browser without them changes pages instantly. The owner asked for patterns 5 and 6 on 2026-10-26.
7. The wordmark sequence. The first scroll drops the demo's opening and the hero's small diagram away and brings the hero's wordmark down into a pinned stage, shifted right so the slide never crosses the column's left edge, then each step fades every letter but the current one of H, A and L to a low opacity and slides the whole word left so the current letter lands in the same place, using transforms and opacity only. Nothing moves on its own, and scrolling back plays the sequence in reverse. The owner asked for this on 2026-10-27.
8. The sidebar's groups. A group grows open and shrinks closed as pattern 9 describes, and the group's caret turns a quarter turn in 200 ms on the site's ease. With reduced motion both happen at once.
9. Interactive parts. The search dialog, the header's menus and pickers, the phone menu, the sidebar's groups, popovers and other controls that open or change state animate with a popular, maintained animation library (Motion by default), in 150 to 250 ms with an ease out or a soft spring that never bounces past its end. Only transforms, opacity and the height of a disclosure move, and with reduced motion every part opens and closes at once. The owner asked for clean, smooth animations from a proven library on 2026-10-28. Motion's mini animate loads on a person's first pointer, focus or key event, never with the page. Each part opens in 200 ms and closes in 150 ms on the site's ease, cubic-bezier(0.2, 0, 0, 1), which never passes its end. A closing part stays drawn until the motion ends, whatever closes the part, and a part pressed again mid-way turns back from where the part is.

Smooth scrolling on the landing page. Wheel and trackpad scrolling eases on the home page so the story glides, the owner's request on 2026-10-26. It is on by default, a small "Smooth scrolling" switch near the story turns it off and remembers the choice per browser, and it is off under `prefers-reduced-motion`. It only eases the native scroll. The scrollbar, keyboard, anchor links, find in page and touch scrolling behave as usual, there is no snapping, and the speed is the person's own.

With `prefers-reduced-motion: reduce`, nothing moves.

## Copy voice

- Formal and exact, like a good specification.
- Plain declarative sentences of mixed length, joined with "because", "but", "so" or "when" where the ideas connect.
- Defined terms capitalized on first use and linked to the glossary (Hub, Device File, Safety Kernel, Driver, Grant, Conformance Level).
- No hype. Marketing pages use the same voice as the spec.
- "Open protocol" and "specification", never "standard".
- State plainly that OpenHAL is not affiliated with Anthropic or MHS.
- No em dashes or en dashes, and no colons or semicolons in running prose.
- No exclamation marks.
- Say "agent", not "AI". The agent pauses the print. Keep "AI" only where "agent" alone would be unclear, as in "AI agents" in the one-line description.
- Name the subject. Write "the agent", "the limits" or "the stop" instead of "it" or "them", unless the noun sits earlier in the same sentence. The owner asked for this on 2026-10-26.
- Never set up a contrast like "An agent can't loosen them. Only a person editing the device file can." Say what happens in one plain sentence, for example "A person sets the limits in the device file, and every command is checked against the limits."
- No vague wrap-ups like "That fixes it." Say what changed.
- The owner's writing rules for all site copy, 2026-10-27.
  - Write like technical documentation, not ad copy. No punchy fragments and no dramatic runs of short sentences.
  - Never write three or more short sentences in a row. Combine related ideas with "because", "but", "so" or "when".
  - State the cause before the effect. The reason something happens comes before the outcome or with the outcome, never as an afterthought.
  - Don't personify software. Write that the hub refuses the request, blocks the command or returns an error, never that OpenHAL "says no" or the kernel "steps in" or "asks".
  - Be precise with units and nouns. Write "a nozzle temperature of 300 °C", not "a 300 °C nozzle".
  - Read each sentence aloud. A sentence that sounds like a movie trailer becomes one plain sentence.

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
- Status shown by color alone. Always show its word.
- A dot, circle, shape or icon beside a status word, including the old circle with a bar for blocked and the half circle for confirmation.
- A status, error code or verdict inside a box with a colored border or a tinted background. Show it as plain text, in mono for codes.
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
- Modals for anything except confirmations, destructive actions and the site search dialog (⌘K or Ctrl K), which the owner asked for.

Dashboard
- Donut or pie charts for single values. Decorative gauges that can't be read precisely.
- Rainbow chart palettes. More than 5 series colors.
- Numbers without units. Values that jump or shift layout when they update.
- Spinners on content that is already loaded. Skeleton screens that don't match the real layout.
- Charts without axes or labeled scales.

Motion and interaction
- Scroll-jacking, parallax, scroll-triggered fade-in on every section. The landing page's smooth scrolling under Motion is the one exception, since it only eases the native scroll and can be turned off.
- Typewriter text effects, counting-up numbers.
- Custom cursors, cursor trails, magnetic buttons.
- More than the nine motion patterns above. Any animation that doesn't communicate a state change.

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
5. The message trace, the seven exchanges of the canonical scenario ending with the owner's approval, as a code block generated from the scenario (`uv run python -m openhal.demo.readme`).
6. "What OpenHAL does", three bullets.
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
3. **Memory.** What does a visitor remember ten minutes later? It should be the agent spotting the failed print on the camera, the request for a nozzle temperature of 300 °C refused with LIMIT_EXCEEDED, and the owner approving the cancel.
