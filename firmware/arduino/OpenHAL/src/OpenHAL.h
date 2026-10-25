// OpenHAL for Arduino. A board running this library describes itself to an OpenHAL hub,
// enforces its own output limits, and falls to its safe state when the hub goes quiet.
// Protocol: spec/FIRMWARE-PROTOCOL.md in the OpenHAL repository. License: Apache-2.0.
//
// The hub's safety kernel is the authority. These limits are a second wall in the firmware,
// so a bug or a cable fault on the host side still can't drive an output past them.

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

typedef float (*OpenHalReadFn)();
typedef void (*OpenHalWriteFn)(float value);
typedef const char* (*OpenHalActionFn)(const float* args);

class OpenHalReading {
 public:
  // Stream this value to the hub every `ms` milliseconds (0 means only when asked).
  OpenHalReading& every(unsigned long ms);
  // The range a working sensor reports. Values outside it are flagged as suspect by the hub.
  OpenHalReading& range(float lo, float hi);
  OpenHalReading& states(const char* const* labels, uint8_t count);

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
};

class OpenHalOutput {
 public:
  // The lowest and highest value this output accepts. Writes outside are refused.
  OpenHalOutput& limits(float min, float max);
  // The value applied at start, on SAFE, and when heartbeats stop.
  OpenHalOutput& safe(float value);
  // The fastest change the hardware should see, in units per second. Advertised to the hub.
  OpenHalOutput& rate(float perSecond);
  // Return to the safe value if nothing rewrites this output within `ms` (a pump's maximum run).
  OpenHalOutput& timeout(unsigned long ms);
  // A switch with values 0 and 1, reported to the hub as a bool.
  OpenHalOutput& onOff();
  OpenHalOutput& internal();

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

  // Register before begin(). Names are lowercase letters, digits and underscores.
  OpenHalReading& reading(const char* name, const char* unit, OpenHalReadFn read);
  OpenHalOutput& output(const char* name, const char* unit, OpenHalWriteFn write);
  OpenHalAction& action(const char* name, OpenHalActionFn run);
  // Short forms. read() is reading(), and write() is output() with its limits in one call.
  OpenHalReading& read(const char* name, const char* unit, OpenHalReadFn fn) { return reading(name, unit, fn); }
  OpenHalOutput& write(const char* name, const char* unit, float min, float max, OpenHalWriteFn fn) {
    return output(name, unit, fn).limits(min, max).safe(min);
  }
  // Fall to the safe state when no heartbeat arrives for `ms` milliseconds (0 turns this off).
  void heartbeat(unsigned long ms);

  // Applies every safe value, then starts listening on `port`.
  void begin(Stream& port);
  // Call from loop(). Reads the port, streams values and watches the heartbeat.
  void poll();
  // Apply the safe state from the sketch itself, for example from a local stop button.
  void applySafeState(const char* reason);
  void drive(OpenHalOutput& output, float value, unsigned long forMs = 0);

  // True if registration failed (too many channels, a bad name, or min above max).
  bool misconfigured() const { return misconfigured_; }

 private:
  void handleLine(char* line);
  void handleWrite(unsigned int seq, char* name, char* text);
  void handleAction(unsigned int seq, char** parts, uint8_t count);
  void handleRead(unsigned int seq, char* name);
  void putReading(const OpenHalReading& reading, float value);
  void sendDescription(unsigned int seq);
  void startLine(unsigned int seq, const char* verb);
  void put(const char* text);
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
};

// Exposed for tests. Strict decimal parsing (no exponents) and compact formatting.
bool openhalParseNumber(const char* text, float* out);
void openhalFormatNumber(float value, char* out, size_t size);
bool openhalValidName(const char* name);

#endif
