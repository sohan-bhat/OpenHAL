# modbus driver

The modbus driver reads and writes Modbus RTU devices on a serial line (usually RS-485) and Modbus TCP devices on the network, through pymodbus. Each channel's map names a register, its table, its number format and a linear scale, taken from the device's register map.

## What it supports

- All four tables, where coils and discrete inputs map to bool channels and holding and input registers map to number, bool and enum channels.
- Formats `uint16`, `int16`, `uint32`, `int32` and `float32`, with configurable word order and byte order.
- Writes to coils (function 5) and holding registers (function 6, or 16 for 32-bit values and for devices that only accept 16).
- Single bits of a register as read-only bool channels.
- Read Device Identification (function 43 / 14) for `identify()` where the device supports it.

## Setup

```sh
uv tool install --compile-bytecode "openhal-hub[modbus] @ git+https://github.com/sohan-bhat/OpenHAL"
```

For RTU you need a USB to RS-485 adapter and the bus wired A to A and B to B, with termination at both ends of longer runs. On Linux, add your user to the `dialout` group to open the port.

## Parameters

| Parameter | Default | Meaning |
|---|---|---|
| `transport` | required | `tcp` or `rtu`. The shorthand `modbus: rtu` sets it |
| `host` | none | TCP only. Address of the device or gateway |
| `port` | `502` for TCP | TCP port number, or the serial device for RTU (`/dev/ttyUSB0`, `COM3`) |
| `unit` | `1` | Unit id, 1 to 247 |
| `baud` | `9600` | RTU only |
| `parity` | `N` | RTU only. `N`, `E` or `O` |
| `stopbits` | `1` | RTU only |
| `bytesize` | `8` | RTU only |
| `timeout` | `1 s` | How long to wait for each response |
| `retries` | `1` | Extra attempts after a timeout |
| `word_order` | `big` | Default order of the two registers of 32-bit values. `big` sends the high word first |
| `byte_order` | `big` | Default byte order inside each register. Only a few devices need `little` |
| `always_write_multiple` | `false` | Use function 16 even for single registers |

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
| `register` | required | Zero-based protocol address. Manuals that write `40011` or `30001` mean holding register 10 and input register 0 |
| `kind` | `holding` | `coil`, `discrete`, `holding` or `input` |
| `format` | `uint16` | `uint16`, `int16`, `uint32`, `int32`, `float32` |
| `word_order`, `byte_order` | from the parameters | Per-channel override |
| `scale`, `offset` | `1`, `0` | channel value = raw × scale + offset |
| `bit` | none | Read one bit (0 to 15) of a register as a bool. Read channels only |
| `values` | none | Enum word to raw value, required for enum channels |
| `on`, `off` | `1`, `0` | Raw values for a bool channel on a register |

Writes compute raw = (value - offset) / scale and round integer formats to the nearest whole number. The reading the driver returns shows the value it really sent, so `42.47 %` with `scale: 0.1` is sent as 425 and reported as 42.5 %. Set `step` on the channel to the register's resolution and the kernel rejects values that would be rounded.

Because changing one bit needs a read-modify-write that could race with the device or another master, bit channels can't be written.

## Example

`openhal/drivers/modbus/examples/sdm120-energy-meter.hal.yaml` reads an Eastron SDM120 meter over RTU. The file has no write channels, so the file needs no confirmation.

## Errors and health

- No response within `timeout`, after `retries`, raises `TimeoutError` with a hint about the unit id, wiring, baud rate and parity.
- Modbus exception responses raise `DriverError` naming the exception, for example illegal data address.
- A NaN float, an enum raw value outside the map, or a value that doesn't fit the register format raises `DriverError`.
- Because a TCP socket or a serial port stays open after the device behind it dies, `health()` reads the first mapped channel, and three failed transactions in a row also report the device as disconnected.

## Limitations

- Because scanning unit ids would send requests to devices nobody configured, the driver has no discovery.
- The driver doesn't support strings, 64-bit values or file records.
- Modbus devices don't describe their registers, so `describe()` only returns the unit id and any identification objects.
- The driver doesn't coordinate with other masters, so don't run the driver on a bus with another master.

## Hazard default and safe state

The default hazard is medium, because Modbus often drives motors, heaters and valves. Raise the hazard to high for drives and anything that can injure. Modbus has no emergency behavior of its own, so `safe_state_support` is `file`, and the hub applies the device file's `safe_state` through ordinary writes, which work only while the device responds. Wire hardware stops for anything dangerous.

## Sources

- Modbus Application Protocol Specification V1.1b3, https://www.modbus.org/docs/Modbus_Application_Protocol_V1_1b3.pdf
- Modbus over Serial Line Specification and Implementation Guide V1.02, https://www.modbus.org/docs/Modbus_over_serial_line_V1_02.pdf
- Modbus Messaging on TCP/IP Implementation Guide V1.0b, https://www.modbus.org/docs/Modbus_Messaging_Implementation_Guide_V1_0b.pdf
- pymodbus documentation, https://pymodbus.readthedocs.io/
- Eastron SDM120 Modbus protocol, register table, https://www.eastroneurope.com/products/view/sdm120modbus
