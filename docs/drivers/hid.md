# hid driver

The hid driver reads input and feature reports from USB HID devices and writes output and feature reports, through hidapi. The driver suits macropads, knobs, foot switches, status lights and homemade gadgets with a documented report layout. Fields are bools, numbers or enums at any byte offset, with an optional bit mask.

## Setup

```sh
uv tool install --compile-bytecode "halkit[hid] @ git+https://github.com/sohan-bhat/OpenHAL"
```

On Linux a regular user needs a udev rule such as `/etc/udev/rules.d/70-openhal-hid.rules` containing `KERNEL=="hidraw*", ATTRS{idVendor}=="1209", ATTRS{idProduct}=="0001", MODE="0660", TAG+="uaccess"`, then `sudo udevadm control --reload` and a replug. On macOS, devices that send keyboard reports may need Input Monitoring permission. `discover()` lists interfaces without opening any.

| Parameter | Default | Meaning |
|---|---|---|
| `name` | `auto` | Part of the product string, any case. `hid: auto` is shorthand |
| `vid`, `pid` | from a single `match.usb` entry | Vendor and product id, decimal or `0x` hex |
| `serial` | none | Picks one of several identical devices |
| `path` | none | Exact hidapi path from `discover()` |
| `usage_page` | none | Picks one interface of a composite device |
| `interface` | none | USB interface number, for the same purpose |
| `report_length` | `64` | Largest report read, in bytes after the report id |
| `timeout` | `1 s` | Feature read and write deadline |

Exactly one interface must match, or connect fails listing the candidates.

## Channel maps

```yaml
read:
  key_1: { type: bool, stream: true, map: { report: 1, byte: 0, mask: 0x01 } }
  knob: { unit: percent, stream: true, map: { report: 1, byte: 1, scale: 0.392156862745098 } }
  mode: { unit: dimensionless, map: { report: 3, kind: feature } }
write:
  key_1_led: { type: bool, map: { report: 2, kind: output, byte: 0, mask: 0x01, length: 2 } }
  brightness: { unit: dimensionless, min: 0, max: 255, step: 1, map: { report: 2, kind: output, byte: 1 } }
```

| Key | Default | Meaning |
|---|---|---|
| `report` | `0` | Report id, 0 for devices without ids |
| `kind` | `input` | `input` or `feature` for reads, `output` or `feature` for writes |
| `byte` | `0` | Offset after the report id byte |
| `format` | `uint8` | `uint8`, `int8`, `uint16`, `int16`, `uint32`, `int32` |
| `byteorder` | `little` | Some vendor reports are big-endian |
| `mask` | none | Bit mask, with the value shifted down to the mask's lowest bit |
| `scale`, `offset` | `1`, `0` | value = raw × scale + offset |
| `on`, `off` | `1`, `0` | Raw bool values |
| `values` | none | Enum word to raw value, required for enums |
| `length` | end of the furthest field | Output or feature payload length |
| `fill` | zeros | Starting bytes, for reports with a command byte |

A write changes only the channel's bits and sends the whole report. Output channels read back the last value sent. Input reads return the newest report, so a button never pressed reads as unknown.

## Describe

`describe()` parses the report descriptor and suggests a channel per whole-byte or single-bit field, named from the usage tables or `field_r<report>_b<bit>`, with the logical range as `range` or limits. Feature and odd-sized fields go in the notes.

## Example

`openhal/drivers/hid/examples/diy-macropad.hal.yaml` describes a homemade macropad with four keys, a knob and key LEDs.

## Errors and health

- `DriverError` for no match, several matches, a device held elsewhere or blocked by permissions, short reports, unmapped enum values, values too big for the field and reports the device fails.
- A failed read marks the device gone in `health()`, and the hub reopens the device on return.

## Limitations

- `describe()` skips long items and fields that are neither whole bytes nor single bits.
- Keyboards, mice and gamepads the OS claims, especially keyboards on macOS and Windows, may not open.
- No actions.

## Hazard default and safe state

Low. `safe_state_support` is `file`, sent as ordinary reports.

## Sources

- Device Class Definition for HID 1.11, USB-IF, https://www.usb.org/document-library/device-class-definition-hid-111
- HID Usage Tables 1.5, USB-IF, https://www.usb.org/document-library/hid-usage-tables-15
- hidapi, https://github.com/libusb/hidapi
- cython-hidapi, the `hidapi` Python package, https://github.com/trezor/cython-hidapi
- pid.codes test PID `1209:0001`, https://pid.codes/1209/0001/
