# OpenHAL for Arduino

Add OpenHAL to a sketch and your board describes itself to an OpenHAL hub. The hub builds the device file from that description, you confirm the limits once, and then AI agents and routines can read and control the board through the hub's safety kernel.

The board also blocks output values outside the limits you set in the sketch, and the board returns every output to its safe value when the hub stops sending heartbeats. The hub's kernel is still the authority, and the board's checks back up the kernel's checks.

## Sketch

This sketch is the plant waterer, shortened from `examples/PlantWaterer`. Because the pump has no channel of its own, the hub can run the pump only through `water`, and the board never runs the pump from an empty tank.

```cpp
#include <OpenHAL.h>

OpenHAL hal("plant-waterer", "1.0.0");
OpenHalOutput* pump = nullptr;
const char* const TANK_STATES[] = {"empty", "ok"};

float readMoisture() { /* your sensor, 0 to 100 */ }
float readTank() { return digitalRead(4) == LOW ? 1 : 0; }
void setPump(float on) { digitalWrite(7, on > 0.5f ? HIGH : LOW); }

const char* water(const float* args) {
  if (readTank() == 0) return "tank_empty";
  hal.drive(*pump, 1, static_cast<unsigned long>(args[0] * 1000.0f));
  return nullptr;
}

void setup() {
  pinMode(7, OUTPUT);
  pinMode(4, INPUT_PULLUP);
  Serial.begin(115200);
  hal.reading("soil_moisture", "percent", readMoisture).every(1000).range(0, 100);
  hal.reading("tank", "enum", readTank).states(TANK_STATES, 2).every(1000);
  pump = &hal.output("pump", "bool", setPump).onOff().safe(0).timeout(30000).internal();
  hal.action("water", water).arg("duration", "s", 1, 30);
  hal.heartbeat(3000);
  hal.begin(Serial);
}

void loop() { hal.poll(); }
```

`begin()` applies every safe value before the board accepts commands, so outputs start in their safe state after a reset.

An output the hub may set directly works the same way without `.internal()`. The short forms `hal.read("ambient_light", "percent", readLight)` and `hal.write("brightness", "percent", 0, 100, setBrightness)` from the LedStrip example do the same as `reading()` and `output()`, and `write()` makes the minimum the safe value unless `.safe()` sets another value.

## Readings and outputs

| Call | What it does |
|---|---|
| `reading(name, unit, fn)` | A value the hub can read. `fn` returns a float, or `NAN` when the sensor has no value |
| `.every(ms)` | Stream the value every `ms` milliseconds |
| `.range(lo, hi)` | The range a working sensor reports. The hub flags values outside it |
| `output(name, unit, fn)` | A value the hub can set. `fn` receives a value already checked against the limits |
| `.limits(min, max)` | The board blocks values outside this range |
| `.safe(value)` | Applied at start, on a stop, and when heartbeats stop |
| `.rate(perSecond)` | The fastest safe change, sent to the hub as a suggested limit |
| `.timeout(ms)` | Return to the safe value if nothing sets the output again in time, like a pump's maximum run |
| `.onOff()` | A switch with values 0 and 1 |
| `heartbeat(ms)` | Fall to the safe state when no heartbeat arrives from the hub for `ms` milliseconds |
| `applySafeState(reason)` | Apply the safe state from the sketch, for example from a local stop button |
| `.states(labels, count)` | A reading with named states, such as a float switch. `fn` returns the index of the state |
| `.internal()` | An output only the sketch sets. The hub can't read or set the output, but a stop and a lost heartbeat still return the output to safe |
| `action(name, fn)` | An action the hub can request from the board. `fn` receives the arguments in the order they were declared and returns `nullptr` to run, or a short reason such as `"tank_empty"` to refuse |
| `.arg(name, unit, min, max)` | One argument of an action, up to 3. The board blocks values outside the range |
| `drive(output, value, ms)` | Set an output from the sketch, and return it to safe after `ms` milliseconds when `ms` isn't 0 |
| `misconfigured()` | True if a name was invalid, a limit was backwards or there were too many channels. The board then blocks all commands |

Names are lowercase letters, digits and underscores, up to 24 characters, and units use the names in the OpenHAL spec (`degC`, `percent`, `deg`, `V`, `A`, `rpm` and so on). A sketch can have up to 8 readings, 8 outputs and 4 actions by default, and defining `OPENHAL_MAX_READS`, `OPENHAL_MAX_OUTPUTS` or `OPENHAL_MAX_ACTIONS` before the include changes those limits.

## Examples

| Example | Board shows the hub | Wiring on an Uno (ESP32 pins in brackets) |
|---|---|---|
| PlantWaterer | Soil moisture, a tank float switch and a `water` action that never runs the pump from an empty tank. The canonical OpenHAL example (examples/plant-waterer/) | Capacitive soil sensor on A0 (GPIO 35), float switch from pin 4 to ground (GPIO 27), pump relay on pin 7 (GPIO 26) |
| DeskFan | A thermistor temperature streamed every second and a PWM fan. The board blocks fan_speed values outside 0 to 100 % and stops the fan when no heartbeat arrives for 2 s | A 10k NTC thermistor and a 10k resistor as a divider on A0, the fan's MOSFET gate on pin 9 |
| LedStrip | An ambient light level and the brightness of a 12 V LED strip | MOSFET gate on pin 6 (GPIO 25), photoresistor divider on A1 (GPIO 34) |
| ServoArm | A servo angle kept between 20 and 160 degrees so the arm can't hit its end stops. The arm parks at 90 degrees on a stop and when the hub's heartbeat stops. Because the Arduino Servo library doesn't support ESP32, the sketch drives the 50 Hz pulse with the LEDC peripheral on ESP32 | Servo signal on pin 3 (GPIO 13), servo powered from its own 5 V supply |
| SoilPump | Soil moisture and a pump that stops itself after 20 s, with a local stop button. The board also stops the pump when no heartbeat arrives for 3 s | Capacitive soil sensor on A2 (GPIO 35), pump relay on pin 7 (GPIO 26), button from pin 2 to ground (GPIO 27) |

## Connecting to the hub

Plug the board in and run `openhal discover`. The hub only sends `HELLO`, which never changes anything, to USB serial ports that belong to common Arduino and ESP32 boards. Then `openhal writer start --driver openhal-firmware --param port=<port>` drafts a device file from the board's own description, with every limit marked suggested, and the hub keeps the device read-only until you confirm the limits. For the plant waterer you can also copy `examples/plant-waterer/plant-waterer.hal.yaml` and follow its test plan.

The wire protocol is in `spec/FIRMWARE-PROTOCOL.md` in the OpenHAL repository.

## Memory

Every example compiles with arduino-cli 1.1.1 for `arduino:avr:uno` (core 1.8.8) and `esp32:esp32:esp32` (Espressif core 3.x) with no warnings from the library. Pins differ per board, so the examples pick ESP32 GPIO numbers when `ESP32` is defined, and ServoArm drives the servo pulse with the LEDC peripheral there because the Arduino Servo library doesn't support ESP32.

The library allocates nothing on the heap, and the DeskFan example on an Uno uses 9.5 KB of flash (29 %) and 1,369 bytes of RAM (66 %), including the Arduino serial buffers. Most of the library's share is the line buffer of 250 bytes and the tables for 8 readings and 8 outputs. Lower `OPENHAL_MAX_READS` and `OPENHAL_MAX_OUTPUTS` to save RAM.

## Building on a computer

`extras/host` holds a small stand-in for the Arduino core, and the OpenHAL test suite builds every example with the stand-in and runs the conformance suite against the real library code, as `tests/firmware/test_arduino_host.py` shows.

## License

The library is licensed under Apache-2.0, like the rest of OpenHAL.
