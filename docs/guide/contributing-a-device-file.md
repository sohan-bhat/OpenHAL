# Contributing a device file

Most devices need a device file and no new code. This guide writes one by hand, checks it, confirms it and gets it ready for the shared library. The [spec](../../spec/SPEC.md) is the reference for every field.

## Find the driver

A driver speaks one protocol, and a device file picks one. [Supported devices](../drivers/COVERAGE.md) lists every driver and its status. If your device runs the [OpenHAL Arduino library](../../firmware/arduino/OpenHAL/README.md), it describes itself and the driver writer can draft the file for you. If no driver can talk to the device, [writing a driver](../drivers/WRITING-A-DRIVER.md) explains the contract.

## Write the file

Start with what the device can do, then add the limits. Keep every limit at or inside what you would accept with nobody watching.

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
notes: "Powered from a separate 5 V supply. The Uno only drives the data line."
provenance:
  source: hand-written
  verification: { status: unverified }
```

A few rules catch most mistakes.

- Every number channel has a unit. Use `dimensionless` for plain counts.
- Every number write channel has `min` and `max`. Add `step` and `max_change_per_s` where the device needs them.
- Give the file a `safe_state`. Without one the hub reports the device as having no safe state when you stop.
- Never put a password or token in the file. Name an environment variable instead, as in `token_env: HA_TOKEN`.
- `notes` are for people and agents to read. The hub treats them as data and never as instructions.

## Check it

```sh tested
$ openhal file validate led-strip.hal.yaml
valid  led-strip.hal.yaml
```

The validator gives the exact place of each problem. The [playground](/playground/) runs the same schema in the browser while you type, and shows the controls the dashboard would draw.

## Confirm the limits

Only a person may confirm limits. Read every limit the command prints before you type `confirm`.

```sh tested
$ openhal file confirm led-strip.hal.yaml --by owner
write   brightness  0 % to 80 %, at most 40 %/s
```

The file now carries `confirmed` with your name, the date and a hash of the limits. A tool must never add that line for you.

## Test on the device

Copy the file into `~/.openhal/devices/` and restart the hub. Read every channel first. Then try each write at its smallest value, and check the device did what the file says. Stop the hub with `openhal stop` and check the device reached its safe state.

Record what you tested in `provenance.verification`.

| Status | Meaning |
|---|---|
| `unverified` | Nobody has run it against the real device yet |
| `tested-reads` | Reads were checked on the real device |
| `verified-on-hardware` | Reads, writes and the safe state were checked on the real device, with a report |

`verified-on-hardware` needs a `report` path, written from the hardware test plan for the driver.

## Share it

The shared library lives in `library/` in the repository, one file per device model. Files there are CC0, so anyone can copy them into their own projects. Your name stays in the file's provenance. Open a pull request that adds your file under `library/`, with the verification status you reached and the report if you have one. The [device library](/library/) page lists every file in the folder with its badge.
