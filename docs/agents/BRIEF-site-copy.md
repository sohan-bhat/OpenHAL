# Brief: every page of the site follows the owner's writing rules

Read docs/agents/COMMON.md first, then the "Copy voice" section of docs/DESIGN.md, which now holds the owner's writing rules for all site copy.

## What the owner said

- Write like technical documentation, not ad copy. No punchy fragments, no dramatic short-sentence sequences.
- Never write three or more short sentences in a row. Combine related ideas with "because", "but", "so", "when".
- State cause before effect. The reason something happens comes before or with the outcome, never as an afterthought.
- Don't personify software ("OpenHAL says no", "the kernel steps in"). Say what it does: refuses, blocks, rejects, returns an error.
- Be precise with units and nouns: "nozzle temperature of 300 °C", not "a 300 °C nozzle".
- Test: read it aloud. If it sounds like a movie trailer, rewrite it as one plain sentence.

## Goal

Rewrite the prose on every page of the website except the home page, so every sentence follows Copy voice. Keep the meaning, facts, numbers, code, commands, method names, error codes and links exactly as they are. Only prose changes.

1. **Pages and components in website/src.** The docs index, the SDK pages, the Python reference's intro, the Playground's headings, information marks and notes, the drivers index and driver page text, the library pages, the Inspector page, the blog post, the 404, the search dialog's text, the nav and footer text, page titles and descriptions (website/src/lib/pages.ts, docs-nav.ts, spec-nav.ts and safety.ts) and the text on social images (website/src/lib/og.ts).
2. **The repo docs the site renders** (FIXED_ROUTES in website/src/lib/markdown/routes.mjs, plus docs/drivers/*.md): docs/guide/, docs/SAFETY.md, docs/ARCHITECTURE.md, docs/interfaces/CLI.md, MCP.md and PYTHON.md, docs/drivers/, spec/MHS-MAPPING.md, spec/FIRMWARE-PROTOCOL.md, spec/VERSIONING.md, spec/ERRORS.md, spec/CONFORMANCE.md, spec/GLOSSARY.md, firmware/arduino/OpenHAL/README.md, and README.md.
3. **Look first for** personified software ("the hub asks", "OpenHAL says", "the kernel steps in", "the kernel says no"), imprecise nouns ("a 300 °C nozzle"), runs of three or more short sentences, punchy fragments and effects stated before their causes.
4. **Tests that pin copy.** tests/docs/test_scenario_docs.py matches demo values in prose with patterns such as `(\d+) °C nozzle`. When your wording changes a phrase a pattern looks for, update the pattern so every check still finds its value on a page, and keep the check that each pattern finds something.

Leave the dated spec in spec/2026-10-24/ alone, because its text is fixed once published. Leave the one-line description "An open-source protocol for AI agents to control hardware." exactly as it is. Leave generated trace blocks (the README trace and the `scenario` fences) to their generators.

## Gates

COMMON.md's gates, `pnpm build` with zero warnings, vitest, Playwright in Chromium and Firefox (the copy tests and axe), and `uv run pytest tests/docs tests/website tests/demo`. Run one suite at a time, because a story round shares the machine.

## Files you own

website/src except the home page (website/src/pages/index.astro), website/src/components/landing/, website/src/lib/story/ and website/src/styles/story.css, which the story round owns (BRIEF-website-9.md). The repo docs listed above, README.md, the website tests that pin copy you change and tests/docs/test_scenario_docs.py.

## Not yours

The home page and the landing story, openhal/, dashboard/, docs/DESIGN.md, docs/agents/ and spec/2026-10-24/.
