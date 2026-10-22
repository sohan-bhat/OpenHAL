"""Arduino-compatible boards running StandardFirmata.

Protocol. Firmata (github.com/firmata/protocol) is a MIDI-like binary protocol at 57600 baud.
The driver uses its own small client in `protocol.py`. The maintained Python clients are either
AGPL-3.0 (pymata4, pymata-express, telemetrix) or synchronous with their own reader threads and
callbacks (pyfirmata2, MIT), and the protocol subset needed here is small, so an own client keeps
the dependency list to pyserial and fits the async driver model.

Connect sequence. Open the port (most boards reset), wait for the version and firmware report,
then send REPORT_FIRMWARE, CAPABILITY_QUERY and ANALOG_MAPPING_QUERY. Every channel's pin and
mode are checked against the board's capabilities. Read pins are put in their input mode and
reporting is turned on. Output pins are left alone until the first granted write, because
setting a pin to OUTPUT already drives it.

Mapping, per channel.

    read   bool    { pin: 7, mode: input | pullup, invert: false }       digital port reports
    read   number  { pin: A0 }                                           analog reports, 10 bit
    write  bool    { pin: 13, invert: false }                            SET_DIGITAL_PIN_VALUE
    write  number  { pin: 9 } in percent                                 PWM, 0 to 2^res - 1
    write  number  { pin: 6, mode: servo, min_pulse: 544, max_pulse: 2400 } in degree, 0 to 180

Analog values are `raw * scale + offset`. Without `scale` the driver uses `vref / (2^res - 1)`
for volt channels, `100 / (2^res - 1)` for percent and 1 for dimensionless counts.

Firmata writes have no acknowledgement. With `verify: true` (the default) every write is
followed by a PIN_STATE_QUERY, so a write to a board that stopped answering fails instead of
passing silently. Write channels read back through PIN_STATE_QUERY as well.

Safe state. From the device file. Firmata's SYSTEM_RESET returns pins to their power-on modes,
which is not a safe state for every circuit, so the driver never sends it.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from collections import defaultdict
from typing import Any, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from openhal.drivers.base import Discovered, Driver, DriverError, DriverInfo, Health, Reading
from openhal.drivers.firmata import protocol as p
from openhal.drivers.serial import mapping
from openhal.drivers.serial.link import (
    Opener,
    SerialLink,
    list_serial_ports,
    port_identifiers,
    pyserial_opener,
    resolve_port,
)
from openhal.spec.models import DeviceFile
from openhal.spec.units import Quantity, UnitError, convert, parse_quantity, parse_unit

MODES = {"input": p.INPUT, "pullup": p.PULLUP, "analog": p.ANALOG, "output": p.OUTPUT, "pwm": p.PWM, "servo": p.SERVO}


class FirmataParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    port: str = Field(min_length=1, max_length=300)
    baud: int = Field(default=57600, ge=9600, le=2_000_000)
    timeout: float = 1.0
    settle: float = 2.0
    sampling: float = 0.1
    vref: float = 5.0
    verify: bool = True
    board: str | None = Field(default=None, max_length=80)

    @field_validator("timeout", "settle", "sampling", mode="before")
    @classmethod
    def _duration(cls, value: Any) -> float:
        return mapping.duration(value)

    @field_validator("vref", mode="before")
    @classmethod
    def _volts(cls, value: Any) -> float:
        if isinstance(value, int | float) and not isinstance(value, bool):
            raise ValueError("vref needs a unit, for example 5 V or 3.3 V.")
        return convert(parse_quantity(value), "V")

    @model_validator(mode="after")
    def _ranges(self) -> FirmataParams:
        if not 0.05 <= self.timeout <= 10:
            raise ValueError("timeout must be between 50 ms and 10 s.")
        if not 0 <= self.settle <= 10:
            raise ValueError("settle must be between 0 s and 10 s.")
        if not 0.01 <= self.sampling <= 10:
            raise ValueError("sampling must be between 10 ms and 10 s.")
        if not 0 < self.vref <= 24:
            raise ValueError("vref must be above 0 V and at most 24 V.")
        return self


class PinMap(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    pin: int | str
    mode: Literal["input", "pullup", "analog", "output", "pwm", "servo"] | None = None
    invert: bool = False
    scale: float | None = None
    offset: float = 0.0
    min_pulse: int = Field(default=544, ge=0, le=16383)
    max_pulse: int = Field(default=2400, ge=0, le=16383)

    @field_validator("pin")
    @classmethod
    def _pin(cls, value: int | str) -> int | str:
        if isinstance(value, bool):
            raise ValueError("pin must be a number or A0 to A15.")
        if isinstance(value, int):
            if not 0 <= value <= 127:
                raise ValueError("pin must be between 0 and 127.")
            return value
        text = value.strip().upper()
        if not (text.startswith("A") and text[1:].isdigit() and int(text[1:]) <= 15):
            raise ValueError("pin must be a number or A0 to A15.")
        return text


def _pin_map(raw: dict[str, Any] | None, where: str) -> PinMap:
    if raw is None:
        raise DriverError(f"{where} needs a map with the pin, for example map: {{ pin: 13 }}.")
    try:
        return PinMap.model_validate(raw)
    except ValidationError as exc:
        problems = "; ".join(f"{'.'.join(str(x) for x in e['loc']) or 'map'}: {e['msg']}" for e in exc.errors())
        raise DriverError(f"{where}.map is not valid for the Firmata driver ({problems}).") from exc


class _Channel:
    def __init__(self, name: str, pin_map: PinMap, mode: int, unit: str | None, writable: bool) -> None:
        self.name = name
        self.map = pin_map
        self.mode = mode
        self.unit = unit
        self.writable = writable
        self.pin = -1
        self.analog_channel: int | None = None
        self.resolution = 0


class FirmataDriver(Driver):
    """Digital and analog I/O, PWM and servos on boards running StandardFirmata."""

    info: ClassVar[DriverInfo] = DriverInfo(
        name="firmata",
        protocols=("Firmata 2.x over USB serial",),
        hazard_default="low",
        summary="Arduino-compatible boards running StandardFirmata. Digital, analog, PWM and servo pins.",
    )
    params_model: ClassVar[type[Any] | None] = FirmataParams

    def __init__(self, device: DeviceFile, *, opener: Opener | None = None) -> None:
        super().__init__(device)
        self.settings = FirmataParams.model_validate(device.connect.params)
        self._opener = opener
        self.link: SerialLink | None = None
        self.channels: dict[str, _Channel] = {}
        self.firmware: tuple[str, int, int] | None = None
        self.protocol_version: tuple[int, int] | None = None
        self.capabilities: list[dict[int, int]] = []
        self.analog_map: dict[int, int] = {}
        self.analog_values: dict[int, tuple[int, float]] = {}
        self.ports: dict[int, int] = {}
        self.malformed = 0
        self._modes: dict[int, int] = {}
        self._out_ports: dict[int, int] = defaultdict(int)
        self._servo_ready: set[int] = set()
        self._waiters: dict[tuple[int, int], list[asyncio.Future[bytes]]] = defaultdict(list)
        self._lock = asyncio.Lock()
        self._pump_task: asyncio.Task[None] | None = None
        self._parser = p.Parser()
        self._check_maps()

    def _check_maps(self) -> None:
        for name, spec in self.device.read.items():
            pin_map = _pin_map(spec.map, f"read.{name}")
            if spec.type == "bool":
                mode = MODES[pin_map.mode or "input"]
                if mode not in (p.INPUT, p.PULLUP):
                    raise DriverError(f"read.{name}: bool reads use mode input or pullup.")
            elif spec.type == "number":
                if pin_map.mode not in (None, "analog"):
                    raise DriverError(f"read.{name}: number reads use mode analog.")
                mode = p.ANALOG
                self._analog_scale_ok(name, spec.unit, pin_map)
            else:
                raise DriverError(f"read.{name}: the Firmata driver reads bool and number channels only.")
            self.channels[name] = _Channel(name, pin_map, mode, spec.unit, writable=False)
        for name, write_spec in self.device.write.items():
            pin_map = _pin_map(write_spec.map, f"write.{name}")
            if write_spec.type == "bool":
                if pin_map.mode not in (None, "output"):
                    raise DriverError(f"write.{name}: bool writes use mode output.")
                mode = p.OUTPUT
            elif write_spec.type == "number":
                mode = MODES[pin_map.mode or "pwm"]
                if mode == p.PWM and write_spec.unit not in ("percent", "%"):
                    raise DriverError(f"write.{name}: PWM channels are numbers in percent.")
                if mode == p.SERVO:
                    self._convertible(name, write_spec.unit, "degree")
                if mode not in (p.PWM, p.SERVO):
                    raise DriverError(f"write.{name}: number writes use mode pwm or servo.")
            else:
                raise DriverError(f"write.{name}: the Firmata driver writes bool and number channels only.")
            self.channels[name] = _Channel(name, pin_map, mode, write_spec.unit, writable=True)
        pins: dict[str, str] = {}
        for channel in self.channels.values():
            key = str(channel.map.pin)
            if key in pins:
                raise DriverError(f"{channel.name} and {pins[key]} both use pin {key}. Give each pin one channel.")
            pins[key] = channel.name

    def _analog_scale_ok(self, name: str, unit: str | None, pin_map: PinMap) -> None:
        if pin_map.scale is not None:
            return
        if unit in ("percent", "%", "dimensionless"):
            return
        self._convertible(name, unit, "V")

    def _convertible(self, name: str, unit: str | None, wanted: str) -> None:
        try:
            convert(Quantity(1, parse_unit(unit or "")), wanted)
        except UnitError:
            raise DriverError(f"{name} needs a unit that converts to {wanted}, or an explicit scale.") from None

    # ------------------------------------------------------------------ discovery and identity

    @classmethod
    async def discover(cls) -> list[Discovered]:
        ports = await asyncio.to_thread(list_serial_ports)
        return [
            Discovered(driver="firmata", address=str(info.device), identifiers=port_identifiers(info))
            for info in ports
            if getattr(info, "vid", None) is not None
        ]

    async def identify(self) -> dict[str, str]:
        identity = {"port": self.settings.port}
        if self.firmware is not None:
            name, major, minor = self.firmware
            identity.update({"firmware": name, "firmware_version": f"{major}.{minor}"})
        if self.protocol_version is not None:
            identity["protocol"] = "{}.{}".format(*self.protocol_version)
        return identity

    async def describe(self) -> dict[str, Any] | None:
        if not self.capabilities:
            return None
        read: dict[str, Any] = {}
        write: dict[str, Any] = {}
        top = round(self.settings.vref, 3)
        for pin, caps in enumerate(self.capabilities):
            if p.ANALOG in caps and pin in self.analog_map:
                channel = self.analog_map[pin]
                read[f"a{channel}"] = {"unit": "V", "range": [0, top], "map": {"pin": f"A{channel}"}}
            elif p.PWM in caps:
                write[f"pwm_{pin}"] = {"unit": "percent", "min": 0, "max": 100, "suggested": True, "map": {"pin": pin}}
            elif p.OUTPUT in caps:
                write[f"d{pin}"] = {"type": "bool", "suggested": True, "map": {"pin": pin}}
        name = self.firmware[0] if self.firmware else "Firmata board"
        return {
            "device": {"name": name.removesuffix(".ino")},
            "read": read,
            "write": write,
            "notes": "Proposed from the board's capability report. Keep only the pins that are wired.",
        }

    # ------------------------------------------------------------------ connection

    async def connect(self) -> None:
        await self.close()
        opener = self._opener
        if opener is None:
            port = await asyncio.to_thread(
                resolve_port,
                self.settings.port,
                self.device.match.usb,
                self.device.match.serial_number,
                driver="firmata",
            )
            opener = pyserial_opener(port, self.settings.baud)
        self.link = SerialLink(opener, name=self.settings.port)
        await self.link.open()
        if self.settings.settle:
            await asyncio.sleep(self.settings.settle)
        self.link.take_buffered()
        self._reset_state()
        self._pump_task = asyncio.create_task(self._pump(self.link))
        try:
            await self._handshake()
        except TimeoutError:
            raise DriverError(
                f"No Firmata reply on {self.settings.port}. Upload StandardFirmata to the board "
                f"and check the baud rate ({self.settings.baud})."
            ) from None
        self._bind_pins()
        await self._configure_inputs()

    async def _handshake(self) -> None:
        firmware = await self._query(p.REPORT_FIRMWARE, b"", (p.REPORT_FIRMWARE, -1))
        if len(firmware) < 2:
            raise DriverError("The board sent a malformed firmware report. Re-upload StandardFirmata.")
        self.firmware = (p.decode_string(firmware[2:]), firmware[0], firmware[1])
        await self._send(bytes([p.REPORT_VERSION]))
        self.capabilities = p.parse_capabilities(
            await self._query(p.CAPABILITY_QUERY, b"", (p.CAPABILITY_RESPONSE, -1))
        )
        mapping_data = await self._query(p.ANALOG_MAPPING_QUERY, b"", (p.ANALOG_MAPPING_RESPONSE, -1))
        self.analog_map = {pin: ch for pin, ch in enumerate(mapping_data) if ch != p.NOT_ANALOG}

    def _reset_state(self) -> None:
        self._parser = p.Parser()
        self.analog_values.clear()
        self.ports.clear()
        self._modes.clear()
        self._out_ports.clear()
        self._servo_ready.clear()
        self.malformed = 0
        for waiters in self._waiters.values():
            for waiter in waiters:
                waiter.cancel()
        self._waiters.clear()

    def _bind_pins(self) -> None:
        by_channel = {channel: pin for pin, channel in self.analog_map.items()}
        for channel in self.channels.values():
            pin = channel.map.pin
            if isinstance(pin, str):
                analog = int(pin[1:])
                if analog not in by_channel:
                    raise DriverError(f"{channel.name}: the board has no analog pin {pin}.")
                channel.pin, channel.analog_channel = by_channel[analog], analog
            else:
                channel.pin = pin
                channel.analog_channel = self.analog_map.get(pin)
            if channel.pin >= len(self.capabilities):
                raise DriverError(f"{channel.name}: the board has no pin {pin}.")
            caps = self.capabilities[channel.pin]
            if channel.mode not in caps:
                supported = ", ".join(p.MODE_NAMES.get(mode, str(mode)) for mode in caps) or "nothing"
                wanted = p.MODE_NAMES[channel.mode]
                raise DriverError(f"{channel.name}: pin {pin} can't do {wanted}. It supports {supported}.")
            if channel.mode == p.ANALOG and channel.analog_channel is None:
                raise DriverError(f"{channel.name}: pin {pin} is not an analog input.")
            channel.resolution = caps[channel.mode]

    async def _configure_inputs(self) -> None:
        interval = max(10, min(16383, round(self.settings.sampling * 1000)))
        await self._send(p.sysex(p.SAMPLING_INTERVAL, bytes(p.split14(interval))))
        for channel in self.channels.values():
            if channel.writable:
                continue
            await self._send(bytes([p.SET_PIN_MODE, channel.pin, channel.mode]))
            self._modes[channel.pin] = channel.mode
            if channel.mode == p.ANALOG:
                assert channel.analog_channel is not None
                await self._send(bytes([p.REPORT_ANALOG | (channel.analog_channel & 0x0F), 1]))
            else:
                await self._send(bytes([p.REPORT_DIGITAL | (channel.pin // 8), 1]))

    async def _pump(self, link: SerialLink) -> None:
        with contextlib.suppress(DriverError):
            while True:
                try:
                    chunk = await link.read_chunk(3600)
                except TimeoutError:
                    continue
                for message in self._parser.feed(chunk):
                    self._dispatch(message)
        for waiters in self._waiters.values():
            for waiter in waiters:
                if not waiter.done():
                    waiter.set_exception(DriverError("The board disconnected. Check the USB cable, then reconnect."))
                    waiter.exception()
        self._waiters.clear()

    def _dispatch(self, message: p.Message) -> None:
        if message.kind == "analog":
            self.analog_values[message.index] = (message.value, time.monotonic())
        elif message.kind == "digital":
            self.ports[message.index] = message.value
        elif message.kind == "version":
            self.protocol_version = (message.index, message.value)
        elif message.kind == "sysex":
            key_pin = message.data[0] if message.index == p.PIN_STATE_RESPONSE and message.data else -1
            for key in ((message.index, key_pin), (message.index, -1)):
                waiters = self._waiters.get(key)
                while waiters:
                    waiter = waiters.pop(0)
                    if not waiter.done():
                        waiter.set_result(message.data)
                        return
        else:
            self.malformed += 1

    def _require_link(self) -> SerialLink:
        if self.link is None or not self.link.connected or self._pump_task is None or self._pump_task.done():
            raise DriverError(f"The Firmata board on {self.settings.port} is not connected. Reconnect it.")
        return self.link

    async def _send(self, data: bytes) -> None:
        await self._require_link().write(data)

    async def _query(self, command: int, payload: bytes, key: tuple[int, int]) -> bytes:
        waiter: asyncio.Future[bytes] = asyncio.get_running_loop().create_future()
        self._waiters[key].append(waiter)
        try:
            await self._send(p.sysex(command, payload))
            return await asyncio.wait_for(waiter, self.settings.timeout)
        except TimeoutError:
            raise TimeoutError(
                f"The board didn't answer a Firmata query within {self.settings.timeout:g} s. "
                "Check that StandardFirmata is running."
            ) from None
        finally:
            with contextlib.suppress(ValueError):
                self._waiters[key].remove(waiter)

    async def _pin_state(self, pin: int) -> tuple[int, int]:
        async with self._lock:
            data = await self._query(p.PIN_STATE_QUERY, bytes([pin]), (p.PIN_STATE_RESPONSE, pin))
        if len(data) < 3:
            raise DriverError(f"The board sent a malformed pin state for pin {pin}.")
        return data[1], p.unpack7(data[2:])

    # ------------------------------------------------------------------ channels

    def _channel(self, name: str) -> _Channel:
        channel = self.channels.get(name)
        if channel is None:
            raise DriverError(f"{self.device.device_id} has no channel {name!r}.")
        return channel

    def _analog_scale(self, channel: _Channel) -> float:
        full = (1 << channel.resolution) - 1 if channel.resolution else 1023
        if channel.map.scale is not None:
            return channel.map.scale
        if channel.unit in ("percent", "%"):
            return 100.0 / full
        if channel.unit == "dimensionless":
            return 1.0
        return convert(Quantity(self.settings.vref / full, parse_unit("V")), channel.unit or "V")

    async def read(self, channel_name: str) -> Reading:
        channel = self._channel(channel_name)
        self._require_link()
        if channel.writable:
            return await self._read_output(channel)
        if channel.mode == p.ANALOG:
            assert channel.analog_channel is not None
            stale_after = max(1.0, 5 * self.settings.sampling)
            sample = await self._fresh_sample(channel.analog_channel, stale_after)
            if sample is None:
                raise TimeoutError(
                    f"No analog report for {channel_name} in the last {stale_after:g} s. "
                    "The board may have stopped or reset."
                )
            value = sample[0] * self._analog_scale(channel) + channel.map.offset
            return Reading(channel_name, value, channel.unit)
        bits = self.ports.get(channel.pin // 8)
        deadline = time.monotonic() + self.settings.timeout
        while bits is None and time.monotonic() < deadline:
            await asyncio.sleep(0.01)
            self._require_link()
            bits = self.ports.get(channel.pin // 8)
        if bits is None:
            raise DriverError(f"The board hasn't reported pin {channel.pin} yet. Try again shortly.")
        level = bool((bits >> (channel.pin % 8)) & 1)
        return Reading(channel_name, level != channel.map.invert, None)

    async def _fresh_sample(self, analog: int, stale_after: float) -> tuple[int, float] | None:
        """The latest analog report, waiting up to `stale_after` for one if none is fresh."""
        deadline = time.monotonic() + stale_after
        while True:
            sample = self.analog_values.get(analog)
            if sample is not None and time.monotonic() - sample[1] <= stale_after:
                return sample
            if time.monotonic() >= deadline:
                return None
            await asyncio.sleep(0.01)
            self._require_link()

    async def _read_output(self, channel: _Channel) -> Reading:
        mode, state = await self._pin_state(channel.pin)
        if channel.mode == p.OUTPUT:
            if mode != p.OUTPUT:
                return Reading(channel.name, None, None)
            return Reading(channel.name, bool(state & 1) != channel.map.invert, None)
        if channel.mode == p.PWM:
            full = (1 << channel.resolution) - 1
            if mode == p.PWM:
                return Reading(channel.name, round(100.0 * state / full, 3), channel.unit)
            if mode == p.OUTPUT:
                return Reading(channel.name, 100.0 if state & 1 else 0.0, channel.unit)
            return Reading(channel.name, None, channel.unit)
        if mode != p.SERVO:
            return Reading(channel.name, None, channel.unit)
        degrees = float(state)
        value = degrees if channel.unit in (None, "degree", "deg") else self._from_degrees(degrees, channel.unit)
        return Reading(channel.name, value, channel.unit)

    def _from_degrees(self, value: float, unit: str) -> float:
        return convert(Quantity(value, parse_unit("degree")), unit)

    async def _write(self, channel_name: str, value: float | bool | str) -> Reading | None:
        channel = self._channel(channel_name)
        if not channel.writable:
            raise DriverError(f"{channel_name} is a read channel.")
        async with self._lock:
            if channel.mode == p.OUTPUT:
                await self._digital_write(channel, bool(value))
                expected = int(bool(value) != channel.map.invert)
            elif channel.mode == p.PWM:
                assert isinstance(value, int | float)
                full = (1 << channel.resolution) - 1
                expected = max(0, min(full, round(float(value) / 100 * full)))
                await self._ensure_mode(channel.pin, p.PWM)
                await self._analog_write(channel.pin, expected)
            else:
                assert isinstance(value, int | float)
                degrees = convert(Quantity(float(value), parse_unit(channel.unit or "degree")), "degree")
                expected = max(0, min(180, round(degrees)))
                await self._ensure_servo(channel)
                await self._analog_write(channel.pin, expected)
        if self.settings.verify:
            mode, state = await self._pin_state(channel.pin)
            if mode != channel.mode or state != expected:
                raise DriverError(
                    f"The board reports pin {channel.pin} as mode {p.MODE_NAMES.get(mode, mode)} value {state} "
                    f"after the write, expected {p.MODE_NAMES[channel.mode]} value {expected}."
                )
        return Reading(channel_name, value, channel.unit)

    async def _ensure_mode(self, pin: int, mode: int) -> None:
        if self._modes.get(pin) != mode:
            await self._send(bytes([p.SET_PIN_MODE, pin, mode]))
            self._modes[pin] = mode

    async def _ensure_servo(self, channel: _Channel) -> None:
        if channel.pin not in self._servo_ready:
            low, high = channel.map.min_pulse, channel.map.max_pulse
            await self._send(p.sysex(p.SERVO_CONFIG, bytes([channel.pin, *p.split14(low), *p.split14(high)])))
            self._servo_ready.add(channel.pin)
        await self._ensure_mode(channel.pin, p.SERVO)

    async def _digital_write(self, channel: _Channel, on: bool) -> None:
        await self._ensure_mode(channel.pin, p.OUTPUT)
        level = int(on != channel.map.invert)
        if self.protocol_version is not None and self.protocol_version >= (2, 5):
            await self._send(bytes([p.SET_DIGITAL_PIN_VALUE, channel.pin, level]))
            return
        port, bit = channel.pin // 8, 1 << (channel.pin % 8)
        bits = (self._out_ports[port] | bit) if level else (self._out_ports[port] & ~bit)
        self._out_ports[port] = bits
        await self._send(bytes([p.DIGITAL_MESSAGE | port, *p.split14(bits)]))

    async def _analog_write(self, pin: int, value: int) -> None:
        if pin <= 15 and value < (1 << 14):
            await self._send(bytes([p.ANALOG_MESSAGE | pin, *p.split14(value)]))
        else:
            await self._send(p.sysex(p.EXTENDED_ANALOG, bytes([pin]) + p.pack7(value)))

    async def health(self) -> Health:
        try:
            self._require_link()
        except DriverError as exc:
            return Health(connected=False, detail=str(exc))
        name = self.firmware[0] if self.firmware else "Firmata"
        return Health(connected=True, detail=name)

    async def close(self) -> None:
        task, link = self._pump_task, self.link
        self._pump_task = None
        self.link = None
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        if link is not None:
            await link.close()
