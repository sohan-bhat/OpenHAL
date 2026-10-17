# 0004 Drivers only write with a single-use grant issued by the safety kernel

## Context

Requirement 6.1.1. Every write and action from any source passes through one safety kernel, and there must be no other code path to a driver's write method. It has to be structural, not a convention.

## Options considered

1. Convention plus code review. Not structural.
2. Drivers live in a separate process and only the kernel holds the IPC channel. Strong, but costly for v0.1 and unnecessary for drivers in this repository.
3. Capability grants. The driver base class's public `write` and `action` are final and require a `Grant` object. Grants can only be created by the kernel, are bound to one device, one channel or action, one exact value in the device's own unit, carry an expiry, and are consumed on use.

## Decision

Option 3, with option 2 on the roadmap for third-party drivers.

- `Grant` is created through a private constructor guarded by a module-level secret held only by `openhal.kernel.grants`. Constructing one any other way raises.
- The kernel records every grant it issues in an in-memory table. The base class asks the kernel's verifier whether the grant is live, matches the call and has not been used, then marks it used before calling the driver's `_write` implementation.
- Driver subclasses implement `_write` and `_action`. `openhal.drivers.base` is the only caller of those. A test walks the AST of every module in the package and fails if anything else calls `_write` or `_action`.
- The conformance suite tries to write without a grant, with a used grant, with a grant for another device, channel or value, and with an expired grant. Every attempt must raise before the mock transport sees a byte.

## Consequences

- A driver in this repository can't be driven around the kernel by any OpenHAL interface.
- A deliberately malicious in-process driver could still talk to its own transport directly. The threat model lists this, the conformance suite and review are the control for bundled drivers, and out-of-process drivers are on the roadmap.
