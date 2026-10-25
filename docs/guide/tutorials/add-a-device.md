# Add a device

Most devices need a [Device File](glossary:device-file) and no new code. This tutorial creates one, validates it, confirms it and shares it. The [device file format](../../../spec/SPEC.md) defines every field.

## Pick a driver

A device file names one [Driver](glossary:driver). [Drivers](/drivers/) lists each one and its status. If no driver speaks your device's protocol, see [Build a driver](build-a-driver.md).

## Describe the device

List what the device can do, then add the limits. Keep each limit at or inside what you would accept with nobody watching.

```yaml tested file=led-strip.hal.yaml
openhal: "0.1"
device: { name: Bench LED strip, manufacturer: OpenHAL community, model: WS2812 strip on Uno }
id: led-strip
connect: { openhal-firmware: auto, baud: 115200 }
match:
  firmware: { product: led-strip }
read:
  current_draw: { unit: A, every: 1 s, range: [0, 3] }
write:
  brightness: { unit: percent, min: 0, max: 80, step: 1, max_change_per_s: 40 }
  power: { type: bool }
interlocks:
  - if: "brightness > 60 %"
    require: "current_draw < 2 A"
    message: "The strip's supply is rated for 2 A."
safe_state: { brightness: 0, power: false }
hazard: low
provenance:
  source: hand-written
  verification: { status: unverified }
```

- Every number channel has a unit.
- Every number channel you can change has `min` and `max`.
- Every file has a `safe_state`.
- A file never holds a password or token. It names an environment variable, as in `token_env: HA_TOKEN`.

## Validate it

```sh tested
$ uv run openhal file validate led-strip.hal.yaml
valid  led-strip.hal.yaml
```

The [playground](/spec/playground/) runs the same schema in the browser.

## Confirm the limits

Only a person may confirm limits. Read each limit before you type `confirm`.

```sh tested
$ uv run openhal file confirm led-strip.hal.yaml --by owner
write   brightness  0 % to 80 %, at most 40 %/s
```

The file now records who confirmed it, the date and a hash of the limits.

## Test it

Copy the file into `~/.openhal/devices/` and restart the hub. Read every channel, then try each change at its smallest value. Run `uv run openhal stop` and check the device reached its safe state. Record what you tested in `provenance.verification`.

| Status | Meaning |
|---|---|
| `unverified` | Not yet run against the real device |
| `tested-reads` | Reads checked on the real device |
| `verified-on-hardware` | Reads, changes and the safe state checked on the real device, with a report |

## Share it

Open a pull request that adds the file under `library/`, one file per device model. Files there are CC0. The [Device Library](/library/) lists each file with its badge.
