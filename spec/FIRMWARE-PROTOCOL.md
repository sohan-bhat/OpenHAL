# OpenHAL firmware protocol, version 1

The wire protocol between the hub's `openhal-firmware` driver and a board running the OpenHAL Arduino library (firmware/arduino/OpenHAL/). A board that speaks it describes itself, so the hub can build its device file without a person typing channels.

The board enforces its own limits too. That is defense in depth. The hub's safety kernel is still the authority, and nothing in this protocol can widen a limit the device file sets.

## Transport

- A serial line (USB CDC, UART). Default 115200 baud, 8N1.
- ASCII text, one message per line, lines end with `\n` (a preceding `\r` is ignored).
- Lines are at most 250 bytes, except the `DESC` reply, which may be up to 1,500 bytes.

## Message format

```
<seq> <verb> [arg ...]*<checksum>
```

- `seq` is a decimal number from 1 to 65535 chosen by the host. The board echoes it in its reply. Unsolicited board messages use `0`.
- `verb` is an uppercase word. Arguments are separated by single spaces. Names match `[a-z][a-z0-9_]{0,23}`. Numbers are decimal, with an optional sign and decimal point.
- `*<checksum>` is two uppercase hex digits, the XOR of every byte before the `*`. Both sides check it and discard lines with a wrong or missing checksum.

## Host to board

| Verb | Arguments | Reply | Meaning |
|---|---|---|---|
| `HELLO` | | `OK openhal 1 <product> <firmware-version>` | Identify. Read-only. Safe to send to an unknown device during discovery |
| `DESC` | | `DESC <json>` | The capability document below |
| `READ` | `<name>` | `VAL <name> <value>` | Read one channel. A channel with states answers with the state's name |
| `WRITE` | `<name> <value>` | `OK <name> <value>` or `ERR <code> <detail>` | Set one write channel. The board checks its own min and max first |
| `ACT` | `<name> [<arg> <value> ...]` | `OK <name>` or `ERR <code> <detail>` | Run one action. Every argument it declares is given once, in any order. The board checks each against its own min and max, then its own conditions |
| `HB` | | `OK` | Heartbeat. The board falls to its safe state if heartbeats stop for `hb` milliseconds |
| `SAFE` | | `OK` | Apply the safe state now |

## Board to host

| Message | Meaning |
|---|---|
| `0 EVT <name> <value>` | A streamed value (the board's channel has `every` set) |
| `0 SAFE <reason>` | The board applied its safe state on its own. Reasons include `heartbeat_lost`, `<name>_timeout` and whatever the sketch passes, such as `local_button` |
| `<seq> ERR <code> <detail>` | A request failed. Codes are `unknown` (verb, channel or action), `limit` (outside the board's own limits), `format` (bad argument), `interlock` (the sketch refused the action, with its reason such as `tank_empty`), `checksum`, `fault` (the sensor returned no value), `busy` (the board refused commands because its sketch registered channels wrongly) |

## Capability document

The `DESC` reply is a compact JSON object.

```json
{
  "p": "desk-fan",
  "v": "1.0.0",
  "hb": 2000,
  "r": [{ "n": "temperature", "u": "degC", "e": 1000, "lo": -20, "hi": 80 }],
  "w": [{ "n": "fan_speed", "u": "percent", "min": 0, "max": 100, "safe": 0, "rate": 20 }]
}
```

The plant waterer (examples/plant-waterer/) reports a float switch as states and offers actions instead of a writable pump.

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
| `w` | Write channels. `n`, `u`, `min`, `max`, `safe` (the safe-state value), optional `rate` (unit per second) and `t` (milliseconds after which the board returns the output to `safe` on its own). A unit of `bool` marks an on and off output with values 0 and 1. An output the sketch keeps to itself is left out, and `WRITE` to it answers `ERR unknown`. `SAFE` and a lost heartbeat still return it to `safe` |
| `r` with `s` | A channel with states, such as a float switch. `u` is `enum` and `s` lists the state names, at most 8. `VAL` and `EVT` carry the name |
| `a` | Actions, at most 4. `n` name and `g` its arguments, at most 3, each with `n`, `u`, `min` and `max` |

The hub turns this into a draft device file with every limit marked `suggested: true`. A human still confirms the limits in the interview, and may tighten them below what the board allows.

## Example session

```
host  1 HELLO*53
board 1 OK openhal 1 desk-fan 1.0.0*39
host  2 READ temperature*4C
board 2 VAL temperature 27.4*3A
host  3 WRITE fan_speed 60*19
board 3 OK fan_speed 60*40
host  4 WRITE fan_speed 150*2C
board 4 ERR limit fan_speed max 100*30
board 0 EVT temperature 27.1*21
board 0 SAFE heartbeat_lost*02
```

The plant waterer.

```
host  4 ACT water duration 120*3A
board 4 ERR limit duration max 30*4D
host  5 ACT water duration 20*0A
board 5 OK water*44
board 0 EVT tank empty*32
host  6 ACT water duration 20*09
board 6 ERR interlock tank_empty*06
```

The checksums are real. `openhal.drivers.openhal_firmware.protocol.checksum` computes them, and the Arduino library computes the same value while it prints.

## Versioning

The `1` in the `HELLO` reply is the protocol version. A board that speaks a newer major version than the hub refuses commands other than `HELLO` and `DESC`, and the hub reports it as unsupported.
