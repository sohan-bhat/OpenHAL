// A text protocol fan board. Commands end with a newline.
#define FAN_PIN 9
const int SENSOR_PIN = A0;
String line;

void setup() {
  pinMode(FAN_PIN, OUTPUT);
  Serial.begin(115200);
}

void loop() {
  if (!Serial.available()) return;
  line = Serial.readStringUntil('\n');
  line.trim();
  if (line == "TEMP?") {
    Serial.print("T=");
    Serial.println(analogRead(SENSOR_PIN) * 0.1);
  } else if (line.startsWith("FAN ")) {
    int value = constrain(line.substring(4).toInt(), 0, 255);
    analogWrite(FAN_PIN, value);
    Serial.println("OK");
  } else if (line == "BEEP") {
    Serial.println("OK");
  } else {
    Serial.println("ERR");
  }
}
