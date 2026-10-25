"""Fake I2C and SPI buses with simulated chips, for tests and the conformance case.

`FakeI2CBus` has the smbus2.SMBus methods the driver calls (`read_i2c_block_data`,
`write_i2c_block_data`, `i2c_rdwr` with real `smbus2.i2c_msg` objects and `close`), and
`FakeSpiDev` has the spidev.SpiDev ones (`open`, `xfer2`, `close` and the settings attributes).
Chips answer from their datasheets.

- `Tmp102`, a TI temperature sensor at 0x48. Registers are 16 bits, sent most significant byte
  first. 0x00 temperature, 12-bit two's complement left-justified, 0.0625 degC per step,
  read-only. 0x01 configuration, with SD (shutdown) in bit 8, the read-only resolution bits R1 R0
  in bits 14 and 13, the conversion rate CR1 CR0 in bits 7 and 6 and the read-only alert bit AL in
  bit 5. 0x02 T_LOW and 0x03 T_HIGH
  in the temperature format. A read starts at the pointer register and repeats its two bytes.
- `Mcp3008`, a Microchip 8-channel 10-bit ADC. Clocking out `[0x01, (0x08 | channel) << 4, 0x00]`
  returns the conversion in the low 2 bits of the second byte and all of the third.
- `Mcp4921`, a Microchip 12-bit DAC. A 16-bit word with A/B, BUF, GA and SHDN in bits 15 to 12 and
  the code in bits 11 to 0.

Faults. `fail_next` makes that many transactions fail with EREMOTEIO, `latency_s` slows every
transaction, `unplug(address)` removes a chip, and every transaction is kept in `log`.
"""

from __future__ import annotations

import ctypes
import errno
import time
from dataclasses import dataclass, field
from typing import Any

I2C_M_RD = 0x0001
EREMOTEIO = getattr(errno, "EREMOTEIO", 121)


def _nack() -> OSError:
    return OSError(EREMOTEIO, "Remote I/O error")


@dataclass
class Tmp102:
    """A TMP102 that converts continuously unless shut down."""

    temperature: float = 23.5
    config: int = 0x60A0
    t_low: float = 75.0
    t_high: float = 80.0
    pointer: int = 0

    @staticmethod
    def encode(celsius: float) -> int:
        return (round(celsius / 0.0625) & 0xFFF) << 4

    @staticmethod
    def decode(word: int) -> float:
        raw = word >> 4
        if raw & 0x800:
            raw -= 0x1000
        return raw * 0.0625

    @property
    def shut_down(self) -> bool:
        return bool(self.config & 0x0100)

    def register(self, number: int) -> int:
        if number == 0:
            return self.encode(self.temperature)
        if number == 1:
            return self.config
        if number == 2:
            return self.encode(self.t_low)
        if number == 3:
            return self.encode(self.t_high)
        raise _nack()

    def read(self, length: int) -> bytes:
        word = self.register(self.pointer).to_bytes(2, "big")
        return (word * (length // 2 + 1))[:length]

    def write(self, data: bytes) -> None:
        if not data:
            return
        if data[0] > 3:
            raise _nack()
        self.pointer = data[0]
        if len(data) < 3:
            return
        word = int.from_bytes(data[1:3], "big")
        if self.pointer == 1:
            self.config = (self.config & 0x6020) | (word & ~0x6020 & 0xFFFF)
        elif self.pointer == 2:
            self.t_low = self.decode(word)
        elif self.pointer == 3:
            self.t_high = self.decode(word)


@dataclass
class FakeI2CBus:
    """One I2C bus with chips at addresses. Pass `board.i2c` as the driver's i2c_factory."""

    chips: dict[int, Any] = field(default_factory=dict)
    fail_next: int = 0
    latency_s: float = 0.0
    log: list[tuple[str, int, bytes]] = field(default_factory=list)
    opened: list[int] = field(default_factory=list)
    closed: bool = False

    def i2c(self, number: int) -> FakeI2CBus:
        """The driver's i2c_factory. Only bus 1 exists, as on a Raspberry Pi header."""
        if number != 1:
            raise OSError(errno.ENOENT, f"No such file or directory: '/dev/i2c-{number}'")
        self.opened.append(number)
        self.closed = False
        return self

    def unplug(self, address: int) -> None:
        self.chips.pop(address, None)

    def _chip(self, address: int) -> Any:
        if self.closed:
            raise OSError(errno.EBADF, "Bad file descriptor")
        if self.latency_s:
            time.sleep(self.latency_s)
        if self.fail_next:
            self.fail_next -= 1
            raise _nack()
        chip = self.chips.get(address)
        if chip is None:
            raise _nack()
        return chip

    def read_i2c_block_data(self, i2c_addr: int, register: int, length: int, force: bool | None = None) -> list[int]:
        chip = self._chip(i2c_addr)
        chip.write(bytes([register]))
        data = chip.read(length)
        self.log.append(("read", i2c_addr, bytes([register]) + data))
        return list(data)

    def write_i2c_block_data(self, i2c_addr: int, register: int, data: list[int], force: bool | None = None) -> None:
        chip = self._chip(i2c_addr)
        payload = bytes([register, *data])
        chip.write(payload)
        self.log.append(("write", i2c_addr, payload))

    def i2c_rdwr(self, *messages: Any) -> None:
        for message in messages:
            chip = self._chip(message.addr)
            if message.flags & I2C_M_RD:
                data = chip.read(message.len)
                ctypes.memmove(message.buf, data, message.len)
                self.log.append(("rdwr-read", message.addr, data))
            else:
                data = bytes(message)
                chip.write(data)
                self.log.append(("rdwr-write", message.addr, data))

    def close(self) -> None:
        self.closed = True

    def writes(self, address: int) -> list[bytes]:
        """Every payload written to one address, register first."""
        return [data for kind, addr, data in self.log if addr == address and kind in ("write", "rdwr-write")]


@dataclass
class Mcp3008:
    """Eight single-ended inputs, in volts, against a 3.3 V reference."""

    volts: list[float] = field(default_factory=lambda: [0.0, 1.65, 3.3, 0.5, 0.0, 0.0, 0.0, 0.0])
    reference: float = 3.3

    def transfer(self, data: bytes) -> bytes:
        if len(data) < 3 or data[0] != 0x01 or not data[1] & 0x80:
            return bytes(len(data))
        channel = (data[1] >> 4) & 0x07
        code = max(0, min(1023, round(self.volts[channel] / self.reference * 1023)))
        return bytes([0, (code >> 8) & 0x03, code & 0xFF]) + bytes(len(data) - 3)


@dataclass
class Mcp4921:
    """A DAC whose output follows the last 16-bit word clocked in."""

    reference: float = 3.3
    word: int = 0

    @property
    def output(self) -> float:
        if not self.word & 0x1000:
            return 0.0
        gain = 1 if self.word & 0x2000 else 2
        return self.reference * (self.word & 0x0FFF) / 4096 * gain

    def transfer(self, data: bytes) -> bytes:
        if len(data) == 2:
            self.word = int.from_bytes(data, "big")
        return bytes(len(data))


@dataclass
class FakeSpiDev:
    """The spidev.SpiDev surface. `FakeSpiBus.spi` hands these out as the driver's spi_factory."""

    bus: FakeSpiBus
    max_speed_hz: int = 0
    mode: int = 0
    bits_per_word: int = 8
    target: tuple[int, int] | None = None

    def open(self, bus: int, device: int) -> None:
        if (bus, device) not in self.bus.chips:
            raise OSError(errno.ENOENT, f"No such file or directory: '/dev/spidev{bus}.{device}'")
        self.target = (bus, device)

    def xfer2(self, values: list[int]) -> list[int]:
        if self.target is None:
            raise OSError(errno.EBADF, "Bad file descriptor")
        if self.bus.latency_s:
            time.sleep(self.bus.latency_s)
        if self.bus.fail_next:
            self.bus.fail_next -= 1
            raise OSError(errno.EIO, "Input/output error")
        data = bytes(values)
        reply = self.bus.chips[self.target].transfer(data)
        self.bus.log.append((self.target, data, reply, self.max_speed_hz, self.mode))
        return list(reply)

    def close(self) -> None:
        self.target = None


@dataclass
class FakeSpiBus:
    """SPI chips by (bus, chip select). Pass `bus.spi` as the driver's spi_factory."""

    chips: dict[tuple[int, int], Any] = field(default_factory=dict)
    fail_next: int = 0
    latency_s: float = 0.0
    log: list[tuple[tuple[int, int], bytes, bytes, int, int]] = field(default_factory=list)

    def spi(self) -> FakeSpiDev:
        return FakeSpiDev(self)
