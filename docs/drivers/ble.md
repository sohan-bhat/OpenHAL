# ble driver

The ble driver reads and writes GATT characteristics of Bluetooth Low Energy peripherals through bleak, on Linux with BlueZ, macOS and Windows.

## Supports

- Number, bool, enum and string reads. `stream: true` subscribes to notifications or indications.
- Writes with or without response, replacing the whole characteristic.
- Every GATT Specification Supplement number format, including IEEE 11073 `sfloat` and `float`.
- `address: auto` picks the one advertiser matching `match.ble_name` and `match.ble_services`. `discover()` lists advertisers without connecting.
- `identify()` and `describe()` read the Device Information service.

## Setup

```sh
uv tool install --compile-bytecode "halkit[ble] @ git+https://github.com/sohan-bhat/OpenHAL"
```

Linux needs BlueZ 5.55 or newer and the `bluetooth` group. On macOS the app running the hub needs Bluetooth permission, and peripherals use a CoreBluetooth UUID from `discover()` instead of a MAC address.

| Parameter | Default | Meaning |
|---|---|---|
| `address` | `auto` | MAC address, CoreBluetooth UUID on macOS, or `auto`. `ble: auto` is shorthand |
| `scan_timeout` | `5 s` | Scan time for `auto` |
| `timeout` | `10 s` | Connect, read and write deadline |
| `pair` | `false` | Pair on connect, for encrypted characteristics |

## Channel maps

```yaml
read:
  temperature: { unit: degC, stream: true, map: { characteristic: 2a6e, format: sint16, scale: 0.01 } }
  battery: { unit: percent, map: { characteristic: 2a19 } }
write:
  led: { unit: percent, min: 0, max: 100, map: { characteristic: 6e400002-b5a3-f393-e0a9-e50e24dcca9e, scale: 0.5 } }
```

| Key | Default | Meaning |
|---|---|---|
| `characteristic` | required | 16-bit SIG UUID such as `2a6e`, or a 128-bit UUID |
| `service` | none | Service UUID, when the characteristic is in several services |
| `format` | `uint8` | `uint8`, `uint16`, `uint24`, `uint32`, `sint8` to `sint32`, `float32`, `float64`, `sfloat`, `float`, `utf8` |
| `byte` | `0` | Byte offset. Reads only |
| `byteorder` | `little` | Some vendor characteristics are big-endian |
| `scale`, `offset` | `1`, `0` | value = raw × scale + offset |
| `on`, `off` | `1`, `0` | Raw bool values |
| `values` | none | Enum word to raw value, required for enums |
| `response` | device default | Write with or without response |

Writes send `raw = (value - offset) / scale`, rounded for integer formats, and return the value sent. A value outside the format fails with nothing sent.

A `stream: true` channel returns the newest notification, or a GATT read before the first one, or `None` when the characteristic has no read. Other channels read each time. A write-only characteristic reports the last value written.

## Describe

| Characteristic | Channel | Format | Scale | Unit |
|---|---|---|---|---|
| 0x2A6E Temperature | `temperature` | sint16 | 0.01 | degC |
| 0x2A6F Humidity | `humidity` | uint16 | 0.01 | percent |
| 0x2A6D Pressure | `pressure` | uint32 | 0.1 | Pa |
| 0x2A76 UV Index | `uv_index` | uint8 | 1 | dimensionless |
| 0x2A6C Elevation | `elevation` | sint24 | 0.01 | m |
| 0x2A19 Battery Level | `battery_level` | uint8 | 1 | percent |

`describe()` suggests these channels, fills `device` and `match.ble_services`, and lists vendor characteristics in the notes.

## Example

`openhal/drivers/ble/examples/environment-sensor.hal.yaml` reads a room sensor's Environmental Sensing service.

## Errors

- `DriverError` for no match or several matches under `auto`, failed connects, missing characteristics, GATT errors, short values, IEEE 11073 NaN, NRes and infinity, and non-finite floats.
- `TimeoutError` past `timeout`.

## Limitations

- No actions, images or descriptors.
- Most peripherals take one central, so close the vendor's phone app.
- Values split across characteristics or behind a flags byte, such as Health Thermometer, need a dedicated driver.
- No advertisement-only sensors yet.

## Hazard default and safe state

Low. `safe_state_support` is `file`, and the hub writes `safe_state` only while the link is up. Many peripherals keep their last state when the link drops.

## Sources

- Bluetooth Core Specification 5.4, Vol 3, Part G, Generic Attribute Profile, https://www.bluetooth.com/specifications/specs/core-specification-5-4/
- GATT Specification Supplement, https://www.bluetooth.com/specifications/gss/
- Assigned Numbers for UUIDs and format types, https://www.bluetooth.com/specifications/assigned-numbers/
- Environmental Sensing Service 1.0, https://www.bluetooth.com/specifications/specs/environmental-sensing-service-1-0/
- IEEE 11073-20601 SFLOAT and FLOAT types, as summarised in the GATT Specification Supplement
- bleak documentation, https://bleak.readthedocs.io/
