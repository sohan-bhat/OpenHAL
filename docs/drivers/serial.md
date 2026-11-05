# serial driver

The `serial` driver connects to any device with a line-based text protocol over a serial port, with pyserial 3.5, on USB CDC and UART paths, `socket://host:port` or `rfc2217://host:port`. Every query, reply pattern and command template comes from the device file, so one driver covers Arduino sketches, RS-232 instruments and sensor modules.

## Supports

- Number, bool, enum and string reads, queried with `map.query` or pushed by the device and caught with `map.listen`.
- Writes with an optional readback query, `map.get`.
- Actions whose arguments fill a command template.
- Unit conversion, plus linear `scale` and `offset` for raw counts.
- Discovery of serial ports with USB ids, opening none.
- `port: auto` picks the one port matching `match.usb` and any `match.serial_number`.

## Setup

1. Install with `uv tool install --compile-bytecode "halkit[serial] @ git+https://github.com/sohan-bhat/OpenHAL"`.
2. Find the port with `openhal discover` or `python -m serial.tools.list_ports -v`.
3. Give each read channel a `map` with `query` or `listen`, and each write channel and action a `map` with `command`.
4. Validate with `openhal file validate my-device.hal.yaml`.
5. Confirm the limits by hand, since high risk channels and actions stay read-only until then.

| Key | Default | Meaning |
|---|---|---|
| `port` | required | Device path, pyserial URL or `auto` |
| `baud` | 9600 | Baud rate |
| `newline` | `lf` | Line ending, `lf`, `crlf` or `cr` |
| `framing` | `line` | `line`, or `stx-etx` for packets from STX 0x02 to ETX 0x03 as New Era syringe pumps reply |
| `encoding` | `ascii` | `ascii`, `utf-8` or `latin-1` |
| `timeout` | `1 s` | Reply deadline, 50 ms to 30 s |
| `settle` | `0 s` | Delay after opening for boards that reset, with bytes received meanwhile dropped |
| `identify` | none | Read-only query for `identify()`, such as `ID?` or `*IDN?` |
| `board` | none | Free text for the identity |
| `rtscts`, `dsrdtr` | false | Hardware flow control |

## Channel maps

| Key | Used by | Meaning |
|---|---|---|
| `query` | read | Line to send. The next non-stream line is the reply |
| `listen` | read | Regex for unsolicited lines. The latest match is the value |
| `command` | write, action | Template with `{value}` for writes or argument names for actions |
| `get` | write | Readback query. Without one, a read returns the last value sent, or null before the first write |
| `parse` | read, write | Reply regex. Group `value`, else group 1, else the whole match |
| `expect` | write, action | Regex the reply must match. Without `expect` or `error` no reply is read |
| `error` | write, action | Regex for an error reply, reported as a failed command |
| `scale`, `offset` | read, write | `channel value = raw * scale + offset`, inverted for writes |
| `unit` | read, write | Device unit when different from the channel unit |
| `on`, `off` | bool channels, actions | Device text for true and false. Reads accept common words when unset |
| `lookup` | enum channels | Device text to enum value, inverted for writes |

Templates accept only these placeholders, with an optional format spec such as `{value:.1f}`. A rendered command with a control character is blocked before sending, so a string value can't append a second command.

## Example device file

`openhal/drivers/serial/examples/arduino-fan-board.hal.yaml` reads a temperature with `TEMP?` and sets a fan speed with `FAN {value:.0f}` on an Arduino Uno.

## Known limitations

- One command and one reply line at a time, so multi-line replies and binary protocols need a dedicated driver.
- Replies match by order, so out-of-order replies or chatter that no `listen` pattern covers get matched wrongly. Add a `listen` pattern for the chatter.
- Regexes have no per-match timeout, and lines are cut at 4096 characters.
- Give every file a `safe_state`, and prefer firmware that falls back to a safe output when commands stop.

## Hazard defaults

`medium`, since the driver can drive anything. Set `hazard` to what the device really is. `safe_state` comes from the device file only.

## Sources

- pyserial documentation for URL handlers, exclusive access and `list_ports`, https://pyserial.readthedocs.io/en/latest/
- Arduino serial reference for reset on open and line endings, https://docs.arduino.cc/language-reference/en/functions/communication/serial/
- Python `string.Formatter` documentation, https://docs.python.org/3/library/string.html#format-string-syntax
