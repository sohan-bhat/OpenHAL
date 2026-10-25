# Brief: the OpenHAL Inspector (the dashboard)

Read docs/agents/COMMON.md first, then docs/DESIGN.md (all of it, especially "The Inspector", "Signature element: the message trace" and "Banned"), docs/adr/0008 (Svelte 5 and Vite, served by the hub), docs/adr/0012, docs/adr/0014, docs/adr/0015 and docs/api/openapi.json.

## Goal

Build the OpenHAL Inspector, a protocol inspector for a running hub, in `dashboard/` with Svelte 5, Vite and TypeScript, using design/tokens.css and design/fonts/. The production build goes to `openhal/hub/static/`, which the hub already serves at `/`. It authenticates with the existing dashboard session cookie, created through pairing.

## Layout

- **Header.** The hub name, connection state and protocol version. On the right, a large STOP control that is always visible, in the blocked red with its word. When stopped, it becomes UNLOCK, which needs the phrase `unlock` typed.
- **Left pane.** Devices with their state, conformance level and verification status.
- **Main pane.** The selected device's channels, with live values and units, limits drawn as a limit line on each control, rate limits, and write controls that stop at the limit. Actions show their confirmation tier. Writes from the Inspector are human writes.
- **Bottom pane.** The live message log, every JSON-RPC request, response, notification and error from every client, formatted as the message trace in DESIGN.md.
  - Filter by client, device, method and outcome.
  - Arrows drawn as inline SVG.
  - The house syntax theme.
  - The feed is `/v1/rpc/log/live`, which the protocol workstream is building in parallel. Until it lands in your branch, build against the shape in BRIEF-protocol.md section 7, with a fixture, then switch.
- **Other views** reachable from the header or left pane:
  - The confirmation queue. Approve and reject, showing exactly what was requested, by which client, and the dry-run result.
  - The audit log viewer, with filters and blocked entries highlighted with their reason.
  - Routines. List, source, dry run, enable and disable, and run history.
  - The driver writer flow. Unknown devices, the limits interview, a file preview with a diff, and save.
  - Settings. Client tokens and scopes, and the LAN toggle (read-only display if the API has no toggle).

Agent actions and human confirmations must look different (DESIGN.md).

## Quality

- WCAG AA in both themes, keyboard navigable, visible focus. Status never by color alone.
- Body text at least 14 px.
- Values never shift layout when they update, and every number has its unit.
- Playwright tests (headless Chromium, Firefox and WebKit) against a real embedded hub with mock devices.
  - The block shows LIMIT_EXCEEDED in the log.
  - Stop and unlock.
  - Approve and reject.
  - Keyboard navigation.
  - An axe AA check.
- Vitest for the stores and the trace formatter.
- `pnpm build` with zero warnings. The build output is committed to openhal/hub/static/ so a Python-only install serves it.

## Design critique

When feature complete:
1. Take screenshots at 1440 and 390, light and dark, of each view, with the mock fan and heater and a blocked write in the log. Save them to `docs/design-rounds/inspector-round-1/`.
2. Commit and hand back with "Inspector round 1 is ready".

The orchestrator runs an independent reviewer and sends you the findings for rounds 2 and 3.

## Files you own

dashboard/, openhal/hub/static/, tests/inspector/ (Python tests that start the hub for Playwright), and docs/design-rounds/inspector-*.

## Not yours

Hub Python code. If you need an API change, propose it in your report.
