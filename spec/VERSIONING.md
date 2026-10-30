# Versioning

OpenHAL gives version numbers to two things, the specification with its hub protocol and the device file format, and neither number follows the software's version.

## Specification versions are numbered

1. Each version of the specification is numbered `MAJOR.MINOR`, such as `0.1`. People see the version with a leading v, as v0.1, but the wire and the data carry the bare number, as in `"protocolVersion": "0.1"`.
2. Versions compare as numbers, major first and then minor, so 0.10 is newer than 0.9.
3. Before 1.0, a minor version may change or remove behavior. From 1.0 on, a minor version only adds methods, notifications, fields and error codes, so every exchange that was valid keeps its meaning, and only a major version may break a Client.
4. Each version lives in its own folder, `spec/v<version>/`, with its own [changelog](v0.1/changelog.md), and the website serves it at `/spec/v<version>/`.
5. [`spec/versions.json`](versions.json) lists every version with its status, `draft` or `final`, and names `latest`.
6. A version marked `final` does not change except for wording fixes that change no requirement, so a version has no patch number.
7. Clients and Hubs negotiate the version in `hal/initialize` ([Lifecycle](v0.1/basic/lifecycle.md#version-negotiation)).
8. Error codes are stable across versions and are never reused ([ERRORS.md](ERRORS.md)).

The first version is [v0.1](v0.1/index.md), a draft. It was named by its date, 2026-10-24, until [ADR 0017](../docs/adr/0017-version-numbers.md) numbered the versions.

## The device file format uses semantic versioning

A Device File's `openhal` field names the format version it was written for, such as `"0.1"`. Each version of the specification states which format version it defines, and v0.1 defines format 0.1.

| Change | Meaning |
|---|---|
| Patch (0.1.x) | Wording fixes and clarifications. No file changes meaning |
| Minor (0.x) | New optional fields or values. Every valid file stays valid with the same meaning |
| Major (x.0) | Changes that can make a valid file invalid or change its meaning. Each major version ships `openhal file migrate` and a migration guide |

Hubs load files from the same major version and report a warning for a newer minor version. The full rules are in [device-files.md](v0.1/device-files.md#versioning).
