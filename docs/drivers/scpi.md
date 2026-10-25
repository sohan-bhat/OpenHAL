# scpi driver

The `scpi` driver talks to programmable test instruments over VISA. Bench supplies, multimeters, electronic loads, function generators and oscilloscopes all speak SCPI over USB-TMC, LAN, serial or GPIB. Each channel's `map` gives the query or setting command, and `describe()` proposes channels for common instrument families from the `*IDN?` reply.

| | |
|---|---|
| Driver name | `scpi` |
| Libraries | PyVISA 1.16.2 (MIT), pyvisa-py 0.8.1 (MIT), pyusb 1.3.1 (BSD-3-Clause), pyserial 3.5 (BSD-3-Clause). pyvisa-sim 0.7.1 (MIT) for tests only |
| Extra | `uv tool install --compile-bytecode "openhal-hub[scpi] @ git+https://github.com/sohan-bhat/OpenHAL"` |
| Hazard default | medium |
| Safe state | from the device file only (SCPI has no universal outputs-off command) |
| Self-describe | yes, from `*IDN?` |

## What it supports

- Read channels of type number, bool, enum and string through a query.
- Write channels of every type through a setting command, with an optional readback query.
- Actions whose arguments fill a command template, such as `APPL CH1,{volts},{amps}`.
- Error checking. After every setting the driver reads `SYST:ERR?` until the queue says `0`. Any error fails the command with the instrument's message, for example `-222,"Data out of range"`.
- Health checks with `*OPC?`, which every IEEE 488.2 instrument answers.
- `resource: auto`, which picks the one USB instrument whose vendor and product id match `match.usb`. `match.scpi_idn` is checked against `*IDN?` on every connect, so a file can't drive the wrong instrument.

## Channel maps

| Key | Used by | Meaning |
|---|---|---|
| `query` | read | Query to send, such as `MEAS:VOLT? CH1` |
| `set` | write | Setting template. `{value}` for every type, `{on_off}` (ON or OFF) for bool channels |
| `get` | write | Readback query. Without it a read returns the last value sent, or unknown before the first write |
| `command` | action | Template with the action's argument names as placeholders |
| `parse`, `scale`, `offset`, `unit`, `on`, `off`, `lookup` | read, write | As in the serial driver (docs/drivers/serial.md) |

`unit` in a map is the unit the instrument uses, so a channel in `mA` can read a query that answers in amps. Numbers are formatted with Python format specs, for example `{value:.3f}`. Templates are checked when the file loads and a rendered command with a control character is refused.

## describe()

The proposal always has `device` and `match.scpi_idn`. Then, by family.

| Family | Matched by | Proposal |
|---|---|---|
| Rigol DP800, Siglent SPD | IDN model `DP8..`, `SPD..` | voltage and current reads per channel, output switch, set actions when the ratings are known. Siglent SPD gets separate `CHn:VOLT` and `CHn:CURR` actions and no output read back |
| Keysight E36300 | `E363..A` | the same with `(@n)` channel lists |
| Multimeters | Keysight 344xx, Rigol DM, Siglent SDM, Keithley 2000 and DMM | DC voltage, DC current and resistance reads |
| Electronic loads | Rigol DL3000, Siglent SDL | voltage, current and power reads, input switch |
| Generators | Rigol DG, Siglent SDG, Keysight 33500 and 33600 | channel 1 frequency read and output switch |
| Scopes | Rigol DS, MSO and DHO, Siglent SDS | trigger status |

Every proposed write and action is `suggested: true` and carries rated limits at most. The file loads read-only until a human lowers and confirms them.

## Setup

1. Install the extra with `uv tool install --compile-bytecode "openhal-hub[scpi] @ git+https://github.com/sohan-bhat/OpenHAL"`. It brings pyusb and pyserial for the USB-TMC and serial transports. USB-TMC also needs the system libusb library.
2. On Linux, give your user access to the USB device (a udev rule for the vendor id).
3. Find the resource with `python -m pyvisa info` and `python -c "import pyvisa; print(pyvisa.ResourceManager('@py').list_resources())"`.
4. Start from `openhal/drivers/scpi/examples/rigol-dp832.hal.yaml`, or from the driver's `describe()` output.
5. Validate with `openhal file validate`, then confirm the limits by hand.

## Parameters

| Key | Default | Meaning |
|---|---|---|
| `resource` | required | VISA resource string, for example `USB0::0x1AB1::0x0E11::DP8C1234::INSTR` or `TCPIP0::192.168.1.20::5025::SOCKET`, or `auto` |
| `visa_library` | `@py` | `@py` for pyvisa-py, a path to NI-VISA, or `file.yaml@sim` for pyvisa-sim |
| `timeout` | `2 s` | VISA timeout per exchange |
| `termination` | `lf` | Read and write termination. `lf`, `crlf` or `cr` |
| `check_errors` | true | Read `SYST:ERR?` after every setting |
| `baud` | none | Baud rate for `ASRL` resources |

## Example device file

```yaml
device: { name: Bench power supply, model: DP832, manufacturer: Rigol }
id: bench-psu
match: { usb: ["1ab1:0e11"], scpi_idn: "^RIGOL TECHNOLOGIES,DP832" }
connect: { driver: scpi, resource: auto, timeout: 2 s }
read:
  ch1_voltage: { unit: V, every: 500 ms, map: { query: "MEAS:VOLT? CH1" } }
  ch1_current: { unit: A, every: 500 ms, map: { query: "MEAS:CURR? CH1" } }
write:
  ch1_output: { type: bool, confirm: confirm-each-time, map: { set: "OUTP CH1,{on_off}", get: "OUTP? CH1" } }
actions:
  set_ch1:
    args:
      volts: { unit: V, min: 0, max: 12, step: 0.01 }
      amps: { unit: A, min: 0, max: 1, step: 0.001 }
    confirm: confirm-each-time
    map: { command: "APPL CH1,{volts},{amps}" }
safe_state:
  - { ch1_output: false }
hazard: medium
```

## Known limitations

- Binary block transfers (screenshots, waveform data) are not read. Use the `string` type for short text replies only.
- An instrument that doesn't implement `SYST:ERR?` needs `check_errors: false`, and then a refused setting passes silently.
- After a timeout the driver reopens the VISA session before the next command, so a late reply can't be read as the next answer. Instruments that are slow to accept new sessions may take one extra timeout to recover.
- The first `ResourceManager('@py')` in a process can take several seconds while pyvisa-py loads its backends.
- Supplies keep their outputs on after the host disconnects. The safe state only runs when the hub can still reach the instrument.

## Hazard defaults

`medium`. Supplies and loads can damage circuits and start fires. Keep `confirm-each-time` on output switches and set actions, and keep the volt and amp limits at what the circuit can take.

## Sources

- SCPI 1999 standard and IEEE 488.2 common commands, https://www.ivifoundation.org/specifications/default.html
- PyVISA documentation, https://pyvisa.readthedocs.io/en/latest/
- pyvisa-py documentation, https://pyvisa.readthedocs.io/projects/pyvisa-py/en/latest/
- pyvisa-sim definition format, https://pyvisa.readthedocs.io/projects/pyvisa-sim/en/latest/definitions.html
- Rigol DP800 Programming Guide (`MEAS`, `OUTP`, `APPL`, `SYST:ERR?`)
- Keysight E36300 Series Programming Guide (channel lists)
- Siglent SPD3303X Programming Guide
