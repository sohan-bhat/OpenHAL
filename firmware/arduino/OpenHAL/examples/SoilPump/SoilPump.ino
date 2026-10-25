#include <OpenHAL.h>

#if defined(ESP32)
const int PUMP_PIN = 26;
const int SOIL_PIN = 35;
const int BUTTON_PIN = 27;
const int SOIL_DRY = 2600;
const int SOIL_WET = 1200;
#else
const int PUMP_PIN = 7;
const int SOIL_PIN = A2;
const int BUTTON_PIN = 2;
const int SOIL_DRY = 620;
const int SOIL_WET = 280;
#endif
#ifndef PUMP_MAX_RUN_MS
#define PUMP_MAX_RUN_MS 20000
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
