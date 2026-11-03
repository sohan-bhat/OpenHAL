#include <OpenHAL.h>

#if defined(LED_BUILTIN)
const int LED_PIN = LED_BUILTIN;
#else
const int LED_PIN = 2;
#endif

#if defined(ESP8266)
ADC_MODE(ADC_VCC);
const bool LED_ACTIVE_LOW = true;
#else
const bool LED_ACTIVE_LOW = false;
#endif

#if defined(CONFIG_IDF_TARGET_ESP32C3) || defined(CONFIG_IDF_TARGET_ESP32C6)
const int BUTTON_PIN = 9;
#else
const int BUTTON_PIN = 0;
#endif

const char* const BUTTON_STATES[] = {"released", "pressed"};

OpenHAL hal("bare-board", "1.1.0");

float readButton() { return digitalRead(BUTTON_PIN) == LOW ? 1 : 0; }

float readUptime() { return millis() / 1000.0f; }

#if defined(ESP8266)
float readSupply() { return ESP.getVcc() / 1000.0f; }
#endif

#if defined(SOC_TEMP_SENSOR_SUPPORTED) && SOC_TEMP_SENSOR_SUPPORTED
float readChip() { return temperatureRead(); }
#endif

void setBrightness(float percent) {
  int duty = static_cast<int>(percent * 2.55f + 0.5f);
  analogWrite(LED_PIN, LED_ACTIVE_LOW ? 255 - duty : duty);
}

void setup() {
  pinMode(LED_PIN, OUTPUT);
  pinMode(BUTTON_PIN, INPUT_PULLUP);
#if defined(ESP8266)
  analogWriteRange(255);
#endif
  setBrightness(0);
  Serial.begin(115200);
  hal.reading("button", "enum", readButton).states(BUTTON_STATES, 2).every(500).pin(BUTTON_PIN);
  hal.reading("uptime", "s", readUptime).every(5000);
#if defined(ESP8266)
  hal.reading("supply_voltage", "V", readSupply).every(2000).range(2.5, 3.6);
#endif
#if defined(SOC_TEMP_SENSOR_SUPPORTED) && SOC_TEMP_SENSOR_SUPPORTED
  hal.reading("chip_temperature", "degC", readChip).every(5000).range(-10, 80);
#endif
  hal.write("brightness", "percent", 0, 100, setBrightness).rate(50).pin(LED_PIN);
  hal.pins();
  hal.heartbeat(5000);
  hal.begin(Serial);
}

void loop() { hal.poll(); }
