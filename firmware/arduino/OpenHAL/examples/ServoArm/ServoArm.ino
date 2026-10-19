// A hobby servo that points a small arm. The hub sees angle, limited to 20 to 160 degrees so the
// arm can't hit its end stops. It parks at 90 degrees on SAFE and when the hub goes quiet.
// Wiring: the servo signal on pin 3, with the servo powered from its own 5 V supply.

#include <OpenHAL.h>
#include <Servo.h>

const int SERVO_PIN = 3;

OpenHAL hal("servo-arm", "1.0.0");
Servo arm;

void setAngle(float degrees) { arm.write(static_cast<int>(degrees + 0.5f)); }

void setup() {
  arm.attach(SERVO_PIN);
  Serial.begin(115200);
  hal.output("angle", "deg", setAngle).limits(20, 160).safe(90).rate(90);
  hal.heartbeat(3000);
  hal.begin(Serial);
}

void loop() { hal.poll(); }
