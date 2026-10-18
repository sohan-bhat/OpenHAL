# Progress

## Current milestone

M2 Hub core and safety kernel.

## Active subagents

- safety-review (fresh reviewer, Opus). Owns docs/agents/REVIEW-safety.md, docs/agents/REPORT-safety-review.md and tests/review_safety/. Brief in docs/agents/BRIEF-safety-review.md. Started during M2 once the kernel was complete.

Concurrency cap is 3 subagents at once, lower than the 5 the build prompt allows, because the owner's standing rule caps parallel agents at 3. Every coding subagent runs on Opus 5.5 and may not start subagents of its own.

## Done

- Repository created at ~/code/openhal.
- Research brief copied to docs/research/OPENHAL_RESEARCH.md, updated with OpenMHP, DCP, Octopus, HACP and EMQ findings.
- Name check recorded in docs/research/SOURCES.md.

- M0 complete. ARCHITECTURE, SAFETY, THREAT_MODEL, DESIGN, COVERAGE plan, ADRs 0001 to 0012 and the spec draft are written and committed.

- M1 complete. Pydantic models, JSON Schema, 14 examples, `openhal file validate` and `openhal file schema`, spec CHANGELOG and versioning policy, MHS mapping, DEPENDENCIES. 128 tests, ruff and mypy clean.

## Next

- M2. Driver base and grants, safety kernel, audit log, confirmation queue, stop, dry run, tokens, registry, mock framework, conformance skeleton, minimal local API, then the independent safety review.

## Milestone 1 review

Built. The spec models with every section of SPEC.md, a restricted YAML loader (no anchors, aliases or custom tags, size limit), unit handling that converts degF against degC limits and uses delta units for temperature rates, a three-valued expression language with its own parser, the generated JSON Schema with a test that it matches the models, fourteen example files and the validate CLI.

Weak. Location strings for errors raised inside model validators come from the message text rather than the error path. Driver parameters are not validated until drivers exist. The schema describes limits as number or string, so editors can't check units.

Would change. Move per-driver parameter models next to each driver and reference them from the schema with a discriminated union once all drivers exist.

## Milestone 0 review

Built. The research brief with the October findings, sources, twelve ADRs, the architecture with seven diagrams, the safety model with a fixed check order and stable codes, the threat model with twenty threats mapped to tests, the design system with verified contrast figures, the coverage plan and the v0.1 spec draft.

Weak. Device estimates in the coverage plan are reasoning only and still need sources. The MHS mapping depends on a spec nobody can read yet. The expression semantics for unknown values are conservative and may block legitimate commands when a sensor is slow.

Would change. Nothing structural yet. The spec draft will be tightened as the models are written.

## Known issues

- PyPI name `openhal` is taken by an unrelated project. See NEEDS_HUMAN.md and ADR 0002.
