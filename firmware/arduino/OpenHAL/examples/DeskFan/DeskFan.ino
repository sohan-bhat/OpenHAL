// A desk fan with a thermistor. The hub sees temperature (streamed every second) and fan_speed.
// Wiring: a 10k NTC thermistor and a 10k resistor as a divider on A0, the fan's MOSFET gate on pin 9.
// The board refuses fan_speed outside 0 to 100 % and stops the fan if the hub goes quiet for 2 s.

#include <OpenHAL.h>

const int FAN_PIN = 9;
const int THERMISTOR_PIN = A0;

OpenHAL hal("desk-fan", "1.0.0");

float readTemperature() {
  int raw = analogRead(THERMISTOR_PIN);
  if (raw <= 0 || raw >= 1023) return NAN;  // open or shorted sensor
  float resistance = 10000.0f * raw / (1023.0f - raw);
  float kelvin = 1.0f / (1.0f / 298.15f + log(resistance / 10000.0f) / 3950.0f);
  return kelvin - 273.15f;
}

void setFan(float percent) { analogWrite(FAN_PIN, static_cast<int>(percent * 2.55f + 0.5f)); }

void setup() {
  pinMode(FAN_PIN, OUTPUT);
  Serial.begin(115200);
  hal.reading("temperature", "degC", readTemperature).every(1000).range(-20, 80);
  hal.output("fan_speed", "percent", setFan).limits(0, 100).safe(0).rate(20);
  hal.heartbeat(2000);
  hal.begin(Serial);
}

void loop() { hal.poll(); }
