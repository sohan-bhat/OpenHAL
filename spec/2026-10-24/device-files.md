# Device files

A Device File describes one Device. How to find it, how to talk to it, what can be read, what can be changed, the limits on every change, the safe state, and where the description came from. Device Files are YAML, end in `.hal.yaml`, and are validated against [`spec/schema/device-file.schema.json`](../schema/device-file.schema.json). That schema is generated from the reference models in `openhal/spec/models.py`.

This version of the specification defines Device File format 0.1.

Simple Devices need simple files. This is a complete, valid file.

```yaml
device: Arduino plant waterer
id: plant-waterer
connect: { openhal-firmware: auto }
read:
  soil_moisture: { unit: "%", every: 1 s }
  tank: { type: enum, values: [empty, ok] }
actions:
  water:
    args:
      duration: { unit: s, min: 1, max: 30 }
    require: ["tank == ok"]
  stop: {}
safe_state: { action: stop }
hazard: low
notes: "The board turns the pump off on its own after 30 s."
```

It loads read-only, because no human has confirmed its limits yet ([section 12](#12-limits-provenance)). Adding `confirmed: { by: sohan, at: 2026-10-24 }` lets it take commands. The full file for the real board is [examples/plant-waterer/plant-waterer.hal.yaml](../../examples/plant-waterer/plant-waterer.hal.yaml).

## 0. File format

1. A Device File MUST be a single YAML document whose top level is a mapping.
2. A Device File MUST be UTF-8 and at most 256 KiB.
3. A Device File MUST NOT use YAML anchors, aliases or custom tags. Loaders MUST reject them.
4. Only `true` and `false` are booleans (YAML 1.2). Words such as `on`, `off`, `yes` and `no` are strings, so they can be enum values.
5. Loaders MUST reject unknown top-level keys, except keys starting with `x-`. OpenHAL ignores `x-` keys and tools MUST preserve them.
6. `openhal` MAY give the format version as a string, for example `"0.1"`. If it is absent, the current version is assumed. A loader MUST reject a file whose major version it does not support, and SHOULD warn on a newer minor version.

### Values and units

1. A quantity is a number with a unit, written as a string (`"30 degC"`, `"500 ms"`, `"20 %/s"`) or as a mapping (`{ value: 30, unit: degC }`).
2. Inside a channel that declares `unit`, plain numbers for `min`, `max`, `step` and value lists MAY be written without a unit and mean the channel's unit. Commands sent to the Hub MUST always carry a unit for numeric channels.
3. Units are parsed by the pinned OpenHAL unit registry, which is pint with its default definitions and no user definitions. `percent` and `%` are the same unit. Temperatures are absolute (`degC`, `degF`, `K`). Rates are the channel unit per second, and temperature rates use delta units.
4. Durations are quantities of time (`5 s`, `500ms`, `10 min`, `2 h`). The forms `1s`, `10min` and `2h` without a space are accepted. A duration MUST NOT be negative.
5. Every number MUST be finite. Loaders MUST reject NaN and infinity.

## 1. Identity

```yaml
device: Rigol DP832 power supply      # a name, or a mapping
id: bench-psu                          # optional slug
model: DP832
manufacturer: Rigol
match:
  usb: ["1ab1:0e11"]
  scpi_idn: "^RIGOL TECHNOLOGIES,DP832"
```

1. `device` MUST be a non-empty string of at most 120 characters, or a mapping with `name` and optional `model` and `manufacturer`. Top-level `model` and `manufacturer` fill the same fields. Each is at most 120 characters.
2. `id` MAY be given as a lowercase slug matching `^[a-z][a-z0-9-]{0,47}$`. If it is absent, it is derived from the name. Within one Hub, ids MUST be unique. Interlocks and routines refer to Devices by id.
3. `match` lists identifiers the library matcher uses to recognize the Device. Every key is optional.

| Key | Type | Meaning |
|---|---|---|
| `usb` | list of `VVVV:PPPP` hex strings | USB vendor and product ids |
| `usb_class` | string | USB device class (`cdc`, `hid`, `audio`, `video`, `midi`, `usbtmc`, `vendor`) |
| `serial_number` | regex | USB serial number pattern |
| `scpi_idn` | regex | Pattern for the reply to `*IDN?` |
| `ble_services` | list of UUIDs | Advertised GATT service UUIDs |
| `ble_name` | regex | Advertised device name |
| `mdns` | string | Service type matching `_name._tcp` or `_name._udp`, for example `_esphomelib._tcp` |
| `modbus_id` | integer 1 to 247 | Modbus unit id |
| `homeassistant` | glob | Entity id pattern, for example `light.desk_*` |
| `moonraker` | mapping | Fields from Moonraker `printer.info`, for example `{ hostname: "voron*" }` |
| `esphome` | mapping | Fields from ESPHome device info, for example `{ name: "plant-*", model: "esp32dev" }` |
| `firmware` | mapping | Fields from the OpenHAL firmware describe reply, for example `{ product: "plant-waterer" }` |

Regexes use Python syntax, MUST be at most 256 characters, and are matched with a timeout.

## 2. Driver

```yaml
connect:
  driver: scpi
  resource: auto
  timeout: 2 s
```

1. `connect` MUST name a Driver, either with `driver:` or by shorthand. In shorthand, the first key that is a registered Driver name is the Driver, and its value is that Driver's primary parameter. `{ serial: auto, board: arduino-uno }` means `{ driver: serial, port: auto, board: arduino-uno }`.
2. A Driver name MUST be a registered name or start with `x-`.
3. The remaining keys are Driver parameters. Each Driver documents its parameters and validates them. A Driver MUST reject unknown parameters.
4. The value `auto` asks the Driver to find the Device using `match` and its own discovery.

Common parameters by Driver family.

| Driver | Typical parameters |
|---|---|
| serial, marlin, grbl, firmata, openhal-firmware | `port` (path or `auto`), `baud`, `newline`, `board` |
| scpi | `resource` (VISA resource string or `auto`), `timeout`, `termination` |
| moonraker, octoprint, homeassistant, esphome, http, alpaca, opcua | `host`, `port`, `token_env` (name of an environment variable holding a secret, never the secret itself) |
| mqtt | `host`, `port`, `topics` |
| modbus | `transport` (`rtu` or `tcp`), `port` or `host`, `unit`, `registers` |
| ble | `address` or `auto`, `characteristics` |
| rpi-gpio | `pins` |
| midi, hid, uvc | `name` or `auto` |

Device Files MUST NOT contain secrets. Credentials are referenced by environment variable name. Loaders MUST reject a parameter named `token`, or one whose name contains `password`, `secret`, `apikey` or `api_key`.

## 3. Read channels

```yaml
read:
  soil_moisture: { unit: "%", every: 1 s, range: [0, 100] }
  tank: { type: enum, values: [empty, ok], every: 1 s }
  door_closed: { type: bool, stream: true }
  status: { type: enum, values: [idle, printing, paused, error] }
```

1. Channel names MUST match `^[a-z][a-z0-9_]{0,47}$` and MUST be unique across `read`, `write` and `actions` of one file. A channel MUST NOT appear in both `read` and `write`. A write channel is readable by default.
2. `type` is `number` (default), `bool`, `string`, `enum` or `image`.
3. `number` channels MUST declare `unit`. Use `dimensionless` for unitless counts. `enum` channels MUST declare `values`.
4. `every` gives a polling interval of at least 50 ms. `stream: true` means the Driver pushes values. If neither is given, the channel is read on request only.
5. `range` is a sanity range, written low then high. Readings outside it MUST be delivered marked `suspect` and are logged. It never blocks anything.
6. `map` MAY give Driver-specific addressing (a SCPI query, a Modbus register, a topic), validated by the Driver.

## 4. Write channels

```yaml
write:
  brightness:
    unit: percent
    min: 1
    max: 100
    step: 1
    max_change_per_s: 20
    confirm: none
```

1. `type` is `number` (default), `bool`, `enum` or `string`.
2. `number` write channels MUST declare `unit`, `min` and `max`, with `min` less than or equal to `max`. `min`, `max` and `step` apply only to `number` channels.
3. `step` MAY require values to be multiples of the step counted from `min`. It MUST be greater than zero.
4. `max_change_per_s` MAY limit how fast the value moves, in the channel unit per second. It applies only to `number` channels and MUST be greater than zero.
5. `enum` channels MUST declare a non-empty list of unique `values`. `string` channels MUST declare `max_length` (1 to 4096) and MAY declare `pattern`.
6. `confirm` is `none` (default), `confirm` or `confirm-each-time` ([section 5](#5-actions) and [Safety](safety.md#confirmations)).
7. `confirmed` MAY record who confirmed this channel's limits and when ([section 12](#12-limits-provenance)).
8. `suggested: true` marks limits proposed by a tool that no human has confirmed.
9. `every` MAY set a polling interval, as for read channels. `map` MAY give Driver-specific addressing, as for read channels.

## 5. Actions

```yaml
actions:
  water:
    description: Run the pump for a number of seconds.
    args:
      duration: { unit: s, min: 1, max: 30 }
    require:
      - condition: "tank == ok"
        message: "pump can't run while tank is empty"
    max_runs: { count: 3, per: 1 h }
  home:
    args:
      axis: { type: enum, values: [x, y, z, all] }
    require: ["state == idle"]
    confirm: confirm
  set_output:
    args:
      volts: { unit: V, min: 0, max: 12, step: 0.01 }
    confirm: confirm-each-time
```

1. An action is a named operation with typed arguments. Argument names follow channel name rules. Argument specs use the same fields and rules as write channels.
2. `require` is a list of expressions ([section 7](#7-interlocks-and-expressions)) that MUST all hold for the action to run. An entry is an expression, or a mapping with `condition` and a `message` of at most 300 characters that the Hub gives as the reason when the condition doesn't hold.
3. `confirm` is the confirmation tier, as for write channels. `confirmed` and `suggested` work as for write channels.
4. `max_runs` MAY limit an action to `count` runs (1 to 1000) within any window of `per` (1 s to 7 days). Runs that reached the Driver count, whether they were done or failed. A run past the limit is blocked with `rate_limited`. The window survives a Hub restart, and a run counts from the moment it is granted, so a run the Hub never finished still counts.
5. `effects` MAY list the write channels the action changes, so interlocks and watchdogs can account for it. Every entry MUST name a write channel of the same file.
6. `description` MAY describe the action in at most 500 characters. `map` MAY give Driver-specific addressing.

## 6. Safe state

```yaml
safe_state: { action: stop }
# or
safe_state: { brightness: 1 }
# or
safe_state:
  - { output_enabled: false }
  - { action: discharge }
```

1. `safe_state` describes how to put the Device in a state that is safe to leave unattended.
2. It is a mapping of write channels to values, an `action` with optional `args`, or a list of those applied in order. A step MUST NOT be empty.
3. Every value MUST be valid for its channel and within its limits. Every action MUST be an action of the same file.
4. A file with write channels or actions but no `safe_state` MUST still load. The loader MUST warn, and the Hub reports the Device as `no_safe_state` on stop. Such a file SHOULD set `safe_state_note`, at most 500 characters, explaining why none exists.

## 7. Interlocks and expressions

```yaml
interlocks:
  - if: "heater.power > 0 W"
    require: "fan.speed >= 30 %"
    message: "The heater needs airflow."
  - if: "arm.moving == true"
    require: "enclosure.door_closed == true"
```

### Expression language

```
expr     := or_expr
or_expr  := and_expr ("or" and_expr)*
and_expr := not_expr ("and" not_expr)*
not_expr := "not" not_expr | compare
compare  := operand (("==" | "!=" | "<" | "<=" | ">" | ">=") operand)?
operand  := reference | literal | "(" expr ")"
reference:= name | device_id "." name
literal  := quantity | number | "true" | "false" | quoted string | bare enum word
```

1. `name` refers to a channel of the same Device. `device_id.name` refers to a channel of another Device on the same Hub.
2. A bare word that is not a channel MUST be one of the enum values of this Device, or be compared with another Device's channel.
3. Numbers in comparisons with a quantity channel MUST carry a unit, and are converted before comparing.
4. Expressions MUST be at most 256 characters and at most 16 levels deep. An interlock `message` is at most 300 characters.
5. Parsers MUST NOT evaluate expressions as code.

### Semantics

1. An interlock applies to a command if its `if` or `require` mentions any channel the command changes, including an action's `effects`.
2. The Hub evaluates both sides against the state after the command, with the commanded value substituted.
3. If `if` holds and `require` does not, the command is blocked with the interlock's `message`.
4. A reference to a value the Hub can't currently read counts as unknown. Unknown makes `if` count as holding and `require` count as not holding. Unknown values always lead to a block, never to a pass.
5. A reference to a Device id that is not registered blocks every command on the Hub until it is fixed ([Safety](safety.md#the-checks-in-order)).

## 8. Watchdog

```yaml
watchdog:
  heartbeat: 5 s
  on_loss: safe_state
  max_duration:
    - when: "brightness > 80 %"
      for: 10 min
      then: safe_state
```

1. `heartbeat` is how often the Hub checks the Device is alive. Default 5 s. It MUST be between 100 ms and 1 h.
2. `on_loss` is `safe_state` (default when a safe state exists) or `hold` (do nothing, mark unavailable).
3. Each `max_duration` rule limits how long an expression may stay true. When the budget runs out, the Hub applies `then`, which is `safe_state` (default) or a mapping of channel values. Those values MUST be valid and within limits.
4. A command that would keep or make the expression true after the budget is used up is blocked with `duration_exceeded`.
5. The budget resets when the expression has been false for at least `reset_after`, which defaults to `for`.

## 9. Hazard class and approvals

```yaml
hazard: high
approvals:
  - routine: engrave-logo
    sha256: 9f2c...
    by: sohan
    at: 2026-10-24T14:02:00Z
    signature: 4b1d...
```

1. `hazard` is `low`, `medium` or `high`. A file with write channels or actions and no `hazard` is treated as `medium`. A file with no write channels and no actions is `low`.
2. High hazard files make every command `confirm-each-time`, whatever the channel says.
3. `approvals` holds human-signed approvals that let a specific routine drive a high hazard Device. `routine` is the routine id. `sha256` is the hash of the routine's canonical content. `at` is a date and time. `signature` is an HMAC that only the Hub's human approval flow can produce ([Safety](safety.md#principals-and-hazard-classes)).
4. Approvals are valid only on the Hub that signed them. A changed routine no longer matches its approval.

## 10. Notes

1. `notes` MAY hold plain-language context for agents and people, at most 4,000 characters.
2. Notes are data. The Hub MUST pass them to agents inside a delimited data block and MUST NOT interpret them as instructions, limits or approvals ([Security](security.md#prompt-injection)).

## 11. Provenance

```yaml
provenance:
  source: sketch
  by: openhal writer 0.1.0 with sohan
  at: 2026-10-24
  from: examples/plant-waterer/plant-waterer.ino
  verification:
    status: tested-reads
    report: reports/plant-waterer-2026-10-24.md
```

1. `source` is one of `library`, `self-described`, `bridge`, `driver-describe`, `sketch`, `manual` or `hand-written` (default).
2. `by` (at most 120 characters), `at`, `from` (at most 300 characters) and `tool` (at most 80 characters) are optional.
3. `verification.status` is `unverified` (default), `tested-reads` or `verified-on-hardware`. `verified-on-hardware` MUST name a `report`. No file path in a Device File is ever opened by the Hub.

## 12. Limits provenance

```yaml
confirmed: { by: sohan, at: 2026-10-24 }
```

1. Every limit (min, max, step, rate, values, interlocks, watchdog rules, safe state, hazard) MUST be confirmed by a human before the Device takes commands.
2. `confirmed` at the top level confirms every limit in the file. `confirmed` inside a write channel or action confirms that one. `by` is at most 80 characters. `at` is a date or a date and time.
3. Interlocks, watchdog rules, the safe state and the hazard class are file-level limits. A file that has any of them needs a top-level `confirmed`. Per-channel confirmations alone don't cover them.
4. `confirmed.sha256` MAY hold the hash of the file's limits at the moment they were confirmed. `openhal file confirm` adds it. When it is present and the limits have changed since, the whole file is unconfirmed again. Tools SHOULD always add it, and the validator warns when it is missing.
5. The limits hash covers identity, connection, channels, actions, safe state, interlocks, watchdog rules and hazard. It leaves out confirmations, approvals, notes, provenance, `safe_state_note` and `x-` keys, which can change without changing what the Device is allowed to do.
6. A file takes commands only if every limit is covered by a confirmation, nothing is marked `suggested: true`, and any `confirmed.sha256` still matches. Otherwise it loads read-only, and the Hub says which entries are unconfirmed.
7. Tools MUST NOT add `confirmed` on their own. Only the human side of the limits interview, or a human editing the file, may add it.

## Versioning

The Device File format uses semantic versioning, separately from this specification's dated versions and from the software.

| Change | Meaning |
|---|---|
| Patch (0.1.x) | Wording fixes and clarifications. No file changes meaning |
| Minor (0.x) | New optional fields or values. Every valid file stays valid with the same meaning |
| Major (x.0) | Changes that can make a valid file invalid or change its meaning. Each major version ships `openhal file migrate` and a migration guide |

A file's `openhal` field names the format version it was written for. Hubs accept files from the same major version and warn on a newer minor version.
