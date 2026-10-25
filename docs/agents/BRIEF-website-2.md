# Brief: the website as a protocol site (replaces the round 1 direction)

Read docs/agents/COMMON.md first, then docs/DESIGN.md in full (the one theme, the signature elements, the theme mapping, the canonical demo scenario and Banned), then docs/adr/0015-openhal-hub-protocol.md.

## Goal

Turn the website in `website/` into a protocol site, modeled on how modern protocol documentation is organized but with OpenHAL's own identity. Keep everything that still fits:
- the TypeScript kernel port and its parity tests
- the playground
- the catalog and library collections
- snippet testing
- the Open Graph pipeline
- the Lighthouse and axe checks

Drop the instrument-panel theme completely. That means Sofia Sans Condensed, Martian Mono, the limit-line hero, hazard stripes and the bezel stop bar. Use design/tokens.css and design/fonts/ from main.

## Structure

The top navigation is Overview, Specification, Drivers, Device Library, SDKs, Inspector, Blog, GitHub.

- **Overview (home).**
  - One sentence. "OpenHAL is an open protocol for AI agents to discover, read and control hardware safely."
  - The animated flow diagram as the hero. Use `docs/diagrams/flow-light.svg` and `flow-dark.svg` when they land on main (the orchestrator is building them now) as an inline SVG component.
    - It starts animating when scrolled into view.
    - Hovering or focusing a node highlights its path and shows a one-line explanation.
    - Until the files exist, leave a sized slot that renders nothing.
  - The message trace below it.
  - A three-command quickstart, identical to the README's and tested.
  - Supported device families from drivers/catalog.json.
  - The relationship to MHS in two sentences, including that OpenHAL is not affiliated with Anthropic or MHS.
  - Links into the spec.
  - No marketing sections.
- **Specification.**
  - Versioned by date, with a version switcher and the version in the URL (`/spec/2026-10-24/...`, plus `/spec/latest/` as the alias).
  - Rendered from `spec/2026-10-24/*.md` and `spec/versions.json`, which the spec workstream is writing now. Build the collection so it renders whatever is there, in this order: Introduction, Architecture, Base Protocol (lifecycle, transports, messages), Device Files, Safety (kernel requirements, error codes), Drivers (interface, conformance), Routines, Security, Schema Reference (`schema.md` and `schema.json` from the protocol workstream), Glossary, Changelog.
  - The Playground sits under Specification. Its "try to break the limits" demo answers with the same JSON-RPC errors as the real hub: `error -32010 LIMIT_EXCEEDED` with the ADR's reason template, shown as message traces, and clearly labeled as an in-browser demo. Update the TypeScript port's messages and the parity test to the ADR's error names, codes and reasons.
- **Drivers.** A searchable, filterable datasheet table from drivers/catalog.json, with tier, status, conformance level (once the catalog has it) and hazard default, plus a page per driver. Every status is honest. The 18 implemented drivers are "tested on simulator", none is "verified on hardware", and 16 are planned.
- **Device Library.** Searchable device files with verification badges and a page per device. Keep the honest empty state until library/ exists.
- **SDKs.** Python as the reference, with install, quickstart and an API reference generated from `openhal/client` docstrings. TypeScript marked planned.
- **Inspector.** Docs for the dashboard. Leave slots for real screenshots from the Inspector workstream, which comes later.
- **Docs.** Quickstart, concepts, tutorials (connect Claude, add a device, write a driver, write a routine) and FAQ, in `docs/guide/`.
- **Blog.** The launch post draft "Why we built OpenHAL", in the spec voice. Show Blog in the nav only once a post is published. Drafts don't count.
- **Every docs and spec page.** An "On this page" outline, heading anchors, copy buttons on every code block, previous and next links, "Edit on GitHub", and the spec version in the URL.
- **Site basics.**
  - 404 as a message trace ending in `error -32004 UNKNOWN_TARGET`.
  - An Open Graph image per page, showing the message trace on the page title.
  - The favicon from the mark described in DESIGN.md.
  - Sitemap and robots.txt.

## Copy

- Formal and exact, short declarative sentences.
- Defined terms linked to the glossary on first use.
- "Open protocol" and "specification", never "standard".
- Little text. The owner keeps asking for less.
- Every demo value matches DESIGN.md's canonical demo scenario: desk-fan, fan_speed, current 20 %, requested 150 %, limit 100 %, granted 60 %.

## Quality

Keep the existing bar:
- Lighthouse 95+ on home mobile and 90+ elsewhere.
- WCAG AA and axe clean.
- Chromium, Firefox and WebKit.
- No layout shift.
- Minimal JavaScript outside the Playground and the diagram.
- Every snippet tested.
- Zero build warnings.

## Design critique

When feature complete:
1. Take screenshots of every page at 390 and 1440 px, light and dark, into `docs/design-rounds/round-2/`.
2. Commit and hand back with "Website round 2 is ready".

## Before you start

Your branch is based on an older main. Run `git rebase main` in your worktree. Main has the new DESIGN.md, design/tokens.css, the fonts and ADR 0015. Take main's version of any file you don't own. Then run every gate.

## Files you own

website/, docs/guide/, docs/design-rounds/ and tests/website/.

## Not yours

Everything else, including spec/, docs/diagrams/ and README.md.
