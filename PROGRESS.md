# Progress

## Current milestone

M0 Research and design.

## Active subagents

None. Phase A runs on the orchestrator alone.

Concurrency cap is 3 subagents at once, lower than the 5 the build prompt allows, because the owner's standing rule caps parallel agents at 3. Every coding subagent runs on Opus 5.5 and may not start subagents of its own.

## Done

- Repository created at ~/code/openhal.
- Research brief copied to docs/research/OPENHAL_RESEARCH.md, updated with OpenMHP, DCP, Octopus, HACP and EMQ findings.
- Name check recorded in docs/research/SOURCES.md.

## Next

- Finish M0 documents: ARCHITECTURE, SAFETY, THREAT_MODEL, DESIGN, COVERAGE plan, ADRs, spec draft.

## Known issues

- PyPI name `openhal` is taken by an unrelated project. See NEEDS_HUMAN.md and ADR 0002.
