# OpenHAL for Arduino

Add OpenHAL to a sketch and your board describes itself to an OpenHAL hub. The hub builds the device file from that description, you confirm the limits once, and then AI agents and routines can read and control the board through the hub's safety kernel.

The board also protects itself. It refuses output values outside the limits you set in the sketch, and it returns every output to its safe value when the hub stops sending heartbeats. The hub's kernel is still the authority. The board's checks are a second wall.

## Sketch

```cpp
#include <OpenHAL.h>

OpenHAL hal("desk-fan", "1.0.0");

float readTemperature() { /* your sensor */ }
void setFan(float percent) { analogWrite(9, percent * 2.55); }

void setup() {
  Serial.begin(115200);
  hal.reading("temperature", "degC", readTemperature).every(1000).range(-20, 80);
  hal.output("fan_speed", "percent", setFan).limits(0, 100).safe(0).rate(20);
  hal.heartbeat(2000);
  hal.begin(Serial);
}

void loop() { hal.poll(); }
```

`begin()` applies every safe value before it listens, so outputs start in their safe state after a reset.

## Readings and outputs

| Call | What it does |
|---|---|
| `reading(name, unit, fn)` | A value the hub can read. `fn` returns a float, or `NAN` when the sensor has no value |
| `.every(ms)` | Stream the value every `ms` milliseconds |
| `.range(lo, hi)` | The range a working sensor reports. The hub flags values outside it |
| `output(name, unit, fn)` | A value the hub can set. `fn` receives a value already checked against the limits |
| `.limits(min, max)` | Writes outside this range are refused by the board |
| `.safe(value)` | Applied at start, on a stop, and when heartbeats stop |
| `.rate(perSecond)` | The fastest safe change, sent to the hub as a suggested limit |
| `.timeout(ms)` | Return to the safe value if nothing rewrites the output in time, like a pump's maximum run |
| `.onOff()` | A switch with values 0 and 1 |
| `heartbeat(ms)` | Fall to the safe state when the hub goes quiet for `ms` milliseconds |
| `applySafeState(reason)` | Apply the safe state from the sketch, for example from a local stop button |
| `misconfigured()` | True if a name was invalid, a limit was backwards or there were too many channels. The board then refuses all writes |

Names are lowercase letters, digits and underscores, up to 24 characters. Units use the names in the OpenHAL spec (`degC`, `percent`, `deg`, `V`, `A`, `rpm` and so on). Up to 8 readings and 8 outputs by default. Define `OPENHAL_MAX_READS` or `OPENHAL_MAX_OUTPUTS` before the include to change that.

## Examples

| Example | Board shows the hub |
|---|---|
| DeskFan | A thermistor temperature and a PWM fan |
| LedStrip | An ambient light level and LED brightness |
| ServoArm | A servo angle kept away from its end stops |
| SoilPump | Soil moisture and a pump that stops itself after 20 s, with a local stop button |

## Connecting to the hub

Plug the board in and run `openhal discover`. The hub only sends `HELLO`, which never changes anything, to USB serial ports that belong to common Arduino and ESP32 boards. Then `openhal device add` writes a draft device file with every limit marked suggested, and the hub keeps the device read-only until you confirm them.

The wire protocol is in `spec/FIRMWARE-PROTOCOL.md` in the OpenHAL repository.

## Memory

No heap allocation. On an Uno the library uses about 900 bytes of RAM with 8 readings and 8 outputs, mostly the 250 byte line buffer and the channel tables. Lower the limits to save RAM.

## Building on a computer

`extras/host` holds a small stand-in for the Arduino core. The OpenHAL test suite builds every example with it and runs the conformance suite against the real library code. See `tests/firmware/test_arduino_host.py`.

## License

Apache-2.0, like the rest of OpenHAL.
