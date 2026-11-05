# OpenHAL for Arduino

Add OpenHAL to a sketch and the board describes itself to an OpenHAL hub. The board also blocks outputs outside the sketch's limits and returns every output to its safe value when the hub's heartbeat stops, as a backup to the hub's kernel.

## Sketch

The plant waterer, shortened from `examples/PlantWaterer`. The pump has no channel of its own, so the hub runs the pump only through `water`, and the board never runs the pump from an empty tank.

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

`begin()` applies every safe value before the board accepts commands, so outputs start safe after a reset.

Leave out `.internal()` for an output the hub may set. The LedStrip example's short forms `hal.read("ambient_light", "percent", readLight)` and `hal.write("brightness", "percent", 0, 100, setBrightness)` equal `reading()` and `output()`, and `write()` makes the minimum the safe value unless `.safe()` sets another.

## Readings and outputs

| Call | Does |
|---|---|
| `reading(name, unit, fn)` | A readable value. `fn` returns a float, or `NAN` for no value |
| `.every(ms)` | Stream the value every `ms` milliseconds |
| `.range(lo, hi)` | A working sensor's range. The hub flags values outside the range |
| `output(name, unit, fn)` | A settable value. `fn` gets a value already checked against the limits |
| `.limits(min, max)` | The board blocks values outside this range |
| `.safe(value)` | Applied at start, on a stop and when heartbeats stop |
| `.rate(perSecond)` | The fastest safe change, sent to the hub as a suggested limit |
| `.timeout(ms)` | Back to safe if nothing sets the output again in time, like a pump's maximum run |
| `.onOff()` | A switch, 0 or 1 |
| `heartbeat(ms)` | Safe state after `ms` milliseconds with no hub heartbeat |
| `applySafeState(reason)` | Safe state from the sketch, such as from a local stop button |
| `.states(labels, count)` | Named states, such as a float switch. `fn` returns the state's index |
| `.internal()` | An output only the sketch sets, hidden from the hub and still returned to safe on a stop or a lost heartbeat |
| `action(name, fn)` | A requestable action. `fn` gets the arguments in declared order and returns `nullptr` to run, or a short reason such as `"tank_empty"` to block the action |
| `.arg(name, unit, min, max)` | One action argument, up to 3. The board blocks values outside the range |
| `drive(output, value, ms)` | Set an output from the sketch, back to safe after `ms` milliseconds unless `ms` is 0 |
| `misconfigured()` | True after an invalid name, a backwards limit or too many channels. The board then blocks all commands |
| `pins()` | Offer every free pin to the hub, with its modes |
| `.pin(number)` | The pin a reading or output uses, kept from the hub's pin commands |
| `reserve(pin)` | Keep a sketch pin from the hub's pin commands |

## Every pin

`hal.pins()` offers every free pin with the modes the Arduino core reports, from digital in, input pull-up, digital out, PWM out and analog in, and marks interrupt pins and the built-in LED. The modes come from core macros such as `NUM_DIGITAL_PINS` and `digitalPinHasPWM`, so the list fits any board.

The board keeps the serial pins, the flash pins of an ESP8266 or ESP32, pins named with `.pin()` or `reserve()`, and pins set to output before `begin()`.

Each free pin becomes `pin<N>` for digital reads and output, `pin<N>_pwm` for a PWM duty in percent, `pin<N>_analog` for an analog input in percent of full scale and `pin<N>_mode` for input, input_pullup, output or pwm. Each command sets the mode the command needs, and an analog read leaves a driven pin alone. A stop, a lost heartbeat and `applySafeState()` return every pin the hub set to input. A plain pin is medium risk, since the file has no word for what is wired to the pin, and `openhal risk set` changes the level.

PWM uses 8 bits and analog inputs 10 bits, or 12 on an ESP32. Define `OPENHAL_PWM_BITS` before the include to change the PWM range, or `OPENHAL_PINS` as 0 to leave the pin code out.

Names are lowercase letters, digits and underscores, up to 24 characters. Units use the OpenHAL spec names, such as `degC`, `percent`, `deg`, `V`, `A` and `rpm`. A sketch has up to 8 readings, 8 outputs and 4 actions, and `OPENHAL_MAX_READS`, `OPENHAL_MAX_OUTPUTS` or `OPENHAL_MAX_ACTIONS` defined before the include change those limits.

## Examples

| Example | Board shows the hub | Wiring on an Uno or ESP32 |
|---|---|---|
| PlantWaterer | The canonical example from examples/plant-waterer/. Soil moisture, a tank float switch and a `water` action that never runs the pump from an empty tank | Capacitive soil sensor on A0 or GPIO 35, float switch from pin 4 or GPIO 27 to ground, pump relay on pin 7 or GPIO 26 |
| DeskFan | A thermistor temperature every second and a PWM fan. The board blocks fan_speed outside 0 to 100 % and stops the fan after 2 s with no heartbeat | 10k NTC thermistor and 10k resistor divider on A0, fan MOSFET gate on pin 9 |
| LedStrip | Ambient light and the brightness of a 12 V LED strip | MOSFET gate on pin 6 or GPIO 25, photoresistor divider on A1 or GPIO 34 |
| ServoArm | A servo angle held between 20 and 160 degrees, clear of the end stops, parking at 90 degrees on a stop or a lost heartbeat. On ESP32 the LEDC peripheral drives the 50 Hz pulse, since the Arduino Servo library doesn't support ESP32 | Servo signal on pin 3 or GPIO 13, servo on its own 5 V supply |
| SoilPump | Soil moisture and a pump that stops after 20 s or after 3 s with no heartbeat, with a local stop button | Capacitive soil sensor on A2 or GPIO 35, pump relay on pin 7 or GPIO 26, button from pin 2 or GPIO 27 to ground |
| BareBoard | Nothing wired. The built-in LED as brightness, the boot button, the uptime, the supply voltage on an ESP8266 and every free pin | Nothing |

## Connecting to the hub

Plug the board in and run `openhal discover`. The hub sends only `HELLO`, which changes nothing, and only to USB serial ports of common Arduino and ESP32 boards. Then `openhal writer start --driver openhal-firmware --param port=<port>` drafts a device file from the board's description, with every limit suggested. Low and medium risk channels take commands within the board's range at once, and high risk ones stay read-only until you confirm their limits. For the plant waterer, copy `examples/plant-waterer/plant-waterer.hal.yaml` instead and follow its test plan. The wire protocol is in `spec/FIRMWARE-PROTOCOL.md`.

## Memory

Every example compiles with no library warnings for `arduino:avr:uno`, core 1.8.8 with arduino-cli 1.5.1, and `esp32:esp32:esp32`, core 3.x with arduino-cli 1.1.1. BareBoard, DeskFan, ServoArm and PlantWaterer also compile for `esp8266:esp8266:generic`, core 3.1.2. LedStrip and SoilPump name analog pins an ESP8266 lacks. The examples pick ESP32 GPIO numbers when `ESP32` is defined.

The library allocates nothing on the heap. DeskFan on an Uno uses 1,799 bytes of RAM, 87 %, serial buffers included. Most of the library's share is the 250 byte line buffer and the tables for 8 readings and 8 outputs. The pin code adds about 45 bytes of RAM on an Uno. Lower `OPENHAL_MAX_READS` and `OPENHAL_MAX_OUTPUTS`, or set `OPENHAL_PINS` to 0, to save RAM.

## Building on a computer

`extras/host` stands in for the Arduino core, so `tests/firmware/test_arduino_host.py` builds every example and runs the conformance suite on the real library code.

## License

Apache-2.0, like the rest of OpenHAL.
