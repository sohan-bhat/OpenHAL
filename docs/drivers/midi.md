# midi driver

The midi driver reads knobs, faders and pads from MIDI controllers and sends notes and control changes to light pad LEDs, move motorised faders and set synth parameters. It uses mido with the python-rtmidi backend, which talks to ALSA on Linux, CoreMIDI on macOS and WinMM on Windows.

## What it supports

- Control Change, Note On and Note Off, Program Change and Pitch Bend, in both directions.
- Read channels of type number (the raw value or percent) and bool (a CC at 64 or above, or a held note).
- Write channels that send a CC, a note (as on and off for bool channels, or with a velocity for numbers, which many controllers use as the LED colour), a program change or a pitch bend.
- One default MIDI channel for the device and a per-channel override, numbered 1 to 16 as on the device.
- `discover()` lists MIDI ports, and `describe()` proposes read channels for every control you move while it listens.

## Setup

```sh
uv tool install --compile-bytecode "openhal-hub[midi] @ git+https://github.com/sohan-bhat/OpenHAL"
```

python-rtmidi has no prebuilt wheel for every Python version and platform. Where none exists, pip builds it from source, which needs a C++ compiler (Xcode command line tools on macOS) and, on Linux, the ALSA headers (`sudo apt install libasound2-dev`). To use another mido backend, set `backend`, for example `backend: mido.backends.portmidi`.

## Parameters

| Parameter | Default | Meaning |
|---|---|---|
| `name` | `auto` | Part of the port name, matched without case. `auto` takes the only port there is. The shorthand `midi: "LPD8"` sets it |
| `input`, `output` | none | Exact port names, when the input and output ports are named differently |
| `channel` | `1` | Default MIDI channel, 1 to 16 |
| `backend` | mido's default (rtmidi) | mido backend module |
| `timeout` | `2 s` | Deadline for sending one message |

The driver opens an input port only if the file has read channels, and an output port only if it has write channels.

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
| `channel` | the device's `channel` | MIDI channel for this map, 1 to 16 |
| `velocity` | `127` | Velocity for bool note writes |
| `on`, `off` | `127`, `0` | CC values for bool CC writes |

Units. `dimensionless` channels carry the raw MIDI value (0 to 127, or -8192 to 8191 for pitch bend). `percent` channels map 0 to 100 onto 0 to 127, and -100 to 100 onto the pitch bend range, rounded to the nearest step. The reading a write returns shows the value really sent, so `50 %` reads back as 50.4 %.

## How reads work

MIDI controllers push messages when something moves and can't be asked where a knob is. A read returns the newest value received since the driver connected, stamped with the time it arrived, and no value (`None`) until the control is first moved. The kernel treats that as unknown. Write channels report the last value the driver sent, because controllers don't report LED or parameter state.

## Example

`openhal/drivers/midi/examples/lpd8-pads.hal.yaml` reads two knobs and a pad of an Akai LPD8 and drives two pad LEDs.

## Errors and health

- No matching port, more than one match for `auto` or a partial name, and ports that fail to open raise `DriverError` that lists the ports there are.
- Raw values outside the MIDI range raise `DriverError` and nothing is sent.
- `health()` checks that the ports are still listed by the MIDI system, so an unplugged USB controller shows as disconnected at the next heartbeat.

## Limitations

- No SysEx, NRPN, RPN, 14-bit CC pairs, aftertouch or MIDI 2.0.
- No timestamps from the device. The arrival time on the hub is used.
- No actions. Model each message as a write channel.

## Hazard default and safe state

The default hazard is low, because MIDI devices are controllers, lights and instruments. MIDI has no emergency behavior, so `safe_state_support` is `file`, and the hub sends the device file's `safe_state` like any other message. A MIDI device driving something physical, such as a motorised fader or a DMX bridge, deserves a higher hazard in its device file.

## Sources

- MIDI 1.0 Detailed Specification, The MIDI Association, https://midi.org/midi-1-0-core-specifications
- Universal Serial Bus Device Class Definition for MIDI Devices 1.0, https://www.usb.org/sites/default/files/midi10.pdf
- mido documentation, messages and backends, https://mido.readthedocs.io/
- python-rtmidi documentation, https://spotlightkid.github.io/python-rtmidi/
