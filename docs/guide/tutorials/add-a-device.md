# Add a device

Most devices need only a [Device File](glossary:device-file), with no new code. The [device file format](../../../spec/SPEC.md) defines every field.

## Pick a driver

A device file names one [Driver](glossary:driver). [Drivers](/drivers/) lists every driver, and [Build a driver](build-a-driver.md) covers a protocol with no driver yet.

## Describe the device

Set each limit at or inside what you would accept with nobody watching.

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
- A file never holds a password or token, and names an environment variable instead, as in `token_env: HA_TOKEN`.

## Validate the file

```sh tested
$ uv run openhal file validate led-strip.hal.yaml
valid  led-strip.hal.yaml
```

The [playground](/spec/playground/) runs the same schema in the browser.

## Confirm the limits

Read each limit before you type `confirm`.

```sh tested
$ uv run openhal file confirm led-strip.hal.yaml --by owner
control brightness  0 % to 80 %, at most 40 %/s
```

The file now records the confirmer, the date and a hash of the limits.

## Test the file

Copy the file into `~/.openhal/devices/` and run `uv run openhal start`, or run `uv run openhal file confirm` on the copy when the hub already runs. Read every channel, then try each change at the smallest value. Run `uv run openhal stop`, check the safe state, and record what you tested in `provenance.verification`.

| Status | Meaning |
|---|---|
| `unverified` | Not yet run against the real device |
| `tested-reads` | Reads checked on the real device |
| `verified-on-hardware` | Reads, changes and the safe state checked on the real device, with a report |

## Share the file

Open a pull request that adds the file under `library/`, one CC0 file per model. The [Device Library](/library/) lists each file with a badge.
