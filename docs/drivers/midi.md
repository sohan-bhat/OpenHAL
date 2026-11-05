# midi driver

The midi driver reads knobs, faders and pads from MIDI controllers and sends notes and control changes to light pad LEDs, move motorised faders and set synth parameters. The driver uses mido with python-rtmidi on ALSA, CoreMIDI or WinMM.

## Supports

- Control Change, Note On and Off, Program Change and Pitch Bend, both directions.
- Bool reads are a CC at 64 or above or a held note. A note write on a number channel sends the value as velocity, often the LED colour.
- `discover()` lists ports, and `describe()` returns a channel for every control moved while listening.

## Setup

```sh
uv tool install --compile-bytecode "halkit[midi] @ git+https://github.com/sohan-bhat/OpenHAL"
```

Where python-rtmidi has no wheel, pip builds the package with a C++ compiler, plus `libasound2-dev` on Linux. `backend` picks another mido backend such as `mido.backends.portmidi`.

| Parameter | Default | Meaning |
|---|---|---|
| `name` | `auto` | Part of the port name, any case. `auto` takes the only port. `midi: "LPD8"` is shorthand |
| `input`, `output` | none | Exact port names when input and output differ |
| `channel` | `1` | Default MIDI channel, 1 to 16 |
| `backend` | rtmidi | mido backend module |
| `timeout` | `2 s` | Send deadline per message |

## Channel maps

```yaml
read:
  knob_1: { unit: percent, stream: true, map: { cc: 1 } }
  pad_1: { type: bool, stream: true, map: { note: 36 } }
  bend: { unit: percent, map: { pitchwheel: true } }
write:
  pad_1_led: { type: bool, map: { note: 36 } }
  pad_2_colour: { unit: dimensionless, min: 0, max: 127, map: { note: 37 } }
  cutoff: { unit: percent, min: 0, max: 100, map: { cc: 74, channel: 2 } }
```

| Key | Default | Meaning |
|---|---|---|
| `cc`, `note` | none | Controller or note number, 0 to 127. Give exactly one of `cc`, `note`, `program: true` or `pitchwheel: true` |
| `program` | `false` | Program Change |
| `pitchwheel` | `false` | Pitch Bend |
| `channel` | the device's | MIDI channel, 1 to 16 |
| `velocity` | `127` | Velocity for bool note writes |
| `on`, `off` | `127`, `0` | CC values for bool CC writes |

`dimensionless` channels carry the raw value, 0 to 127 or -8192 to 8191 for pitch bend. `percent` maps 0 to 100 onto 0 to 127, or -100 to 100 onto pitch bend, rounded, so `50 %` reads back as 50.4 %.

Controllers can't be queried, so reads return the newest message since connecting, or `None` until the control first moves. Write channels report the last value sent.

## Example

`openhal/drivers/midi/examples/lpd8-pads.hal.yaml` reads two knobs and a pad of an Akai LPD8 and drives two pad LEDs.

## Errors and health

- No matching port, several matches, a port that fails to open and out-of-range raw values raise `DriverError`, with nothing sent.
- `health()` checks that the ports are still listed, so an unplugged controller shows disconnected.

## Limitations

- No SysEx, NRPN, RPN, 14-bit CC pairs, aftertouch or MIDI 2.0.
- Timestamps are arrival times.
- No actions. Model each message as a write channel.

## Hazard default and safe state

Low. `safe_state_support` is `file`, sent like any message. A MIDI device driving something physical, such as a motorised fader or a DMX bridge, needs a higher hazard.

## Sources

- MIDI 1.0 Detailed Specification, The MIDI Association, https://midi.org/midi-1-0-core-specifications
- Universal Serial Bus Device Class Definition for MIDI Devices 1.0, https://www.usb.org/sites/default/files/midi10.pdf
- mido documentation, messages and backends, https://mido.readthedocs.io/
- python-rtmidi documentation, https://spotlightkid.github.io/python-rtmidi/
