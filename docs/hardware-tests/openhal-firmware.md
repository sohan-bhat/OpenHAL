# Hardware test plan for the openhal-firmware driver

This plan checks the openhal-firmware driver and the OpenHAL Arduino library on a real board, with the library's `LedStrip` example and its device file from the starter library. The plan covers what the plant waterer plan doesn't, a control channel with a range and a rate, a library file and a lost USB link. Run [the plant waterer plan](../../examples/plant-waterer/TEST-PLAN.md) first, since that plan checks discovery, actions and the board's own fallback. [README.md](README.md) has the setup and rules every plan shares. Stop at the first step that fails and send what [If something fails](#if-something-fails) lists.

## What you need

- An Arduino Uno and its USB cable. An ESP32 works too, with the pins in brackets.
- An LED with a 330 ohm resistor from pin 6 (ESP32 pin 25) to ground, in place of a strip.
- Optional. A potentiometer or a light sensor divider on A1 (ESP32 pin 34). Without it `ambient_light` reads noise.
- arduino-cli, or the Arduino IDE.
- A checkout of this repository with the openhal-firmware extra, `uv sync --extra openhal-firmware`.

## Before you start

Flash the example with the library from this checkout. Use the board's port from step 1. On an ESP32, install the `esp32:esp32` core and use `--fqbn esp32:esp32:esp32`.

```
arduino-cli core install arduino:avr
arduino-cli compile --fqbn arduino:avr:uno --library firmware/arduino/OpenHAL --upload --port /dev/ttyACM0 firmware/arduino/OpenHAL/examples/LedStrip
```

Make a test home and start the hub with no device files.

```
export OPENHAL_HOME="$PWD/openhal-test"
uv run openhal init --yes --no-sample --no-discover --no-service
bash docs/hardware-tests/hub.sh start
```

## Read-only steps

### 1. The port is listed

```
uv run python -m serial.tools.list_ports -v
```

Expected. A port with `VID:PID=2341:0043` for an Uno R3, `1A86:7523` for a CH340 clone, or an Espressif or CP210x id for an ESP32.

### 2. Discovery

```
uv run openhal discover --driver openhal-firmware
```

Expected.

```
matched  OpenHAL board led-strip as openhal-led-strip
  The library has openhal-led-strip, and the hub has no device file for it yet. Add it with openhal library add openhal-led-strip
```

### 3. The library file loads read-only

```
uv run openhal library add openhal-led-strip
bash docs/hardware-tests/hub.sh restart
uv run openhal devices openhal-led-strip
```

Expected. `added` and the path of the copy in `$OPENHAL_HOME/devices/`. The device is listed as `read-only` and `connected`, with `brightness` among the unconfirmed limits and `ambient_light` among the readings.

### 4. Read

```
uv run openhal read openhal-led-strip.ambient_light openhal-led-strip.brightness
```

Expected. `ambient_light` in `%`, which follows the potentiometer or the light on the sensor, and `brightness  0 %`.

### 5. A lost USB link

Unplug the board's USB cable for five seconds, then plug it back in, and run this before and after.

```
uv run openhal devices
```

Expected. `not connected` while it is unplugged, and `connected` again within a few seconds of plugging it back in. The board resets when the port opens, which the file's `boot_s: 2` allows for.

## Smallest safe changes

### 6. Confirm the limits

The library marks every limit as suggested. Stop the hub, open `$OPENHAL_HOME/devices/openhal-led-strip.hal.yaml`, check the `brightness` limits (at most 60 %, at most 25 % per second), and delete `, suggested: true` from that line. Then confirm the file and start the hub.

```
bash docs/hardware-tests/hub.sh stop
uv run openhal file confirm "$OPENHAL_HOME/devices/openhal-led-strip.hal.yaml"
bash docs/hardware-tests/hub.sh start
uv run openhal devices
```

Expected. The confirm lists `control brightness  0 % to 60 %, at most 25 %/s`, asks you to type `confirm` and ends with `confirmed`. The device is now `writable`.

### 7. The smallest change

```
uv run openhal write openhal-led-strip.brightness "10 %"
uv run openhal read openhal-led-strip.brightness
```

Expected. `done  Done. brightness is now 10 %.`, the LED glows dimly, and the read says `10 %`.

### 8. A blocked command never reaches the board

```
uv run openhal write openhal-led-strip.brightness "80 %"
```

Expected. `blocked above_max  Blocked. The brightness limit is 60 % (max). Asked for 80 %.` The LED doesn't change.

### 9. Stop

```
uv run openhal stop
uv run openhal read openhal-led-strip.brightness
uv run openhal unlock
```

Expected. The stop reports `openhal-led-strip  safe`, the LED goes off, the read says `0 %`, and `unlock` asks you to type `unlock`.

### 10. The board falls safe on its own

The sketch turns the LED off when the hub's heartbeats stop for 5 s. This step kills the hub with SIGKILL, so the hub sends nothing on its way out.

```
uv run openhal write openhal-led-strip.brightness "30 %"
bash docs/hardware-tests/hub.sh kill
```

Expected. The LED glows, and within 5 s of the kill it goes off on its own. Time it.

### 11. The audit chain

```
bash docs/hardware-tests/hub.sh start
uv run openhal log --verify
bash docs/hardware-tests/hub.sh stop
```

Expected. `intact  The audit chain verifies.` and the head hash.

## If something fails

Send what [README.md](README.md#if-a-step-fails) lists, plus the arduino-cli or IDE version and the core version, the board and its USB id from step 1, and the output of `uv run openhal library show openhal-led-strip`. If the LED changed for a command the hub blocked, unplug the board and report it privately as [SECURITY.md](../../SECURITY.md) says.

## Report template

```
Plan: docs/hardware-tests/openhal-firmware.md
Tested by and date:
OpenHAL: (uv run openhal --version, and git rev-parse --short HEAD)
Board and core: (for example Arduino Uno R3, arduino:avr 1.8.8)
Host OS and port path:
Device file: (path, and the sha256 in its confirmed line)
Step 1 port listed:              pass / fail
Step 2 discovery:                pass / fail
Step 3 library file read-only:   pass / fail
Step 4 read:                     pass / fail
Step 5 lost USB link:            pass / fail
Step 6 confirm:                  pass / fail
Step 7 smallest change:          pass / fail
Step 8 blocked command:          pass / fail
Step 9 stop:                     pass / fail
Step 10 board falls safe:        pass / fail   seconds from the kill to LED off:
Step 11 audit chain:             pass / fail
Audit chain: (the line uv run openhal log --verify prints)
Anything unexpected (paste exact output):
Result: verified-on-hardware / tested-reads / failed at step N
```

Save the filled-in report as `docs/hardware-tests/reports/openhal-led-strip-<date>.md`. [README.md](README.md#reports) says when it marks the device file `verified-on-hardware`.
