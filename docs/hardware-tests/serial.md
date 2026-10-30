# Hardware test plan for the serial driver

This plan checks the serial driver on a real board. The plan starts with read-only checks and ends with the smallest safe writes. Stop at the first step that fails and send what [If something fails](#if-something-fails) lists. [README.md](README.md) has the setup and rules every plan shares.

## What you need

- An Arduino Uno or any board that runs the sketch below, with its USB cable.
- Optional. A TMP36 sensor on A0, an LED on pin 13 (the onboard LED is fine) and a small 5 V fan through a logic-level MOSFET on pin 9. Without these parts the readings are just noise and the outputs drive nothing.
- A checkout of this repository with the serial extra, `uv sync --extra serial`.

## The test sketch

Upload this with the Arduino IDE. The sketch implements the protocol in `openhal/drivers/serial/examples/arduino-fan-board.hal.yaml`.

```cpp
// OpenHAL serial driver test sketch. One command per line, one reply per line.
String line;
int fan = 0;
bool led = false;

void setup() {
  Serial.begin(115200);
  pinMode(9, OUTPUT);
  pinMode(13, OUTPUT);
  analogWrite(9, 0);
}

void reply(const String &text) { Serial.print(text); Serial.print('\n'); }

void handle(String cmd) {
  cmd.trim();
  if (cmd == "ID?") { reply("FANBOARD,1.2"); return; }
  if (cmd == "TEMP?") {
    float volts = analogRead(A0) * 5.0 / 1023.0;
    reply("T=" + String((volts - 0.5) * 100.0, 2));
    return;
  }
  if (cmd == "FAN?") { reply("FAN=" + String(fan)); return; }
  if (cmd.startsWith("FAN ")) {
    long value = cmd.substring(4).toInt();
    if (value < 0 || value > 255) { reply("ERR range"); return; }
    fan = value; analogWrite(9, fan); reply("OK"); return;
  }
  if (cmd == "LED?") { reply(led ? "LED=ON" : "LED=OFF"); return; }
  if (cmd == "LED ON" || cmd == "LED OFF") {
    led = cmd == "LED ON"; digitalWrite(13, led); reply("OK"); return;
  }
  if (cmd.startsWith("BEEP ")) { reply("OK"); return; }
  reply("ERR unknown");
}

void loop() {
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n') { handle(line); line = ""; } else { line += c; }
  }
}
```

## The read-only probe

Steps 2 to 4 use this script. The probe connects, requests the identity, calls the driver's `describe()` and reads every channel. The probe holds no kernel grant, so the probe can't write anything. Save it as `probe.py`.

```python
import asyncio, json, sys
from openhal.drivers import registry
from openhal.spec import load

async def main(path):
    file = load(path)
    driver = registry.load(file.connect.driver)(file)
    await driver.connect()
    try:
        print("identify", json.dumps(await driver.identify()))
        print("describe", json.dumps(await driver.describe(), indent=2, default=str))
        for name in [*file.read, *file.write]:
            try:
                reading = await driver.read(name)
                print("read", name, reading.value, reading.unit or "")
            except Exception as exc:
                print("read", name, "ERROR", type(exc).__name__, exc)
    finally:
        await driver.close()

asyncio.run(main(sys.argv[1]))
```

## Step 1. The port is listed (read-only)

```
uv run python -m serial.tools.list_ports -v
```

Expected. A port such as `/dev/ttyACM0` or `/dev/cu.usbmodem1101` with `VID:PID=2341:0043` (other boards show other ids). Note the port path and the id.

## Step 2. Validate the device file (read-only)

Copy the example and set `match.usb` to the id from step 1, or replace `serial: auto` with the port path.

```
cp openhal/drivers/serial/examples/arduino-fan-board.hal.yaml ./fan-board.hal.yaml
uv run openhal file validate ./fan-board.hal.yaml
```

Expected. `valid ./fan-board.hal.yaml (fan-board, low hazard, read-only)` and a note that the limits are unconfirmed.

## Step 3. Identify and read (read-only)

```
uv run python probe.py ./fan-board.hal.yaml
```

Expected.

```
identify {"port": "auto", "board": "arduino-uno", "reply": "FANBOARD,1.2"}
describe null
read temperature 23.4 degC
read fan_speed 0.0 percent
read led False
```

The temperature is about 20 to 30 with a TMP36 and arbitrary without one. If a read times out, check the baud rate and the `settle` time. If a reply doesn't match, send the exact line the Arduino serial monitor shows for the same command.

## Step 4. Unplug during a read (read-only)

Run the probe in a loop and unplug the cable while it runs. Plug the cable back in after five seconds.

```
while true; do uv run python probe.py ./fan-board.hal.yaml; sleep 1; done
```

Expected. While unplugged each run ends with `Could not open` or `stopped sending data`. After replugging the reads come back without restarting anything. Stop the loop with Ctrl-C.

## Step 5. Start the hub with the device

Read every limit in the file, then confirm them yourself. The confirm lists each limit and prompts you to type `confirm`. Then the file goes into a fresh test home and hub.

```
export OPENHAL_HOME="$PWD/openhal-test"
uv run openhal init --yes --no-sample --no-discover --no-service
uv run openhal file confirm ./fan-board.hal.yaml
cp ./fan-board.hal.yaml "$OPENHAL_HOME/devices/"
bash docs/hardware-tests/hub.sh start
uv run openhal devices
uv run openhal read fan-board.temperature
```

Expected. `fan-board` is listed as connected and writable, and the read returns a temperature in degC.

## Step 6. The smallest safe write

Switch the LED, which drives nothing that can hurt.

```
uv run openhal write fan-board.led true
uv run openhal read fan-board.led
uv run openhal write fan-board.led false
```

Expected. The LED turns on, the read shows `true`, then it turns off.

## Step 7. A small fan write and the safe state

```
uv run openhal write fan-board.fan_speed "10 %"
uv run openhal read fan-board.fan_speed
uv run openhal stop
uv run openhal read fan-board.fan_speed
uv run openhal unlock
```

Expected. The fan reading is about `10.2 %` (the PWM byte is 26). After `openhal stop` it reads `0 %` and the LED is off. `openhal unlock` prompts you to type `unlock`.

## Step 8. A blocked write never reaches the board

```
uv run openhal write fan-board.fan_speed "150 %"
```

Expected. Blocked with code `above_max`. The fan doesn't change. Stop the hub with `bash docs/hardware-tests/hub.sh stop` when you are done.

## If something fails

Send what [README.md](README.md#if-a-step-fails) lists, plus the line the Arduino serial monitor shows for the same command at 115200 baud with newline endings, the sketch if you changed it, and the output of `uv run python -m serial.tools.list_ports -v`. If a blocked command reached the device, stop the hub, power the device off and report it privately as [SECURITY.md](../../SECURITY.md) describes.

## Report template

```
Plan: docs/hardware-tests/serial.md
Tested by and date:
OpenHAL: (uv run openhal --version, and git rev-parse --short HEAD)
Device file: (path, and the sha256 in its confirmed line)
Board and firmware: (for example Arduino Uno R3 with the test sketch)
Host OS and port path:
Step 1 port listed:            pass / fail
Step 2 file valid:             pass / fail
Step 3 probe output:           pass / fail   (paste it)
Step 4 unplug and replug:      pass / fail
Step 5 hub lists the device:   pass / fail
Step 6 LED write:              pass / fail
Step 7 fan write and stop:     pass / fail   value read after write:
Step 8 blocked write:          pass / fail
Audit chain: (the line uv run openhal log --verify prints)
Anything unexpected (paste exact output):
Result: verified-on-hardware / tested-reads / failed at step N
```

Save the filled-in report as `docs/hardware-tests/reports/<device id>-<date>.md`. [README.md](README.md#reports) lists when a report marks the device file `verified-on-hardware`.
