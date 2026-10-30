# Routines

A routine is an automation that runs on the Hub without a model, such as watering a plant when its soil gets dry or at 07:00. Every write and action a routine makes goes through the Safety Kernel like any other command.

A routine is YAML or Python. YAML routines are data. Python routines are code, so only a human may enable them.

This version exposes `hal/routines/list` and `hal/routines/dryRun`. Drafting, enabling and running routines are MCP and REST only.

## YAML routines

```yaml
id: water-when-dry
description: Water for 20 s when the soil is drier than 40 %.
triggers:
  - when: "plant-waterer.soil_moisture < 40 %"
steps:
  - action: { device: plant-waterer, action: water, args: { duration: { value: 20, unit: s } } }
```

This is the routine `openhal demo --full` runs ([docs/demo/e2e.yaml](../../docs/demo/e2e.yaml)). An agent drafts it, a person enables it, and it waters once each time the soil turns dry.

A YAML routine is parsed with the same restricted loader as a Device File ([Device files](device-files.md#0-file-format)) and MUST be at most 128 KiB.

| Key | Content |
|---|---|
| `id` | A slug matching `^[a-z][a-z0-9-]{0,47}$`. It MUST match the name the routine is stored under |
| `description` | Optional, at most 500 characters |
| `triggers` | 1 to 20 triggers. Default `[{ manual: true }]` |
| `steps` | At least one step |
| `on_block` | `stop` (default) ends the run when a command is not done. `continue` goes on to the next step |
| `max_runtime` | A duration. Default 10 min. The Hub's own cap still applies |

### Triggers

| Trigger | Fires |
|---|---|
| `every: <duration>` | When at least that long has passed since the last start. At least 1 s |
| `at: "HH:MM"` | Once a day at that local time |
| `when: <expression>` | When the expression becomes true, on the change from not true to true |
| `manual: true` | Only when a human runs it |

### Steps

| Step | Shape |
|---|---|
| `write` | `{ device, channel, value }`. Numeric values MUST carry a unit |
| `action` | `{ device, action, args? }`. Numeric arguments MUST carry a unit |
| `wait` | A duration of at most 1 h |
| `log` | Text of at most 300 characters, recorded in the run |
| `if` | `{ if: <expression>, then: [steps], else: [steps] }` |

1. A routine MUST have at most 200 steps in total, counting nested ones. `if` steps nest at most 4 levels.
2. Expressions in routines use the language of [Device files](device-files.md#7-interlocks-and-expressions), but every reference MUST name its Device as `device_id.channel`. A bare word is an enum value, never a channel.
3. An `if` whose expression is unknown takes the `else` branch.

## Python routines

```python
TRIGGERS = [{"when": "plant-waterer.soil_moisture < 40 %"}]


async def run(ctx):
    await ctx.action("plant-waterer", "water", duration={"value": 20, "unit": "s"})
```

1. A Python routine MUST define `async def run(ctx)`. It MAY define `TRIGGERS` as a literal list of trigger mappings. Without it, the routine is manual.
2. `ctx` provides `read(device, channel)`, `write(device, channel, value, unit)`, `action(device, action, **args)` with numbers as `{"value": 2, "unit": "s"}`, `wait(duration)` of at most 1 h, `value(expression)` and `log(message)`.
3. Every device operation goes through `ctx`, and `ctx` goes through the Safety Kernel. A blocked command ends the run.
4. Python routines run in the Hub process as trusted code. The Hub does not sandbox them ([Security](security.md#what-is-not-guaranteed)).

## Enabling

1. A new routine, from any author, MUST start disabled.
2. Changing a routine's content MUST disable it.
3. A human MAY enable any routine. A human reads the dry-run result before enabling.
4. An agent MAY enable a routine only when the Hub setting `routines.agent_enable_low_hazard` is on (default off), the routine is YAML, every Device it touches is low hazard, and the agent's scope is at least `control_low`.
5. A routine whose Devices aren't all registered, or that failed validation, MUST NOT be enabled. Nothing may be enabled while the Hub is stopped.
6. Agents with scope `read` MUST NOT draft routines. Routines MUST NOT create routines. Only a human may delete one or run one by hand.

## Running

1. A routine runs as Principal `routine:<id>` with the scope of whoever enabled it, capped at `control_medium`, and with the SHA-256 of its canonical content. Approvals for high hazard Devices are bound to that hash.
2. YAML content is hashed after parsing, so comments don't change the hash.
3. A routine runs at most once at a time, and starts no more often than `routines.min_interval_s` (default 1 s).
4. A run is cancelled after the smaller of its `max_runtime` and the Hub's `routines.max_runtime_s` (default 1 h).
5. A routine runs unattended, so a routine's command that needs confirmation is blocked ([Safety](safety.md#confirmations)).
6. A run ends `ok`, `blocked`, `failed` or `cancelled`. Every run and every command in it is logged.
7. A stop MUST cancel running routines and disable every enabled routine. A human enables them again.

## Dry run

A dry run evaluates every command in every branch, in order, as the routine would send it. Nothing is sent to any Device.

1. A `wait` advances the simulated clock, so rate limits are evaluated as in a real run.
2. Each branch of an `if` starts from a copy of the state before it.
3. The result is `{ ok, decisions, problems }`. `ok` is `true` only when every Decision is `allowed` and there are no problems.
4. A Python routine can't be dry-run step by step. Its dry run reports that as a problem.
