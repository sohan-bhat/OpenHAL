# Brief: website and Inspector quality checks (M14)

Read docs/agents/COMMON.md first. Then read docs/DESIGN.md (the theme, the mapping table, tokens and the banned list), website/ and dashboard/ with their tests, and docs/demo/scenario.yaml.

## Goal

Measured, recorded quality for the website and the Inspector, and nothing on either that comes from nowhere.

1. **Lighthouse.** Run Lighthouse with the Playwright Chromium against the production builds served on loopback (never port 4000). Cover every page template of the website (home, a spec page, the playground, drivers, a driver page, the library, a guide page, the 404) and every Inspector view on its mock API, on mobile and desktop. Fix anything under 95 in performance or under 100 in accessibility, best practices and SEO that is in our control. Record every score in docs/verification/ui.md, with the date, the commit and the command used.
2. **axe.** Every page and view in both themes with zero violations. Extend the existing axe tests so they cover every page and view, and record the results in the same file.
3. **Orphan audit.** For every page and view, list every visual element and the part of the system it comes from (a token, a component, the mapping table). Remove anything that comes from nowhere. Every piece of UI chrome works or isn't drawn, so add a test for each control that it does something. Record the audit in docs/verification/orphans.md.
4. **The plant waterer everywhere.** The playground and the Inspector demo data start from the plant waterer in docs/demo/scenario.yaml. The desk fan stays only as a secondary example to pick. Check the website and Inspector copy for unexplained jargon like "layer" and "write" ("command" or "change" instead), except in protocol method names like hal/write.

5. **The device library on the website.** The starter library in library/ (33 files) is new. Fix what its agent found.
   - The website's TypeScript unit registry has no `ppm` or `lux`, and `parseLibrary` crashes on an unknown unit instead of catching `UnitError`.
   - Read-only library files show as "confirmed" because `unconfirmed()` comes back empty for them. A file with `suggested: true` entries and no `confirmed` must show as unconfirmed, with the suggested entries listed.
   - docs/guide/library.md is missing from website/src/lib/markdown/routes.mjs.

## Gates

`pnpm build` with zero warnings in website/ and dashboard/, vitest, and Playwright in Chromium and Firefox. WebKit page loads stall on this Mac, so skip WebKit and say so.

## Files you own

website/, dashboard/, tests/website/ and tests/inspector/ only to regenerate their fixtures, docs/verification/ui.md and docs/verification/orphans.md.

## Not yours

docs/DESIGN.md (propose changes in your report), README.md, the Python packages and everything else.
