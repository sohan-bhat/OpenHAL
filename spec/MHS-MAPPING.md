# Mapping to the Model Hardware Standard

Anthropic's Model Hardware Standard (MHS) entered a closed research preview on 2026-08-27. As of 2026-10-24 there is no public specification, schema, SDK or license (docs/research/SOURCES.md). This document maps every OpenHAL concept to what is publicly known about MHS, lists what is unknown, and describes the adapter OpenHAL will ship once a spec is published.

OpenHAL is not a rival standard. OpenHAL uses the same read and write model and the same idea of a reference file, so MHS devices and drivers can be used through OpenHAL and OpenHAL device files can be exported to MHS.

## What maps

| OpenHAL | MHS, as publicly described | Confidence |
|---|---|---|
| Read channels | `read` primitive ("get the temperature") | High. Named in the announcement |
| Write channels | `write` primitive ("set the temperature") | High |
| Actions | Not named publicly. Partners describe multistep operations as code files chaining driver commands | Low |
| `match` and discovery | "Discoverable in a standard format" across networks | Medium. Format unknown |
| `notes`, `provenance` and the limits interview | Natural-language tags on the driver, written by the user or by an agent interview | High for the idea, unknown format |
| The device file as a whole | The reference file generated from tags (what can be measured, what can be adjusted, which limits are enforced) | High for the idea, unknown format |
| `min`, `max`, `max_change_per_s`, interlocks, watchdog rules | "Safety limits" enforced by the driver. Carnegie Mellon's pilot blocked six induced faults before motion | Medium |
| Physical facts in notes (arm weight, safe power range) | Tags carry facts not visible in code, such as a robot arm's weight | High |
| MCP server, CLI, Python library | MCP, command line interface, code files | High |
| Routines | Code files that run without the model, such as QuEra's relock controller | High |
| Hazard classes, confirmations, approvals | Not described publicly | Unknown |
| Audit log | Not described publicly | Unknown |

## What is unknown

- The reference file format, field names and units handling.
- How discovery works on the wire.
- How limits are expressed, and whether interlocks across devices exist.
- Whether drivers are in-process, out-of-process or on the device.
- Versioning, governance, license and conformance testing.
- Authentication, authorization and confirmation flows.

## Adapter plan

When MHS publishes a specification, OpenHAL will add, in order.

1. `openhal file import --from mhs <reference-file>`, which converts an MHS reference file into a `.hal.yaml` file with `provenance.source: library` and every limit marked `suggested: true`, so a human confirms limits before anything is writable.
2. `openhal file export --to mhs <device>.hal.yaml`, which writes an MHS reference file. Concepts MHS lacks (confirmation tiers, approvals) go into MHS tags as plain-language notes where the format allows, and the export reports anything it could not carry over.
3. An `mhs` bridge driver that talks to devices exposing MHS drivers, with OpenHAL's kernel still enforcing the OpenHAL device file.
4. Round-trip tests on every file in `spec/examples/` and `library/`.

Until then, nothing in OpenHAL depends on guesses about the MHS format.

## Other open formats

The same import and export path is planned for OpenMHP device packages (`descriptor.yaml`) and Device Context Protocol manifests. Both are public, so these adapters are on the roadmap for v0.2 (docs/ROADMAP.md).
