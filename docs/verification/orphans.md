# Orphan audit

Every visual element on the website and in the Inspector, and the part of the system it comes from. Rule 4 of docs/DESIGN.md says an element that comes from nowhere is removed. Rule 5 says chrome that is drawn works. Audited on 2026-10-25 by the quality workstream.

Sources are named by where they live.

- **Tokens.** design/tokens.css (colors, status colors, spacing, radius, type scale, the Atkinson faces).
- **Mapping.** The theme mapping table in docs/DESIGN.md.
- **Signature.** The two signature elements in docs/DESIGN.md, the flow diagram and the message trace.
- **Scenario.** docs/demo/scenario.yaml.
- **Catalog.** drivers/catalog.json.
- **Library.** The device files in library/.
- **Schema.** spec/2026-10-24/schema.json and the error registry in ADR 0015.
- **Hub.** A field the hub's REST or JSON-RPC answer carries.

## Removed

| Element | Where | Why |
|---|---|---|
| `PartLabel` component with "lamp" status chips and an `--ink` border | website/src/components | Left from the instrument panel theme. Nothing drew it, `--ink` is not a token, and it imported a function that no longer exists |
| `trace-block.ts` | website/src/lib | A trace parser nothing called |
| `.syn-method` and `.syn-error` rules | website/src/styles/code.css | No highlighter emits these classes. Method and error colors in traces come from trace.css |
| The Status filter on Drivers | /drivers/ | It had one value, so choosing it changed nothing. A filter is now drawn only when it has two or more values |
| `.panel` rule | dashboard/src/app.css | No view used it |
| "Channels it can change" | Library device pages | Renamed "Control channels", the term the Inspector and DECISIONS.md use |

## Fixed because a drawn control did nothing

| Control | Where | What was wrong |
|---|---|---|
| Pair | Inspector pairing page | Svelte read the `{6}` in `pattern="[0-9]{6}"` as an expression, so the browser demanded a digit followed by "6" and refused every real code. Pairing a browser from the page could not work |
| Start from | Playground | A pick made before the playground hydrated was reset, so choosing another example did nothing |
| Wide tables | Spec, docs and driver pages | A table that scrolled sideways could not be reached from the keyboard. It is now a named, focusable region while it overflows |
| Use suggested | Driver writer interview | Its accessible name did not contain its visible text, so voice control could not press it |

## Website

### Every page

| Element | Source |
|---|---|
| Skip to content link | Accessibility rules in DESIGN.md |
| Mark and wordmark | Logo section of DESIGN.md, docs/assets |
| Main navigation, with the current section in the accent tint | Website brief structure, `--accent` |
| Phone menu | Layout, the sidebar becomes a menu at 390 px |
| Footer sentence, the MHS line and Source on GitHub | Copy voice, OpenHAL is not affiliated with Anthropic or MHS |
| 1 px rules, 6 px radius, no shadows | Tokens and Layout |
| Focus outline | Accessibility rules |
| Open Graph image | Mapping, social images |

### Overview

| Element | Source |
|---|---|
| One sentence as the h1 | README and DESIGN.md, the one sentence |
| Flow diagram with the Blocked branch | Signature, docs/diagrams/flow-*.svg |
| Seven part buttons and the note under them | Website brief, a focused node explains itself |
| Message trace, its legend and "Recorded with openhal demo" | Signature and Scenario, labeled as recorded demo data |
| Quickstart block with Shell, Tested and Copy | Mapping, three commands, tested snippet |
| Outcome sentence | Scenario |
| Device families, counts and status marks | Catalog |
| MHS, two sentences | Mapping |
| Numbered specification links | Mapping and the numbered spec sections |

### Specification pages

| Element | Source |
|---|---|
| "Specification 2026-10-24" legend and the version switcher | Mapping, dated version and a switcher, spec/versions.json |
| Numbered sidebar | Spec sections |
| On this page outline | Layout |
| Heading anchors | Layout |
| MUST, SHOULD and MAY in small caps | Mapping |
| Trace blocks with drawn arrows | Signature |
| Tables and code blocks with Copy | Layout and the syntax theme |
| Previous and Next, Edit on GitHub and the source path | Layout |
| Schema reference tables | Mapping, generated from Schema |
| Error registry table | Mapping, Schema |

### Playground

| Element | Source |
|---|---|
| "in-browser demo" mark and the TypeScript kernel note | Mapping, labeled as an in-browser demo |
| Device file editor, Start from and the validity line | Mapping, a spec-style editor |
| Device facts, read channels and Simulate a reading | The edited device file |
| Send a request, As, Device, Channel or action, Value, Send, Dry run | Schema methods `hal/write`, `hal/action`, `hal/dryRun` |
| Confirmation required list with Approve and Reject on a solid surface | Mapping, human decisions look different |
| Stop, then stopped with the Unlock field | Mapping, stopped |
| Message log of traces, newest first | Signature |

### Drivers and a driver page

| Element | Source |
|---|---|
| Search, Tier, Conformance and Hazard filters, the match count and the empty line | Catalog |
| Tested on simulator and Verified on hardware marks | Catalog statuses, unverified shape |
| Datasheet table grouped by status | Mapping, datasheet tables |
| Driver facts, estimated reach and the driver's own doc | Catalog and docs/drivers |
| Coverage plan | docs/drivers/COVERAGE.md |

### Device Library and a device page

| Element | Source |
|---|---|
| Search, match count and empty line | Library |
| Verification mark per file | Library provenance |
| Facts table with Limits | Library, confirmed only when a person confirmed |
| Suggested entries and How a person confirms them | Library `suggested: true`, docs/guide/library.md |
| Control channels, Actions and Read channels tables | Library |
| The file itself with Copy | Library |

### SDKs, Inspector docs, docs, blog and 404

| Element | Source |
|---|---|
| SDK table with reference and planned marks | openhal/client, TypeScript planned |
| Python reference | Generated from openhal/client docstrings |
| Inspector views table and three screenshots | The Inspector on the mock hub, recaptured on 2026-10-25 |
| Docs sidebar groups and pages | docs/guide and the reference docs in routes.mjs |
| Blog list or "No posts are published yet." | src/content/blog, drafts hidden |
| 404 trace with `error -32004 UNKNOWN_TARGET` | Mapping, 404 |

## Inspector

### Every view

| Element | Source |
|---|---|
| Mark, OpenHAL and Inspector | Logo |
| Hub, Connection, Protocol and Conformance | Hub `/v1/status` and the live socket |
| STOP, large and red with its word, UNLOCK after a stop | The Inspector section of DESIGN.md, Stopped |
| Stopped band with `error -32014 STOPPED` and the reason | Mapping, stopped, Schema |
| View navigation with the pending count | Inspector views, Hub confirmations |
| Message log in the header | Bottom pane, moves focus to the log |
| Device list with name, id, simulated, connection, verification, driver, conformance, hazard and read-only | Left pane, Hub |
| Demo data line | Scenario rule, demo values are labeled |
| Message log with live mark, count, filters, Show hal/value, Copy as text, Hide the log | Bottom pane, Signature |
| Log rows with time, client, drawn arrow, method or outcome, payload and reason | Signature, Schema |
| Dashed rule for agent rows, solid for people | The Inspector section, agent and human entries differ |
| Show the whole message, Show older messages, Clear filters | Long payloads, the 400 row page, empty filter result |

### Devices

| Element | Source |
|---|---|
| Title, id and simulated | Hub device view |
| State, verification, driver, conformance, hazard, mode, device file and source | Hub device view |
| Limits not confirmed notice with `error -32015 UNVERIFIED_LIMITS` | Mapping, unverified, Schema |
| Read channels table with fixed width values | Main pane, Dashboard rules on layout that does not move |
| Control channels with the limit scale, number field and Set | Device file limits |
| Actions with argument scales, run limit, requirements and Run | Device file actions |
| Limit scale with min, a middle value and max, and dashed zones past the limits | Device file limits, a labeled scale |
| Result line granted, confirmation required or blocked | Mapping status shapes |
| Safety and Notes | Device file safe state, watchdog and notes |

### Confirmations, audit, routines, writer, settings, pairing, offline

| Element | Source |
|---|---|
| Pending requests with requester, trace, dry run and expiry | Hub confirmations |
| Your decision on a solid surface with Approve, Reject and a reason | The Inspector section, human decisions |
| Decided recently | Hub confirmations |
| Audit filters, Verify the hash chain and entries with hashes and status | Hub audit log |
| Routine list, facts, Dry run, Enable, Disable, Run now, source and run history | Hub routines |
| Unknown devices, Look for devices, Start the driver writer | Hub discovery and the writer |
| Session steps, raw data, draft, limits interview, Use suggested, Confirm these limits | Writer session |
| File preview with its diff, staged test plan and Save | Writer session |
| Client tokens, Show revoked, Revoke and Keep, Create a token, Copy the token | Hub tokens |
| New pairing code and LAN access facts | Hub pairing and settings |
| Pairing page with the code field | Hub `/v1/pair` |
| Offline page that retries every 3 s | The Inspector boot loop |

## Tests that prove each control works

- Website, website/tests/e2e/controls.spec.ts and site.spec.ts. Navigation links, wordmark, phone menu, footer link, sidebar, outline, heading anchors, pager, version switcher, phone section menu and outline, copy buttons, the seven flow parts, every driver filter, the library search, and the playground's example, client and device pickers, Set, Send, Dry run, Approve, Reject, Stop and Unlock.
- Inspector, dashboard/e2e/chrome.spec.ts, control.spec.ts, log.spec.ts and access.spec.ts. The wordmark and every view link, Message log, Hide and Show the log, Show hal/value, Show the whole message, Copy as text, Clear filters, Show older messages, every log filter, disabled controls on a read-only device, sliders, number fields, Set, Run, the queued request link, STOP, UNLOCK, Keep stopped, Approve, Reject, audit filters and Verify the hash chain, routine selection, Dry run, Enable, Disable and Run now, token create, copy, revoke and keep, Show revoked tokens, New pairing code, pairing a new browser, the offline retry, Look for devices, Start the driver writer, the raw data disclosure, Use suggested, Confirm these limits, Save the Device File and All unknown devices.
