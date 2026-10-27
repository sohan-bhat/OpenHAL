# OpenHAL firmware protocol, version 1

This page defines the wire protocol between the hub's `openhal-firmware` driver and a board running the OpenHAL Arduino library (firmware/arduino/OpenHAL/). A board that speaks the protocol describes itself, so the hub can build the board's device file without a person typing channels.

The board also enforces its own limits as defense in depth, but the hub's safety kernel is still the authority, and nothing in this protocol can widen a limit the device file sets.

## Transport

- The transport is a serial line (USB CDC, UART) at a default of 115200 baud, 8N1.
- Messages are ASCII text, one message per line, and lines end with `\n` (a preceding `\r` is ignored).
- Lines are at most 250 bytes, except the `DESC` reply, which may be up to 1,500 bytes.

## Message format

```
<seq> <verb> [arg ...]*<checksum>
```

- `seq` is a decimal number from 1 to 65535 chosen by the host, and the board echoes the number in its reply, while unsolicited board messages use `0`.
- `verb` is an uppercase word, arguments are separated by single spaces, and names match `[a-z][a-z0-9_]{0,23}`. Numbers are decimal, with an optional sign and decimal point.
- `*<checksum>` is two uppercase hex digits, the XOR of every byte before the `*`. Both sides check the checksum and discard lines with a wrong or missing checksum.

## Host to board

| Verb | Arguments | Reply | Meaning |
|---|---|---|---|
| `HELLO` | | `OK openhal 1 <product> <firmware-version>` | Identify the board with a read-only command that is safe to send to an unknown device during discovery |
| `DESC` | | `DESC <json>` | The capability document below |
| `READ` | `<name>` | `VAL <name> <value>` | Read one channel. A channel with states returns the state's name |
| `WRITE` | `<name> <value>` | `OK <name> <value>` or `ERR <code> <detail>` | Set one write channel. The board checks its own min and max first |
| `ACT` | `<name> [<arg> <value> ...]` | `OK <name>` or `ERR <code> <detail>` | Run one action, giving every argument the action declares once, in any order. The board checks each argument against its own min and max, then its own conditions |
| `HB` | | `OK` | Heartbeat. The board falls to its safe state if heartbeats stop for `hb` milliseconds |
| `SAFE` | | `OK` | Apply the safe state now |

## Board to host

| Message | Meaning |
|---|---|
| `0 EVT <name> <value>` | A streamed value (the board's channel has `every` set) |
| `0 SAFE <reason>` | The board applied its safe state on its own. Reasons include `heartbeat_lost`, `<name>_timeout` and whatever the sketch passes, such as the plant waterer's `tank_empty` |
| `<seq> ERR <code> <detail>` | A request failed. Codes are `unknown` (verb, channel or action), `limit` (outside the board's own limits), `format` (bad argument), `interlock` (the sketch refused the action, with its reason such as `tank_empty`), `checksum`, `fault` (the sensor returned no value), `busy` (the board refused commands because its sketch registered channels wrongly) |


## Capability document

The `DESC` reply is a compact JSON object, and the plant waterer (examples/plant-waterer/) reports its float switch as states and offers actions. Because the plant waterer's pump is an output the sketch keeps to itself, `w` is empty and the pump runs only through `water`.

```json
{
  "p": "plant-waterer",
  "v": "1.0.0",
  "hb": 3000,
  "r": [{ "n": "soil_moisture", "u": "percent", "e": 1000, "lo": 0, "hi": 100 },
        { "n": "tank", "u": "enum", "e": 1000, "s": ["empty", "ok"] }],
  "w": [],
  "a": [{ "n": "water", "g": [{ "n": "duration", "u": "s", "min": 1, "max": 30 }] }, { "n": "stop", "g": [] }]
}
```

| Key | Meaning |
|---|---|
| `p` | Product name, matched by the library through `match.firmware.product` |
| `v` | Firmware version |
| `hb` | Heartbeat timeout in milliseconds (0 means none) |
| `r` | Read channels. `n` name, `u` unit, `e` streaming interval in milliseconds (0 means on request), optional `lo` and `hi` sanity range |
| `w` | Write channels. `n`, `u`, `min`, `max`, `safe` (the safe-state value), optional `rate` (unit per second) and `t` (milliseconds after which the board returns the output to `safe` on its own). A unit of `bool` marks an on and off output with values 0 and 1. An output the sketch keeps to itself is left out, and a `WRITE` to that output returns `ERR unknown`, while `SAFE` and a lost heartbeat still return the output to `safe` |
| `r` with `s` | A channel with states, such as a float switch. `u` is `enum` and `s` lists the state names, at most 8. `VAL` and `EVT` carry the name |
| `a` | Actions, at most 4. `n` name and `g` its arguments, at most 3, each with `n`, `u`, `min` and `max` |

The library's LedStrip example reports its one write channel as `{ "n": "brightness", "u": "percent", "min": 0, "max": 100, "safe": 0, "rate": 50 }`.

The hub turns the capability document into a draft device file with every limit marked `suggested: true`, and a human still confirms the limits in the interview and may tighten the limits below what the board allows.

## Example session

This session shows the plant waterer with a watering request over the board's own limit, a watering that runs, the tank running dry, and a `WRITE` to the pump the sketch keeps to itself.

```
host  1 HELLO*53
board 1 OK openhal 1 plant-waterer 1.0.0*4C
host  2 READ soil_moisture*68
board 2 VAL soil_moisture 31*03
host  3 ACT water duration 120*3D
board 3 ERR limit duration max 30*4A
host  4 ACT water duration 20*0B
board 4 OK water*45
board 0 EVT soil_moisture 46*1D
board 0 EVT tank empty*32
host  5 ACT water duration 20*0A
board 5 ERR interlock tank_empty*05
host  6 WRITE pump 1*62
board 6 ERR unknown pump*23
board 0 SAFE heartbeat_lost*02
```

The checksums are real values that `openhal.drivers.openhal_firmware.protocol.checksum` computes, and the Arduino library computes the same value while the library prints each line.

## Versioning

The `1` in the `HELLO` reply is the protocol version. A board that speaks a newer major version than the hub refuses commands other than `HELLO` and `DESC`, and the hub reports the board as unsupported.
