# Glossary

The normative definitions are in [spec/v0.1/index.md](v0.1/index.md#terminology), and defined terms are capitalized wherever they appear.

| Term | Definition |
|---|---|
| Hub | The one process that owns every Device, its Driver, the Safety Kernel, the confirmation queue and the audit log |
| Client | A program that connects to a Hub and sends requests |
| Device | One piece of hardware, or one set of entities in a bridged system, described by one Device File |
| Device File | A YAML document ending in `.hal.yaml` that describes one Device, its channels, actions, limits, safe state and provenance |
| Driver | Code that communicates with Devices over one protocol and changes hardware only when it consumes a Grant |
| Safety Kernel | The deterministic part of a Hub that evaluates every command and issues Grants for the ones that pass |
| Grant | A single-use permission for exactly one operation, bound to one Device, one target and one value, with an expiry |
| Principal | The identity behind a request, of kind `human`, `agent`, `routine` or `system`, with a scope |
| Conformance Level | `core`, `control` or `full`, naming what a Hub implements or a Driver supports |
| Confirmation Request | A command the Hub holds in its queue until a human Principal approves or rejects the command |
