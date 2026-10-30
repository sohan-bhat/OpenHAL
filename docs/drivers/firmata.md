# firmata driver

The `firmata` driver connects to Arduino-compatible boards running StandardFirmata. The driver reads digital and analog pins and drives digital outputs, PWM pins and hobby servos. Each channel's `map` names the pin.

| | |
|---|---|
| Driver name | `firmata` |
| Library | own Firmata client (`openhal/drivers/firmata/protocol.py`) on pyserial 3.5 (BSD-3-Clause) |
| Extra | `uv tool install --compile-bytecode "openhal-hub[firmata] @ git+https://github.com/sohan-bhat/OpenHAL"` |
| Hazard default | low |
| Safe state | from the device file only |
| Self-describe | yes, from the board's capability report |

## Why an own client

The maintained Python Firmata clients are pymata4, pymata-express and telemetrix, which are AGPL-3.0, and pyfirmata2 (MIT, last release November 2024), which is synchronous with its own reader thread and callbacks. The driver needs about a dozen messages, so a small async client written from the protocol documentation is simpler and keeps the license clean.

## What it supports

| Channel | Map | Firmata messages |
|---|---|---|
| read bool | `{ pin: 7 }`, `{ pin: 2, mode: pullup, invert: true }` | SET_PIN_MODE, REPORT_DIGITAL, digital port reports |
| read number | `{ pin: A0 }` or `{ pin: 14 }` | SET_PIN_MODE analog, REPORT_ANALOG, analog reports |
| write bool | `{ pin: 13 }`, `{ pin: 7, invert: true }` | SET_DIGITAL_PIN_VALUE, or port messages before Firmata 2.5 |
| write number in percent | `{ pin: 9 }` | SET_PIN_MODE pwm, analog message or EXTENDED_ANALOG |
| write number in an angle unit | `{ pin: 6, mode: servo, min_pulse: 544, max_pulse: 2400 }` | SERVO_CONFIG, analog message |

- Analog values are `raw * scale + offset`. Without `scale` a volt channel uses `vref / (2^resolution - 1)`, a percent channel `100 / (2^resolution - 1)` and a dimensionless channel the raw count. The resolution comes from the capability report.
- PWM percent maps to `round(percent / 100 * (2^resolution - 1))`, which is 0 to 255 on an Uno.
- Servo angles are converted to degrees and rounded to whole degrees from 0 to 180.
- `invert: true` suits active-low relays and buttons wired to ground.
- Write channels read back with PIN_STATE_QUERY, where a pin that is not yet in the channel's mode reads as unknown and a PWM pin still in output mode after reset reads as 0 % or 100 %.
- With `verify: true` (the default) each write is followed by a pin state query, so a write to a board that stopped responding fails.
- `describe()` returns a volt channel per analog pin, a percent channel per PWM pin and a bool channel per other output-capable pin, all marked `suggested: true`.

## How connect works

1. Open the port. Most boards reset and StandardFirmata takes about 2 s to start, which is the delay `settle` sets.
2. Send REPORT_FIRMWARE, REPORT_VERSION, CAPABILITY_QUERY and ANALOG_MAPPING_QUERY.
3. Check every channel's pin and mode against the capability report. A pin that can't do what the file requires fails the connect with the modes the pin does support.
4. Set the sampling interval, put read pins in their input mode and turn on reporting.

Because setting a pin to output already drives the pin, output pins are not touched until the first granted write, so setting a pin to output only happens as part of a write the kernel passed.

## Setup

1. Upload StandardFirmata from the Arduino IDE (File, Examples, Firmata, StandardFirmata).
2. Install the extra with `uv tool install --compile-bytecode "openhal-hub[firmata] @ git+https://github.com/sohan-bhat/OpenHAL"`.
3. Start from `openhal/drivers/firmata/examples/uno-desk-kit.hal.yaml` and keep only the pins that are wired.
4. Validate the file with `openhal file validate`, then confirm the limits by hand.

## Parameters

| Key | Default | Meaning |
|---|---|---|
| `port` | required | Device path, pyserial URL or `auto` (uses `match.usb`) |
| `baud` | 57600 | StandardFirmata's baud rate |
| `timeout` | `1 s` | How long to wait for a query reply |
| `settle` | `2 s` | Wait after opening, while the board resets |
| `sampling` | `100 ms` | Analog sampling interval. Analog reads fail when no report arrived for 5 intervals (at least 1 s) |
| `vref` | `5 V` | Analog reference, used to scale volt channels. `3.3 V` on 3.3 V boards |
| `verify` | true | Confirm each write with a pin state query |
| `board` | none | Free text |

## Example device file

```yaml
device: { name: Uno desk kit, manufacturer: Arduino }
id: desk-kit
match: { usb: ["2341:0043"] }
connect: { firmata: auto, vref: 5 V }
read:
  light: { unit: V, every: 500 ms, map: { pin: A0 } }
  button: { type: bool, every: 200 ms, map: { pin: 2, mode: pullup, invert: true } }
write:
  led: { type: bool, map: { pin: 13 } }
  fan: { unit: percent, min: 0, max: 80, map: { pin: 9 } }
  pointer: { unit: degree, min: 10, max: 170, map: { pin: 6, mode: servo } }
safe_state: { led: false, fan: 0 }
hazard: low
```

## Known limitations

- I2C, SPI, OneWire, stepper and encoder features of ConfigurableFirmata are not supported.
- Digital inputs report on change only, so a read can't distinguish a quiet board from a stopped one, but analog reads and pin state queries raise a timeout on a stopped board.
- Because pins 0 and 1 carry the serial link on an Uno, StandardFirmata reports no modes for those pins, and a channel on those pins fails the capability check at connect.
- Because a servo holds its last angle after a stop unless the safe state moves the servo, record that behavior in `safe_state_note`.
- Because power-on pin modes are not a safe state for every circuit, the driver never sends SYSTEM_RESET.

## Hazard defaults

The default hazard is `low`, because boards running Firmata usually drive LEDs, small fans and hobby servos. Set `hazard` higher in the device file when the pins switch relays or motors that can hurt.

## Sources

- Firmata protocol, https://github.com/firmata/protocol/blob/master/protocol.md
- Capability, analog mapping and pin state queries, https://github.com/firmata/protocol/blob/master/capability-query.md and https://github.com/firmata/protocol/blob/master/pin-state-query.md
- Servo configuration, https://github.com/firmata/protocol/blob/master/servos.md
- StandardFirmata defaults (57600 baud, startup pin modes), https://github.com/firmata/arduino (read for behavior only, no code copied)
