# 0011 Device files in the library are CC0, code is Apache-2.0

## Context

The device library is data that people will copy into their own projects, vendors may ship, and other projects (OpenMHP, DCP, MHS later) may import.

## Options considered

1. CC-BY-4.0. Requires attribution in every copy, which is awkward for data embedded in firmware and tools.
2. CC0. No conditions, maximum reuse, matches how hardware description data is usually shared.

## Decision

CC0 for everything under `library/` and `spec/examples/`. Apache-2.0 for all code, including the firmware library. Provenance inside each device file still records who made it, which gives credit without a legal requirement.

## Consequences

Contributors agree to CC0 for device files in CONTRIBUTING.md.
