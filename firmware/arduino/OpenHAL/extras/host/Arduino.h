#ifndef OPENHAL_HOST_ARDUINO_H
#define OPENHAL_HOST_ARDUINO_H

#include <math.h>
#include <stddef.h>
#include <stdint.h>

#define HIGH 1
#define LOW 0
#define INPUT 0
#define OUTPUT 1
#define INPUT_PULLUP 2
#define A0 100
#define A1 101
#define A2 102
#define A3 103

template <typename T>
T constrain(T value, T low, T high) {
  return value < low ? low : (value > high ? high : value);
}

unsigned long millis();
void pinMode(int pin, int mode);
void digitalWrite(int pin, int value);
int digitalRead(int pin);
void analogWrite(int pin, int value);
int analogRead(int pin);

class Stream {
 public:
  virtual ~Stream() {}
  virtual int available() = 0;
  virtual int read() = 0;
  virtual size_t write(uint8_t byte) = 0;
};

class HostSerial : public Stream {
 public:
  void begin(unsigned long baud) { (void)baud; }
  int available() override;
  int read() override;
  size_t write(uint8_t byte) override;
};

extern HostSerial Serial;

int hostPinValue(int pin);

void setup();
void loop();

#endif
