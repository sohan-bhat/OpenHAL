# ble driver

The ble driver reads and writes GATT characteristics of Bluetooth Low Energy peripherals, through bleak. It runs on Linux (BlueZ), macOS (CoreBluetooth) and Windows (WinRT). Each channel's map names a characteristic UUID, the value format, a byte offset and a scale. `describe()` maps the standard Environmental Sensing and Battery services by itself.

## What it supports

- Read channels of type number, bool, enum and string from any readable or notifying characteristic.
- `stream: true` read channels subscribe to notifications or indications when the driver connects.
- Write channels to writable characteristics, with or without response.
- All GATT Specification Supplement number formats, including the IEEE 11073 `sfloat` and `float` medical formats.
- `address: auto`, which scans advertisements and picks the one peripheral matching `match.ble_name` and `match.ble_services`.
- `discover()`, which lists advertising peripherals without connecting.
- `identify()` and `describe()` read the Device Information service.

## Setup

```sh
uv pip install 'openhal-hub[ble]'
```

On Linux, BlueZ 5.55 or newer must be running and your user needs access to it (usually the `bluetooth` group). On macOS, the terminal or app running the hub needs Bluetooth permission in System Settings, and peripherals are addressed by the UUID CoreBluetooth assigns, not by MAC address. Run `discover()` (or the hardware test plan's step 1) to find it.

## Parameters

| Parameter | Default | Meaning |
|---|---|---|
| `address` | `auto` | MAC address on Linux and Windows, CoreBluetooth UUID on macOS, or `auto`. The shorthand `ble: auto` sets it |
| `scan_timeout` | `5 s` | How long `auto` listens for advertisements |
| `timeout` | `10 s` | Connect, read and write deadline |
| `pair` | `false` | Ask the OS to pair while connecting. Needed by devices with encrypted characteristics |

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
| `characteristic` | required | 16-bit SIG UUID such as `2a6e`, or a full 128-bit UUID |
| `service` | none | Service UUID, when the same characteristic appears in more than one service |
| `format` | `uint8` | `uint8`, `uint16`, `uint24`, `uint32`, `sint8` to `sint32`, `float32`, `float64`, `sfloat`, `float`, `utf8` |
| `byte` | `0` | Byte offset of the value inside the characteristic. Read channels only |
| `byteorder` | `little` | GATT values are little-endian. Some vendor characteristics are big-endian |
| `scale`, `offset` | `1`, `0` | channel value = raw × scale + offset |
| `on`, `off` | `1`, `0` | Raw values for bool channels |
| `values` | none | Enum word to raw value, required for enum channels |
| `response` | the device's choice | `true` for write with response, `false` for write without response |

Writes encode raw = (value - offset) / scale, rounded for integer formats, and the returned reading shows the value really sent. Values that don't fit the format fail with `DriverError` and nothing is sent. Writes always replace the whole characteristic value.

## How reads work

A `stream: true` channel returns the newest notification. Before the first notification it does a GATT read if the characteristic allows one, and otherwise reports no value (`None`), which the kernel treats as unknown. Other channels do a GATT read every time. A write channel on a write-only characteristic reports the last value the driver wrote.

## Describe

`describe()` proposes read channels for the standard characteristics it finds, with their units, formats and scales.

| Characteristic | Channel | Format | Scale | Unit |
|---|---|---|---|---|
| 0x2A6E Temperature | `temperature` | sint16 | 0.01 | degC |
| 0x2A6F Humidity | `humidity` | uint16 | 0.01 | percent |
| 0x2A6D Pressure | `pressure` | uint32 | 0.1 | Pa |
| 0x2A76 UV Index | `uv_index` | uint8 | 1 | dimensionless |
| 0x2A6C Elevation | `elevation` | sint24 | 0.01 | m |
| 0x2A19 Battery Level | `battery_level` | uint8 | 1 | percent |

It also fills `device` from the Device Information service and `match.ble_services` from the service list, and lists every vendor characteristic with its properties in the notes, because their formats can't be known without the device's documentation.

## Example

`openhal/drivers/ble/examples/environment-sensor.hal.yaml` reads a room sensor with the standard Environmental Sensing service, found by name and service.

## Errors

- No matching advertiser, or more than one, for `address: auto` raises `DriverError` listing the candidates.
- Connect failures, missing characteristics, refused reads and writes raise `DriverError` with what to check.
- No answer within `timeout` raises `TimeoutError`.
- Values too short for the format, IEEE 11073 special values (NaN, NRes, infinity) and non-finite floats raise `DriverError`.

## Limitations

- No actions, no image channels and no descriptors.
- Only one central can usually connect to a peripheral. Close the vendor's phone app first.
- Values that are split over several characteristics, or that need a flags byte to parse (such as Health Thermometer measurements), need a dedicated driver.
- Broadcast-only sensors that put readings in advertisements without a GATT server are not covered yet.

## Hazard default and safe state

The default hazard is low, because most BLE peripherals are sensors, lights and small gadgets. BLE has no emergency behavior of its own, so `safe_state_support` is `file`. The hub writes the device file's `safe_state` like any other value, which only works while the link is up. Many peripherals keep their last state when the link drops, so don't rely on BLE alone for anything that must turn off.

## Sources

- Bluetooth Core Specification 5.4, Vol 3, Part G (Generic Attribute Profile), https://www.bluetooth.com/specifications/specs/core-specification-5-4/
- GATT Specification Supplement, https://www.bluetooth.com/specifications/gss/
- Assigned Numbers (UUIDs, format types), https://www.bluetooth.com/specifications/assigned-numbers/
- Environmental Sensing Service 1.0, https://www.bluetooth.com/specifications/specs/environmental-sensing-service-1-0/
- IEEE 11073-20601 (SFLOAT and FLOAT types), as summarised in the GATT Specification Supplement
- bleak documentation, https://bleak.readthedocs.io/
