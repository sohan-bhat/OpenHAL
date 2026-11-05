# Device library

The device library holds starter device files for real products, shipped with the hub. [library/README.md](../../library/README.md) lists every file.

## Matching

`openhal discover` runs each driver's discovery with read-only identify commands. Drivers report identifiers such as a USB vendor and product id, a Bluetooth name or an ESPHome project name, and the hub returns the library file whose `match` section fits best.

A USB class or mDNS service type only names a kind of device, so a class or type adds to a match but never makes a match alone.

Some drivers report no product identifier yet. midi lists port names only, and rpi-gpio, rpi-camera and alpaca report identifiers no match key holds. moonraker, homeassistant, modbus and mqtt don't discover anything, so add files for those drivers by name. An RS-232 instrument on the serial driver shows only the USB serial adapter's identifiers, so add a serial file such as the Mettler Toledo balance by name too.

## Adding a file

```console tested
$ openhal library list --driver scpi
rigol-dp832
$ openhal library show rigol-dp832
match  usb 1ab1:0e11
$ openhal library add rigol-dp832
added
```

`add` copies the file into your devices folder unchanged. `add` never adds a confirmation or overwrites an existing file.

## Suggested limits

Control channels and actions in a library file are marked `suggested: true`, and the notes start with "Suggested limits." The suggestions start low, such as 5 V and 0.5 A on a bench supply or PLA temperatures on a printer. Anything with heat, motion or mains power needs a person to confirm each change.

## Confirmation

Low and medium entries take commands within the file's range once the connection is set. High risk entries, such as a heater or a mains relay, stay read-only until you do two things.

1. Set the connection, such as the host name, serial port or entity ids.
2. Run `openhal file confirm` on the file and answer each limit, where Enter keeps the suggestion, then type `confirm`. The file records your name, the date and a hash of the limits, and a running hub loads the file at once.

To change a limit later, run `openhal limits set DEVICE.CHANNEL` with `--min`, `--max` or `--rate`. The change goes into the file, and the confirmation binds to the new limits. A wider limit takes your typed confirm.

## Adding a product

Add one file per model as `library/<driver package>/<maker>-<model>.hal.yaml`, with an `id` that matches the file name. Use real identifiers and cite each source in docs/research/SOURCES.md. Give the file library provenance with the status unverified, mark every control channel and action suggested, and never add `confirmed`. Then run `uv run python -m openhal.cli.library_cmd` to update the list. tests/library checks every rule.
