# Hardware test: openhal-firmware

For a person with an Arduino Uno (or any AVR or ESP32 board), a USB cable, an LED and a 330 ohm resistor. Steps 1 to 5 need nothing on the output pins. This plan checks the driver with the library's PlantWaterer example and an LED in place of the relay, so nothing gets wet. The full plant waterer test with the relay and pump is [examples/plant-waterer/TEST-PLAN.md](../../examples/plant-waterer/TEST-PLAN.md). The agent that wrote this driver never ran it on real hardware.

Status. Not yet run on hardware.

## Before you start

1. Install arduino-cli or the Arduino IDE, and the OpenHAL library from `firmware/arduino/OpenHAL` (copy the folder into your Arduino `libraries` folder).
2. Flash `examples/PlantWaterer` with nothing connected to pin 7. Leave pin 4 open, so the tank reads `empty`.
3. Install the hub with the serial extra: `uv pip install "openhal-hub[openhal-firmware]"`.
4. Run `openhal init`, then copy `examples/plant-waterer/plant-waterer.hal.yaml` into `~/.openhal/devices/`. Don't confirm it yet.

## Read-only steps

1. **Discovery.** Run `openhal discover --driver openhal-firmware`. Expect one entry with driver `openhal-firmware`, `firmware.product=plant-waterer` and the port path.
2. **Draft file.** Run `openhal writer start --driver openhal-firmware --param port=<port>`. Expect a draft with `soil_moisture`, `tank`, `water` and `stop`, and every limit marked suggested.
3. **Read-only file.** Start `openhald` and run `openhal devices plant-waterer`. Expect the device listed as read-only, with `water` and `stop` unconfirmed.
4. **Read.** Run `openhal read plant-waterer.soil_moisture plant-waterer.tank`. Expect a percentage and `empty`. Connect pin 4 to GND and read again. Expect `ok`.
5. **Heartbeat.** Unplug the USB cable and plug it back in. Expect `openhal devices` to show the board disconnected, then connected again.

## Smallest safe actions

Connect the LED with the resistor from pin 7 to GND. Keep pin 4 on GND unless a step says otherwise.

6. **Confirm.** Run `openhal file confirm ~/.openhal/devices/plant-waterer.hal.yaml` after reading every limit, then restart `openhald`.
7. **Too long.** Run `openhal action plant-waterer.water duration=120s`. Expect `blocked above_max  Blocked. The duration limit is 30 s (max). Asked for 120 s.` and the LED stays off.
8. **Short run.** Run `openhal action plant-waterer.water duration=2s`. Expect `done  Done. water ran.`, the LED on, and off again about 2 s later.
9. **Empty tank.** Disconnect pin 4 and run `openhal action plant-waterer.water duration=2s`. Expect `INTERLOCK_BLOCKED` with "pump can't run while tank is empty" and the LED stays off.
10. **Stop.** Connect pin 4 to GND, run `openhal action plant-waterer.water duration=20s`, then `openhal stop`. Expect the LED off at once and `plant-waterer  safe`. Run `openhal unlock`.
11. **Board falls safe.** Run `openhal action plant-waterer.water duration=20s`, then stop the hub process. Within 3 s the LED must turn off on its own.

## Report

```
Board and core:              (for example Arduino Uno R3, arduino:avr 1.8.6)
Hub version and OS:
Step 1 to 11 results:        (pass or fail, with output)
Time from hub stop to LED off in step 11:
Anything unexpected:
```

Send the report as an issue or add it to this file, and update the status line above.
