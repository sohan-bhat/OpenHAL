#include <OpenHAL.h>

#if defined(ESP32)
const int SERVO_PIN = 13;

void attachServo() { ledcAttach(SERVO_PIN, 50, 16); }

void setAngle(float degrees) {
  float pulseUs = 500.0f + degrees * (2000.0f / 180.0f);
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
