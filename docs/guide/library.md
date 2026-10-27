# Device library

The device library is a set of starter device files for real products, kept in `library/` in the repository and shipped with the hub. [library/README.md](../../library/README.md) lists every file.

## Matching

`openhal discover` runs each driver's discovery, and the drivers send only read-only identify commands. Each driver reports identifiers, such as a USB vendor and product id, a Bluetooth name or an ESPHome project name, and the hub compares the identifiers with the `match` section of every library file and offers the file that fits best.

Because a USB class or an mDNS service type only names a kind of device, a class or a type adds to a match but never makes a match alone, so a MIDI keyboard is never offered the file for a different MIDI controller.

Some drivers can't report a product identifier yet. The midi driver lists port names only, and the rpi-gpio, rpi-camera and alpaca drivers report identifiers no match key holds. The moonraker, homeassistant, modbus and mqtt drivers don't discover anything, so add the files for those drivers by name.

## Adding a file

```console tested
$ openhal library list --driver scpi
rigol-dp832
$ openhal library show rigol-dp832
match  usb 1ab1:0e11
$ openhal library add rigol-dp832
added
```

`add` copies the file into your devices folder unchanged, and `add` never adds a confirmation or overwrites a file that is already there.

## Suggested limits

A library file's control channels and actions are marked `suggested: true`, and its notes start with "Suggested limits." The suggested limits deliberately start low, such as 5 V and 0.5 A on a bench supply or PLA temperatures on a printer. Anything with heat, motion or mains power needs a person to confirm each change.

## Confirmation

A library file loads read-only, and the hub refuses every change to the device until you do four things.

1. Set the connection, such as the host name, the serial port or the entity ids.
2. Check each limit against your device and what is wired to the device, change the limit if you need to, and remove `suggested: true`.
3. Run `openhal file confirm` on the file. You type confirm, and the command records your name, the date and a hash of the limits.
4. Restart `openhald`.

Changing any limit later makes the file read-only again until you confirm the file again.

## Adding a product

Add one file per product model as `library/<driver package>/<maker>-<model>.hal.yaml`, with an `id` that matches the file name. Use real identifiers and cite where each identifier comes from in docs/research/SOURCES.md. Give the file library provenance with the status unverified, mark every control channel and action suggested, and never add `confirmed`. Then run `uv run python -m openhal.cli.library_cmd` to update the list. The tests in tests/library check every one of these rules.
