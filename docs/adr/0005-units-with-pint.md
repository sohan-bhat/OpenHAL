# 0005 Every number carries a unit, converted with pint into the device's declared unit

## Context

Limits are meaningless without units, and unit tricks are an obvious bypass (asking for a temperature in degF to exceed a degC limit, or a speed in rpm against a percent limit).

## Decision

- Every numeric value in a device file, a command, a routine and an API payload carries a unit. Device files and routines use quantity strings, and messages carry a number and a unit apart (ADR 0016). Bare numbers are rejected with an error that names the expected unit.
- The kernel converts every incoming value to the channel's declared unit with one shared pint registry before any check runs. Conversion failures block the command.
- Temperatures are absolute quantities. Rate limits on temperature use delta units (`delta_degC/s`) internally, so offset units convert correctly.
- `percent` and `dimensionless` are both supported. A percent channel accepts `50 %`, `50 percent` and `0.5` with an explicit `dimensionless` unit, all compared in percent.
- After conversion the kernel checks the value is finite (no NaN or infinity) before any comparison.

## Consequences

pint becomes a hard dependency of the kernel. The kernel pins the registry definition and never loads user-supplied unit definitions.
