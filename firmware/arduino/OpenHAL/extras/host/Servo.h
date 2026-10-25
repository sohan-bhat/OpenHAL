#ifndef OPENHAL_HOST_SERVO_H
#define OPENHAL_HOST_SERVO_H

#include <Arduino.h>

class Servo {
 public:
  void attach(int pin) { pin_ = pin; }
  void write(int degrees) { analogWrite(pin_, degrees); }

 private:
  int pin_ = -1;
};

#endif
