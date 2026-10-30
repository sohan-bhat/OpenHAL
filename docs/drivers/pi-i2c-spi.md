# pi-i2c-spi driver

The pi-i2c-spi driver reads and sets I2C and SPI chips on a Raspberry Pi, or any Linux board with i2c-dev and spidev. The driver uses smbus2 for I2C and spidev for SPI, and the device file is the register map. Each channel names a register, or the bytes to clock out over SPI, and where the value sits in the bytes that come back, so temperature sensors, ADCs, DACs and port expanders work without chip-specific code.

## What it supports

- I2C chips with 8-bit or 16-bit register addresses, and chips read without a register.
- SPI chips that respond to a command in the same transfer, such as most ADCs, and chips that only take values, such as DACs.
- Read channels of type number, bool and enum, decoded from any byte range or bit range, big or little endian, signed or unsigned, with scale, offset and a device unit.
- Control channels that set one register, or clock out one SPI word, with the value placed in it.
- `preserve: true` for I2C configuration registers, which reads the register and changes only the field's bits.
- Actions that send fixed bytes to a register, with action arguments placed in them.
- `discover()` lists `/dev/i2c-*` and `/dev/spidev*` without touching any bus.

## Setup

```sh
uv tool install --compile-bytecode "openhal-hub[pi-i2c-spi] @ git+https://github.com/sohan-bhat/OpenHAL"
```

Enable I2C and SPI with `sudo raspi-config` (Interface Options), reboot, and add the hub's user to the `i2c` and `spi` groups. spidev builds only on Linux, so on other systems only the tests run.

## Parameters

| Parameter | Default | Meaning |
|---|---|---|
| `bus` | required | `1`, `i2c-1` or `/dev/i2c-1` for I2C bus 1, `spi0.1` or `/dev/spidev0.1` for SPI bus 0 with chip select 1. The shorthand `pi-i2c-spi: i2c-1` sets it |
| `address` | required for I2C | The chip's 7-bit address, such as `0x48`. Not allowed for SPI |
| `register_width` | `1` | I2C register address size in bytes, `1` or `2` |
| `speed_hz` | `500000` | SPI clock |
| `mode` | `0` | SPI mode, `0` to `3` |
| `timeout` | `1 s` | How long one transaction may take |

## Channel maps

```yaml
read:
  temperature: { unit: degC, map: { register: 0x00, length: 2, signed: true, bit: 4, bits: 12, scale: 0.0625 } }
  potentiometer: { unit: V, map: { command: [0x01, 0x80, 0x00], byte: 1, length: 2, bits: 10, scale: 0.0032258 } }
write:
  shutdown: { type: bool, map: { register: 0x01, length: 2, bit: 8, bits: 1, preserve: true } }
  control_voltage: { unit: V, min: 0, max: 2.5, map: { data: [0x30, 0x00], length: 2, bits: 12, scale: 0.00080566 } }
actions:
  power_down: { map: { data: [0x00, 0x00] } }
```

| Key | Default | Meaning |
|---|---|---|
| `register` | none | I2C. The register to read or set. Commands and actions on I2C need one |
| `read_length` | the field's end | I2C. How many bytes to read from the register |
| `command` | required for SPI reads | SPI. The bytes to clock out, padded with zeros to the field's end |
| `data` | zeros | Commands and actions. The bytes the rest of the payload carries. For SPI this is the whole word |
| `preserve` | `false` | I2C commands. Read the register and change only this field's bits |
| `byte`, `length` | `0`, `1` | Where the value starts in the payload and how many bytes it spans, 1 to 8 |
| `endian` | `big` | Byte order, `big` or `little` |
| `signed` | `false` | Two's complement |
| `bit`, `bits` | `0`, the rest | The bit range inside those bytes, counted from the least significant bit |
| `scale`, `offset` | `1`, `0` | device value = raw × scale + offset |
| `unit` | the channel unit | The unit the device value is in, which the driver converts to the channel unit |
| `on`, `off` | `1`, `0` | Raw values for bool channels |
| `lookup` | none | Raw numbers to enum values |
| `state` | none | Control channels. A read map that shows the result, often the same register |
| `args` | none | Actions. A field map for each action argument |

## How reads and commands behave

- The driver only changes the registers and byte sequences that the device file's control channels and actions list, and connecting changes nothing. Configuration a chip needs before measuring, such as starting conversions, goes in an action so the configuration passes through the safety kernel.
- Values are rounded to the field's raw step, and the reading a command returns shows the value actually sent. A value the field can't hold fails the command, and nothing is sent or clamped.
- A control channel without `state` reads as the last value sent, or no value before the first command.
- Because `health()` reads the first read channel, make the first read channel a register that is safe to read often rather than one that clears on read.
- Transactions on one device run one at a time, and other devices on the same bus are separate device files whose transactions the Linux kernel's i2c-dev locking keeps apart.

## Examples

- `tmp102-temperature.hal.yaml` reads a TMP102 and sets its alert thresholds and shutdown bit.
- `mcp3008-adc.hal.yaml` reads three channels of an MCP3008 ADC.
- `mcp4921-dac.hal.yaml` sets an MCP4921 DAC that drives a fan controller's speed input.

## Errors

- A chip that doesn't acknowledge raises `DriverError` with the `i2cdetect` command to try.
- A missing `/dev/i2c-N` or `/dev/spidev` node and a permission problem raise `DriverError` with a message that names what to enable or which group to join.
- A transaction that hangs raises `TimeoutError`. A reply of the wrong length and a raw value a bool or enum map doesn't name raise `DriverError`.

## Limitations

- The driver converts linear values only, so sensors that need calibration math, such as the BME280 compensation formulas, can be read as raw registers but not converted.
- The driver doesn't support SMBus block protocols with a length byte, packet error checking or 10-bit I2C addresses.
- SPI words are whole bytes.
- `describe()` returns nothing, because a register map can't be read from the chip.

## Hazard default and safe state

The default hazard is low, because most chips on these buses are sensors and converters. A DAC or driver chip can still switch a real load, so set the file's hazard to match what the chip controls. I2C and SPI have no emergency behavior, so `safe_state_support` is `file` and the hub sends the device file's safe state like any other value. A chip keeps its last output if the Pi stops, so wire pull resistors that make power loss safe.

## Sources

- Linux i2c-dev interface, https://docs.kernel.org/i2c/dev-interface.html
- Linux spidev, https://docs.kernel.org/spi/spidev.html
- smbus2, https://github.com/kplindegaard/smbus2
- spidev, https://github.com/doceme/py-spidev
- TI TMP102 datasheet, https://www.ti.com/lit/ds/symlink/tmp102.pdf
- Microchip MCP3008 datasheet, https://ww1.microchip.com/downloads/en/DeviceDoc/21295d.pdf
- Microchip MCP4921 datasheet, https://ww1.microchip.com/downloads/en/DeviceDoc/21897B.pdf
