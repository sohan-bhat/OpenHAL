# 0007 Routines in Python or YAML, never enabled by an agent by default

## Context

Routines are automations that run without a model (keep the temperature under 28 degC, water the plant at 7am). They must pass through the kernel like everything else. The brief asks whether an agent may enable a routine on its own when every device it touches is low hazard.

## Options considered

1. YAML only. Safe and inspectable, but too limited for real logic.
2. Python only. Flexible, but a drafted Python routine is arbitrary code.
3. Both. Declarative YAML for the common case (triggers, conditions, writes, waits), and Python routines that run in the hub using the OpenHAL library with a restricted import list.

## Decision

Option 3.

- YAML routines are data. They are validated against a schema, dry-run before enabling, and every write they produce goes through the kernel.
- Python routines run in the hub process inside a task with only the `openhal.routine` API in scope (the routine module must define `async def run(ctx)`). Every device operation goes through `ctx`, which goes through the kernel. Python routines can only be enabled by a human, because they are code.
- Agent-drafted routines of either kind start disabled. A human enables them in the CLI or dashboard after reading the dry-run result.
- An opt-in setting, `routines.agent_enable_low_hazard` (default false), lets an agent token with the `control_low` scope enable a YAML routine whose every target device is low hazard. Python routines and anything touching medium or high hazard devices always need a human.
- High hazard devices can be driven by a routine only if the device file carries a human-signed approval for that routine's content hash (spec section 9).

## Consequences

The default is conservative and matches the safety model. The opt-in exists for people automating sensors and LEDs who do not want to click approve.
