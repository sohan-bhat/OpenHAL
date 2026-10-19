# openhal-firmware

Boards running the OpenHAL Arduino library (`firmware/arduino/OpenHAL`). The board describes its readings and outputs, enforces its own limits and falls to its safe state when heartbeats stop. Protocol in `spec/FIRMWARE-PROTOCOL.md`.

## Device file

```yaml
device: Desk fan controller
connect: { openhal-firmware: auto }
match:
  firmware: { product: desk-fan }
read:
  temperature: { unit: degC, stream: true, range: [-20, 80] }
write:
  fan_speed: { unit: percent, min: 0, max: 100, max_change_per_s: 20 }
safe_state: { fan_speed: 0 }
watchdog: { heartbeat: 1000 ms, on_loss: safe_state }
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
- Reads use a streamed `EVT` value if it is less than 5 s old, otherwise `READ`.
- Writes send `WRITE` and return the value the board applied. A board refusal (`ERR limit`) becomes a DriverError, and the kernel marks the channel unknown until a readback.
- `safe_state_support` is native. A stop sends `SAFE` and the kernel also applies the device file's safe state.
- `describe()` turns `DESC` into device file sections. Every write limit is marked suggested, so the file stays read-only until a person confirms it.
- Discovery only probes ports whose USB vendor id is Arduino, WCH CH340, Silicon Labs CP210x, Espressif, Adafruit or FTDI, and only sends `HELLO`.

## Quirks

- Many boards reset when the port opens. Use `boot_s` or the first `HELLO` times out.
- A sketch that registers channels wrongly (`misconfigured()`) answers writes with `ERR busy misconfigured`. Reads still work.
- On an ESP32 the USB CDC port may enumerate under Espressif (303a) or a bridge chip id. Both are probed.

## Tests

`tests/drivers/test_openhal_firmware.py` covers the codec, the simulator and the driver through the kernel. `tests/firmware/test_arduino_host.py` builds the real library and every example for the host computer and runs the conformance suite against it. Hardware steps are in `docs/hardware-tests/openhal-firmware.md`.
