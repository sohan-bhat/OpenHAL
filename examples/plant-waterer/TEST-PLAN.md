# Hardware test: Arduino plant waterer

For a person with the parts in README.md. Steps 1 to 4 need nothing on the relay. Steps 5 to 9 use the relay with the pump unplugged from its supply, so nothing gets wet until step 10.

Status. Not yet run on hardware.

## Before you start

1. Install the OpenHAL library from `firmware/arduino/OpenHAL` and flash `plant-waterer.ino` to the Uno.
2. Install the hub with the serial extra: `uv pip install "openhal-hub[openhal-firmware]"`.
3. Copy `plant-waterer.hal.yaml` into the hub's `devices` folder. Don't confirm it yet.

## Read-only steps

1. **Discovery.** Run `openhal discover`. Expect one entry with driver `openhal-firmware`, `firmware.product=plant-waterer` and the port path.
2. **Read-only file.** Start `openhald` and run `openhal devices plant-waterer`. Expect the device listed as read-only, with `water` and `stop` unconfirmed.
3. **Soil.** Run `openhal read plant-waterer.soil_moisture` with the sensor in dry air, then in a glass of water. Expect a low value, then a high one. Calibrate `SOIL_DRY` and `SOIL_WET` in the sketch if they are far from 0 % and 100 %.
4. **Tank.** Run `openhal read plant-waterer.tank` with the float down, then lifted. Expect `empty`, then `ok`.

## Smallest safe actions

The pump stays unplugged from its supply. Listen for the relay click instead.

5. **Confirm.** Run `openhal file confirm` on the device file after reading every limit.
6. **Too long.** Lift the float and run `openhal action plant-waterer.water duration=120s`. Expect `LIMIT_EXCEEDED` with "water duration 120 s exceeds the limit of 30 s" and no click.
7. **Empty tank.** Let the float drop and run `openhal action plant-waterer.water duration=2s`. Expect `INTERLOCK_BLOCKED` with "pump can't run while tank is empty" and no click.
8. **Short run.** Lift the float and run `openhal action plant-waterer.water duration=2s`. Expect done, a click on, and a click off about 2 s later.
9. **Board falls safe.** Run `openhal action plant-waterer.water duration=20s`, then stop the hub process at once. Within 3 s the relay must click off on its own.

## Water

10. **Real run.** Plug the pump into its supply, put the outlet in the pot and run `openhal action plant-waterer.water duration=5s`. Expect water for about 5 s and soil moisture to rise over the next readings. Run it three more times within the hour. Expect the fourth to be refused with `RATE_LIMITED`.

## Report

```
Board and core:              (for example Arduino Uno R3, arduino:avr 1.8.6)
Hub version and OS:
Step 1 to 10 results:        (pass or fail, with output)
Soil reading dry and wet:
Time from hub stop to relay off in step 9:
Anything unexpected:
```

Send the report as an issue or add it to this file, and update the status line above.
