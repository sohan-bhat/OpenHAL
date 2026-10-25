// A hobby servo that points a small arm. The hub sees angle, limited to 20 to 160 degrees so the
// arm can't hit its end stops. It parks at 90 degrees on SAFE and when the hub goes quiet.
// Wiring: the servo signal on pin 3 (GPIO 13 on an ESP32), with the servo powered from its own 5 V supply.

#include <OpenHAL.h>

#if defined(ESP32)
// The Arduino Servo library doesn't support ESP32, so drive the 50 Hz pulse with the LEDC peripheral.
const int SERVO_PIN = 13;

void attachServo() { ledcAttach(SERVO_PIN, 50, 16); }

void setAngle(float degrees) {
  float pulseUs = 500.0f + degrees * (2000.0f / 180.0f);  // 0.5 ms to 2.5 ms
  ledcWrite(SERVO_PIN, static_cast<uint32_t>(pulseUs / 20000.0f * 65535.0f));
}
#else
#include <Servo.h>

const int SERVO_PIN = 3;
Servo arm;

void attachServo() { arm.attach(SERVO_PIN); }

void setAngle(float degrees) { arm.write(static_cast<int>(degrees + 0.5f)); }
#endif

OpenHAL hal("servo-arm", "1.0.0");

void setup() {
  attachServo();
  Serial.begin(115200);
  hal.output("angle", "deg", setAngle).limits(20, 160).safe(90).rate(90);
  hal.heartbeat(3000);
  hal.begin(Serial);
}

void loop() { hal.poll(); }
