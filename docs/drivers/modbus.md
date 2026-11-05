# modbus driver

The modbus driver reads and writes Modbus RTU devices on serial lines, usually RS-485, and Modbus TCP devices, through pymodbus. Coils and discrete inputs map to bools, holding and input registers to numbers, bools and enums. Coil writes use function 5 and register writes function 6, or 16 for 32-bit values. `identify()` uses Read Device Identification, function 43 / 14, where supported.

## Setup

```sh
uv tool install --compile-bytecode "halkit[modbus] @ git+https://github.com/sohan-bhat/OpenHAL"
```

RTU needs a USB to RS-485 adapter wired A to A and B to B, termination at both ends of long runs, and on Linux the `dialout` group.

## Parameters

| Parameter | Default | Meaning |
|---|---|---|
| `transport` | required | `tcp` or `rtu`. `modbus: rtu` is shorthand |
| `host` | none | TCP device or gateway address |
| `port` | `502` for TCP | TCP port, or the RTU serial device such as `/dev/ttyUSB0` or `COM3` |
| `unit` | `1` | Unit id, 1 to 247 |
| `baud` | `9600` | RTU only |
| `parity` | `N` | RTU only. `N`, `E` or `O` |
| `stopbits` | `1` | RTU only |
| `bytesize` | `8` | RTU only |
| `timeout` | `1 s` | Response deadline |
| `retries` | `1` | Extra attempts after a timeout |
| `word_order` | `big` | High word first for 32-bit values |
| `byte_order` | `big` | Byte order in each register |
| `always_write_multiple` | `false` | Function 16 for single registers too |

## Channel maps

```yaml
read:
  voltage: { unit: V, map: { register: 0, kind: input, format: float32 } }
  temperature: { unit: degC, map: { register: 4, kind: input, format: int16, scale: 0.1 } }
  door_closed: { type: bool, map: { register: 0, kind: discrete } }
  alarm: { type: bool, map: { register: 30, bit: 3 } }
write:
  speed: { unit: percent, min: 0, max: 100, step: 0.1, map: { register: 10, scale: 0.1 } }
  enable: { type: bool, map: { register: 0, kind: coil } }
  mode: { type: enum, values: [stop, run], map: { register: 20, values: { stop: 0, run: 1 } } }
```

| Key | Default | Meaning |
|---|---|---|
| `register` | required | Zero-based address. Manual addresses `40011` and `30001` mean holding register 10 and input register 0 |
| `kind` | `holding` | `coil`, `discrete`, `holding` or `input` |
| `format` | `uint16` | `uint16`, `int16`, `uint32`, `int32`, `float32` |
| `word_order`, `byte_order` | from the parameters | Per-channel override |
| `scale`, `offset` | `1`, `0` | value = raw × scale + offset |
| `bit` | none | Bit 0 to 15 as a read-only bool |
| `values` | none | Enum word to raw value, required for enums |
| `on`, `off` | `1`, `0` | Raw values for a bool on a register |

Writes send `raw = (value - offset) / scale`, rounded for integer formats, and return the value sent, so with `scale: 0.1` a write of `42.47 %` sends 425 and reads back 42.5 %. Set `step` to the register resolution so the kernel blocks values that would round. Bit channels are read-only, since read-modify-write races other masters.

## Example

`openhal/drivers/modbus/examples/sdm120-energy-meter.hal.yaml` reads an Eastron SDM120 meter over RTU.

## Errors and health

- A timeout after `retries` raises `TimeoutError` with a hint about unit id, wiring, baud rate and parity.
- A Modbus exception, a NaN float, an unmapped enum value or a value too big for the format raises `DriverError`.
- `health()` reads the first mapped channel. Three failed transactions in a row mark the device disconnected.

## Limitations

- No discovery, strings, 64-bit values or file records.
- `describe()` returns only the unit id and identification objects.
- One master per bus.

## Hazard default and safe state

Medium, or high for drives and anything that can injure. `safe_state_support` is `file`, so `safe_state` goes out as ordinary writes while the device responds.

## Sources

- Modbus Application Protocol Specification V1.1b3, https://www.modbus.org/docs/Modbus_Application_Protocol_V1_1b3.pdf
- Modbus over Serial Line Specification and Implementation Guide V1.02, https://www.modbus.org/docs/Modbus_over_serial_line_V1_02.pdf
- Modbus Messaging on TCP/IP Implementation Guide V1.0b, https://www.modbus.org/docs/Modbus_Messaging_Implementation_Guide_V1_0b.pdf
- pymodbus documentation, https://pymodbus.readthedocs.io/
- Eastron SDM120 Modbus protocol, register table, https://www.eastroneurope.com/products/view/sdm120modbus
