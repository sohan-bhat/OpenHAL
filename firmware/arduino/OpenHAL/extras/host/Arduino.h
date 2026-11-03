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
#define NUM_DIGITAL_PINS 20
#define NUM_ANALOG_INPUTS 6
#define PIN_A0 14
#define LED_BUILTIN 13
#define NOT_AN_INTERRUPT -1
#define analogInputToDigitalPin(p) (((p) < 6) ? (p) + 14 : -1)
#define digitalPinHasPWM(p) ((p) == 3 || (p) == 5 || (p) == 6 || (p) == 9 || (p) == 10 || (p) == 11)
#define digitalPinToInterrupt(p) ((p) == 2 ? 0 : ((p) == 3 ? 1 : NOT_AN_INTERRUPT))

class __FlashStringHelper;
#define F(text) (reinterpret_cast<const __FlashStringHelper*>(text))
#define pgm_read_byte(address) (*reinterpret_cast<const uint8_t*>(address))

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
