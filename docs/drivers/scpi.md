# scpi driver

The `scpi` driver connects to programmable test instruments over VISA with PyVISA 1.16.2 and pyvisa-py 0.8.1. Bench supplies, multimeters, electronic loads, function generators and oscilloscopes use SCPI over USB-TMC, LAN, serial or GPIB. Each channel `map` gives the query or setting command, and `describe()` drafts channels for common families from the `*IDN?` reply.

## Supports

- `SYST:ERR?` after every setting until the queue reports `0`, so any error fails the command with the instrument's message, such as `-222,"Data out of range"`.
- Health through `*OPC?`.
- `resource: auto` picks the one USB instrument matching `match.usb`, and `match.scpi_idn` is checked against `*IDN?` on every connect.
- `resource: sim:scope` or `sim:supply` connects to a simulated oscilloscope or Rigol DP832 supply, served in the hub's process on a loopback port.

## Channel maps

| Key | Used by | Meaning |
|---|---|---|
| `query` | read | Query such as `MEAS:VOLT? CH1` |
| `set` | write | Setting template with `{value}`, or `{on_off}` for ON or OFF on bools |
| `get` | write | Readback query. Without one, a read returns the last value sent |
| `command` | action | Template with the action's argument names |
| `parse`, `scale`, `offset`, `unit`, `on`, `off`, `lookup` | read, write | As in `docs/drivers/serial.md` |

An image channel's `query`, such as `:DISP:DATA? PNG`, returns an IEEE 488.2 definite-length block holding a PNG, JPEG or GIF. A reading of 9.9E37 or more fails as an invalid measurement. `unit` is the instrument's unit, so a `mA` channel can read a query in amps. Numbers use Python format specs such as `{value:.3f}`. Templates are checked at load, and a rendered command with a control character is blocked.

## Describe

The draft always has `device` and `match.scpi_idn`, plus channels for the family.

| Family | Matched by | Draft |
|---|---|---|
| Rigol DP800, Siglent SPD | IDN model `DP8..`, `SPD..` | voltage and current reads per channel, output switch, set actions when the ratings are known. Siglent SPD gets separate `CHn:VOLT` and `CHn:CURR` actions and no output read back |
| Keysight E36300 | `E363..A` | the same with `(@n)` channel lists |
| Multimeters | Keysight 344xx, Rigol DM, Siglent SDM, Keithley 2000 and DMM | DC voltage, DC current and resistance reads |
| Electronic loads | Rigol DL3000, Siglent SDL | voltage, current and power reads, input switch |
| Generators | Rigol DG, Siglent SDG, Keysight 33500 and 33600 | channel 1 frequency read and output switch |
| Scopes | Rigol DS, MSO and DHO, Siglent SDS | trigger status |
| Simulated scope | `OpenHAL,SIM-SCOPE` | the channels of `simulated-scope.hal.yaml` |

Drafted writes and actions are `suggested: true` with rated limits at most. High risk entries stay read-only until a person lowers and confirms the limits, and low and medium ones work within the rated limits.

## Setup

1. Install with `uv tool install --compile-bytecode "halkit[scpi] @ git+https://github.com/sohan-bhat/OpenHAL"`, which brings pyusb and pyserial. USB-TMC also needs the system libusb.
2. On Linux, add a udev rule for the vendor id.
3. Find the resource with `python -m pyvisa info` and `python -c "import pyvisa; print(pyvisa.ResourceManager('@py').list_resources())"`.
4. Start from `openhal/drivers/scpi/examples/rigol-dp832.hal.yaml` or `describe()`. `openhal/drivers/scpi/examples/simulated-scope.hal.yaml` drives the simulated scope with no hardware.

| Key | Default | Meaning |
|---|---|---|
| `resource` | required | VISA resource such as `USB0::0x1AB1::0x0E11::DP8C1234::INSTR` or `TCPIP0::192.168.1.20::5025::SOCKET`, `auto`, `sim:scope` or `sim:supply` |
| `visa_library` | `@py` | `@py` for pyvisa-py, an NI-VISA path, or `file.yaml@sim` for pyvisa-sim |
| `timeout` | `2 s` | Per exchange |
| `termination` | `lf` | `lf`, `crlf` or `cr` |
| `check_errors` | true | Read `SYST:ERR?` after every setting |
| `baud` | none | Baud rate for `ASRL` resources |

## Known limitations

- No binary block transfers such as screenshots or waveforms. `string` suits short text replies only.
- Instruments without `SYST:ERR?` need `check_errors: false`, and failed settings then pass silently.
- After a timeout the VISA session reopens, so a late reply can't pass as the next response and slow instruments may take one extra timeout to recover.
- The first `ResourceManager('@py')` in a process can take several seconds.
- Supplies keep outputs on after the host disconnects, and the safe state runs only while the hub reaches the instrument.

## Hazard defaults

`medium`, since supplies and loads can damage circuits and start fires. `safe_state` comes from the device file only, since SCPI has no universal outputs-off command. Keep `confirm-each-time` on output switches and set actions.

## Sources

- SCPI 1999 standard and IEEE 488.2 common commands, https://www.ivifoundation.org/specifications/default.html
- PyVISA documentation, https://pyvisa.readthedocs.io/en/latest/
- pyvisa-py documentation, https://pyvisa.readthedocs.io/projects/pyvisa-py/en/latest/
- pyvisa-sim definition format, https://pyvisa.readthedocs.io/projects/pyvisa-sim/en/latest/definitions.html
- Rigol DP800 Programming Guide for `MEAS`, `OUTP`, `APPL` and `SYST:ERR?`
- Keysight E36300 Series Programming Guide for channel lists
- Siglent SPD3303X Programming Guide
