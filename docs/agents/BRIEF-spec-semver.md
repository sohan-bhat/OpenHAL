# Brief: version numbers instead of dates for the specification and the protocol

Read docs/agents/COMMON.md first, then docs/adr/0015-openhal-hub-protocol.md, spec/VERSIONING.md, spec/versions.json, spec/CHANGELOG.md and the places in openhal/ that report or negotiate the protocol version.

## What the owner said

"For versioning don't use date, use v.XX or whatever the format is."

## Goal

The specification and the hub protocol move from dated versions to semantic versions. The current draft, 2026-10-24, becomes version 0.1, shown to people as v0.1.

1. **The decision.** Add an ADR that supersedes the dated-version part of ADR 0015. Versions are MAJOR.MINOR, with the usual reading for 0.x (a minor version may still change behavior before 1.0). People see "v0.1". The identifier on the wire and in data is "0.1".
2. **The specification.** Move spec/2026-10-24/ to a folder for v0.1. Choose the folder name so the website can serve the pages at /spec/v0.1/. Update spec/versions.json, the spec's own text ("Version 2026-10-24. Status draft."), spec/VERSIONING.md, spec/CHANGELOG.md and the schema's identifiers. The spec is a draft, so renaming the draft's version is allowed. Record the rename in the changelog.
3. **The hub and its clients.** `hal/initialize` negotiates "0.1", and every place that reports the protocol version says "0.1": REST, MCP, the CLI, the Python client and the hub's info the Inspector reads. No outside client exists yet, so make a clean change. The hub refuses an unknown version with its existing error, which names the supported version.
4. **Real dates stay dates.** Only the spec and protocol version identifier changes. Device files' `confirmed: { at: ... }`, ADR dates, changelog dates, record times and every other real date keep their dates. Check each match before changing it.
5. **Everything that pins the version follows.** That covers tests, docs (docs/ except DESIGN.md, agents and verification/ui.md), README.md, examples, conformance, generated files (the schema, website/tests/kernel-parity/expected.json and website/src/content/generated/python-api.json) and the Inspector's fixtures and tests in dashboard/. Rebuild openhal/hub/static if the dashboard's source changes.

## Signal early

As soon as the spec folder, versions.json and the protocol constant are committed, send `main` the commit hash and the new folder name and identifiers. A website round (website-12) is rebuilding the docs on Starlight at the same time and wires its version picker and spec routes to them.

## Gates

COMMON.md's gates, `uv run openhal demo` and `uv run openhal demo --full` read as a person would read them, the dashboard's vitest and its Playwright tests that show the protocol version, and `git grep 2026-10-24` reviewed line by line at the end, with every remaining match a real date.

## Files you own

openhal/, spec/, docs/ except docs/DESIGN.md, docs/agents/ and docs/verification/ui.md, tests/, examples/, README.md, dashboard/ (fixtures, tests and the static rebuild) and the two generated website files named above.

## Not yours

website/ except those two generated files, docs/DESIGN.md (propose), every safety rule and every device file's limits.
