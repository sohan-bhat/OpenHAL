# Brief: website round 5, the final critique's fixes

Read docs/agents/COMMON.md first, then docs/DESIGN.md and website/ with its tests. Load the skills frontend-design:frontend-design, design-taste-frontend, web-design-guidelines and playwright-cli before UI work. A fresh critic scored the website 3.5 of 5 from screenshots taken before round 4 (the owner's fixes and site search). Check each finding against the current site, since round 4 may have fixed some, and fix the rest.

## The critic's findings, worst first

1. **The drivers table is missing on phones.** At 390 px the page goes from the driver count straight to the footer.
2. **Driver pages scroll sideways on phones.** Long source URLs push 30 of 35 driver pages wider than 390 px (alpaca reaches 922 px). The fact table also draws stub rules under its labels on phones.
3. **The library table is cut off on phones.** Channel counts show as "6 r" and "co", and the verification column can't be seen.
4. **The architecture diagrams are off the house style.** The docs architecture diagrams render as soft rasters with tiny text in a generic sans, and the spec sequence diagram sets message labels in a default sans instead of the mono face. Bring every diagram on the site into the one house style in DESIGN.md (the D2 flow diagram's lines, arrowheads, radius, fonts and mono labels, in light and dark).
5. **The Python SDK reference.** Literal backticks show in rendered text. Signature boxes are cut at the right edge, the `audit(...)` chip breaks across lines, and sixty-odd methods sit in one ungrouped list. Group them (connecting, reading, commanding, confirmations, routines, tokens, the audit log) and show each method's docstring.
6. **The error registry ignores its mapping.** Codes and names in the registry tables are plain proportional text. Make them mono, and give blocked codes their red with the blocked shape, as DESIGN.md maps them.
7. **Spec pages.** Number the section headings. Give the version box a visible switcher. Link each capitalized defined term (Hub, Safety Kernel, Conformance Level and the rest) to the glossary on its first use on a page. On phones the stacked check table prints a "#" label above every row. Drop it.
8. **Navigation.** "Overview" is the active tab on every docs page and there is no Docs item, the docs index only repeats the sidebar as bullets, and the blog can't be reached. Give every page one clear place in the navigation, alongside the Playground item round 4 added.
9. **One left edge.** Home is at 216 px, blog and 404 at 296, docs and spec at 344, and drivers, library and playground at 56. Round 4 aligned drivers and library with overview and specification. Finish the job for every template.
10. **Small labels.** Small-caps table headers and eyebrows measure 11 to 12 px, below the 13 px legend size, and the home diagram's labels are about 11 px.
11. **The home flow diagram.** Node widths run from 114 to 142 px, the `check` connector sits 11 px below the other wires, and the Safety kernel and Driver boxes are empty shells. Fix the craft in docs/diagrams/flow.d2 and scripts/diagrams.py, rebuild with scripts/build-diagrams, and keep the README's picture the same files.
12. **The drivers table header.** "CONFORMANCE" and "PROTOCOL" touch, one group header covers every row, and the count is said three times.
13. **Copy and data.**
    - The driver page prints "Estimated reach." followed by a lowercase phrase. Capitalize it when shown.
    - The library device page has a colon in running prose ("not yet confirmed by a person: water (action)").
    - The blog's empty state and the mock driver's "This driver has no documentation page yet." name what is missing but give no link to fill it.
14. **Traces.** `hal/value` carries prose where JSON should be, and the `result` row aligns differently from the rest on phones. The 404 uses the HTTP verb GET inside a JSON-RPC style trace.
15. **Phones.** The quickstart's clone command and `init` output are clipped, and the playground's "Set" buttons are cut off at the right edge.
16. **Status shapes.** An empty circle is used beyond DESIGN.md's four status shapes, and the granted green marks the SDK "reference" status. Use only the four shapes and their meanings.
17. **The Inspector page.** The screenshots are unreadable (about 6 px text, illegible on phones). Show them so their text can be read, for example cropped to the part each caption is about, with the full shot one click away. The Inspector round owns the capture script and the images themselves, so change only how the page shows them.

## Gates

`pnpm build` with zero warnings, vitest, Playwright in Chromium and Firefox with axe at 0 violations, Lighthouse still where docs/verification/ui.md records it, and `uv run pytest tests/docs tests/website tests/demo` (use `export PATH="$HOME/Library/Python/3.13/bin:$PATH"`). Save screenshots of every page at 390, 768 and 1440 px, light and dark, in your scratch folder, look at them, fix and screenshot again.

## Files you own

website/ except the Inspector captures (website/scripts/inspector-captures.mjs, website/public/captures/ and website/src/data/inspector-captures.json), docs/diagrams/, scripts/diagrams.py and scripts/build-diagrams, and docs/verification/ui.md.

## Not yours

drivers/catalog.json and the driver catalogs (propose wording changes), the spec's text (propose changes), dashboard/ and everything else.
