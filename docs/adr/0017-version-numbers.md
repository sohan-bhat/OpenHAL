# 0017 The specification and the hub protocol use version numbers, starting at v0.1

## Context

ADR 0015 named each version of the specification and the hub protocol by its date, and the first draft was dated 2026-10-24. The owner asked for version numbers instead, written the way most software writes them, such as v0.1. A number also tells a client how large a change is, which a date can't.

## Options considered

1. **Dates**, the way MCP names its versions. A date says when a version was written but not whether it breaks clients.
2. **MAJOR.MINOR.PATCH**, full semantic versioning. A patch number would only count wording fixes, and those never change a requirement (spec/VERSIONING.md), so a client has nothing to negotiate on it.
3. **MAJOR.MINOR**, such as 0.1.

## Decision

Option 3.

- The specification and the hub protocol share one version, `MAJOR.MINOR`. The first is 0.1, which is the draft dated 2026-10-24 under a new name with no change to its requirements.
- People see the version with a leading v, as v0.1, in titles, folder names and URLs. The wire and the data carry the bare number, so `protocolVersion`, `spec/versions.json` and the generated schema say `"0.1"`.
- Before 1.0, a minor version may change or remove behavior. From 1.0 on, a minor version only adds methods, notifications, fields and error codes, so every exchange that was valid keeps its meaning, and only a major version may break a client.
- Versions compare as numbers, major first and then minor, so 0.10 is newer than 0.9.
- Each version lives in `spec/v<version>/`, such as `spec/v0.1/`, and the website serves it at `/spec/v0.1/`. `spec/versions.json` lists every version with its status, `draft` or `final`, and names `latest`.
- `hal/initialize` negotiates the version by the rule in ADR 0015. A `protocolVersion` that isn't a version number, such as a date or `"v0.1"`, gets INVALID_PARAMS, and the reason names the versions the hub supports.
- The Device File format keeps its own version in each file's `openhal` field, and specification v0.1 defines Device File format 0.1.

This decision replaces the dated versions in ADR 0015 and keeps its negotiation rule. Error codes stay stable across versions and are never reused.

## Consequences

- The draft's folder moves from its dated name to spec/v0.1/, and the spec's changelog records the new name. The website sends the old dated pages to the matching v0.1 pages.
- The reference hub speaks 0.1 only. No client outside this repository exists yet, so no compatibility shim is kept, and a client that still sends a date gets INVALID_PARAMS.
- REST `/v1/status`, the MCP `hub_status` tool, the CLI, the Python client and the Inspector report `0.1`.
