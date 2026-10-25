// A 12 V LED strip on a MOSFET. The hub sees brightness and an ambient light reading.
// Wiring: the MOSFET gate on pin 6, a photoresistor divider on A1 (GPIO 25 and GPIO 34 on an ESP32).

#include <OpenHAL.h>

#if defined(ESP32)
const int STRIP_PIN = 25;  // any output-capable GPIO
const int LIGHT_PIN = 34;  // an ADC1 pin, input only
#else
const int STRIP_PIN = 6;
const int LIGHT_PIN = A1;
#endif

OpenHAL hal("led-strip", "1.0.0");

float readLight() { return analogRead(LIGHT_PIN) * 100.0f / 1023.0f; }

void setBrightness(float percent) { analogWrite(STRIP_PIN, static_cast<int>(percent * 2.55f + 0.5f)); }

void setup() {
  pinMode(STRIP_PIN, OUTPUT);
  Serial.begin(115200);
  hal.read("ambient_light", "percent", readLight).every(2000).range(0, 100);
  hal.write("brightness", "percent", 0, 100, setBrightness).rate(50);  // safe value is the minimum
  hal.heartbeat(5000);
  hal.begin(Serial);
}

void loop() { hal.poll(); }
