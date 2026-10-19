# Hardware test: openhal-firmware

For a person with an Arduino Uno (or any AVR or ESP32 board), a USB cable, and nothing connected to the output pins for steps 1 to 4. The agent that wrote this driver never ran it on real hardware.

Status. Not yet run on hardware.

## Before you start

1. Install arduino-cli or the Arduino IDE, and the OpenHAL library from `firmware/arduino/OpenHAL` (copy the folder into your Arduino `libraries` folder).
2. Flash `examples/DeskFan` with nothing connected to pin 9.
3. Install the hub with the serial extra: `uv pip install "openhal-hub[openhal-firmware]"`.

## Read-only steps

1. **Discovery.** Run `openhal discover`. Expect one entry with driver `openhal-firmware`, `firmware.product=desk-fan` and the port path.
2. **Draft file.** Run `openhal device add <port>`. Expect a draft with `temperature` and `fan_speed`, `fan_speed` marked suggested, and the device listed as read-only.
3. **Read.** Run `openhal read desk-fan temperature`. Expect a room temperature in degC if a thermistor is wired, or a fault error if A0 is floating. Both are correct.
4. **Heartbeat.** With the hub running, unplug the USB cable and plug it back in. Expect the device to show as disconnected, then connected again.

## Smallest safe writes

Connect an LED with a 330 ohm resistor from pin 9 to ground instead of a fan.

5. **Confirm.** Run `openhal file confirm desk-fan` and accept the suggested limits.
6. **Write.** Run `openhal write desk-fan fan_speed 20%`. Expect the LED to glow dimly. Then `openhal write desk-fan fan_speed 150%`. Expect "Blocked. The fan_speed limit is 100 % (max)." and no change.
7. **Stop.** Run `openhal stop`. Expect the LED to turn off, and the stop result to say safe.
8. **Board falls safe.** Set the LED to 50 %, then stop the hub process (`openhal hub stop`). Within 2 s the LED must turn off on its own.

## Report

```
Board and core:            (for example Arduino Uno R3, arduino:avr 1.8.6)
Hub version and OS:
Step 1 to 8 results:       (pass or fail, with output)
Time from hub stop to LED off in step 8:
Anything unexpected:
```

Send the report as an issue or add it to this file, and update the status line above.
