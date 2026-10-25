# Conformance

The normative text is in [spec/2026-10-24/drivers.md](2026-10-24/drivers.md#conformance-levels). This page summarizes it.

OpenHAL has three Conformance Levels. Each includes the one below it.

| Level | A Hub implements | A Driver supports |
|---|---|---|
| `core` | Initialize, list, describe, read, read many and `hal/value` | Identify, connect, describe, read and close |
| `control` | Core plus channel changes, dry run, plan check, stop, unlock, `hal/blocked` and `hal/stopped`, all through a Safety Kernel that meets the [safety section](2026-10-24/safety.md) | Core plus channel changes through Grants and a safe state |
| `full` | Control plus actions, confirmations, routines, the audit query and `hal/confirmationRequested` | Control plus actions through Grants |

- A Hub declares its level in the `hal/initialize` result and answers methods above it with `METHOD_NOT_FOUND`. The reference Hub is `full`.
- A Driver declares its level in `DriverInfo.conformance`. A read-only camera Driver is `core`.
- The conformance suite in `openhal/conformance/suite.py` tests the declared level and nothing above it. Run it with `uv run pytest tests/conformance`.

The [drivers section](2026-10-24/drivers.md#conformance-suite) lists every check and its level.
