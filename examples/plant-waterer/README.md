# Arduino plant waterer

The Arduino OpenHAL example. An Arduino Uno reads a soil moisture sensor and a tank float switch, and runs a small pump through a relay. An agent can send a request to water the plant. The hub's safety kernel checks every request, and the board checks again on its own.

## What the hub reads and controls

| Name | Kind | Detail |
|---|---|---|
| `soil_moisture` | reading | percent, every 1 s |
| `tank` | reading | `empty` or `ok` |
| `water` | action | `duration` in s |
| `stop` | action | turns the pump off now |

## Limits

A person confirms these before the hub accepts any command.

- One watering runs at most 30 s.
- The pump runs at most 3 times per hour.
- The pump never runs while the tank is empty.
- The safe state is pump off.
- If the hub stops sending heartbeats for 3 s, the board turns the pump off on its own.

The board also enforces the 30 s limit and the tank check itself, so a bug on the host side still can't run the pump dry.

## Parts

- Arduino Uno, or an ESP32 with the pins in the sketch
- Capacitive soil moisture sensor
- Float switch for the tank
- 5 V relay module
- Small 5 V or 12 V water pump with its own power supply
- Tubing and a water tank

## Wiring

| Part | Uno pin |
|---|---|
| Soil sensor signal | A0 |
| Float switch | pin 4 to GND. It closes when the water is high enough |
| Relay input | pin 7 |

The pump's power goes through the relay contacts, never through the Arduino.

## Files

| File | What it is |
|---|---|
| `plant-waterer.ino` | The sketch. It is also the library's `PlantWaterer` example |
| `plant-waterer.hal.yaml` | The device file for a real board. It loads read-only until you confirm it |
| `mock/plant-waterer.hal.yaml` | The same device on the simulated board, confirmed by owner on 2026-10-24. `openhal demo` and the tests use it |
| `TEST-PLAN.md` | The hardware test, read-only steps first |

## Try it without hardware

```
uv run openhal demo --full
```

The full demo discovers the simulated board, builds a draft of the board's device file from the board and its sketch, and connects an agent, which drafts a routine that a person enables.

## Use a real board

1. Copy `firmware/arduino/OpenHAL` into your Arduino `libraries` folder.
2. Flash `plant-waterer.ino`.
3. Copy `plant-waterer.hal.yaml` into your hub's `devices` folder and run `openhal file confirm` on it after you have read every limit.
4. Follow `TEST-PLAN.md` before the pump goes near a plant.
