# Conformance

The normative text is in [spec/v0.1/drivers.md](v0.1/drivers.md#conformance-levels), and this page summarizes that text.

OpenHAL has three Conformance Levels, and each level includes the level below it.

| Level | A Hub implements | A Driver supports |
|---|---|---|
| `core` | Initialize, list, describe, read, read many and `hal/value` | Identify, connect, describe, read and close |
| `control` | Core plus channel changes, dry run, plan check, stop, unlock, `hal/blocked` and `hal/stopped`, all through a Safety Kernel that meets the [safety section](v0.1/safety.md) | Core plus channel changes through Grants and a safe state |
| `full` | Control plus actions, confirmations, routines, the audit query and `hal/confirmationRequested` | Control plus actions through Grants |

- A Hub declares its level in the `hal/initialize` result and returns `METHOD_NOT_FOUND` for methods above that level, and the reference Hub is `full`.
- A Driver declares its level in `DriverInfo.conformance`, and a read-only camera Driver, for example, is `core`.
- The conformance suite in `openhal/conformance/suite.py` tests the declared level and nothing above it. Run the suite with `uv run pytest tests/conformance`.

The [drivers section](v0.1/drivers.md#conformance-suite) lists every check and its level.
