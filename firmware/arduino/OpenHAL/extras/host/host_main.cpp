// Runs a sketch on a desktop. Exits when stdin closes. Pin writes are logged to stderr.

#include <poll.h>
#include <stdio.h>
#include <stdlib.h>
#include <time.h>
#include <unistd.h>

#include <Arduino.h>

HostSerial Serial;

namespace {
int pins[128];
struct timespec started;
bool closed = false;
}  // namespace

unsigned long millis() {
  struct timespec now;
  clock_gettime(CLOCK_MONOTONIC, &now);
  return static_cast<unsigned long>((now.tv_sec - started.tv_sec) * 1000L + (now.tv_nsec - started.tv_nsec) / 1000000L);
}

void pinMode(int pin, int mode) {
  (void)pin;
  (void)mode;
}

void digitalWrite(int pin, int value) { analogWrite(pin, value); }

int digitalRead(int pin) { return pin == 2 ? HIGH : pins[pin & 127]; }

void analogWrite(int pin, int value) {
  pins[pin & 127] = value;
  fprintf(stderr, "pin %d = %d\n", pin, value);
}

int analogRead(int pin) {
  char name[32];
  snprintf(name, sizeof name, "OPENHAL_HOST_A%d", pin - A0);
  const char* value = getenv(name);
  return value ? atoi(value) : 512;
}

int hostPinValue(int pin) { return pins[pin & 127]; }

int HostSerial::available() {
  struct pollfd fd = {0, POLLIN, 0};
  return poll(&fd, 1, 0) > 0 ? 1 : 0;
}

int HostSerial::read() {
  unsigned char byte;
  ssize_t got = ::read(0, &byte, 1);
  if (got <= 0) {
    closed = true;
    return -1;
  }
  return byte;
}

size_t HostSerial::write(uint8_t byte) { return ::write(1, &byte, 1) == 1 ? 1 : 0; }

int main() {
  clock_gettime(CLOCK_MONOTONIC, &started);
  setup();
  while (!closed) {
    loop();
    usleep(500);
  }
  return 0;
}
