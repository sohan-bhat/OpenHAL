# Versioning

OpenHAL uses two version schemes. Neither follows the software's version.

## Specification versions are dated

1. Each version of the specification is named by its date, `YYYY-MM-DD`. A later date is a newer version.
2. Each version lives in its own folder, `spec/<version>/`, with its own [changelog](2026-10-24/changelog.md).
3. [`spec/versions.json`](versions.json) lists every version with its status, `draft` or `final`, and names `latest`.
4. A version marked `final` does not change except for wording fixes that change no requirement.
5. Clients and Hubs negotiate the version in `hal/initialize` ([Lifecycle](2026-10-24/basic/lifecycle.md#version-negotiation)).
6. Error codes are stable across versions and are never reused ([ERRORS.md](ERRORS.md)).

The first version is [2026-10-24](2026-10-24/index.md), a draft.

## The device file format uses semantic versioning

A Device File's `openhal` field names the format version it was written for, such as `"0.1"`. Each dated specification says which format version it defines. 2026-10-24 defines format 0.1.

| Change | Meaning |
|---|---|
| Patch (0.1.x) | Wording fixes and clarifications. No file changes meaning |
| Minor (0.x) | New optional fields or values. Every valid file stays valid with the same meaning |
| Major (x.0) | Changes that can make a valid file invalid or change its meaning. Each major version ships `openhal file migrate` and a migration guide |

Hubs accept files from the same major version and warn on a newer minor version. The full rules are in [device-files.md](2026-10-24/device-files.md#versioning).
