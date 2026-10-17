# Spec changelog

The device file spec follows semantic versioning, separately from the software.

- **Patch** (0.1.x). Wording fixes and clarifications. No file changes meaning.
- **Minor** (0.x). New optional fields or values. Every valid file stays valid with the same meaning.
- **Major** (x.0). Changes that can make a valid file invalid or change its meaning. Each major version ships `openhal file migrate` and a migration guide.

A file's `openhal` field names the spec version it was written for. Hubs accept files from the same major version and warn on a newer minor version.

## 0.1 (draft, 2026-10-24)

First public draft.

- Identity and library matching (`device`, `id`, `match`).
- Driver selection with shorthand (`connect`).
- Read channels, write channels with min, max, step, rate and enum limits, and actions with typed arguments.
- Safe state as values, an action, or ordered steps.
- Interlocks and the expression language, with three-valued evaluation where unknown never passes.
- Watchdog heartbeat, loss behavior and max duration rules.
- Hazard classes and human-signed approvals for routines on high hazard devices.
- Notes as data, provenance and verification status.
- Limits provenance. Files load read-only until a human confirms every limit.
