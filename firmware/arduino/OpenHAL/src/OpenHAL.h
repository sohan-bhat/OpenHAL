#ifndef OPENHAL_H
#define OPENHAL_H

#include <Arduino.h>

#ifndef OPENHAL_MAX_READS
#define OPENHAL_MAX_READS 8
#endif
#ifndef OPENHAL_MAX_OUTPUTS
#define OPENHAL_MAX_OUTPUTS 8
#endif
#ifndef OPENHAL_MAX_ACTIONS
#define OPENHAL_MAX_ACTIONS 4
#endif
#define OPENHAL_MAX_ARGS 3
#define OPENHAL_MAX_STATES 8
#define OPENHAL_LINE_MAX 250
#define OPENHAL_PROTOCOL 1

#ifndef OPENHAL_PINS
#if defined(NUM_DIGITAL_PINS)
#define OPENHAL_PINS 1
#else
#define OPENHAL_PINS 0
#endif
#endif
#ifndef OPENHAL_PWM_BITS
#define OPENHAL_PWM_BITS 8
#endif
#ifndef OPENHAL_ADC_BITS
#if defined(ARDUINO_ARCH_ESP32)
#define OPENHAL_ADC_BITS 12
#else
#define OPENHAL_ADC_BITS 10
#endif
#endif
#if OPENHAL_PINS
#if defined(PIN_A0) && defined(NUM_ANALOG_INPUTS) && (PIN_A0 + NUM_ANALOG_INPUTS > NUM_DIGITAL_PINS)
#define OPENHAL_PIN_COUNT (PIN_A0 + NUM_ANALOG_INPUTS)
#else
#define OPENHAL_PIN_COUNT NUM_DIGITAL_PINS
#endif
#else
#define OPENHAL_PIN_COUNT 0
#endif

typedef float (*OpenHalReadFn)();
typedef void (*OpenHalWriteFn)(float value);
typedef const char* (*OpenHalActionFn)(const float* args);

class OpenHalReading {
 public:
  OpenHalReading& every(unsigned long ms);
  OpenHalReading& range(float lo, float hi);
  OpenHalReading& states(const char* const* labels, uint8_t count);
  OpenHalReading& pin(uint8_t number);

 private:
  friend class OpenHAL;
  const char* name_ = nullptr;
  const char* unit_ = nullptr;
  OpenHalReadFn read_ = nullptr;
  const char* const* labels_ = nullptr;
  uint8_t labelCount_ = 0;
  bool bad_ = false;
  unsigned long every_ = 0;
  unsigned long last_ = 0;
  bool hasRange_ = false;
  float lo_ = 0;
  float hi_ = 0;
  int8_t pin_ = -1;
};

class OpenHalOutput {
 public:
  OpenHalOutput& limits(float min, float max);
  OpenHalOutput& safe(float value);
  OpenHalOutput& rate(float perSecond);
  OpenHalOutput& timeout(unsigned long ms);
  OpenHalOutput& onOff();
  OpenHalOutput& internal();
  OpenHalOutput& pin(uint8_t number);

 private:
  friend class OpenHAL;
  const char* name_ = nullptr;
  const char* unit_ = nullptr;
  OpenHalWriteFn write_ = nullptr;
  float min_ = 0;
  float max_ = 0;
  float safe_ = 0;
  float rate_ = 0;
  float value_ = 0;
  unsigned long timeout_ = 0;
  unsigned long setAt_ = 0;
  unsigned long runFor_ = 0;
  bool onOff_ = false;
  bool internal_ = false;
  int8_t pin_ = -1;
};

class OpenHalAction {
 public:
  OpenHalAction& arg(const char* name, const char* unit, float min, float max);

 private:
  friend class OpenHAL;
  const char* name_ = nullptr;
  OpenHalActionFn run_ = nullptr;
  const char* argNames_[OPENHAL_MAX_ARGS] = {nullptr, nullptr, nullptr};
  const char* argUnits_[OPENHAL_MAX_ARGS] = {nullptr, nullptr, nullptr};
  float argMin_[OPENHAL_MAX_ARGS] = {0, 0, 0};
  float argMax_[OPENHAL_MAX_ARGS] = {0, 0, 0};
  uint8_t argCount_ = 0;
  bool bad_ = false;
};

class OpenHAL {
 public:
  OpenHAL(const char* product, const char* version);

  OpenHalReading& reading(const char* name, const char* unit, OpenHalReadFn read);
  OpenHalOutput& output(const char* name, const char* unit, OpenHalWriteFn write);
  OpenHalAction& action(const char* name, OpenHalActionFn run);
  OpenHalReading& read(const char* name, const char* unit, OpenHalReadFn fn) { return reading(name, unit, fn); }
  OpenHalOutput& write(const char* name, const char* unit, float min, float max, OpenHalWriteFn fn) {
    return output(name, unit, fn).limits(min, max).safe(min);
  }
  void heartbeat(unsigned long ms);
  void pins();
  void reserve(uint8_t pin);
  uint8_t pinModes(uint8_t pin) const;

  void begin(Stream& port);
  void poll();
  void applySafeState(const char* reason);
  void drive(OpenHalOutput& output, float value, unsigned long forMs = 0);

  bool misconfigured() const { return misconfigured_; }

 private:
  void handleLine(char* line);
  void handleWrite(unsigned int seq, char* name, char* text);
  void handleAction(unsigned int seq, char** parts, uint8_t count);
  void handleRead(unsigned int seq, char* name);
  void handlePin(unsigned int seq, char** parts, uint8_t count);
  void putPin(unsigned int seq, uint8_t pin, uint8_t state, float value);
  void putPins();
  bool releasePins();
  bool claimed(uint8_t pin) const;
  void claim(int pin);
  void putReading(const OpenHalReading& reading, float value);
  void sendDescription(unsigned int seq);
  void startLine(unsigned int seq, const char* verb);
  void put(const char* text);
  void put(const __FlashStringHelper* text);
  void putText(const char* text);
  void putChar(char c);
  void putNumber(float value);
  void endLine();
  OpenHalReading* findReading(const char* name);
  OpenHalOutput* findOutput(const char* name);
  OpenHalAction* findAction(const char* name);
  void setOutput(OpenHalOutput& output, float value);

  const char* product_;
  const char* version_;
  Stream* port_ = nullptr;
  OpenHalReading reads_[OPENHAL_MAX_READS];
  OpenHalOutput outputs_[OPENHAL_MAX_OUTPUTS];
  OpenHalAction actions_[OPENHAL_MAX_ACTIONS];
  uint8_t readCount_ = 0;
  uint8_t outputCount_ = 0;
  uint8_t actionCount_ = 0;
  unsigned long heartbeat_ = 0;
  unsigned long lastHeartbeat_ = 0;
  bool misconfigured_ = false;
  bool overflow_ = false;
  char line_[OPENHAL_LINE_MAX + 1];
  uint8_t length_ = 0;
  uint8_t sum_ = 0;
  OpenHalReading spareReading_;
  OpenHalOutput spareOutput_;
  OpenHalAction spareAction_;
  bool pinsOn_ = false;
#if OPENHAL_PINS
  uint8_t pinState_[OPENHAL_PIN_COUNT] = {0};
#if OPENHAL_PWM_BITS > 8
  uint16_t pinDuty_[OPENHAL_PIN_COUNT] = {0};
#else
  uint8_t pinDuty_[OPENHAL_PIN_COUNT] = {0};
#endif
  uint8_t claimed_[(OPENHAL_PIN_COUNT + 7) / 8] = {0};
#endif
};

bool openhalParseNumber(const char* text, float* out);
void openhalFormatNumber(float value, char* out, size_t size);
bool openhalValidName(const char* name);

#endif
