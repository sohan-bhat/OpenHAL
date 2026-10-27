# hid driver

The hid driver reads input reports from USB HID devices and sends output and feature reports to them, through hidapi. The driver suits macropads, knobs, foot switches, status lights and homemade HID gadgets whose report layout is documented. `describe()` reads the device's report descriptor and proposes channels from it.

## What it supports

- Input reports, read by a background thread as they arrive. Each read decodes the newest report.
- Feature reports, read with a GET_REPORT request each time and written with SET_REPORT.
- Output reports, written as whole reports from a buffer the driver keeps per report.
- Fields at any byte offset, as `uint8`, `int8`, `uint16`, `int16`, `uint32` or `int32`, with an optional bit mask for single bits and packed fields.
- Bool, number and enum channels.
- `discover()` lists HID interfaces without opening them. `describe()` parses the report descriptor.

## Setup

```sh
uv tool install --compile-bytecode "openhal-hub[hid] @ git+https://github.com/sohan-bhat/OpenHAL"
```

The `hidapi` package bundles the hidapi C library. On Linux, a regular user can only open HID devices with a udev rule, for example `/etc/udev/rules.d/70-openhal-hid.rules` containing `KERNEL=="hidraw*", ATTRS{idVendor}=="1209", ATTRS{idProduct}=="0001", MODE="0660", TAG+="uaccess"`, then `sudo udevadm control --reload` and replug the device. On macOS, the app running the hub may need Input Monitoring permission for devices that send keyboard reports.

## Parameters

| Parameter | Default | Meaning |
|---|---|---|
| `name` | `auto` | Part of the product string, matched without case. The shorthand `hid: auto` sets it |
| `vid`, `pid` | from `match.usb` when it has exactly one entry | USB vendor and product id, as numbers or `0x` hex |
| `serial` | none | Serial number, to pick one of several identical devices |
| `path` | none | Exact hidapi path, from `discover()` |
| `usage_page` | none | HID usage page, to pick one interface of a composite device |
| `interface` | none | USB interface number, for the same reason |
| `report_length` | `64` | Largest report the driver reads, in bytes after the report id |
| `timeout` | `1 s` | Deadline for feature reads and for writes |

Exactly one interface must match, otherwise connect fails and lists the candidates.

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
| `report` | `0` | Report id. Use 0 for devices without report ids |
| `kind` | `input` | `input` for read channels, `output` or `feature` for write channels. Read channels can also use `feature` |
| `byte` | `0` | Byte offset into the report, after the report id byte |
| `format` | `uint8` | `uint8`, `int8`, `uint16`, `int16`, `uint32`, `int32` |
| `byteorder` | `little` | HID fields are little-endian. Some vendor reports are big-endian |
| `mask` | none | Bit mask inside the field. The value is shifted down by the mask's lowest bit |
| `scale`, `offset` | `1`, `0` | channel value = raw × scale + offset |
| `on`, `off` | `1`, `0` | Raw values for bool channels |
| `values` | none | Enum word to raw value, required for enum channels |
| `length` | the end of the furthest field | Length of the output or feature report payload |
| `fill` | zeros | Starting bytes for an output or feature report, for reports with a command byte |

When several write channels share one output report, a write changes only that channel's bits and sends the whole report, so the other channels keep the values last written. Write channels on output reports read back the last value the driver sent, or no value before the first write.

## How reads work

The device decides when to send input reports. A read returns the newest input report for the channel's report id, stamped with the time it arrived, and no value (`None`) until the first report, which the kernel treats as unknown. Most devices send a report whenever something changes, so a button that has never been pressed reads as unknown until it is.

## Describe

`describe()` parses the report descriptor (USB HID 1.11 section 6.2.2) and proposes one channel per data field that sits on whole bytes (8, 16 or 32 bits) or is a single bit. Buttons, LEDs and the generic desktop axes get names from the usage tables, other fields get `field_r<report>_b<bit>`. Input fields become read channels with their logical range as `range`. Output fields become write channels marked `suggested: true`, with the logical range as limits. Feature fields and odd-sized fields are listed in the notes.

## Example

`openhal/drivers/hid/examples/diy-macropad.hal.yaml` describes a homemade macropad with four keys, a knob and key LEDs.

## Errors and health

- No match, several matches, or a device that can't be opened (held by another program or blocked by permissions) raises `DriverError` with what to do.
- Reports too short for the map, enum raw values outside the map, values that don't fit the field and reports the device refuses raise `DriverError`.
- A failed read in the reader thread marks the device as gone, `health()` reports it, and the hub reopens the device when it comes back.

## Limitations

- `describe()` skips long items in report descriptors and doesn't propose fields that are neither whole bytes nor single bits.
- Keyboards, mice and gamepads that the operating system claims exclusively can't be opened on some platforms (macOS and Windows keyboards in particular).
- No actions. Model each report field as a channel.

## Hazard default and safe state

The default hazard is low, because HID devices are mostly inputs and indicators. HID has no emergency behavior, so `safe_state_support` is `file`, and the hub sends the device file's `safe_state` as ordinary reports. A HID gadget that switches something physical deserves a higher hazard in its device file.

## Sources

- Device Class Definition for HID 1.11, USB-IF, https://www.usb.org/document-library/device-class-definition-hid-111
- HID Usage Tables 1.5, USB-IF, https://www.usb.org/document-library/hid-usage-tables-15
- hidapi, https://github.com/libusb/hidapi
- cython-hidapi (the `hidapi` Python package), https://github.com/trezor/cython-hidapi
- pid.codes test PID `1209:0001`, https://pid.codes/1209/0001/
