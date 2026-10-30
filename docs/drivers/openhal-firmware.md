# openhal-firmware

The openhal-firmware driver connects to boards running the OpenHAL Arduino library (`firmware/arduino/OpenHAL`). The board reports a description of its readings, outputs and actions, enforces its own limits and falls to its safe state when heartbeats stop, and the protocol is in `spec/FIRMWARE-PROTOCOL.md`.

## Device file

This device file is the plant waterer from [examples/plant-waterer/](../../examples/plant-waterer/), for a real Uno.

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
| `port` | `auto` | A serial device path, a pyserial URL, `auto` (the first known Arduino or ESP32 USB id) or `sim:<name>` for the built-in simulator |
| `baud` | 115200 | Serial speed |
| `timeout_s` | 1.0 | How long to wait for each reply |
| `boot_s` | 0 | Wait after opening the port, for boards that reset when the port opens (set 2 for an Uno) |

Install the optional dependency with `uv pip install "openhal-hub[openhal-firmware]"` (pyserial).

## Behavior

- Connect sends `HELLO`, checks the protocol version, reads `DESC`, and starts a heartbeat at a third of the board's timeout.
- Reads use a streamed `EVT` value when the value is less than 5 s old, and send `READ` otherwise.
- Channel changes send `WRITE` and return the value the board applied, and actions send `ACT` with every argument in the board's unit. A board error reply (`ERR limit`, `ERR interlock`) becomes a DriverError, and the kernel marks what the command touched unknown until a readback.
- `safe_state_support` is native, so a stop sends `SAFE` and the kernel also applies the device file's safe state.
- `describe()` turns `DESC` into device file sections with every limit marked suggested, so the file stays read-only until a person confirms the file.
- Discovery only probes ports whose USB vendor id is Arduino, WCH CH340, Silicon Labs CP210x, Espressif, Adafruit or FTDI, and only sends `HELLO`.

## Quirks

- Because many boards reset when the port opens, set `boot_s`, or the first `HELLO` times out.
- A sketch that registers channels wrongly (`misconfigured()`) returns `ERR busy misconfigured` for every `WRITE` and `ACT`, but reads still work.
- On an ESP32 the USB CDC port may enumerate under Espressif (303a) or a bridge chip id, so discovery probes both.

## Tests

`tests/drivers/test_openhal_firmware.py` covers the codec, the simulator and the driver through the kernel. `tests/firmware/test_arduino_host.py` builds the real library and every example for the host computer and runs the conformance suite against it. Hardware steps are in `docs/hardware-tests/openhal-firmware.md`.
