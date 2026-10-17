# Progress

## Current milestone

M1 Spec and validator.

## Active subagents

None. Phase A runs on the orchestrator alone.

Concurrency cap is 3 subagents at once, lower than the 5 the build prompt allows, because the owner's standing rule caps parallel agents at 3. Every coding subagent runs on Opus 5.5 and may not start subagents of its own.

## Done

- Repository created at ~/code/openhal.
- Research brief copied to docs/research/OPENHAL_RESEARCH.md, updated with OpenMHP, DCP, Octopus, HACP and EMQ findings.
- Name check recorded in docs/research/SOURCES.md.

- M0 complete. ARCHITECTURE, SAFETY, THREAT_MODEL, DESIGN, COVERAGE plan, ADRs 0001 to 0012 and the spec draft are written and committed.

## Next

- M1. Pydantic models, JSON Schema export, ten or more examples, `openhal file validate`, CHANGELOG, MHS mapping, then freeze contracts.

## Milestone 0 review

Built. The research brief with the October findings, sources, twelve ADRs, the architecture with seven diagrams, the safety model with a fixed check order and stable codes, the threat model with twenty threats mapped to tests, the design system with verified contrast figures, the coverage plan and the v0.1 spec draft.

Weak. Device estimates in the coverage plan are reasoning only and still need sources. The MHS mapping depends on a spec nobody can read yet. The expression semantics for unknown values are conservative and may block legitimate commands when a sensor is slow.

Would change. Nothing structural yet. The spec draft will be tightened as the models are written.

## Known issues

- PyPI name `openhal` is taken by an unrelated project. See NEEDS_HUMAN.md and ADR 0002.
