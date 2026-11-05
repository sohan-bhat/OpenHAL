# openhal-firmware

The openhal-firmware driver connects to boards running the OpenHAL Arduino library in `firmware/arduino/OpenHAL`. The board reports the readings, outputs and actions available, enforces the limits on the board and falls to a safe state when heartbeats stop. The protocol is in `spec/FIRMWARE-PROTOCOL.md`.

## Device file

The plant waterer from [examples/plant-waterer/](../../examples/plant-waterer/), for a real Uno.

```yaml
device: Arduino plant waterer
id: plant-waterer
match:
  firmware: { product: plant-waterer }
connect: { openhal-firmware: auto, boot_s: 2 }
read:
  soil_moisture: { unit: "%", every: 1 s, range: [0, 100] }
  tank: { type: enum, values: [empty, ok], every: 1 s }
actions:
  water:
    description: Run the pump for a number of seconds.
    args:
      duration: { unit: s, min: 1, max: 30 }
    require:
      - condition: "tank == ok"
        message: "pump can't run while tank is empty"
    max_runs: { count: 3, per: 1 h }
  stop:
    description: Turn the pump off now.
safe_state: { action: stop }
watchdog: { heartbeat: 1 s, on_loss: safe_state }
hazard: low
```

| Parameter | Default | Meaning |
|---|---|---|
| `port` | `auto` | Serial device path, pyserial URL, `auto` for the first known Arduino or ESP32 USB id, or `sim:<name>` for the built-in simulator |
| `baud` | 115200 | Serial speed |
| `timeout_s` | 1.0 | Reply deadline |
| `boot_s` | 0 | Delay after opening the port, 2 for an Uno, which resets on open |

Install with `uv tool install --compile-bytecode "halkit[openhal-firmware] @ git+https://github.com/sohan-bhat/OpenHAL"`, which adds pyserial.

## Behavior

- Connect sends `HELLO`, checks the protocol version, reads `DESC` and heartbeats at a third of the board's timeout.
- Reads use a streamed `EVT` value under 5 s old, or else send `READ`.
- Changes send `WRITE` and return the applied value, and actions send `ACT` in the board's units. `ERR limit` and `ERR interlock` become a DriverError, and the kernel marks what the command touched unknown until a readback.
- `safe_state_support` is native. A stop sends `SAFE`, and the kernel also applies the file's safe state.
- `describe()` turns `DESC` into suggested sections. Low and medium risk channels take commands within the board's range, and high risk ones stay read-only until a person confirms the limits, as [Safety](../SAFETY.md#risk-levels) describes.
- A sketch that calls `pins()` lists free pins in `DESC` as `pin<N>`, `pin<N>_pwm` in percent, `pin<N>_analog` in percent of full scale and `pin<N>_mode`, each with `map: { pin: N, mode: ... }` and sent as `PIN` with the mode set per command. A pin used by a named output shares that output's risk, and a plain pin is medium.
- Discovery sends only `HELLO`, and only to Arduino, WCH CH340, Silicon Labs CP210x, Espressif, Adafruit or FTDI USB ids. An ESP32 may show as Espressif 303a or a bridge chip, so discovery probes both.

## Quirks

- Boards that reset on open need `boot_s`, or the first `HELLO` times out.
- A sketch with `misconfigured()` returns `ERR busy misconfigured` for every `WRITE` and `ACT`, and reads still work.

## Tests

`tests/drivers/test_openhal_firmware.py` covers the codec, simulator and driver through the kernel, and `tests/drivers/test_openhal_firmware_pins.py` covers every simulated pin. `tests/firmware/test_arduino_host.py` builds the real library and every example for the host and runs the conformance suite. Hardware steps are in `docs/hardware-tests/openhal-firmware.md`.
