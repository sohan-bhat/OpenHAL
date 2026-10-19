// A plant waterer. The hub sees soil moisture and a pump switch. The pump turns itself off after
// 20 s even if the hub never says so, and the board stops it if the hub goes quiet for 3 s.
// A local button on pin 2 stops the pump at once.
// Wiring: a capacitive soil sensor on A2, the pump's relay on pin 7, a button from pin 2 to ground.

#include <OpenHAL.h>

const int PUMP_PIN = 7;
const int SOIL_PIN = A2;
const int BUTTON_PIN = 2;
const int SOIL_DRY = 620;  // raw reading in dry air, calibrate for your sensor
const int SOIL_WET = 280;  // raw reading in a glass of water
#ifndef PUMP_MAX_RUN_MS
#define PUMP_MAX_RUN_MS 20000  // the longest the pump may run without a fresh command
#endif

OpenHAL hal("soil-pump", "1.0.0");

float readMoisture() {
  float percent = (SOIL_DRY - analogRead(SOIL_PIN)) * 100.0f / (SOIL_DRY - SOIL_WET);
  return constrain(percent, 0.0f, 100.0f);
}

void setPump(float on) { digitalWrite(PUMP_PIN, on > 0.5f ? HIGH : LOW); }

void setup() {
  pinMode(PUMP_PIN, OUTPUT);
  pinMode(BUTTON_PIN, INPUT_PULLUP);
  Serial.begin(115200);
  hal.reading("soil_moisture", "percent", readMoisture).every(5000).range(0, 100);
  hal.output("pump", "bool", setPump).onOff().safe(0).timeout(PUMP_MAX_RUN_MS);
  hal.heartbeat(3000);
  hal.begin(Serial);
}

bool wasPressed = false;

void loop() {
  bool pressed = digitalRead(BUTTON_PIN) == LOW;
  if (pressed && !wasPressed) hal.applySafeState("local_button");
  wasPressed = pressed;
  hal.poll();
}
