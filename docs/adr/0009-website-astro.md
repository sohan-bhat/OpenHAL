# 0009 Website is a static Astro site generated partly from the repository

## Context

The website renders the spec, the driver catalog, the device library and the docs, plus an interactive device file playground. It must score 95+ on Lighthouse on mobile and ship little JavaScript outside the playground.

## Options considered

1. Astro. Static output, content collections from Markdown and JSON, islands for the playground only.
2. Next.js static export. More JavaScript by default.
3. A custom Python static generator. Full control, much more work.

## Decision

Astro with content collections that read `spec/`, `docs/`, `drivers/catalog.json` and `library/` at build time. The playground is a single island (Svelte, sharing code with the dashboard's control renderer) that validates YAML against the exported JSON Schema and runs a TypeScript port of the kernel's checks, clearly labeled as a demo. A test runs the same command fixtures through the Python kernel and the TypeScript port and requires identical results and messages.

## Consequences

Site content can't drift from the repository. The TypeScript port of the kernel checks is demo-only and is never used to protect hardware.
