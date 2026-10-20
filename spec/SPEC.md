# OpenHAL device file specification, version 0.1

Status. Draft. This document is normative. The key words MUST, MUST NOT, SHOULD, SHOULD NOT and MAY are used as in RFC 2119.

A device file describes one device: how to find it, how to talk to it, what can be read, what can be changed, the limits on every change, the safe state, and where the description came from. Device files are YAML, end in `.hal.yaml`, and are validated against `spec/schema/device-file.schema.json`, which is generated from the reference models in `openhal/spec/models.py`.

Simple devices need simple files. This is a complete, valid file.

```yaml
device: Desk fan controller
connect: { serial: auto, board: arduino-uno }
read:
  temperature: { unit: degC, every: 1s }
write:
  fan_speed: { unit: percent, min: 0, max: 100, max_change_per_s: 20 }
safe_state: { fan_speed: 0 }
notes: "Fan is next to the plant. Never run above 80 for more than 10 minutes."
```

It loads read-only, because no human has confirmed its limits yet (section 12). Adding `confirmed: { by: sohan, at: 2026-10-24 }` makes it writable.

## 0. File format

- A device file MUST be a single YAML document whose top level is a mapping.
- Files MUST be UTF-8, at most 256 KiB.
- YAML anchors and aliases MUST NOT be used. Loaders MUST reject them, along with custom tags.
- Only `true` and `false` are booleans (YAML 1.2). Words such as `on`, `off`, `yes` and `no` are strings, so they can be enum values.
- Unknown top-level keys MUST be rejected, except keys starting with `x-`, which are ignored by OpenHAL and preserved by tools.
- `openhal` MAY give the spec version as a string, for example `"0.1"`. If absent, the current version is assumed. A loader MUST reject a file whose major version it does not support, and SHOULD warn on a newer minor version.

### Values and units

- A quantity is a number with a unit, written as a string (`"30 degC"`, `"500 ms"`, `"20 %/s"`) or as a mapping (`{ value: 30, unit: degC }`).
- Inside a channel that declares `unit`, plain numbers for `min`, `max`, `step` and value lists MAY be written without a unit and mean the channel's unit. Commands sent to the hub MUST always carry a unit for numeric channels.
- Units are parsed by the pinned OpenHAL unit registry (pint with its default definitions). `percent` and `%` are the same unit. Temperatures are absolute (`degC`, `degF`, `K`). Rates are the channel unit per second.
- Durations are quantities of time (`5 s`, `500ms`, `10 min`, `2 h`). The forms `1s`, `10min` and `2h` without a space are accepted.
- Every number MUST be finite. NaN and infinity MUST be rejected.

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

- `device` MUST be a non-empty string of at most 120 characters, or a mapping with `name` and optional `model` and `manufacturer`.
- `id` MAY be given as a lowercase slug matching `^[a-z][a-z0-9-]{0,47}$`. If absent, it is derived from the name. Within one hub, ids MUST be unique. Interlocks and routines refer to devices by id.
- `match` lists identifiers the library matcher uses to recognize the device. Every key is optional.

| Key | Type | Meaning |
|---|---|---|
| `usb` | list of `VVVV:PPPP` hex strings | USB vendor and product ids |
| `usb_class` | string | USB device class (`cdc`, `hid`, `audio`, `video`, `midi`, `usbtmc`) |
| `serial_number` | regex | USB serial number pattern |
| `scpi_idn` | regex | Pattern for the reply to `*IDN?` |
| `ble_services` | list of UUIDs | Advertised GATT service UUIDs |
| `ble_name` | regex | Advertised device name |
| `mdns` | string | Service type, for example `_esphomelib._tcp` |
| `modbus_id` | integer 1 to 247 | Modbus unit id |
| `homeassistant` | glob | Entity id pattern, for example `light.desk_*` |
| `moonraker` | mapping | Fields from Moonraker `printer.info`, for example `{ hostname: "voron*" }` |
| `esphome` | mapping | Fields from ESPHome device info, for example `{ name: "fan-*", model: "esp32dev" }` |
| `firmware` | mapping | Fields from the OpenHAL firmware describe reply, for example `{ product: "desk-fan" }` |

Regexes use Python syntax, are limited to 256 characters, and are matched with a timeout.

## 2. Driver

```yaml
connect:
  driver: scpi
  resource: auto
  timeout: 2 s
```

- `connect` MUST name a driver, either with `driver:` or by shorthand. In shorthand, the first key that is a registered driver name is the driver, and its value is that driver's primary parameter. `{ serial: auto, board: arduino-uno }` means `{ driver: serial, port: auto, board: arduino-uno }`.
- The remaining keys are driver parameters. Each driver documents its parameters and validates them. Unknown parameters MUST be rejected by the driver.
- The value `auto` asks the driver to find the device using `match` and its own discovery.
- Common parameters by driver family.

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

Device files MUST NOT contain secrets. Credentials are referenced by environment variable name.

## 3. Read channels

```yaml
read:
  temperature: { unit: degC, every: 1 s, range: [-20, 80] }
  door_closed: { type: bool, stream: true }
  status: { type: enum, values: [idle, printing, paused, error] }
```

- Channel names MUST match `^[a-z][a-z0-9_]{0,47}$` and be unique across `read`, `write` and `actions` of one file. A channel that appears in both `read` and `write` is not allowed. A write channel is readable by default.
- `type` is `number` (default), `bool`, `string`, `enum` or `image`.
- `number` channels MUST declare `unit` (use `dimensionless` for unitless counts).
- `every` gives a polling interval of at least 50 ms. `stream: true` means the driver pushes values. If neither is given, the channel is read on request only.
- `range` is a sanity range. Readings outside it are delivered marked `suspect` and logged. It never blocks anything.
- `map` MAY give driver-specific addressing (a SCPI query, a Modbus register, a topic), validated by the driver.

## 4. Write channels

```yaml
write:
  fan_speed:
    unit: percent
    min: 0
    max: 100
    step: 1
    max_change_per_s: 20
    confirm: none
```

- `type` is `number` (default), `bool`, `enum` or `string`.
- `number` write channels MUST declare `unit`, `min` and `max`, with `min` less than or equal to `max`.
- `step` MAY require values to be multiples of the step counted from `min`.
- `max_change_per_s` MAY limit how fast the value moves, in the channel unit per second.
- `enum` channels MUST declare `values`. `string` channels MUST declare `max_length` and MAY declare `pattern`.
- `confirm` is `none` (default), `confirm` or `confirm-each-time` (section 5 and docs/SAFETY.md).
- `confirmed` MAY record who confirmed this channel's limits and when (section 12).
- `suggested: true` marks limits proposed by a tool that no human has confirmed.
- `map` MAY give driver-specific addressing, as for read channels.

## 5. Actions

```yaml
actions:
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

- An action is a named operation with typed arguments. Argument specs use the same fields as write channels.
- `require` is a list of expressions (section 7) that MUST all hold for the action to run.
- `confirm` is the confirmation tier, as for write channels.
- `effects` MAY list the write channels the action changes, so interlocks and watchdogs can account for it.

## 6. Safe state

```yaml
safe_state: { fan_speed: 0 }
# or
safe_state: { action: park }
# or
safe_state:
  - { output_enabled: false }
  - { action: discharge }
```

- `safe_state` describes how to put the device in a state that is safe to leave unattended.
- It is a mapping of write channels to values, an `action` with optional `args`, or a list of those applied in order.
- A file with write channels or actions but no `safe_state` MUST still load. The loader MUST warn, and the hub reports the device as `no safe state` on stop. Such a file SHOULD set `safe_state_note` explaining why none exists.

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

- `name` refers to a channel of the same device. `device_id.name` refers to a channel of another device on the same hub.
- Numbers in comparisons with a quantity channel MUST carry a unit, and are converted before comparing.
- Expressions MUST be at most 256 characters and at most 16 levels deep.
- Parsers MUST NOT evaluate expressions as code.

### Semantics

- An interlock applies to a command if its `if` or `require` mentions any channel the command changes (including an action's `effects`).
- The hub evaluates both sides against the state after the command, with the commanded value substituted.
- If `if` holds and `require` does not, the command is blocked with the interlock's `message`.
- A reference to a value the hub can't currently read counts as unknown. Unknown makes `if` count as holding and `require` count as not holding. Unknown values always lead to a block, never to a pass.

## 8. Watchdog

```yaml
watchdog:
  heartbeat: 5 s
  on_loss: safe_state
  max_duration:
    - when: "fan_speed > 80 %"
      for: 10 min
      then: safe_state
```

- `heartbeat` is how often the hub checks the device is alive. Default 5 s.
- `on_loss` is `safe_state` (default when a safe state exists) or `hold` (do nothing, mark unavailable).
- Each `max_duration` rule limits how long an expression may stay true. When the budget runs out, the hub applies `then` (`safe_state`, or a mapping of channel values). A command that would keep or make the expression true after the budget is used up is blocked with `duration_exceeded`. The budget resets when the expression has been false for at least `reset_after` (default equal to `for`).

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

- `hazard` is `low`, `medium` or `high`. A file with write channels or actions and no `hazard` is treated as `medium`. A file with no writes is `low`.
- High hazard files make every write and action `confirm-each-time`, whatever the channel says.
- `approvals` holds human-signed approvals that let a specific routine drive a high hazard device. `sha256` is the hash of the routine's canonical content. `signature` is an HMAC that only the hub's human approval flow can produce (docs/SAFETY.md). Approvals are valid only on the hub that signed them. A changed routine no longer matches its approval.

## 10. Notes

- `notes` MAY hold plain-language context for agents and people, at most 4,000 characters.
- Notes are data. The hub MUST pass them to agents inside a delimited data block and MUST NOT interpret them as instructions, limits or approvals.

## 11. Provenance

```yaml
provenance:
  source: sketch
  by: openhal writer 0.1.0 with sohan
  at: 2026-10-24
  from: ./fan/fan.ino
  verification:
    status: tested-reads
    report: reports/desk-fan-2026-10-24.md
```

- `source` is one of `library`, `self-described`, `bridge`, `driver-describe`, `sketch`, `manual`, `hand-written`.
- `verification.status` is `unverified` (default), `tested-reads` or `verified-on-hardware`. `verified-on-hardware` MUST name a `report`.

## 12. Limits provenance

```yaml
confirmed: { by: sohan, at: 2026-10-24 }
```

- Every limit (min, max, step, rate, values, interlocks, watchdog rules, safe state, hazard) MUST be confirmed by a human before the device can be written.
- `confirmed` at the top level confirms every limit in the file. `confirmed` inside a write channel or action confirms that one.
- Interlocks, watchdog rules, the safe state and the hazard class are file-level limits. A file that has any of them needs a top-level `confirmed`. Per-channel confirmations alone don't cover them.
- `confirmed.sha256` MAY hold the hash of the file's limits at the moment they were confirmed (`openhal file confirm` writes it). When it is present and the limits have changed since, the whole file is unconfirmed again. Tools SHOULD always write it, and the validator warns when it is missing.
- A file is writable only if every limit is covered by a confirmation, nothing is marked `suggested: true`, and any `confirmed.sha256` still matches. Otherwise it loads read-only, and the hub says which entries are unconfirmed.
- Tools MUST NOT add `confirmed` on their own. Only the human side of the limits interview, or a human editing the file, may add it.

## Versioning

The spec uses semantic versioning. Patch versions fix wording. Minor versions add optional fields, and older files stay valid. Major versions may break files, and the hub ships a migration command. See spec/CHANGELOG.md.
