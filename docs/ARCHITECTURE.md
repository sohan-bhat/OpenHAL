# Architecture

One hub process owns every device and checks every command in one deterministic safety kernel. Thin clients, including the MCP server an agent connects to, send requests to the hub. The decisions are in docs/adr/, the safety rules in docs/SAFETY.md and the device file format in spec/SPEC.md.

## Components

```mermaid
flowchart LR
  subgraph Clients
    MCP["openhal mcp<br/>(stdio MCP server)"]
    CLI["openhal CLI"]
    LIB["Python library<br/>openhal.connect()"]
    DASH["Dashboard<br/>(Svelte, served by hub)"]
  end

  subgraph Hub["openhal start (one process)"]
    API["Local API<br/>FastAPI + WebSocket<br/>127.0.0.1:7420"]
    AUTH["Tokens and principals"]
    REG["Device registry"]
    KERNEL["Safety kernel<br/>(deterministic, no LLM)"]
    RT["Routine engine"]
    WD["Watchdogs"]
    CQ["Confirmation queue"]
    AUDIT["Audit log<br/>(hash chain)"]
    DISC["Discovery + library matcher"]
    WRITER["Driver writer"]
    DRV["Drivers<br/>(protocol drivers and bridges)"]
  end

  HW[("Hardware<br/>and bridged systems")]

  MCP --> API
  CLI --> API
  LIB --> API
  DASH --> API
  API --> AUTH --> KERNEL
  API --> REG
  API --> CQ
  API --> WRITER
  RT --> KERNEL
  WD --> KERNEL
  WRITER --> DISC
  DISC --> DRV
  KERNEL -->|single-use grant| DRV
  KERNEL --> AUDIT
  CQ --> KERNEL
  DRV --> HW
```

| Component | Module | Role |
|---|---|---|
| Brand | `openhal/_brand.py` | Every public name, per ADR 0002 |
| Spec models | `openhal/spec/` | Models for device files, routines and commands, units, the expression language, JSON Schema export |
| Safety kernel | `openhal/kernel/` | Checks, grants, rate limit state, interlocks, watchdog budgets, stop lock, confirmations |
| Audit log | `openhal/audit/` | Append-only SQLite table with a hash chain, per ADR 0010 |
| Hub | `openhal/hub/` | Daemon, registry, config, tokens, storage, local API, discovery, library matcher, dashboard files |
| Drivers | `openhal/drivers/` | Base class, registry, mock framework, one package per protocol or bridge |
| Routines | `openhal/routines/` | YAML and Python routines, triggers, scheduler |
| MCP server | `openhal/mcp/` | Tools and prompts that forward to the hub |
| CLI | `openhal/cli/` | Typer application |
| Client | `openhal/client/` | Sync and async API client behind the CLI, MCP server and library |
| Driver writer | `openhal/writer/` | Detection, sketch parsing, manual extraction, interview, staged test plans |
| Conformance | `openhal/conformance/` | The battery every driver must pass |
| Dashboard | `dashboard/` | Svelte 5 app, built into `openhal/hub/static/` |
| Website | `website/` | Astro site built from the repository |
| Firmware | `firmware/arduino/OpenHAL/` | Arduino library that gives a maker's device a self-description |
| Library | `library/` | Shared CC0 device files |

## The life of a command

Every command takes this path, shown for an agent's `pause` of the printer. No other path reaches a driver's `_write` or `_action`.

```mermaid
sequenceDiagram
  participant A as Agent (MCP client)
  participant M as openhal mcp
  participant H as Hub API
  participant K as Safety kernel
  participant Q as Confirmation queue
  participant D as Driver
  participant L as Audit log
  A->>M: action printer.pause
  M->>H: POST /v1/action (agent token)
  H->>K: evaluate(command, principal)
  K->>K: parse unit, convert to device unit, finite check
  K->>K: device state (connected, not stopped, limits confirmed)
  K->>K: min, max, step, enum
  K->>K: rate and run limits, interlocks and requirements, watchdog budget
  K->>K: hazard tier, principal scope, confirmation tier
  alt blocked
    K->>L: block entry with reason
    K-->>H: Blocked(reason, limit)
    H-->>M: 200 {status: blocked, reason}
  else needs confirmation
    K->>Q: enqueue(request, dry-run result, expiry)
    K->>L: pending entry
    K-->>H: Pending(id)
  else allowed
    K->>K: issue Grant(device, target, value, expiry)
    K->>D: action(name, args, grant)
    D->>K: verify and consume grant
    D->>D: _action(name, args)
    D-->>K: result
    K->>L: action entry (before, after, source)
    K-->>H: Done(result)
  end
```

A person approves a queued request with `POST /v1/confirmations/{id}/approve` and a human token. The kernel checks the request again against the current state, then follows the allowed branch.

## Device discovery

```mermaid
flowchart TD
  S[openhal discover] --> U[USB enumeration<br/>VID:PID, class, serial number]
  S --> N[mDNS / Zeroconf browse]
  S --> V[VISA resource list]
  S --> B[BLE scan]
  S --> E[Ecosystem APIs<br/>Moonraker, OctoPrint,<br/>Home Assistant, ESPHome]
  S --> P[Platform checks<br/>Raspberry Pi GPIO and camera]
  U --> ID[identify with read-only commands only<br/>*IDN?, firmware describe, M115]
  N --> ID
  V --> ID
  B --> ID
  E --> ID
  P --> ID
  ID --> MATCH{Library matcher}
  MATCH -->|match| OFFER[Offer library file,<br/>high risk entries wait for confirmed limits]
  MATCH -->|protocol known| DESC[driver.describe&#40;&#41; builds a draft file]
  MATCH -->|unknown| UNK[List as unknown device,<br/>offer the driver writer]
```

Serial probing sends only identify commands documented as read-only for the protocol, with a short timeout, and never opens a port another process holds.

## Driver writer

```mermaid
flowchart TD
  START[Unknown device] --> LIB{1. Library match?}
  LIB -->|yes| DONE
  LIB -->|no| PROT{2. Can a protocol driver connect?}
  PROT -->|yes| DESCRIBE[3. Self-description<br/>describe&#40;&#41;, firmware JSON,<br/>SCPI, Moonraker objects, GATT, OPC UA browse]
  PROT -->|no| CODE{4. Sketch available?}
  CODE -->|yes| SKETCH[Parse sketch<br/>commands, pins, ranges, units]
  CODE -->|no| MANUAL{5. Manual available?}
  MANUAL -->|yes| MAN[Extract commands,<br/>all marked unconfirmed]
  MANUAL -->|no| PROBE[6. Read-only probing<br/>known read commands only]
  DESCRIBE --> DRAFT[Draft device file<br/>every limit marked suggested]
  SKETCH --> DRAFT
  MAN --> DRAFT
  PROBE --> DRAFT
  DRAFT --> INT[7. Limits interview<br/>human answers every limit]
  INT --> PLAN[8. Staged test plan<br/>smallest safe value, approval per step]
  PLAN --> SCAF{9. Needs new code?}
  SCAF -->|yes| NEW[openhal driver new<br/>experimental until conformance and hardware test]
  SCAF -->|no| DONE[10. Device file with provenance<br/>plus library submission bundle]
  NEW --> DONE
```

The user's own model takes part through MCP, per ADR 0006, and the hub runs every deterministic step. Nothing a model proposes can confirm a limit.

## Routine execution

```mermaid
sequenceDiagram
  participant T as Trigger (schedule, threshold, event, manual)
  participant R as Routine engine
  participant K as Safety kernel
  participant D as Driver
  T->>R: fire(routine)
  R->>R: routine enabled? approvals valid for high hazard?
  R->>K: each read and command as principal routine:<name>
  K->>K: same checks as any client
  alt blocked
    K-->>R: Blocked(reason)
    R->>R: stop the run, record failure, apply routine on_block policy
  else allowed
    K->>D: command with grant
  end
  R->>R: record run history
```

Routines run with no model as `routine:<name>`, with the scope of the human who enabled the routine, capped at `control_medium`.

## Bridges

```mermaid
sequenceDiagram
  participant K as Safety kernel
  participant B as Bridge driver (Home Assistant, ESPHome, ROS 2)
  participant S as Bridged system
  K->>B: write(entity, value, grant)
  B->>S: service call / API request
  S-->>B: new state
  B-->>K: result
  Note over K,B: The device file governs limits even when the bridged system has its own. Only user-selected entities are exposed.
```

## Stop

```mermaid
flowchart TD
  STOP["stop_all from CLI, MCP, dashboard,<br/>library call or Pi GPIO button"] --> LOCK[Kernel sets the global lock first]
  LOCK --> CANCEL[Cancel pending confirmations<br/>pause every routine]
  CANCEL --> SAFE[Apply each device's safe state<br/>with kernel-internal grants]
  SAFE --> REPORT[Report per device: safe, failed, no safe state defined]
  REPORT --> LOCKED[Commands blocked until a human unlocks]
  LOCKED --> UNLOCK[openhal unlock or dashboard unlock<br/>human token, typed phrase]
```

The lock comes before any safe-state step, so a racing command can't slip in. The kernel issues safe-state steps to itself, and those steps still pass the driver's grant check.

## Contracts frozen after M1

- `spec/schema/device-file.schema.json` and the Pydantic models in `openhal/spec/models.py`.
- The driver interface in `openhal/drivers/base.py`, with `discover`, `identify`, `connect`, `describe`, `read`, `write`, `action`, `safe_state`, `health`, `close`.
- The kernel API in `openhal/kernel/__init__.py`, with `Kernel.evaluate`, `Kernel.execute`, `Kernel.dry_run`, `Kernel.stop_all`, `Kernel.unlock`, `Kernel.confirm`, `Kernel.reject`.
- The local API, versioned under `/v1`, described by FastAPI's OpenAPI document checked in at `docs/api/openapi.json`.
- The MCP tool list and input schemas in `openhal/mcp/tools.py`.

After the freeze, only the orchestrator changes these, and each change gets an ADR.
