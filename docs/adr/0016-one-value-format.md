# 0016 Values travel as a number and a unit, never as one string

## Context

Protocol messages carried numeric values two ways. Requests used quantity strings such as `"150 %"`, and results and notifications used a number with a separate `unit`. Two formats mean two parsers in every client, ambiguous whitespace and locale rules, and examples that disagree with each other.

## Options considered

1. **Quantity strings everywhere** (`"150 %"`). Compact and readable, but every client must parse text, and the format invites mistakes like `"150%"` versus `"150 %"`, `"1,5 V"` or `"1e3 mV"`.
2. **A number and a unit everywhere** (`{"value": 150, "unit": "%"}`). JSON Schema validates the number. The unit is one token that pint parses on its own, and nothing is parsed from text.

## Decision

Option 2.

- **Channel messages carry `value` and `unit` side by side.** This covers `hal/write` params, `hal/read` and `hal/readMany` results, `hal/value` notifications, write results and decisions. `{ "device": "printer", "channel": "bed_temp", "value": 60, "unit": "degC" }`.
- **Nested places carry a Quantity object `{ "value": <number>, "unit": "<unit>" }`.** This covers action arguments (`"args": { "duration": { "value": 20, "unit": "s" } }`), `error.data.limit` and `error.data.requested`, and the `duration` of a plan wait.
- **Booleans, enum values and text** are plain JSON values with no `unit`.
- **A numeric value without a unit, or sent as one string such as `"150 %"`, gets UNIT_INVALID** with a reason that shows the right shape.
- **This applies to the hub protocol, the REST API, MCP tool inputs and outputs, the Python client and the CLI's `--json` output.** People still type `150%` at the CLI prompt, and the CLI converts it before sending. Human-readable reasons and CLI text show `150 %`.
- **Device files are a human-written file format and keep quantity strings for limits** (`max: 100 %`, `every: 1 s`). They are not protocol messages.

A test fails if any JSON example in README.md or docs/ carries a numeric value as a single string.

## Consequences

- ADR 0015 and spec/v0.1 use the structured form in every example, and the generated schema changes with the models.
- Clients that sent quantity strings must send the number and unit separately. Nothing is released yet, so no compatibility shim is kept.
