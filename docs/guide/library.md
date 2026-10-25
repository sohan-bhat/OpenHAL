# Device library

The device library is a set of starter device files for real products. It lives in `library/` in the repository and ships with the hub. [library/README.md](../../library/README.md) lists every file.

## Matching

`openhal discover` asks each driver what it can see. Drivers send only read-only identify commands. Each one reports identifiers, such as a USB vendor and product id, a Bluetooth name or an ESPHome project name. The hub compares them with the `match` section of every library file and offers the file that fits best.

A USB class or an mDNS service type only says what kind of device it is. It adds to a match but never makes one alone, so a MIDI keyboard is never offered the file for a different MIDI controller.

Some drivers can't report a product identifier yet. The midi driver lists port names only, and the rpi-gpio, rpi-camera and alpaca drivers report identifiers no match key holds. The moonraker, homeassistant, modbus and mqtt drivers don't discover anything. Add their files by name.

## Adding a file

```console tested
$ openhal library list --driver scpi
rigol-dp832
$ openhal library show rigol-dp832
match  usb 1ab1:0e11
$ openhal library add rigol-dp832
added
```

`add` copies the file into your devices folder exactly as it is. It never adds a confirmation and never overwrites a file that is already there.

## Suggested limits

Every library file is unverified. Its writes and actions are marked `suggested: true`, and its notes start with "Suggested limits." The limits start low on purpose, such as 5 V and 0.5 A on a bench supply or PLA temperatures on a printer. Anything with heat, motion or mains power needs a person to confirm each change.

## Confirmation

A library file loads read-only. The hub lets nothing change the device until you do four things.

1. Set the connection, such as the host name, the serial port or the entity ids.
2. Check each limit against your device and what is wired to it, change it if you need to, and remove `suggested: true`.
3. Run `openhal file confirm` on the file. You type confirm, and it records your name, the date and a hash of the limits.
4. Restart `openhald`.

Changing any limit later makes the file read-only again until you confirm it again.

## Adding a product

Add one file per product model as `library/<driver package>/<maker>-<model>.hal.yaml`, with an `id` that matches the file name. Use real identifiers and cite where each one comes from in docs/research/SOURCES.md. Give the file library provenance with the status unverified, mark every write and action suggested, and never add `confirmed`. Then run `uv run python -m openhal.cli.library_cmd` to update the list. The tests in tests/library check all of this.
