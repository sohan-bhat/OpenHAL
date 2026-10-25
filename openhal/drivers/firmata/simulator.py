"""A StandardFirmata board simulator, laid out like an Arduino Uno.

It answers the queries a host sends (version, firmware, capabilities, analog mapping, pin
state), keeps pin modes and output values, and sends analog and digital reports the way
StandardFirmata 2.5 does. Plug it into `SerialSimulator` from the serial driver.
"""

from __future__ import annotations

import threading

from openhal.drivers.firmata import protocol as p

PWM_PINS = frozenset({3, 5, 6, 9, 10, 11})
ANALOG_PINS = range(14, 20)


class FirmataBoard:
    def __init__(self, *, pins: int = 20, firmware: str = "StandardFirmata.ino", version: tuple[int, int] = (2, 5)):
        self.pin_count = pins
        self.firmware = firmware
        self.version = version
        self.modes: dict[int, int] = dict.fromkeys(range(pins), p.OUTPUT)
        for pin in ANALOG_PINS:
            self.modes[pin] = p.ANALOG
        self.values: dict[int, int] = dict.fromkeys(range(pins), 0)
        self.inputs: dict[int, int] = dict.fromkeys(range(pins), 0)
        self.analog: dict[int, int] = dict.fromkeys(range(len(ANALOG_PINS)), 512)
        self.analog_reporting: set[int] = set()
        self.digital_reporting: set[int] = set()
        self.servo_config: dict[int, tuple[int, int]] = {}
        self.sampling_ms = 19
        self.received = bytearray()
        self.resets = 0
        self.ignore_queries = False
        self._buffer = bytearray()
        self._last_sample = 0.0
        self._pending_reports = bytearray()
        self._lock = threading.RLock()

    def on_open(self) -> bytes:
        return self._version() + self._firmware()

    def _version(self) -> bytes:
        return bytes([p.REPORT_VERSION, *self.version])

    def _firmware(self) -> bytes:
        return p.sysex(p.REPORT_FIRMWARE, bytes(self.version) + p.encode_string(self.firmware))

    def capabilities(self, pin: int) -> dict[int, int]:
        if pin < 2:
            return {}
        found = {p.INPUT: 1, p.OUTPUT: 1, p.PULLUP: 1, p.SERVO: 14}
        if pin in PWM_PINS:
            found[p.PWM] = 8
        if pin in ANALOG_PINS:
            found[p.ANALOG] = 10
        return found

    def _capability_response(self) -> bytes:
        payload = bytearray()
        for pin in range(self.pin_count):
            for mode, resolution in self.capabilities(pin).items():
                payload += bytes([mode, resolution])
            payload.append(0x7F)
        return p.sysex(p.CAPABILITY_RESPONSE, bytes(payload))

    def _analog_mapping(self) -> bytes:
        payload = bytes(pin - 14 if pin in ANALOG_PINS else p.NOT_ANALOG for pin in range(self.pin_count))
        return p.sysex(p.ANALOG_MAPPING_RESPONSE, payload)

    def _pin_state(self, pin: int) -> bytes:
        if pin >= self.pin_count:
            return b""
        mode = self.modes[pin]
        state = self.values[pin] if mode in (p.OUTPUT, p.PWM, p.SERVO) else int(mode == p.PULLUP)
        return p.sysex(p.PIN_STATE_RESPONSE, bytes([pin, mode]) + p.pack7(state))

    def _port_report(self, port: int) -> bytes:
        bits = 0
        for offset in range(8):
            pin = port * 8 + offset
            if pin < self.pin_count and self.modes[pin] in (p.INPUT, p.PULLUP):
                bits |= (self.inputs[pin] & 1) << offset
            elif pin < self.pin_count and self.modes[pin] == p.OUTPUT:
                bits |= (self.values[pin] & 1) << offset
        return bytes([p.DIGITAL_MESSAGE | port, bits & 0x7F, (bits >> 7) & 0x01])

    def set_input(self, pin: int, level: int) -> bytes:
        """Change a digital input like a button press. Returns the report the board would send."""
        with self._lock:
            self.inputs[pin] = level
            port = pin // 8
            return self._port_report(port) if port in self.digital_reporting else b""

    def poll(self, now: float) -> bytes:
        with self._lock:
            out = bytes(self._pending_reports)
            self._pending_reports.clear()
            if now - self._last_sample < self.sampling_ms / 1000:
                return out
            self._last_sample = now
            for channel in sorted(self.analog_reporting):
                pin = 14 + channel
                if self.modes.get(pin) == p.ANALOG:
                    value = self.analog[channel]
                    out += bytes([p.ANALOG_MESSAGE | channel, *p.split14(value)])
            return out

    def receive(self, data: bytes) -> bytes:
        with self._lock:
            self.received += data
            self._buffer += data
            out = bytearray()
            while self._buffer:
                consumed, reply = self._one()
                if consumed == 0:
                    break
                del self._buffer[:consumed]
                out += reply
            return bytes(out)

    def _one(self) -> tuple[int, bytes]:
        buffer = self._buffer
        command = buffer[0]
        if not command & 0x80:
            return 1, b""
        if command == p.START_SYSEX:
            end = buffer.find(bytes([p.END_SYSEX]))
            if end < 0:
                return 0, b""
            return end + 1, self._sysex(buffer[1], bytes(buffer[2:end]))
        if command in (p.REPORT_VERSION, p.SYSTEM_RESET):
            if command == p.SYSTEM_RESET:
                self._reset()
                return 1, b""
            return 1, b"" if self.ignore_queries else self._version()
        size = 2 if command & 0xF0 in (p.REPORT_ANALOG, p.REPORT_DIGITAL) else 3
        if len(buffer) < size:
            return 0, b""
        return size, self._short(command, bytes(buffer[1:size]))

    def _short(self, command: int, data: bytes) -> bytes:
        high = command & 0xF0
        if command == p.SET_PIN_MODE:
            pin, mode = data
            if mode not in self.capabilities(pin):
                return b""
            self.modes[pin] = mode
            if mode in (p.OUTPUT, p.PWM, p.SERVO):
                self.values[pin] = 0
            return b""
        if command == p.SET_DIGITAL_PIN_VALUE:
            pin, value = data
            if self.modes.get(pin) == p.OUTPUT:
                self.values[pin] = value & 1
            return b""
        if high == p.DIGITAL_MESSAGE:
            port, bits = command & 0x0F, data[0] | (data[1] << 7)
            for offset in range(8):
                pin = port * 8 + offset
                if pin < self.pin_count and self.modes[pin] == p.OUTPUT:
                    self.values[pin] = (bits >> offset) & 1
            return b""
        if high == p.ANALOG_MESSAGE:
            self._analog_write(command & 0x0F, data[0] | (data[1] << 7))
            return b""
        if high == p.REPORT_ANALOG:
            if data[0]:
                self.analog_reporting.add(command & 0x0F)
            else:
                self.analog_reporting.discard(command & 0x0F)
            return b""
        if high == p.REPORT_DIGITAL:
            port = command & 0x0F
            if data[0]:
                self.digital_reporting.add(port)
                return self._port_report(port)
            self.digital_reporting.discard(port)
        return b""

    def _analog_write(self, pin: int, value: int) -> None:
        if self.modes.get(pin) == p.PWM:
            self.values[pin] = min(value, 255)
        elif self.modes.get(pin) == p.SERVO:
            self.values[pin] = min(value, 180)

    def _sysex(self, command: int, data: bytes) -> bytes:
        if self.ignore_queries:
            return b""
        if command == p.REPORT_FIRMWARE:
            return self._firmware()
        if command == p.CAPABILITY_QUERY:
            return self._capability_response()
        if command == p.ANALOG_MAPPING_QUERY:
            return self._analog_mapping()
        if command == p.PIN_STATE_QUERY and data:
            return self._pin_state(data[0])
        if command == p.SERVO_CONFIG and len(data) >= 5:
            self.servo_config[data[0]] = (data[1] | data[2] << 7, data[3] | data[4] << 7)
            return b""
        if command == p.EXTENDED_ANALOG and len(data) >= 2:
            self._analog_write(data[0], p.unpack7(data[1:]))
            return b""
        if command == p.SAMPLING_INTERVAL and len(data) >= 2:
            self.sampling_ms = max(1, data[0] | data[1] << 7)
            return b""
        return b""

    def _reset(self) -> None:
        self.resets += 1
        for pin in range(self.pin_count):
            self.modes[pin] = p.ANALOG if pin in ANALOG_PINS else p.OUTPUT
            self.values[pin] = 0
        self.analog_reporting.clear()
        self.digital_reporting.clear()
