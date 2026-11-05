# pi-i2c-spi driver

The pi-i2c-spi driver reads and sets I2C and SPI chips on a Raspberry Pi or any Linux board with i2c-dev and spidev, through smbus2 and spidev. The device file is the register map, so temperature sensors, ADCs, DACs and port expanders need no chip-specific code.

## Supports

- I2C chips with 8-bit, 16-bit or no register addresses, and SPI chips that reply in the same transfer, such as ADCs, or only take values, such as DACs.
- `preserve: true` read-modify-write for I2C configuration registers.
- `discover()` lists `/dev/i2c-*` and `/dev/spidev*` without touching a bus.

## Setup

```sh
uv tool install --compile-bytecode "halkit[pi-i2c-spi] @ git+https://github.com/sohan-bhat/OpenHAL"
```

Enable I2C and SPI under Interface Options in `sudo raspi-config`, reboot, and add the hub's user to the `i2c` and `spi` groups. spidev builds only on Linux.

| Parameter | Default | Meaning |
|---|---|---|
| `bus` | required | `1`, `i2c-1` or `/dev/i2c-1` for I2C bus 1, `spi0.1` or `/dev/spidev0.1` for SPI bus 0 chip select 1. `pi-i2c-spi: i2c-1` is shorthand |
| `address` | required for I2C | 7-bit address such as `0x48`. Not for SPI |
| `register_width` | `1` | I2C register address bytes, `1` or `2` |
| `speed_hz` | `500000` | SPI clock |
| `mode` | `0` | SPI mode, `0` to `3` |
| `timeout` | `1 s` | Per transaction |

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
| `register` | none | I2C register. I2C commands and actions need one |
| `read_length` | the field's end | I2C bytes to read |
| `command` | required for SPI reads | SPI bytes to clock out, zero-padded to the field's end |
| `data` | zeros | Commands and actions. The other payload bytes, or the whole SPI word |
| `preserve` | `false` | I2C commands. Change only this field's bits |
| `byte`, `length` | `0`, `1` | Start byte and length, 1 to 8 |
| `endian` | `big` | `big` or `little` |
| `signed` | `false` | Two's complement |
| `bit`, `bits` | `0`, the rest | Bit range from the least significant bit |
| `scale`, `offset` | `1`, `0` | device value = raw × scale + offset |
| `unit` | the channel unit | Device unit, converted to the channel unit |
| `on`, `off` | `1`, `0` | Raw bool values |
| `lookup` | none | Raw numbers to enum values |
| `state` | none | Control channels. Read map that shows the result, often the same register |
| `args` | none | Actions. Field map per argument |

## Behavior

- Connecting changes nothing, and only the registers and bytes in the file's control channels and actions are ever sent. Put chip setup such as starting conversions in an action, so the setup passes the safety kernel.
- Values round to the field's raw step and the reading returned shows the value sent. A value the field can't hold fails with nothing sent.
- A control channel without `state` reads as the last value sent.
- `health()` reads the first read channel, so make that channel a register that is safe to read often, not one that clears on read.
- A chip that doesn't acknowledge raises `DriverError` with the `i2cdetect` command to try. Missing nodes and permission problems name the fix, wrong-length replies and unmapped raw values raise `DriverError`, and a hung transaction raises `TimeoutError`.
- Several device files can share one bus.

## Examples

- `tmp102-temperature.hal.yaml` reads a TMP102 and sets the alert thresholds and shutdown bit.
- `mcp3008-adc.hal.yaml` reads three channels of an MCP3008 ADC.
- `mcp4921-dac.hal.yaml` sets an MCP4921 DAC that drives a fan controller's speed input.

## Limitations

- Linear conversion only, so chips such as the BME280 that need compensation formulas read as raw registers.
- No SMBus block protocols, packet error checking or 10-bit I2C addresses.
- SPI words are whole bytes.
- `describe()` returns nothing, since chips can't report a register map.

## Hazard default and safe state

Low. A DAC or driver chip can switch a real load, so match the hazard to what the chip controls. `safe_state_support` is `file`. A chip keeps the last output if the Pi stops, so wire pull resistors that make power loss safe.

## Sources

- Linux i2c-dev interface, https://docs.kernel.org/i2c/dev-interface.html
- Linux spidev, https://docs.kernel.org/spi/spidev.html
- smbus2, https://github.com/kplindegaard/smbus2
- spidev, https://github.com/doceme/py-spidev
- TI TMP102 datasheet, https://www.ti.com/lit/ds/symlink/tmp102.pdf
- Microchip MCP3008 datasheet, https://ww1.microchip.com/downloads/en/DeviceDoc/21295d.pdf
- Microchip MCP4921 datasheet, https://ww1.microchip.com/downloads/en/DeviceDoc/21897B.pdf
