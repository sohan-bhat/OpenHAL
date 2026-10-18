# 0013 Contracts frozen before parallel work

## Context

Phase B runs several subagents in parallel. They must build against stable interfaces, and only the orchestrator may change those interfaces.

## Decision

These are frozen as of the end of M2.

1. The device file spec. `openhal/spec/models.py`, `spec/schema/device-file.schema.json`, `spec/SPEC.md`.
2. The driver interface. `openhal/drivers/base.py` (Driver, DriverInfo, Reading, Discovered, Health, DriverError) and the package layout in docs/drivers/WRITING-A-DRIVER.md.
3. The conformance case shape. `openhal/conformance/suite.py` (ConformanceCase).
4. The kernel API. `Kernel.evaluate`, `execute`, `dry_run`, `read`, `confirm`, `reject`, `tighten`, `stop_all`, `unlock`, `tick`, `approve_routine`, plus `Write`, `Action`, `Decision`, `Principal` and the block codes in `openhal/kernel/commands.py`.
5. The local API v1. Routes and payloads in `docs/api/openapi.json`, generated from `openhal/hub/api.py`.
6. The live event shapes emitted by `Hub._emit` (`reading`, `state`, `audit`, `watchdog`, `hello`).

Routine endpoints (M6) and driver writer endpoints (M9) will be added to the API by the orchestrator under `/v1/routines` and `/v1/writer`, recorded in later ADRs.

## Consequences

A subagent that needs a change writes a proposal in its report. Internal changes to the kernel that keep these interfaces (for example fixes from the safety review) don't need an ADR.
