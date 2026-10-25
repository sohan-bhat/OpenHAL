#include "OpenHAL.h"

#include <string.h>

namespace {

const float kLargest = 1.0e9f;

bool finite(float value) { return value == value && value < kLargest && value > -kLargest; }

int hexDigit(char c) {
  if (c >= '0' && c <= '9') return c - '0';
  if (c >= 'A' && c <= 'F') return c - 'A' + 10;
  if (c >= 'a' && c <= 'f') return c - 'a' + 10;
  return -1;
}

bool parseSeq(const char* text, unsigned int* out) {
  if (*text == '\0') return false;
  unsigned long value = 0;
  for (const char* c = text; *c; ++c) {
    if (*c < '0' || *c > '9') return false;
    value = value * 10 + (*c - '0');
    if (value > 65535UL) return false;
  }
  *out = static_cast<unsigned int>(value);
  return true;
}

}

bool openhalValidName(const char* name) {
  if (name == nullptr || name[0] < 'a' || name[0] > 'z') return false;
  size_t length = 0;
  for (const char* c = name; *c; ++c, ++length) {
    bool ok = (*c >= 'a' && *c <= 'z') || (*c >= '0' && *c <= '9') || *c == '_';
    if (!ok || length >= 24) return false;
  }
  return true;
}

bool openhalParseNumber(const char* text, float* out) {
  const char* c = text;
  bool negative = false;
  if (*c == '+' || *c == '-') {
    negative = *c == '-';
    ++c;
  }
  float value = 0;
  float scale = 0;
  bool digits = false;
  for (; *c; ++c) {
    if (*c >= '0' && *c <= '9') {
      digits = true;
      if (scale == 0) {
        value = value * 10 + (*c - '0');
      } else {
        value += (*c - '0') * scale;
        scale /= 10;
      }
    } else if (*c == '.' && scale == 0) {
      scale = 0.1f;
    } else {
      return false;
    }
  }
  if (!digits || !finite(value)) return false;
  *out = negative ? -value : value;
  return true;
}

void openhalFormatNumber(float value, char* out, size_t size) {
  char buffer[24];
  size_t at = 0;
  if (!finite(value)) value = 0;
  bool negative = value < 0;
  if (negative) value = -value;
  unsigned long scaled = static_cast<unsigned long>(value * 10000.0f + 0.5f);
  unsigned long whole = scaled / 10000UL;
  unsigned long fraction = scaled % 10000UL;
  if (negative && scaled != 0) buffer[at++] = '-';
  char digits[12];
  int count = 0;
  do {
    digits[count++] = static_cast<char>('0' + whole % 10);
    whole /= 10;
  } while (whole && count < 11);
  while (count) buffer[at++] = digits[--count];
  if (fraction) {
    buffer[at++] = '.';
    char tail[4];
    for (int i = 3; i >= 0; --i) {
      tail[i] = static_cast<char>('0' + fraction % 10);
      fraction /= 10;
    }
    int last = 3;
    while (last > 0 && tail[last] == '0') --last;
    for (int i = 0; i <= last; ++i) buffer[at++] = tail[i];
  }
  buffer[at] = '\0';
  strncpy(out, buffer, size - 1);
  out[size - 1] = '\0';
}

OpenHalReading& OpenHalReading::every(unsigned long ms) {
  every_ = ms;
  return *this;
}

OpenHalReading& OpenHalReading::range(float lo, float hi) {
  hasRange_ = lo <= hi;
  lo_ = lo;
  hi_ = hi;
  return *this;
}

OpenHalReading& OpenHalReading::states(const char* const* labels, uint8_t count) {
  bad_ = labels == nullptr || count == 0 || count > OPENHAL_MAX_STATES;
  for (uint8_t i = 0; !bad_ && i < count; ++i) bad_ = !openhalValidName(labels[i]);
  labels_ = labels;
  labelCount_ = bad_ ? 0 : count;
  unit_ = "enum";
  return *this;
}

OpenHalOutput& OpenHalOutput::limits(float min, float max) {
  min_ = min;
  max_ = max;
  return *this;
}

OpenHalOutput& OpenHalOutput::safe(float value) {
  safe_ = value;
  return *this;
}

OpenHalOutput& OpenHalOutput::rate(float perSecond) {
  rate_ = perSecond > 0 ? perSecond : 0;
  return *this;
}

OpenHalOutput& OpenHalOutput::timeout(unsigned long ms) {
  timeout_ = ms;
  return *this;
}

OpenHalOutput& OpenHalOutput::onOff() {
  onOff_ = true;
  unit_ = "bool";
  min_ = 0;
  max_ = 1;
  if (safe_ != 0) safe_ = 1;
  return *this;
}

OpenHalOutput& OpenHalOutput::internal() {
  internal_ = true;
  return *this;
}

OpenHalAction& OpenHalAction::arg(const char* name, const char* unit, float min, float max) {
  bool duplicate = false;
  for (uint8_t i = 0; i < argCount_; ++i) duplicate |= strcmp(argNames_[i], name) == 0;
  if (argCount_ >= OPENHAL_MAX_ARGS || !openhalValidName(name) || unit == nullptr || min > max || duplicate) {
    bad_ = true;
    return *this;
  }
  argNames_[argCount_] = name;
  argUnits_[argCount_] = unit;
  argMin_[argCount_] = min;
  argMax_[argCount_] = max;
  ++argCount_;
  return *this;
}

OpenHAL::OpenHAL(const char* product, const char* version) : product_(product), version_(version) {}

OpenHalReading& OpenHAL::reading(const char* name, const char* unit, OpenHalReadFn read) {
  if (readCount_ >= OPENHAL_MAX_READS || !openhalValidName(name) || read == nullptr || findReading(name)) {
    misconfigured_ = true;
    return spareReading_;
  }
  OpenHalReading& slot = reads_[readCount_++];
  slot.name_ = name;
  slot.unit_ = unit;
  slot.read_ = read;
  return slot;
}

OpenHalOutput& OpenHAL::output(const char* name, const char* unit, OpenHalWriteFn write) {
  if (outputCount_ >= OPENHAL_MAX_OUTPUTS || !openhalValidName(name) || write == nullptr || findOutput(name) ||
      findReading(name)) {
    misconfigured_ = true;
    return spareOutput_;
  }
  OpenHalOutput& slot = outputs_[outputCount_++];
  slot.name_ = name;
  slot.unit_ = unit;
  slot.write_ = write;
  return slot;
}

OpenHalAction& OpenHAL::action(const char* name, OpenHalActionFn run) {
  if (actionCount_ >= OPENHAL_MAX_ACTIONS || !openhalValidName(name) || run == nullptr || findAction(name)) {
    misconfigured_ = true;
    return spareAction_;
  }
  OpenHalAction& slot = actions_[actionCount_++];
  slot.name_ = name;
  slot.run_ = run;
  return slot;
}

void OpenHAL::heartbeat(unsigned long ms) { heartbeat_ = ms; }

void OpenHAL::drive(OpenHalOutput& output, float value, unsigned long forMs) {
  setOutput(output, value);
  output.runFor_ = forMs;
}

void OpenHAL::begin(Stream& port) {
  for (uint8_t i = 0; i < outputCount_; ++i) {
    OpenHalOutput& output = outputs_[i];
    if (output.min_ > output.max_ || output.safe_ < output.min_ || output.safe_ > output.max_) misconfigured_ = true;
  }
  for (uint8_t i = 0; i < readCount_; ++i) misconfigured_ |= reads_[i].bad_;
  for (uint8_t i = 0; i < actionCount_; ++i) misconfigured_ |= actions_[i].bad_;
  for (uint8_t i = 0; i < outputCount_; ++i) {
    outputs_[i].value_ = outputs_[i].safe_;
    outputs_[i].write_(outputs_[i].safe_);
  }
  port_ = &port;
  lastHeartbeat_ = millis();
}

void OpenHAL::poll() {
  if (port_ == nullptr) return;
  while (port_->available() > 0) {
    int byte = port_->read();
    if (byte < 0) break;
    char c = static_cast<char>(byte);
    if (c == '\r') continue;
    if (c == '\n') {
      if (overflow_) {
        startLine(0, "ERR");
        put(" format line_too_long");
        endLine();
      } else {
        line_[length_] = '\0';
        if (length_) handleLine(line_);
      }
      length_ = 0;
      overflow_ = false;
    } else if (length_ < OPENHAL_LINE_MAX) {
      line_[length_++] = c;
    } else {
      overflow_ = true;
    }
  }

  unsigned long now = millis();
  if (heartbeat_ && now - lastHeartbeat_ > heartbeat_) {
    bool changed = false;
    for (uint8_t i = 0; i < outputCount_; ++i) changed |= outputs_[i].value_ != outputs_[i].safe_;
    if (changed) applySafeState("heartbeat_lost");
    lastHeartbeat_ = now;
  }
  for (uint8_t i = 0; i < outputCount_; ++i) {
    OpenHalOutput& output = outputs_[i];
    if (output.runFor_ && now - output.setAt_ >= output.runFor_) setOutput(output, output.safe_);
    if (output.timeout_ && output.value_ != output.safe_ && now - output.setAt_ > output.timeout_) {
      setOutput(output, output.safe_);
      startLine(0, "SAFE");
      putChar(' ');
      put(output.name_);
      put("_timeout");
      endLine();
    }
  }
  for (uint8_t i = 0; i < readCount_; ++i) {
    OpenHalReading& reading = reads_[i];
    if (reading.every_ && now - reading.last_ >= reading.every_) {
      reading.last_ = now;
      float value = reading.read_();
      if (!finite(value)) continue;
      if (reading.labelCount_ && (value < 0 || value >= reading.labelCount_)) continue;
      startLine(0, "EVT");
      putChar(' ');
      put(reading.name_);
      putChar(' ');
      putReading(reading, value);
      endLine();
    }
  }
}

void OpenHAL::applySafeState(const char* reason) {
  for (uint8_t i = 0; i < outputCount_; ++i) setOutput(outputs_[i], outputs_[i].safe_);
  if (port_ == nullptr) return;
  startLine(0, "SAFE");
  putChar(' ');
  put(reason);
  endLine();
}

void OpenHAL::handleLine(char* line) {
  char* star = strrchr(line, '*');
  if (star == nullptr || hexDigit(star[1]) < 0 || hexDigit(star[2]) < 0 || star[3] != '\0') {
    startLine(0, "ERR");
    put(" checksum bad_line");
    endLine();
    return;
  }
  uint8_t sum = 0;
  for (char* c = line; c < star; ++c) sum ^= static_cast<uint8_t>(*c);
  if (sum != (hexDigit(star[1]) << 4 | hexDigit(star[2]))) {
    startLine(0, "ERR");
    put(" checksum bad_line");
    endLine();
    return;
  }
  *star = '\0';

  char* parts[3 + 2 * OPENHAL_MAX_ARGS] = {nullptr};
  uint8_t count = 0;
  char* token = line;
  while (token && count < 3 + 2 * OPENHAL_MAX_ARGS) {
    parts[count++] = token;
    char* space = strchr(token, ' ');
    if (space) *space = '\0';
    token = space ? space + 1 : nullptr;
  }
  unsigned int seq = 0;
  if (count < 2 || token != nullptr || !parseSeq(parts[0], &seq)) {
    startLine(0, "ERR");
    put(" format bad_line");
    endLine();
    return;
  }
  const char* verb = parts[1];

  if (strcmp(verb, "HELLO") == 0) {
    startLine(seq, "OK");
    put(" openhal 1 ");
    putText(product_);
    putChar(' ');
    putText(version_);
    endLine();
  } else if (strcmp(verb, "DESC") == 0) {
    sendDescription(seq);
  } else if (strcmp(verb, "HB") == 0) {
    lastHeartbeat_ = millis();
    startLine(seq, "OK");
    endLine();
  } else if (strcmp(verb, "SAFE") == 0) {
    for (uint8_t i = 0; i < outputCount_; ++i) setOutput(outputs_[i], outputs_[i].safe_);
    startLine(seq, "OK");
    endLine();
  } else if (strcmp(verb, "READ") == 0 && count == 3) {
    handleRead(seq, parts[2]);
  } else if (strcmp(verb, "WRITE") == 0 && count == 4) {
    handleWrite(seq, parts[2], parts[3]);
  } else if (strcmp(verb, "ACT") == 0 && count >= 3) {
    handleAction(seq, parts + 2, count - 2);
  } else {
    startLine(seq, "ERR");
    put(" unknown ");
    put(verb);
    endLine();
  }
}

void OpenHAL::handleRead(unsigned int seq, char* name) {
  OpenHalReading* reading = findReading(name);
  OpenHalOutput* output = reading ? nullptr : findOutput(name);
  if (reading == nullptr && (output == nullptr || output->internal_)) {
    startLine(seq, "ERR");
    put(" unknown ");
    put(name);
    endLine();
    return;
  }
  float value = reading ? reading->read_() : output->value_;
  bool outside = reading && reading->labelCount_ && (value < 0 || value >= reading->labelCount_);
  if (!finite(value) || outside) {
    startLine(seq, "ERR");
    put(" fault ");
    put(name);
    endLine();
    return;
  }
  startLine(seq, "VAL");
  putChar(' ');
  put(name);
  putChar(' ');
  if (reading) {
    putReading(*reading, value);
  } else {
    putNumber(value);
  }
  endLine();
}

void OpenHAL::putReading(const OpenHalReading& reading, float value) {
  if (reading.labelCount_) {
    put(reading.labels_[static_cast<uint8_t>(value)]);
  } else {
    putNumber(value);
  }
}

void OpenHAL::handleAction(unsigned int seq, char** parts, uint8_t count) {
  OpenHalAction* action = findAction(parts[0]);
  if (action == nullptr) {
    startLine(seq, "ERR");
    put(" unknown ");
    put(parts[0]);
    endLine();
    return;
  }
  if (misconfigured_) {
    startLine(seq, "ERR");
    put(" busy misconfigured");
    endLine();
    return;
  }
  float values[OPENHAL_MAX_ARGS] = {0, 0, 0};
  bool seen[OPENHAL_MAX_ARGS] = {false, false, false};
  if (count != 1 + 2 * action->argCount_) {
    startLine(seq, "ERR");
    put(" format ");
    put(action->name_);
    endLine();
    return;
  }
  for (uint8_t i = 1; i + 1 < count; i += 2) {
    uint8_t index = 0;
    while (index < action->argCount_ && strcmp(action->argNames_[index], parts[i]) != 0) ++index;
    float value = 0;
    if (index == action->argCount_ || seen[index] || !openhalParseNumber(parts[i + 1], &value)) {
      startLine(seq, "ERR");
      put(" format ");
      put(index == action->argCount_ ? action->name_ : action->argNames_[index]);
      endLine();
      return;
    }
    if (value < action->argMin_[index] || value > action->argMax_[index]) {
      bool high = value > action->argMax_[index];
      startLine(seq, "ERR");
      put(" limit ");
      put(action->argNames_[index]);
      put(high ? " max " : " min ");
      putNumber(high ? action->argMax_[index] : action->argMin_[index]);
      endLine();
      return;
    }
    seen[index] = true;
    values[index] = value;
  }
  const char* refused = action->run_(values);
  if (refused != nullptr) {
    startLine(seq, "ERR");
    put(" interlock ");
    putText(refused);
    endLine();
    return;
  }
  startLine(seq, "OK");
  putChar(' ');
  put(action->name_);
  endLine();
}

void OpenHAL::handleWrite(unsigned int seq, char* name, char* text) {
  OpenHalOutput* output = findOutput(name);
  float value = 0;
  if (output == nullptr || output->internal_) {
    startLine(seq, "ERR");
    put(" unknown ");
    put(name);
    endLine();
    return;
  }
  if (misconfigured_) {
    startLine(seq, "ERR");
    put(" busy misconfigured");
    endLine();
    return;
  }
  if (!openhalParseNumber(text, &value) || (output->onOff_ && value != 0 && value != 1)) {
    startLine(seq, "ERR");
    put(" format ");
    put(name);
    endLine();
    return;
  }
  if (value < output->min_ || value > output->max_) {
    bool high = value > output->max_;
    startLine(seq, "ERR");
    put(" limit ");
    put(name);
    put(high ? " max " : " min ");
    putNumber(high ? output->max_ : output->min_);
    endLine();
    return;
  }
  setOutput(*output, value);
  startLine(seq, "OK");
  putChar(' ');
  put(name);
  putChar(' ');
  putNumber(value);
  endLine();
}

void OpenHAL::setOutput(OpenHalOutput& output, float value) {
  output.value_ = value;
  output.setAt_ = millis();
  output.runFor_ = 0;
  output.write_(value);
}

void OpenHAL::sendDescription(unsigned int seq) {
  startLine(seq, "DESC");
  put(" {\"p\":\"");
  putText(product_);
  put("\",\"v\":\"");
  putText(version_);
  put("\",\"hb\":");
  putNumber(static_cast<float>(heartbeat_));
  put(",\"r\":[");
  for (uint8_t i = 0; i < readCount_; ++i) {
    const OpenHalReading& reading = reads_[i];
    if (i) putChar(',');
    put("{\"n\":\"");
    put(reading.name_);
    put("\",\"u\":\"");
    putText(reading.unit_);
    put("\",\"e\":");
    putNumber(static_cast<float>(reading.every_));
    if (reading.hasRange_) {
      put(",\"lo\":");
      putNumber(reading.lo_);
      put(",\"hi\":");
      putNumber(reading.hi_);
    }
    if (reading.labelCount_) {
      put(",\"s\":[");
      for (uint8_t j = 0; j < reading.labelCount_; ++j) {
        if (j) putChar(',');
        putChar('"');
        put(reading.labels_[j]);
        putChar('"');
      }
      putChar(']');
    }
    putChar('}');
  }
  put("],\"w\":[");
  bool first = true;
  for (uint8_t i = 0; i < outputCount_; ++i) {
    const OpenHalOutput& output = outputs_[i];
    if (output.internal_) continue;
    if (!first) putChar(',');
    first = false;
    put("{\"n\":\"");
    put(output.name_);
    put("\",\"u\":\"");
    putText(output.unit_);
    put("\",\"min\":");
    putNumber(output.min_);
    put(",\"max\":");
    putNumber(output.max_);
    put(",\"safe\":");
    putNumber(output.safe_);
    if (output.rate_ > 0) {
      put(",\"rate\":");
      putNumber(output.rate_);
    }
    if (output.timeout_) {
      put(",\"t\":");
      putNumber(static_cast<float>(output.timeout_));
    }
    putChar('}');
  }
  putChar(']');
  if (actionCount_) {
    put(",\"a\":[");
    for (uint8_t i = 0; i < actionCount_; ++i) {
      const OpenHalAction& action = actions_[i];
      if (i) putChar(',');
      put("{\"n\":\"");
      put(action.name_);
      put("\",\"g\":[");
      for (uint8_t j = 0; j < action.argCount_; ++j) {
        if (j) putChar(',');
        put("{\"n\":\"");
        put(action.argNames_[j]);
        put("\",\"u\":\"");
        putText(action.argUnits_[j]);
        put("\",\"min\":");
        putNumber(action.argMin_[j]);
        put(",\"max\":");
        putNumber(action.argMax_[j]);
        putChar('}');
      }
      put("]}");
    }
    putChar(']');
  }
  putChar('}');
  endLine();
}

void OpenHAL::startLine(unsigned int seq, const char* verb) {
  sum_ = 0;
  char digits[6];
  int count = 0;
  do {
    digits[count++] = static_cast<char>('0' + seq % 10);
    seq /= 10;
  } while (seq && count < 5);
  while (count) putChar(digits[--count]);
  putChar(' ');
  put(verb);
}

void OpenHAL::put(const char* text) {
  for (const char* c = text; *c; ++c) putChar(*c);
}

void OpenHAL::putText(const char* text) {
  if (text == nullptr) return;
  for (const char* c = text; *c; ++c) {
    bool printable = *c > ' ' && *c <= '~' && *c != '"' && *c != '\\' && *c != '*';
    if (printable) putChar(*c);
  }
}

void OpenHAL::putChar(char c) {
  sum_ ^= static_cast<uint8_t>(c);
  port_->write(static_cast<uint8_t>(c));
}

void OpenHAL::putNumber(float value) {
  char text[24];
  openhalFormatNumber(value, text, sizeof text);
  put(text);
}

void OpenHAL::endLine() {
  static const char kHex[] = "0123456789ABCDEF";
  uint8_t sum = sum_;
  port_->write(static_cast<uint8_t>('*'));
  port_->write(static_cast<uint8_t>(kHex[sum >> 4]));
  port_->write(static_cast<uint8_t>(kHex[sum & 0x0F]));
  port_->write(static_cast<uint8_t>('\n'));
}

OpenHalReading* OpenHAL::findReading(const char* name) {
  for (uint8_t i = 0; i < readCount_; ++i)
    if (strcmp(reads_[i].name_, name) == 0) return &reads_[i];
  return nullptr;
}

OpenHalOutput* OpenHAL::findOutput(const char* name) {
  for (uint8_t i = 0; i < outputCount_; ++i)
    if (strcmp(outputs_[i].name_, name) == 0) return &outputs_[i];
  return nullptr;
}

OpenHalAction* OpenHAL::findAction(const char* name) {
  for (uint8_t i = 0; i < actionCount_; ++i)
    if (strcmp(actions_[i].name_, name) == 0) return &actions_[i];
  return nullptr;
}
