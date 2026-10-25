#include <OpenHAL.h>

#if defined(ESP32)
const int PUMP_PIN = 26;
const int SOIL_PIN = 35;
const int FLOAT_PIN = 27;
const int SOIL_DRY = 2600;
const int SOIL_WET = 1200;
#else
const int PUMP_PIN = 7;
const int SOIL_PIN = A0;
const int FLOAT_PIN = 4;
const int SOIL_DRY = 620;
const int SOIL_WET = 280;
#endif
#ifndef PUMP_MAX_RUN_MS
#define PUMP_MAX_RUN_MS 30000
#endif

const char* const TANK_STATES[] = {"empty", "ok"};

OpenHAL hal("plant-waterer", "1.0.0");
OpenHalOutput* pump = nullptr;

float readMoisture() {
  float percent = (SOIL_DRY - analogRead(SOIL_PIN)) * 100.0f / (SOIL_DRY - SOIL_WET);
  return constrain(percent, 0.0f, 100.0f);
}

bool tankOk() { return digitalRead(FLOAT_PIN) == LOW; }

float readTank() { return tankOk() ? 1 : 0; }

void setPump(float on) { digitalWrite(PUMP_PIN, on > 0.5f ? HIGH : LOW); }

const char* water(const float* args) {
  if (!tankOk()) return "tank_empty";
  hal.drive(*pump, 1, static_cast<unsigned long>(args[0] * 1000.0f));
  return nullptr;
}

const char* stop(const float* args) {
  (void)args;
  hal.drive(*pump, 0);
  return nullptr;
}

void setup() {
  pinMode(PUMP_PIN, OUTPUT);
  pinMode(FLOAT_PIN, INPUT_PULLUP);
  Serial.begin(115200);
  hal.reading("soil_moisture", "percent", readMoisture).every(1000).range(0, 100);
  hal.reading("tank", "enum", readTank).states(TANK_STATES, 2).every(1000);
  pump = &hal.output("pump", "bool", setPump).onOff().safe(0).timeout(PUMP_MAX_RUN_MS).internal();
  hal.action("water", water).arg("duration", "s", 1, 30);
  hal.action("stop", stop);
  hal.heartbeat(3000);
  hal.begin(Serial);
}

void loop() {
  if (!tankOk() && digitalRead(PUMP_PIN) == HIGH) hal.applySafeState("tank_empty");
  hal.poll();
}
