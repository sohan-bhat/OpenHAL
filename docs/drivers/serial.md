# serial driver

The `serial` driver talks to any device with a line-based text protocol over a serial port. The driver has no command set of its own. Every query, reply pattern and command template comes from the device file, so one driver covers Arduino sketches, RS-232 instruments and sensor modules alike.

| | |
|---|---|
| Driver name | `serial` |
| Library | pyserial 3.5 (BSD-3-Clause) |
| Extra | `uv tool install --compile-bytecode "openhal-hub[serial] @ git+https://github.com/sohan-bhat/OpenHAL"` |
| Transports | USB CDC and UART device paths, `socket://host:port`, `rfc2217://host:port` |
| Hazard default | medium |
| Safe state | from the device file only (the protocol has no emergency behavior) |
| Self-describe | no |

## What it supports

- Read channels of type number, bool, enum and string, either queried (`map.query`) or pushed by the device (`map.listen`).
- Write channels of every type, with an optional readback query (`map.get`).
- Actions whose arguments fill a command template.
- Unit conversion between the device's unit and the channel unit, plus a linear `scale` and `offset` for raw counts.
- Discovery that lists serial ports with their USB ids. Listing never opens a port.
- `port: auto`, which picks the one listed port whose USB id matches `match.usb` (and `match.serial_number` if given).

## Setup

1. Install the extra with `uv tool install --compile-bytecode "openhal-hub[serial] @ git+https://github.com/sohan-bhat/OpenHAL"`.
2. Find the port with `openhal discover` or `python -m serial.tools.list_ports -v`.
3. Write a device file. Each read channel needs a `map` with `query` or `listen`. Each write channel and action needs a `map` with `command`.
4. Validate it with `openhal file validate my-device.hal.yaml`.
5. Confirm the limits by hand (spec section 12). Until then the device loads read-only.

## Parameters

| Key | Default | Meaning |
|---|---|---|
| `port` | required | Device path, pyserial URL or `auto` |
| `baud` | 9600 | Baud rate |
| `newline` | `lf` | Line ending sent and expected. `lf`, `crlf` or `cr` |
| `encoding` | `ascii` | `ascii`, `utf-8` or `latin-1` |
| `timeout` | `1 s` | How long to wait for each reply, 50 ms to 30 s |
| `settle` | `0 s` | Wait after opening, for boards that reset when the port opens. Bytes received meanwhile are dropped |
| `identify` | none | A read-only query sent by `identify()`, such as `ID?` or `*IDN?` |
| `board` | none | Free text recorded in the identity |
| `rtscts`, `dsrdtr` | false | Hardware flow control |

## Channel maps

| Key | Used by | Meaning |
|---|---|---|
| `query` | read | Line to send. The next line that is not a stream line is the reply |
| `listen` | read | Regex for lines the device sends on its own. The latest match is the value |
| `command` | write, action | Template to send. Writes use `{value}`, actions use their argument names |
| `get` | write | Readback query. Without it a read returns the last value sent, and unknown (null) before the first write |
| `parse` | read, write | Regex for the reply. Group `value`, else group 1, else the whole match |
| `expect` | write, action | Regex the reply must match. Without `expect` or `error` the driver doesn't wait for a reply |
| `error` | write, action | Regex that marks a refusal, reported as a failed command |
| `scale`, `offset` | read, write | `channel value = raw * scale + offset`, inverted for writes |
| `unit` | read, write | The device's unit when it differs from the channel unit |
| `on`, `off` | bool channels, actions | Device text for true and false. Reads accept common words when unset |
| `lookup` | enum channels | Device text to enum value, inverted for writes |

Templates accept only the placeholders named above, with an optional format spec such as `{value:.1f}`. Conversions and nested fields are refused when the file loads. A rendered command that contains a control character is refused before anything is sent, so a string value can't append a second command.

## Example device file

`openhal/drivers/serial/examples/arduino-fan-board.hal.yaml`

```yaml
device: { name: Arduino fan board, model: Uno R3, manufacturer: Arduino }
id: fan-board
match: { usb: ["2341:0043"], usb_class: cdc }
connect: { serial: auto, baud: 115200, timeout: 1 s, settle: 2 s, identify: "ID?" }
read:
  temperature: { unit: degC, every: 1 s, map: { query: "TEMP?", parse: "^T=(?P<value>-?[0-9.]+)$" } }
write:
  fan_speed:
    unit: percent
    min: 0
    max: 100
    max_change_per_s: 25
    map: { command: "FAN {value:.0f}", scale: 0.39215686, expect: "^OK$", error: "^ERR", get: "FAN?", parse: "^FAN=(\\d+)$" }
safe_state: { fan_speed: 0 }
hazard: low
```

## Known limitations

- One command and one reply line at a time. Multi-line replies and binary protocols need a dedicated driver.
- Replies are matched by order. A device that answers out of order or sends unrelated chatter that no `listen` pattern covers will confuse the driver. Add a `listen` pattern for the chatter.
- Regexes run with Python `re` and lines are cut at 4096 characters. There is no per-match timeout.
- The protocol has no safe state of its own. Always give the device file a `safe_state`, and prefer firmware that falls back to a safe output when the host goes quiet.

## Hazard defaults

The driver reports `medium`, because it can drive anything. Set `hazard` in the device file to what the device really is.

## Sources

- pyserial documentation, https://pyserial.readthedocs.io/en/latest/ (URL handlers, exclusive access, `list_ports`)
- Arduino serial reference, https://docs.arduino.cc/language-reference/en/functions/communication/serial/ (reset on open, line endings)
- Python `string.Formatter` documentation, https://docs.python.org/3/library/string.html#format-string-syntax
