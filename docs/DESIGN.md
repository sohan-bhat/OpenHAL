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

OpenHAL is an open protocol for AI agents to discover, read and control hardware safely. The reader is an engineer deciding whether to implement or adopt it. The site's job is to make the protocol legible: what a client sends, what the hub returns, and why the hub blocks a write. The Inspector's job is to show every device and every message, and stop anything in one click.

## Signature elements

Three elements carry the identity. The flow diagram heads the README, the message trace shows every exchange, and How it works on the home page shows the three outcomes of a request in one flow chart.

### The animated flow diagram

A clean flowchart of one command, left to right. Agent, then OpenHAL hub (with the Device files that feed the kernel), then Safety kernel, then Driver, then 3D printer (Klipper through Moonraker). A branch from the kernel goes down to a Blocked node, `LIMIT_EXCEEDED: nozzle 300 °C`. Connector labels in the mono face read `hal/write`, `check`, `grant` and `command`, and a thin return line reads `reading`.

- Rounded rectangles with 1.5 px strokes and 6 px corners, every node 112 by 88 on a grid, with every wire level. Orthogonal connectors with right-angle turns only, one arrowhead style, no crossings.
- The Safety kernel and Driver nodes each say what they do in a short line, and the blocked code sits under the Blocked node.
- One neutral for nodes, the secondary text color for the request's path, red only for the Blocked node and its connector. The pink stays off the diagram, so the blocked branch is the one colored path.
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

- **Direction column.** An arrow pointing right for client to hub, left for hub to client, and a dashed left arrow for notifications, in the text color. The Latin cut of IBM Plex Mono the site ships has no arrow glyphs, so the arrows are drawn as small inline SVGs in the house diagram style (1.5 px stroke, 6 px filled head), never typed characters. Plain text renditions in a font that has arrows, such as the README code block, use `→` and `←`. CLI output uses `->` and `<-`.
- **Method or outcome column.** The method name in the text color at weight 700. `error` plus the numeric code and the registry name in the blocked red. `result` in the granted green. Each is paired with its word, never color alone.
- **Payload.** JSON in the mono face with the house syntax theme. Reasons as plain mono text on their own line.
- Method names, codes and names match ADR 0015 and the generated schema exactly, everywhere.
- **A run as steps.** Where a page shows a recorded run, such as the README, the docs quickstart and the blog, each exchange gets a plain sentence that says what the agent did and how the hub handled the request, then the exchange's own trace block, as the owner asked on 2026-10-31. No comment lines sit inside the code. The sentence sits 12 px above its block and 32 px below the block before it, so a reader pairs each sentence with its own messages. Only `openhal demo` in a terminal prints the narration as `#` lines.

### The home page hero

The hero is centered in the column, which the owner's brief of 2026-10-29 allows, because the hero holds only the wordmark with its [hardware], [abstraction] and [layer] labels, the install box with its next step and two actions, Get started and Read the specification. The hero has no tagline and no sentence under the wordmark, which the owner removed on 2026-10-30, the home page's tab title is just OpenHAL, at the owner's request of 2026-11-02, and the tagline stays the home page's description. The hero shows no diagram, and the sections under the hero keep the column's left edge. The full-screen H, A and L sections are gone, and the docs' Concepts page explains the name under "What the name means". The hero draws the built wordmark, one path per letter, so the labels sit under the H, the A and the L, and the heading's own text names OpenHAL for screen readers and search.

The install box sits right under the wordmark and its labels and above the two actions. On 2026-11-02 the owner pointed out that OpenHAL offered only uv, which the owner's own terminal didn't have, and asked for the install commands "right underneath the title but above the two "get started" and "read the specification" buttons" because "another button press is one more surface of friction". So the one-line installers, /install.sh for macOS and Linux and /install.ps1 for Windows, put uv in place first and then install OpenHAL, and the box shows their commands. The box is shadcn/ui's Tabs on Radix in a React island over one command line. The tabs are macOS and Linux, Windows, uv and pipx, in that order, and a script before the island loads chooses Windows on a Windows machine and macOS and Linux everywhere else. The line shows the command in IBM Plex Mono after a `$` prompt, or `PS>` for PowerShell, in `--text-2`, with the site's own Copy button in its 1.5 px outline. The box is a 1 px `--border` outline on `--surface` with the tab row on `--bg`, and the chosen tab sits in the text color on the highlight, so the box carries no pink and no shadow. On a phone a long command wraps only between words and after a slash in an address, and each tab stays 32 px tall. One line under the box in `--text-2` names the next steps in order, `openhal init` and then `openhal start`. Until the first PyPI release the box offers only the macOS and Linux and Windows installers, because uv and pipx install from PyPI. `onPyPI` in website/src/config/install.json is the one value that adds the two tabs, and the release checklist in NEEDS_HUMAN.md turns the value on. The same file holds every install command once, for the hero, the install guide and the quickstart, and scripts/install_docs.py writes the commands into the docs. Without a script the box lists every command under its system's name and draws no tabs and no Copy button.

### How it works

On 2026-11-02 the owner asked for one simple flow chart in place of the scroll story, word for word, "for the how it works section, use a node graph or some tree or something or some very simple flow chart diagram literally this: "The agent sends a request to set the nozzle to 300 °C. Your limit is 260 °C, so the hub blocks the request." is trash ... "The agent sends a request to cancel the print. A cancel can't be undone, so the hub holds the request for your approval" why is every sentence like a slogan keep it simple", and later the same day "also just use a rebotic arm as an example and dont code it directly within the website use claude design to make the flow chart and it can just be static thats fine".

The chart is an illustration of OpenHAL's three outcomes on a robotic arm, not a copy of a device file. The agent sends a request and the OpenHAL hub checks the device file. A shoulder goal of 20° under a limit of 30° moves the arm, a goal of 45° is blocked, and a request to turn the motors on moves the arm once you approve. The outcome words are in the status colors, Arm moves in green, Blocked in red and You approve in blue. The chart was made in Claude Design on the canvas named "OpenHAL How it works" and ships as four static images in docs/assets, wide and narrow in light and dark, 2x PNG exports of 884 by 544 and 440 by 623 CSS pixels. The narrow chart sets its text larger, so the values stay about 14 px tall on a 360 px phone. A change to the chart means editing the canvas and exporting the four images again. The page shows the wide chart from 50rem and the narrow one below, follows the site's theme the way the header's wordmark does, and lazy loads the images. A visually hidden caption lists the three paths with the chart's labels word for word, so screen readers get the same content, and nothing in the section moves. A link under the section, "See a full example with a 3D printer", leads to the full example.

### The full example

/docs/examples/3d-print-watch/ tells the whole nine-step story of the print babysitter on one docs page: the sequence diagram with the owner's lifeline, the reply arrows, the webcam frame with its "Seen:" line and the printer panel, stepped through with Previous and Next, then printer.hal.yaml, every request and response from the record, and the audit log.

## Canonical demo scenario

The main example is a task that needs an agent. A timer or an IoT rule waters a plant on a schedule, but watching a print on a camera, judging what is going wrong and acting takes an agent, so the main example is the 3D print babysitter (examples/print-babysitter/). The owner chose the print babysitter on 2026-10-26.

Every example value in the README, website, Inspector screenshots, docs and social images comes from one file, `docs/demo/scenario.yaml`, written by `uv run openhal demo --record docs/demo/scenario.yaml` from a real run of the hub against simulated devices. There are two. `printer` is a Klipper 3D printer reached through Moonraker, with `state`, `extruder_temp`, `bed_temp` and `progress` readings, `extruder_target` limited to 260 °C and `bed_target` limited to 110 °C, both rate limited, and the actions `pause`, `resume` and `cancel`, where the hub holds a cancel for a person. `printer-cam` is the printer's webcam pointed at the bed, read as snapshots over HTTP the way crowsnest serves it on a Klipper printer (the `http` driver). The limits were confirmed by owner on 2026-10-24.

The story. Someone starts a long print and asks an agent to keep an eye on it.
1. The agent reads a camera frame, an image Reading (ADR 0015), and sees a corner of the first layer lifting.
2. The agent raises `bed_target` from 60 °C to 70 °C. The new target is inside the limit, so the write is done.
3. Because a hotter nozzle might help the corner stick, the agent requests a nozzle temperature of 300 °C, and the kernel blocks the request with `LIMIT_EXCEEDED` because the nozzle limit is 260 °C.
4. Later the camera shows the print has come loose. The agent pauses the print, which is done straight away.
5. The agent sends a request to cancel. Cancelling can't be undone, so `cancel` is `confirm-each-time`, and the hub queues the request and returns pending.
6. The owner approves the cancel within the hub's five minute window. The kernel checks every limit again and grants the cancel, the driver sends the cancel to the printer, and the printer's state reads cancelled. The printer's CANCEL_PRINT macro turns the heaters off, so the record then follows the nozzle as the nozzle cools for a minute. The hub's audit log then holds every request, the blocked request and the person's approval.

Tests check that the file still matches what the hub returns and that every surface matches the file. Demo values are labeled as demo data where shown.

The Arduino plant waterer (examples/plant-waterer/) stays as the Arduino example. It runs the end-to-end demo (`openhal demo --full`, docs/demo/e2e.yaml), the driver writer tutorial and the first hardware test, since it is the lowest hazard. The desk fan stays only as a secondary example in spec/examples/.

## Theme mapping

| Surface, feature or state | How the theme expresses it |
|---|---|
| Home page | The wordmark with its three labels, the install box, Get started and Read the specification, How it works as one flow chart, the safety model in three points, device families from the catalog, the demo command with a link to the Playground, and links to the spec and the docs. |
| Spec pages | The version, v0.1, in the URL and in the header's version picker, numbered sections, MUST, SHOULD and MAY, outline, anchors, previous and next, "Edit on GitHub" |
| Schema reference | Generated tables of every message, type and field, monospace names |
| Error codes | The registry table, the message trace with `error`, code and name in the blocked red as plain text |
| Granted write | `result` in the granted green |
| Confirmation required | The words "confirmation required" in blue |
| Stopped | The blocked red, the word "stopped", the STOP control turning into UNLOCK |
| Unverified driver or device | The word "unverified" in gray |
| Drivers and Device Library | Datasheet-style tables with conformance level, status and hazard default |
| Playground | A spec-style editor, CodeMirror 6 in the house syntax theme, and the message trace for each attempted command, labeled as an in-browser demo |
| Inspector | Device list, device pane and message log as JSON-RPC traces |
| Empty states | One sentence that says what is missing and the command or link that fills it |
| 404 | A message trace of the request and `error -32004 UNKNOWN_TARGET` |
| Loading | The layout at its final size with values shown as an em space until they arrive, no spinners on loaded content |
| CLI output and errors | Plain text with `->` and `<-`, error name and code first, then the reason |
| Social images | The message trace on the page's title, in the house style |
| Favicon | The mark at 16 px |

Anything that doesn't map gets plain, neutral treatment, never a second metaphor.

## Color

The palette comes from Radix Colors 3, defined in website/src/lib/palette.mjs and written into design/tokens.css, the D2 themes and the brand build by website/scripts/palette.mjs, and a unit test fails when a token drifts from its Radix step. The harmony is olive and gold with one striking accent, a hot pink, the pink of maker hardware and an oscilloscope's third trace. Olive is a gray with the faintest dark military green, so the dark page reads as near-black and shows its green only beside pure black, and the light page reads as off-white, as the owner asked on 2026-11-01. Gold is a calm khaki neutral for links, step counters and the highlight behind where a person is, so the pink stays rare, because the owner asked on 2026-11-01 for a neutral beside the pink that is not blue. The owner tried safety yellow on 2026-11-01 and asked the same day to go back to a pinker pink. Blue, green and red are status colors and carry meaning only. No gradients, no glow and no tinted boxes.

| Token | Light | Dark | Role |
|---|---|---|---|
| `--bg` | `#FCFDFC` | `#111210` | Page background, olive 1 |
| `--surface` | `#EFF1EF` | `#212220` | Code blocks, the trace, panels, rows under the pointer and disabled controls, olive 3 |
| `--highlight` | `#EAE6DB` | `#2D2B26` | Behind the current section, the current page and a selected row, gold 4 |
| `--border` | `#D7DAD7` | `#383A36` | Rules and outlines, olive 6 |
| `--text` | `#1D211C` | `#ECEEEC` | Body text, headings, method names and current rows, olive 12 |
| `--text-2` | `#60655F` | `#AFB5AD` | Secondary text, JSON keys, earlier request arrows and hover rings, olive 11 |
| `--neutral` | `#71624B` | `#CBB99F` | Links, always underlined, and the step counter in the example, gold 11 |
| `--accent` | `#C2298A` | `#FF8DCC` | The current location bar, focus rings, the request arrow being drawn, a primary button's edge and the marks in the webcam frame, pink 11 |
| `--accent-fill` | `#FF8DCC` | `#FF8DCC` | Fills, such as primary buttons, selected text and a switch that is on, dark pink 11 |
| `--accent-fill-hover` | `#DE51A8` | `#DE51A8` | A primary button under the pointer, dark pink 10 |
| `--scrollbar-thumb` | `#898E87` | `#687066` | The scrollbar's thumb, on a clear track, olive 9 |
| `--on-accent` | `#111210` | `#111210` | Text and marks on the pink fill, dark olive 1 |

| Status | Light | Dark | How it shows |
|---|---|---|---|
| ok, granted, done | `#3C754F` | `#72B88E` | the word in green, "granted", "ok", "done" or "connected" |
| confirmation required, pending | `#1D5FB4` | `#7DB2F0` | the words "confirmation required" or "pending" in blue |
| blocked, stopped | `#A14034` | `#D57A72` | the word in red, "blocked" or "stopped" |
| unverified | `#60655F` | `#AFB5AD` | the word "unverified" in gray, olive 11 |

Every pair passes WCAG AA for its text size on `--bg` and `--surface`. A status always shows as its word, so it never relies on color alone. No status has a dot, circle, shape or icon beside it, and a status, error code or verdict never sits in a box with a colored border or a tinted background. It is plain text, in mono for codes. The owner had the green and red dulled slightly on 2026-10-26. Neutral states (disabled, started, running, connecting, no confirmation) show their word in the text colors. Dashed rules mark an agent's entries, in the Inspector and in the Playground's log, and nothing else. Simulated devices, demo data, data blocks and empty states sit on a surface fill, and disabled controls are flat surface gray.

Blue means pending, green means done and red means blocked, and nothing else on the site, the docs or the Inspector uses the three. The owner moved pending off amber on 2026-11-01. The status colors keep the owner's tuned values of 2026-10-26 and 2026-11-01, because Radix's step 11 green, blue and tomato are brighter than the dulled green and red the owner asked for.

Every pair passes WCAG AA, measured with culori in website/tests/unit/palette.test.ts. Color blind distances are CIEDE2000 between culori's Machado 2009 simulations of protanopia, deuteranopia and tritanopia at full severity. The status colors stay at least 7.3 apart and the pink at least 5.6 from each, the closest pair being the pink and the blocked red under tritanopia in the light theme, where the status word, the dashed reply and the solid request still tell the two apart. The khaki and the done green stay 22.8 apart for most readers but come within 2.8 under deuteranopia in the light theme, and a link's underline and a status's word tell them apart.

The pink marks what is important or interactive and stays rare. Primary buttons, such as Get started on the home page, Send in the Playground and the Inspector's primary actions, fill with `--accent-fill` and set their word in `--on-accent` at weight 600, 8.9:1. The fill alone stands at 2.1:1 against the light page, so a primary button draws its 1.5 px outline in `--accent`, 5.2:1 against the light page and the same hue as the fill. Under the pointer the fill deepens to `--accent-fill-hover`, 5.2:1 with its word, and the button rises 1 px, with no glow, gradient or shadow, and with reduced motion the button stays in place. Links are underlined and set in `--neutral`, 5.8:1 in the light theme and 9.8:1 in the dark theme. A 2 px bar in `--accent` marks where a person is, on the header's rule under the current section, on the guide line beside the sidebar's current page and beside the phone menu's current section, while the current row keeps the text color on `--highlight`. Focus rings, the search field's rule while the field has focus, the request arrow being drawn and the marks on what the agent sees in the example's webcam frame use the accent too. Selected text sits on the fill in `--on-accent`. Nav rows, sidebar rows, buttons, picker rows and the search palette's rows are not links, so they stay in the text color, and a selected row sits on the highlight, never on a pink tint. The pink never fills an area larger than a button, never sets body text and is never a status color. Red stays for danger only, and a disabled button is flat surface gray rather than a faded pink.

The scrollbar matches the theme on every page, every panel and the Inspector. The thumb is `--scrollbar-thumb` on a clear track, 3:1 against the page in both themes, and darkens to `--text-2` under the pointer where the browser allows. The theme picker sets `color-scheme`, so a forced theme gets its own scrollbar. When the search palette, a select or any other overlay opens, the page keeps its scrollbar and stays where it is, and the overlay floats over the page, as the owner asked on 2026-11-01. The wheel over the backdrop leaves the page still. On a touch screen the browser's own overlay scrollbar shows, because the classic scrollbar fallback applies only with a fine pointer that hovers, and a 12 px classic bar had cut the right edge of every page on phones.

### Syntax theme

One theme built from the neutrals, used on the site, in README images, in the social images and in the Inspector. Keys `--text-2`, strings, numbers and booleans `--text`, punctuation `--text-2`, method names `--text` at weight 700, error names in the blocked red at weight 700, comments `--text-2` italic.

## Typography

Two faces from one family. On 2026-11-02 the owner asked for a more professional font than the previous pair, so every piece of text OpenHAL draws is now set in IBM Plex.

| Role | Face and weights | Why |
|---|---|---|
| Text, headings and the wordmark | IBM Plex Sans (OFL), variable, at 400, 500, 600 and 700 | IBM's corporate typeface, a grotesque that reads as professional and exact. The angled top of the t and the flat cut terminals give Plex Sans more character than Inter or a system stack |
| Code, messages, method names, values and labels | IBM Plex Mono (OFL), static, at 400, 600 and 700, with 400 italic for comments | The same family's monospace, so prose and protocol read as one voice. With a dotted zero, a tailed l and a serifed I, identifiers, units and codes stay unambiguous |

Scale, mobile then desktop. 13/13 legend, 15/15 secondary, 16/17 body with line height 1.65, 20/22 h3, 26/30 h2, 34/44 h1. Reading column at most 72 characters. Headings and labels are sentence case. Table headers, form labels and captions carry meaning and stay, set in sentence case at the legend size or larger. Decorative eyebrows, corner tags and micro labels are not used.

## Layout

- Third-party first, the owner's rule from 2026-10-28 and 2026-10-29, made absolute on 2026-11-01 with "there should be no component that is self written". Every control comes from a popular framework or library rather than hand-written code: Starlight for the docs frame, Tailwind CSS (through Starlight's official Tailwind integration) for styling new components, shadcn/ui components on Radix primitives in React islands for menus, dialogs, the search palette and the sidebar, cmdk for the search palette over the site's Pagefind index, Motion (Framer Motion) for animation, and CodeMirror 6 through @uiw/react-codemirror for the Playground's device file editor. Each library is themed with design/tokens.css, so the protocol theme stays. Tailwind's utilities come only from the component folders, its default palette, shadows and blurs are cleared, and its theme maps shadcn/ui's names onto design/tokens.css. Icons come from lucide-react only where a control has no word: the search field's magnifier, the chevron of a picker or a sidebar group, the panel of the sidebar's button and the arrow keys in the palette's hints.
- The Playground is one React island built from the same parts as the rest of the site. Send, Dry run, Approve, Reject, Unlock, Set, Stop and the story's requests are shadcn/ui Buttons. Start from, As, Device and Channel or action are non-modal DropdownMenu pickers like the header's, and each button reads its label and its choice, such as "Device printer". The Value and reading fields are Input, the device's channels sit in Tables, and Build your own request is a Collapsible that opens in 200 ms and closes in 150 ms with Motion. Send fills with the accent, Approve and Unlock fill with the text color because they carry a person's token, and Stop fills with the blocked red. The device file editor loads when a person opens the builder or points at its button, and shows YAML in the house syntax theme with wrapped lines and no line numbers. The editor's selection sits on the fill in `--on-accent` while the editor has focus and on `--border` after focus moves on. Tab leaves the editor, so a keyboard user never gets trapped. The message log keeps the site's own trace renderer, because no library draws the trace's arrows and columns.
- Documentation-first, on Astro Starlight. On 2026-10-28 the owner asked for the documentation frame to come from a proven third-party base instead of hand-built parts. The header, outline and previous and next links are Starlight's components themed with design/tokens.css, the sidebar, the search palette and the menus are shadcn/ui components in React islands that load when a person reaches for them, and anything Starlight lacks is an override of one of its components, never a second frame. A left sidebar, a 772 px reading column and an "On this page" outline on the right from 1152 px. When one of Starlight's components is too slow for a page, the fix is a small patch to that component in website/patches, kept until Starlight ships the same fix, never a hand-built copy. The outline carries one, which finds the elements the outline observes without testing every element of the page.
- Long pages. A page with more than 20 tables, today only the schema reference, renders each table after the first as the table nears the screen and holds about the table's height until then, so the page opens as fast as a short one. A page with fewer than two sections has no "On this page" outline, and its column takes the space. The outline's column takes no part in scroll anchoring, so a jump lands under the header where the jump would land with every table drawn, and print, find in page, screen readers and search see every table.
- One header on every page, the home page included, as the owner asked on 2026-10-27. The header spans the window. At its far left is the sidebar's button, then the wordmark, then Overview, Docs, Specification, Playground, Drivers and Device Library with the current section in the text color on the highlight and a 2 px bar in the accent on the header's rule, then the search field with its shortcut, and at the window's right edge GitHub, a 1 px rule, the specification version and the theme picker. On a page without a sidebar the button's place stays empty, so the wordmark never moves between pages. From 800 to 1023 px the sections become one Section picker, and from 1024 to 1139 px the search shows as its icon. Under 800 px the header holds the wordmark, the search icon and the menu button, both 44 px with the icon in the middle of its box. The menu lists the six sections, the current one with the accent bar on the highlight, and the theme picker, and GitHub and the specification version sit in the page footer. The header is 61 px tall over a 1 px `--border` rule, with no shadow.
- One left edge. The frame starts at the window's left edge at every width, with no centered maximum width, so no empty band sits left of the sidebar or the wordmark, as the owner asked on 2026-10-31. Every left edge falls on one 8 px grid from the window's edge. The header's button and the sidebar's rows start at 16 px, the group labels, the button's icon and the first guide line at 24 px, each nested group 16 px further in with its guide line under its parent's label, and the wordmark at 56 px. The reading column starts 24 px right of the 300 px sidebar, 324 px from the left at every width, with the outline right after the column. The text then sits beside its navigation and the title's rule runs unbroken from the sidebar to the outline, while a column centered in the space left an empty band between the sidebar and the text at 1728 and 2560 px. The extra space of a wide window falls right of the outline. While the sidebar is hidden the column starts under the wordmark, 56 px from the left. The blog and the 404 page, which have no sidebar, keep the column at 324 px. The home page's column keeps its 1328 px of content and lines up with the wordmark up to 1440 px, and centers in wider windows.
- The sidebar. Each section has its own sidebar, the docs in their groups, the specification's numbered sections under "Specification v0.1", the drivers by status, the device library and the SDKs. The sidebar is shadcn/ui's Sidebar on Radix in a React island, built from Starlight's route data, so every page keeps its items, order, numbers, badges and current page. Rows show words only, and each group collapses on shadcn/ui's Collapsible with a chevron. The group that holds the current page is open, and the open groups and the scroll position carry over between pages. The current page shows in the text color at weight 700 on the highlight, with a 2 px bar in the accent on the guide line beside it, and a row turns the surface gray under the pointer. The sidebar hides off canvas and shows again from its button at the far left of the header, from its rail and from Tab, at the owner's requests of 2026-10-31. The button is shadcn/ui's SidebarTrigger, a 32 px ghost button with the PanelLeft icon, named "Toggle sidebar", with aria-expanded and aria-controls, and shadcn/ui's Tooltip on the button reads "Hide sidebar" or "Show sidebar" with the Tab key. The button stays in the same place while the sidebar is shown or hidden. Tab hides or shows the sidebar only when focus rests on the page, no modifier key is held, no text field, dialog, menu, popover or search palette is open, and the person's last input before Tab was a pointer press or a Tab that hid or showed the sidebar. A person who clicks the page can press Tab again and again to hide and show the sidebar, any other key hands Tab back to moving focus, and a person on the keyboard alone moves focus with Tab as before, the first Tab reaching the skip link. Shift and Tab never toggles the sidebar. No keyboard shortcut is announced for the sidebar, because a screen reader user expects Tab to move focus, and the button is the keyboard's way to the sidebar. The rail is the thin hit area on the sidebar's edge, which shows a line in the controls' outline color over the sidebar's border and a resize cursor on hover and stays at the window's left edge while the sidebar is hidden. The content and the outline move over to use the space, the sidebar never covers the content at any width, and nothing peeks or floats over the text. The hidden sidebar leaves the tab order, the browser keeps the choice, and the head script and a small script after the sidebar apply the choice, the open groups and the scroll position before the first paint. The links work without JavaScript, React loads when a person points at, focuses or presses the button, a group or the rail or presses Tab, the first press is replayed, and a press on the button hides and shows the server-rendered sidebar before the sidebar's own island loads. Under 800 px a button with the section's name and a chevron sits beside On this page, or alone under the header on a page without an outline, because the owner found the phone menu crammed on 2026-11-01. The button opens the section's pages in shadcn/ui's Sheet on Radix Dialog from the left, with the sidebar's rows, the current page marked and in view, and every group collapsible. The sheet opens in 200 ms and closes in 150 ms through tw-animate-css, and at once with reduced motion. Without JavaScript the button is hidden and the phone menu lists the section's pages under the sections.
- The specification version. While spec/versions.json lists one version, the header shows the version as a plain label, v0.1, after GitHub, linking to the specification's Versions section. Once the file lists two versions the label becomes a menu of every version on its own. On a spec page each version opens the same section in that version, or that version's start when the section is missing, and on every other page the menu shows the latest version. Under 800 px the label sits in the page footer. The dated addresses and /spec/latest/ move to the matching v0.1 page and keep the anchor.
- The theme picker. A menu button after the version picker with Auto, Light and Dark, kept per browser in Starlight's own setting, where Auto follows the system.
- Every picker is shadcn/ui's DropdownMenu on Radix, kept non-modal like a popover, so a click outside closes the list and a click on another picker opens that one at once. A picker's island loads when a person points at the picker, focuses the picker or presses the picker, and a press that arrives while the island loads is replayed. Enter, Space and the Down arrow open a picker on its first choice, the arrow keys move through the list in a loop, Home, End and a letter jump, Escape closes the list with focus back on the button, and Tab closes the list and moves on. The list opens 4 px under its button, or above the button where the screen has no room, on the page background in a 1 px `--border` box with rows rounded inside its padding, the current choice in bold on the highlight and no shadow. Radix places the list.
- Controls come from shadcn/ui on Radix, never from hand-written markup, as the owner asked on 2026-11-01. A button, or a link styled as one through buttonVariants, is Button. Fields are Input with Label, a choice from a list is Select, an on and off setting is Switch, a choice between a few views is Tabs, datasheet tables are Table and a status word is Badge, each themed with design/tokens.css. A field, a select's button and an outlined button draw the 1.5 px outline in the control color, which turns to `--text-2` under the pointer and while a select is open. Focus draws the 2 px ring in `--accent`, and a disabled control is flat surface gray.
- A Select's list matches the pickers' lists. The list opens 4 px under its button, or above the button where the screen has no room, at least as wide as the button, on the page background in a 1 px `--border` box with rows rounded inside its padding and no shadow. The chosen row is bold on the highlight with the component's check mark, and the chevron turns over while the list is open. Enter, Space and the arrow keys open the list on the chosen row, the arrow keys, Home, End and a letter move through the list, Enter chooses and Escape closes the list with focus back on the button. While the list is open the rest of the page is inert, so no focusable element sits under Radix's aria-hidden.
- A Badge is the status word alone, bold in its status color, never a box, a tint or a shape.
- Datasheet tables are shadcn/ui's Table. Headers are bold `--text-2` at the legend size over a 1 px rule in `--text-2`, rows sit on 1 px `--border` rules, a caption sits on top and a selected row sits on the surface. Markdown tables in the docs and the spec keep the same look through the site's rehype step.
- The catalog filters. The Drivers page and the Device Library filter their tables with a search field and, on the Drivers page, a Select for each column with more than one value, Any first. The count line reads "34 drivers." or "3 of 34 drivers." in a live region, and the choices sit in the address so a filtered view can be shared. The filters load at once when the address carries a filter and otherwise on a person's first point, focus or keystroke, with the first press replayed. Without a script the full table shows and the filters stay hidden.
- The search. The header's search field and Command or Control and K open a command palette, shadcn/ui's Command and Dialog on cmdk and Radix over the site's Pagefind index. Results are grouped under the header's sections, each page followed by up to two of its sections that matched, and a match shows in extra bold in the text color, and the selected row sits on the highlight. The arrow keys move through the results in a loop, Enter opens one, Escape closes the palette with focus back on the field, and Tab stays on the field because the results are reached with the arrow keys. Before typing the palette lists recent searches, with a way to clear them, and five pages to start with. A search with no match says so and suggests a method or an error code, and a live region counts the pages found. On a phone the palette fills the screen with a Cancel button. Excerpts never show code, YAML, a message trace or the text inside a form field.
- Asides. A note, tip, caution or danger aside sits in a 1 px `--border` box on the page background with its title in `--text`, no icon and no tint.
- Breakpoints 800, 1024, 1140 and 1152. Under 800 px the sections are the menu and a section's pages open in a sheet, from 800 to 1023 px the sections are one picker, from 1024 to 1139 px the search is its icon, and under 1152 px the outline is an "On this page" disclosure under the header. Pages are checked at 390, 768, 1024, 1280 and 1440 px.
- Spacing scale 4, 8, 12, 16, 24, 32, 48, 64.
- Borders are 1 px `--border`, radius at most 6 px, no shadows. Controls with an outline, such as the search field and its shortcut key, inputs, selects and outlined buttons, draw the outline 1.5 px wide, the owner's request on 2026-10-28. Browsers round a border's width down to whole pixels, so the outline is a 1 px border with an inset 0.5 px ring in the same color, a solid line and not a shadow, set by one token. Rules, dividers, table borders, panels and the pickers' lists stay 1 px.
- Pickers and menus show words only, with a chevron where they open, and never an icon beside the word.
- Every spec page has anchor links on headings, copy buttons on code, previous and next links, "Edit on GitHub", and the spec version in the URL.

## Information marks

Pages show the one thing a person needs and keep the depth one tap away. A term or control that needs explaining gets a small information mark, a lowercase i in a 16 px circle in `--text-2`, right after it. Tapping or clicking it, or pressing Enter on it, opens a short popover of one to three sentences with an optional "Read more" link into the docs, and Escape or a click outside closes it. It is a real button with an accessible name ("About hazard"), never hover-only, and the popover keeps AA contrast in both themes. Use it instead of a paragraph above the control. At most one per row, and never on every label. The popover is shadcn/ui's Popover on Radix, a non-modal dialog named for its mark, so focus moves into the note and returns to the mark when the note closes.

## Wordmark

- **Wordmark, no logo.** The brand is the name, OpenHAL, set in IBM Plex Sans at weight 700, the heaviest Plex Sans has, with tracking at -0.04 em, in `--text`. At that tracking the closest pair, p and e, keeps a gap of about 0.04 em, which stays visible in the 24 px header. Every letter is the font's own. The arrow crossbar the H had on 2026-11-01 was removed on 2026-11-02 at the owner's request, and IBM Plex Sans became the wordmark's face the same day, also at the owner's request. Where a square is needed (favicon, app icons) the initials OH are set the same way with tracking at -0.08 em, sized so their outlines span 94 percent of the square's width. tools/readme/build.py draws every letter from the font's own outlines, one path per letter, into docs/assets/wordmark-{light,dark}.svg, mark-{light,dark}.svg and favicon.svg, which the README, the website's header and hero, the Inspector's header, the icons and the social images use. Icon links carry a version that rises when the mark changes.
- **HAL spelled out, on the landing hero only.** Under the letters H, A and L of the large hero wordmark sit three labels, written exactly `[hardware]`, `[abstraction]` and `[layer]` with their square brackets, for Open Hardware Abstraction Layer, in `--text-2` above WCAG AA, up to 17 px and never under 12 px, in one row. From 768 px each label is centered under its letter, and on a phone the labels move apart just enough to keep 8 px between them while each stays under its own letter. They are hidden from screen readers, which read OpenHAL, and the long name Open Hardware Abstraction Layer is in the page's metadata. The header wordmark, icons and the README stay plain.
- Original. It never imitates MCP's, Anthropic's or any other logo.

## Diagrams

One house style for sequence and architecture diagrams.
- 1.5 px lines in `--text-2`.
- Filled triangular arrowheads, 6 px.
- Labels and messages in the mono face.
- Participants as plain bordered boxes with sentence-case names. The 3D print example's story is the exception, with its lifelines named in plain text and no boxes.
- Light and dark variants, transparent backgrounds.
- Status colors only on arrows that carry a granted or blocked outcome, and blue on a request the hub holds for a person.
- A dashed line means a notification, such as `hal/value`, and in the example's story a reply. Every other line is solid, lifelines included.
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
- **Where STOP can't be sent** (an unpaired browser, a hub that is offline), a panel on the surface fill with no colored border takes STOP's place. Its title is in the blocked red, and its text gives the reason and what still keeps devices safe.
- **Buttons are controls, not status.** STOP keeps its solid blocked red fill. No other control has a red outline, so UNLOCK uses the standard secondary button with its word in the blocked red.
- **Kernel reasons outside the trace** read as prose, with identifiers and conditions set in mono.
- **Camera frames are device data.** An image channel shows its latest frame at its own size, labeled demo frame when it comes from a simulator, with its format, size and read time in small mono. A frame is never a link target and nothing on the page acts on what it shows. The message log and the audit log show an image result as its description, never its bytes.
- **A pending request shows the camera a person picks.** No Device File links a camera to the device the camera points at yet, so Confirmations shows a request's own camera when it has one and otherwise offers "Show a camera". The browser keeps that pick for the device.
- **Library controls.** Every control comes from shadcn-svelte on bits-ui, the Svelte version of the site's shadcn/ui on Radix, as the owner asked on 2026-11-01. Buttons are Button, text fields Input and Textarea, pickers Select, checkboxes Checkbox, a true, false or enum choice RadioGroup, value sliders Slider, the UNLOCK dialog Dialog, the revoke confirmation AlertDialog, the hash check's note Tooltip, the views and lists NavigationMenu, data tables Table and the driver writer's raw data Collapsible. Tailwind 4 runs through its Vite plugin without Preflight, with its default palette, shadows and blurs cleared, and its theme maps shadcn-svelte's names onto design/tokens.css. Icons from @lucide/svelte appear only where a control has no word, such as a select's chevron and a checkbox's check.
- **The Inspector draws its own content.** The message trace and its arrows, the JSON view, the status words, the limit scale around the Slider, the camera frame's caption and the driver writer's diff and steps stay hand-drawn, because no library draws a JSON-RPC trace or a limit with bands past the limit.
- **Controls match the site.** Controls are flat with no shadow and a 1.5 px outline in the control border color. Focus shows a 2 px `--accent` ring set 2 px out. Primary actions sit on `--accent-fill` with `--on-accent` text at weight 600, a disabled control is flat surface gray, and the current choice and a selected row sit on `--surface`.
- **STOP is the library Button with its own variant.** STOP keeps its solid blocked red fill, its inset ring in the page color and its 3 px focus ring in the text color, and STOP is the third Tab stop on every view. UNLOCK opens a Dialog that starts in the Phrase field and keeps focus inside. A click outside the Dialog does nothing, Escape or Keep stopped closes the Dialog with focus back on UNLOCK, and Unlock stays disabled until the typed phrase matches. Approve and Reject stay buttons on the decision panel, with no dialog between the click and the request.
- **Overlays float over the page.** A dialog, confirmation, select or tooltip opens over the page while the page keeps its scrollbar and stays in place, as the owner asked on 2026-11-01. Behind a dialog the wheel, a touch and the scroll keys leave the page where it was. An overlay opens in 200 ms and closes in 150 ms on the site's ease, and at once with reduced motion.
- **The revoke confirmation opens on Keep.** Focus starts on Keep, the safe choice, in the revoke AlertDialog.
- **Review limits.** A read-only device with a Device File shows Review limits, a primary button under its "limits not confirmed" note, to a person's session only. Review limits opens the Writer view with the steps Limits interview and Confirmed. Each question is one sentence that names the channel and its unit, with the suggestion beside the field, a Use suggested button and the reason under the question. An answer past the range the device reports stays in its field, marked invalid, with the reason under the field. The Phrase field comes last, and Confirm the limits stays off until every question has an answer and the phrase reads confirm. The confirmed state names the file and reads "DEVICE is now writable."
- **Limits.** A writable device shows a Limits section after its controls to a person's session, with one bordered form per number channel named "Limits of CHANNEL" and fields for Min, Max and Max change in the channel's unit. Review the change lists each change as "max 60 W to 40 W" with no bullets. A narrower limit saves at once. A wider limit adds a Phrase field, and Save the limits stays off until the phrase reads confirm.
- **Limit changes in Confirmations.** A pending limit change sits in its own Limit changes list after Pending, with the agent's dashed rule, the change lines and the reason the hub holds the request. Approve the change stays off until the person types approve, the one approval in Confirmations that takes a phrase, because a wider limit rewrites the Device File for every later command.

## Motion

Seven patterns, nothing else.
1. The flowing connectors in the flow diagram.
2. A message appearing in the trace or log. A 120 ms fade, 4 px rise.
3. A status change. A 120 ms cross-fade.
4. The nav highlight. The highlight behind the current top-level item and the accent bar under the item slide together from the item a person left to the item the person chose, in 240 ms on the site's ease, using transforms only, and neither bounces or stretches. Both stay inside the header under the labels, so every label stays readable through the move, as the owner asked on 2026-11-01. A script right after the sections places them over the item the person left before the new page first paints, and Motion, loaded only for the slide, moves them. With reduced motion they rest on the current item at once.
5. The page transition. A page change moves the content sideways in the direction of travel through the nav, with the header held still as one image and the old header's image hidden. Going to an item further right, the old content slides 24 px left and fades as the new content wipes in from the right with a clip-path, and going left mirrors it. About 260 ms in all. It is not a fade, a rise or a scale, so it stays distinct from the owner's other sites. Built on cross-document view transitions, so a browser without them changes pages instantly. The owner asked for patterns 4 and 5 on 2026-10-26.
6. The sidebar's groups. A group grows open and shrinks closed as pattern 7 describes, and the group's chevron turns a quarter turn in 200 ms on the site's ease. With reduced motion both happen at once.
7. Interactive parts. The search dialog, the header's menus and pickers, the phone menu, the sidebar and its groups, popovers and other controls that open or change state animate with a popular, maintained animation library (Motion by default) or with the component's own CSS transition, in 150 to 250 ms with an ease out or a soft spring that never bounces past its end. Only transforms, opacity and the height of a disclosure move, and with reduced motion every part opens and closes at once. The owner asked for clean, smooth animations from a proven library on 2026-10-28. The React islands carry Motion's React API and load only when a person reaches for one. Motion's mini animate, which moves Starlight's own parts, the sidebar's groups and the content beside the sidebar, loads on a person's first pointer, focus or key event, never with the page and never with reduced motion. The sidebar slides off canvas with shadcn/ui's own transition on the site's ease, 150 ms out and 200 ms back, while the content and the outline move over in the same time with Motion using transforms only, and the sidebar moves only for a person's toggle, never while a page restores the stored state. Each part opens in 200 ms and closes in 150 ms on the site's ease, cubic-bezier(0.2, 0, 0, 1), which never passes its end. A closing part stays drawn until the motion ends, whatever closes the part, and a part pressed again mid-way turns back from where the part is. A Select's list grows in 200 ms and shrinks in 150 ms on the site's ease through tw-animate-css, the animation library shadcn/ui is written for, and opens and closes at once with reduced motion.

The pinned How it works stage and the home page's smooth scrolling with its switch left the site on 2026-11-02, when How it works became a static chart, because both served only the scroll story.

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
- A message that starts or restarts the hub says "Start OpenHAL with openhal start". `openhald` stays a silent alias that no message names, because the owner read "openhald" as a typo on 2026-11-01.
- A limits interview question is one sentence that names the channel and its unit and says what the limit does, such as "brightness, in percent. The most an agent may set. Suggested 100 %." A blocked answer gives the reason and the range to type, such as "120 % is above 100 %, the most the device reports. Answer a value from 0 % to 100 %."
- The owner's writing rules for all site copy, 2026-10-27.
  - Write like technical documentation, not ad copy. No punchy fragments and no dramatic runs of short sentences.
  - Never write three or more short sentences in a row. Combine related ideas with "because", "but", "so" or "when".
  - State the cause before the effect. The reason something happens comes before the outcome or with the outcome, never as an afterthought.
  - Never personify an object. The hub, the kernel, a printer, a device, a driver, a board, a server, a client, an SDK, the Inspector and OpenHAL itself take mechanical verbs, so the hub passes, blocks, holds, returns, records or forwards a request, and a driver connects to a printer over serial. None of them refuses, rejects, asks, tries, waits, wants, decides, sees, watches, knows, says, tells, answers, lets, talks or speaks. The AI agent is the one actor that may decide or watch, and a protocol call the agent makes is a request the agent sends.
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
- Scroll-jacking, parallax, scroll-triggered fade-in on every section.
- Typewriter text effects, counting-up numbers.
- Custom cursors, cursor trails, magnetic buttons.
- More than the seven motion patterns above. Any animation that doesn't communicate a state change.

Copy
- Banned words: unlock (except the literal control after a stop), seamless, supercharge, elevate, effortless, empower, revolutionary, next-generation, cutting-edge, game-changer, magic, harness, unleash, journey, "Welcome to", "the future of".
- "X for Y" taglines ("Stripe for hardware"), "Say goodbye to...", "Meet X", rhetorical questions as headlines.
- "It's not X, it's Y" constructions.
- Exclamation marks.
- Em dashes.
- Vague claims without specifics ("works with everything", "blazing fast", "enterprise-grade").

## README and diagrams

The repository README follows this structure, in this order, left-aligned.

1. The wordmark (SVG, light and dark) and one sentence. "An open-source protocol for AI agents to control hardware." No second sentence and no subtitle. The same sentence is the home page's description and social title, the default OG description, the pyproject description and the GitHub repository description.
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
3. **Memory.** What does a visitor remember ten minutes later? It should be the agent spotting the failed print on the camera, the request for a nozzle temperature of 300 °C blocked with LIMIT_EXCEEDED, and the owner approving the cancel.
