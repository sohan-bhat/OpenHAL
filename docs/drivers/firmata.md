# firmata driver

The `firmata` driver reads digital and analog pins on boards running StandardFirmata and drives digital outputs, PWM pins and hobby servos, with a small async client on pyserial 3.5. Each channel `map` names the pin.

## Supports

| Channel | Map | Firmata messages |
|---|---|---|
| read bool | `{ pin: 7 }`, `{ pin: 2, mode: pullup, invert: true }` | SET_PIN_MODE, REPORT_DIGITAL, digital port reports |
| read number | `{ pin: A0 }` or `{ pin: 14 }` | SET_PIN_MODE analog, REPORT_ANALOG, analog reports |
| write bool | `{ pin: 13 }`, `{ pin: 7, invert: true }` | SET_DIGITAL_PIN_VALUE, or port messages before Firmata 2.5 |
| write number in percent | `{ pin: 9 }` | SET_PIN_MODE pwm, analog message or EXTENDED_ANALOG |
| write number in an angle unit | `{ pin: 6, mode: servo, min_pulse: 544, max_pulse: 2400 }` | SERVO_CONFIG, analog message |

- Analog values are `raw * scale + offset`. Without `scale`, volt channels use `vref / (2^resolution - 1)`, percent channels `100 / (2^resolution - 1)` and dimensionless channels the raw count.
- PWM sends `round(percent / 100 * (2^resolution - 1))`, 0 to 255 on an Uno. Servo angles round to whole degrees from 0 to 180.
- Writes read back with PIN_STATE_QUERY, and with `verify: true` a stalled board fails the write. A pin not yet in the channel's mode reads as unknown.
- `describe()` suggests a channel for every analog, PWM and output pin.

On connect every pin and mode is checked against the board's capability report, and a mismatch fails the connect with the modes the pin supports. Output pins stay untouched until the first write the kernel passes.

## Setup

1. Upload StandardFirmata from the Arduino IDE under File, Examples, Firmata.
2. Install with `uv tool install --compile-bytecode "halkit[firmata] @ git+https://github.com/sohan-bhat/OpenHAL"`.
3. Start from `openhal/drivers/firmata/examples/uno-desk-kit.hal.yaml` and keep only the wired pins.

| Key | Default | Meaning |
|---|---|---|
| `port` | required | Device path, pyserial URL or `auto` with `match.usb` |
| `baud` | 57600 | Baud rate |
| `timeout` | `1 s` | Query reply deadline |
| `settle` | `2 s` | Delay after opening while the board resets |
| `sampling` | `100 ms` | Analog interval. Analog reads fail after 5 intervals without a report, at least 1 s |
| `vref` | `5 V` | Analog reference, `3.3 V` on 3.3 V boards |
| `verify` | true | Check each write with a pin state query |
| `board` | none | Free text |

## Known limitations

- No ConfigurableFirmata I2C, SPI, OneWire, stepper or encoder features.
- Digital inputs report on change only, so a stopped board looks quiet. Analog reads and pin queries time out.
- Uno pins 0 and 1 carry serial and fail the capability check.
- A servo holds the last angle after a stop unless the safe state moves the servo.
- No SYSTEM_RESET, since power-on pin modes aren't safe for every circuit.

## Hazard defaults

`low`, with `safe_state` from the device file only. Raise `hazard` when pins switch relays or motors.

## Sources

- Firmata protocol, https://github.com/firmata/protocol/blob/master/protocol.md
- Capability, analog mapping and pin state queries, https://github.com/firmata/protocol/blob/master/capability-query.md and https://github.com/firmata/protocol/blob/master/pin-state-query.md
- Servo configuration, https://github.com/firmata/protocol/blob/master/servos.md
- StandardFirmata defaults of 57600 baud and startup pin modes, read for behavior only with no code copied, https://github.com/firmata/arduino
