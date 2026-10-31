"""Modbus driver. RTU over serial lines and TCP, through pymodbus.

Protocol. Modbus Application Protocol v1.1b3 with the serial line (RTU) and TCP/IP (MBAP)
framings. The driver uses only the public function codes.

| Use | Function codes |
|---|---|
| read coils, discrete inputs, holding and input registers | 1, 2, 3, 4 |
| write one coil | 5 |
| write one holding register | 6 (or 16 with `always_write_multiple`) |
| write 32-bit values | 16 |
| identify | 43 / 14, Read Device Identification, basic objects only |

Each channel's `map` gives the register address (zero-based, as sent on the wire, not the
"40001" style reference numbers in many manuals), the table (`kind`), the number format and a
linear scale. 32-bit formats span two registers. The word order of those two registers varies
by vendor, so it is configurable per device and per channel, as is the byte order inside a
register for the rare devices that swap it.

Quirks.

- One request at a time. RTU is a shared half-duplex bus, and many TCP gateways forward to one,
  so the driver serializes every transaction.
- Numbers are converted with `channel = raw * scale + offset`. Writes do the inverse and round to
  the nearest whole raw value, and the returned reading shows the value actually sent.
- Modbus has no emergency behavior of its own. Safe state comes from the device file.
- Unit id 0 is broadcast and gets no reply, so it is not allowed.
"""

from __future__ import annotations

import asyncio
import math
import struct
import time
from collections.abc import Callable
from typing import Annotated, Any, ClassVar, Final, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, ValidationError, field_validator, model_validator

from openhal.drivers.base import Discovered, Driver, DriverError, DriverInfo, Health, Reading
from openhal.spec.models import DeviceFile
from openhal.spec.units import parse_duration

Kind = Literal["coil", "discrete", "holding", "input"]
Format = Literal["uint16", "int16", "uint32", "int32", "float32"]
Order = Literal["big", "little"]

_STRUCT: Final = {"uint16": ">H", "int16": ">h", "uint32": ">I", "int32": ">i", "float32": ">f"}
_WORDS: Final = {"uint16": 1, "int16": 1, "uint32": 2, "int32": 2, "float32": 2}
_EXCEPTIONS: Final = {
    1: "illegal function (the device doesn't support this request for that table)",
    2: "illegal data address (no such register on this device)",
    3: "illegal data value (the device does not accept the value)",
    4: "server device failure",
    5: "acknowledge (the device is still working on it)",
    6: "server device busy",
    8: "memory parity error",
    10: "gateway path unavailable",
    11: "gateway target device failed to respond",
}
_FAILURES_BEFORE_UNHEALTHY: Final = 3


def _seconds(value: Any) -> Any:
    if isinstance(value, int | float) and not isinstance(value, bool):
        return float(value)
    return parse_duration(value)


Duration = Annotated[float, BeforeValidator(_seconds), Field(gt=0, le=30)]


class ModbusParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    transport: Literal["tcp", "rtu"]
    host: str | None = None
    port: int | str | None = None
    unit: int = Field(default=1, ge=1, le=247)
    baud: int = Field(default=9600, ge=300, le=1_000_000)
    parity: Literal["N", "E", "O"] = "N"
    stopbits: Literal[1, 2] = 1
    bytesize: Literal[7, 8] = 8
    timeout: Duration = 1.0
    retries: int = Field(default=1, ge=0, le=5)
    word_order: Order = "big"
    byte_order: Order = "big"
    always_write_multiple: bool = False

    @model_validator(mode="after")
    def _addressing(self) -> ModbusParams:
        if self.transport == "tcp":
            if not self.host:
                raise ValueError("Modbus TCP needs host, for example host: 192.168.1.20.")
            if self.port is None:
                self.port = 502
            if isinstance(self.port, str) or not 1 <= self.port <= 65535:
                raise ValueError("For Modbus TCP, port is a TCP port number such as 502.")
        else:
            if self.host is not None:
                raise ValueError("Modbus RTU uses port (a serial device such as /dev/ttyUSB0), not host.")
            if not isinstance(self.port, str) or not self.port:
                raise ValueError("Modbus RTU needs port, a serial device such as /dev/ttyUSB0 or COM3.")
        return self


class RegisterMap(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    address: int = Field(alias="register", ge=0, le=65535)
    kind: Kind = "holding"
    format: Format = "uint16"
    word_order: Order | None = None
    byte_order: Order | None = None
    scale: float = 1.0
    offset: float = 0.0
    bit: int | None = Field(default=None, ge=0, le=15)
    values: dict[str, int] = {}
    on: int = Field(default=1, ge=0, le=0xFFFF)
    off: int = Field(default=0, ge=0, le=0xFFFF)

    @field_validator("scale")
    @classmethod
    def _scale(cls, value: float) -> float:
        if value == 0 or not math.isfinite(value):
            raise ValueError("scale must be a finite number other than zero.")
        return value

    @property
    def words(self) -> int:
        return 1 if self.kind in ("coil", "discrete") else _WORDS[self.format]


def decode(registers: list[int], fmt: Format, word_order: Order, byte_order: Order) -> float:
    """Turn raw 16-bit registers into a number."""
    words = list(registers)
    if word_order == "little":
        words.reverse()
    data = b"".join(word.to_bytes(2, byte_order) for word in words)
    value = struct.unpack(_STRUCT[fmt], data)[0]
    return float(value)


def encode(raw: float, fmt: Format, word_order: Order, byte_order: Order) -> list[int]:
    """Turn a raw number into 16-bit registers. Raises DriverError if it doesn't fit."""
    if fmt == "float32":
        try:
            packed = struct.pack(">f", raw)
        except (OverflowError, struct.error):
            raise DriverError(f"{raw:g} is too large for a float32 register pair.") from None
        if not math.isfinite(struct.unpack(">f", packed)[0]):
            raise DriverError(f"{raw:g} is too large for a float32 register pair.")
    else:
        try:
            packed = struct.pack(_STRUCT[fmt], int(raw))
        except struct.error:
            raise DriverError(f"{raw:g} doesn't fit in a {fmt} register.") from None
    words = [int.from_bytes(packed[index : index + 2], byte_order) for index in range(0, len(packed), 2)]
    if word_order == "little":
        words.reverse()
    return words


ClientFactory = Callable[[ModbusParams], Any]


def _default_client(params: ModbusParams) -> Any:
    from pymodbus import FramerType
    from pymodbus.client import AsyncModbusSerialClient, AsyncModbusTcpClient

    if params.transport == "tcp":
        assert params.host is not None
        assert isinstance(params.port, int)
        return AsyncModbusTcpClient(
            params.host, port=params.port, timeout=params.timeout, retries=params.retries, reconnect_delay=0
        )
    assert isinstance(params.port, str)
    return AsyncModbusSerialClient(
        params.port,
        framer=FramerType.RTU,
        baudrate=params.baud,
        parity=params.parity,
        stopbits=params.stopbits,
        bytesize=params.bytesize,
        timeout=params.timeout,
        retries=params.retries,
        reconnect_delay=0,
    )


class ModbusDriver(Driver):
    """Modbus RTU and TCP. Registers, formats and scales come from each channel's map."""

    info: ClassVar[DriverInfo] = DriverInfo(
        name="modbus",
        protocols=("Modbus RTU", "Modbus TCP"),
        hazard_default="medium",
        summary="Modbus RTU and TCP devices such as energy meters, PLCs, drives and sensors.",
    )
    params_model: ClassVar[type[Any] | None] = ModbusParams

    def __init__(self, device: DeviceFile, *, client_factory: ClientFactory = _default_client) -> None:
        super().__init__(device)
        self.settings = ModbusParams.model_validate(device.connect.params)
        self._factory = client_factory
        self._client: Any = None
        self._lock = asyncio.Lock()
        self._failures = 0
        self.maps: dict[str, RegisterMap] = {}
        for name, spec in device.read.items():
            self.maps[name] = self._check(name, spec.type, spec.map, writable=False, values=spec.values)
        for name, wspec in device.write.items():
            self.maps[name] = self._check(name, wspec.type, wspec.map, writable=True, values=wspec.values)

    def _check(
        self, name: str, kind: str, raw: dict[str, Any] | None, *, writable: bool, values: list[str]
    ) -> RegisterMap:
        if raw is None:
            raise DriverError(f"{name} needs a map with a register, for example map: {{ register: 0, kind: input }}.")
        try:
            rmap = RegisterMap.model_validate(raw)
        except ValidationError as exc:
            problems = "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors())
            raise DriverError(f"{name} has an invalid modbus map. {problems}") from None
        bits = rmap.kind in ("coil", "discrete")
        if writable and rmap.kind in ("discrete", "input"):
            raise DriverError(f"{name} is a write channel, but {rmap.kind} tables are read-only in Modbus.")
        if kind in ("string", "image"):
            raise DriverError(f"{name} is a {kind} channel. The modbus driver reads numbers, bools and enums.")
        if bits and kind != "bool":
            raise DriverError(f"{name} maps to a {rmap.kind}, which holds one bit, so the channel must be type bool.")
        if rmap.bit is not None and (bits or kind != "bool" or writable):
            raise DriverError(f"{name} uses bit, which only works for read-only bool channels on registers.")
        if kind == "enum":
            missing = set(values) - set(rmap.values)
            if missing:
                raise DriverError(f"{name} is an enum, so its map needs values for {', '.join(sorted(missing))}.")
        if rmap.address + rmap.words - 1 > 65535:
            raise DriverError(f"{name} runs past register 65535.")
        return rmap

    @classmethod
    async def discover(cls) -> list[Discovered]:
        return []

    @property
    def _where(self) -> str:
        s = self.settings
        place = f"{s.host}:{s.port}" if s.transport == "tcp" else str(s.port)
        return f"Modbus {s.transport.upper()} {place} unit {s.unit}"

    async def connect(self) -> None:
        await self.close()
        client = self._factory(self.settings)
        try:
            connected = await asyncio.wait_for(client.connect(), self.settings.timeout * 3 + 1)
        except TimeoutError:
            client.close()
            raise TimeoutError(f"{self._where} did not accept a connection in time.") from None
        except Exception as exc:  # noqa: BLE001 (pymodbus raises several types for one failure)
            client.close()
            raise DriverError(f"Could not open {self._where} ({exc}). Check the address and wiring.") from None
        if not connected:
            client.close()
            hint = (
                "the host and port"
                if self.settings.transport == "tcp"
                else "the serial port and that no other program has it open"
            )
            raise DriverError(f"Could not open {self._where}. Check {hint}.")
        self._client = client
        self._failures = 0

    async def close(self) -> None:
        client, self._client = self._client, None
        if client is not None:
            client.close()

    async def health(self) -> Health:
        client = self._client
        if client is None or not client.connected:
            return Health(connected=False, detail=f"{self._where} is not connected")
        if self._failures >= _FAILURES_BEFORE_UNHEALTHY:
            return Health(connected=False, detail=f"{self._where} stopped sending replies ({self._failures} failures)")
        probe = next(iter(self.maps), None)
        if probe is not None:
            started = time.monotonic()
            try:
                await self._read_raw(self.maps[probe])
            except (DriverError, TimeoutError) as exc:
                return Health(connected=False, detail=str(exc))
            return Health(connected=True, detail=self._where, latency_ms=(time.monotonic() - started) * 1000)
        return Health(connected=True, detail=self._where)

    async def identify(self) -> dict[str, str]:
        s = self.settings
        identity = {"transport": s.transport, "unit": str(s.unit)}
        identity["address"] = f"{s.host}:{s.port}" if s.transport == "tcp" else str(s.port)
        if self._client is None:
            return identity
        try:
            response = await self._call("read_device_information", read_code=1, object_id=0)
        except (DriverError, TimeoutError):
            return identity
        names = {0: "vendor", 1: "product_code", 2: "revision", 3: "vendor_url", 4: "product_name", 5: "model"}
        for key, value in (getattr(response, "information", None) or {}).items():
            if key in names:
                text = value.decode("utf-8", "replace") if isinstance(value, bytes) else str(value)
                identity[names[key]] = text[:120]
        return identity

    async def describe(self) -> dict[str, Any] | None:
        identity = await self.identify()
        result: dict[str, Any] = {"match": {"modbus_id": self.settings.unit}}
        if "vendor" in identity or "product_name" in identity:
            device: dict[str, str] = {
                "name": identity.get("product_name") or identity.get("product_code") or "Modbus device"
            }
            if "vendor" in identity:
                device["manufacturer"] = identity["vendor"]
            if "model" in identity or "product_code" in identity:
                device["model"] = identity.get("model") or identity["product_code"]
            result["device"] = device
        result["notes"] = (
            "Modbus devices don't describe their registers. Copy the register map from the device manual "
            "into each channel's map."
        )
        return result

    async def _call(self, method: str, *args: Any, **kwargs: Any) -> Any:
        from pymodbus.exceptions import ConnectionException, ModbusException, ModbusIOException

        client = self._client
        if client is None or not client.connected:
            raise DriverError(f"{self._where} is not connected.")
        deadline = self.settings.timeout * (self.settings.retries + 1) + 0.5
        async with self._lock:
            try:
                response = await asyncio.wait_for(
                    getattr(client, method)(*args, device_id=self.settings.unit, **kwargs), deadline
                )
            except (TimeoutError, ModbusIOException):
                self._failures += 1
                raise TimeoutError(
                    f"{self._where} sent no reply to {method} within {deadline:g} s. Check the unit id, "
                    "wiring, baud rate and parity, or raise timeout."
                ) from None
            except ConnectionException as exc:
                self._failures += 1
                raise DriverError(f"{self._where} lost the connection ({exc}). The hub will reconnect.") from None
            except ModbusException as exc:
                self._failures += 1
                raise DriverError(f"{self._where} returned a bad response to {method} ({exc}).") from None
        if response.isError():
            code = getattr(response, "exception_code", None)
            reason = _EXCEPTIONS.get(code, f"exception code {code}") if isinstance(code, int) else str(response)
            self._failures = 0
            raise DriverError(f"{self._where} returned an error for {method}, {reason}. Check the register map.")
        self._failures = 0
        return response

    async def _read_raw(self, rmap: RegisterMap) -> list[int] | list[bool]:
        method = {
            "coil": "read_coils",
            "discrete": "read_discrete_inputs",
            "holding": "read_holding_registers",
            "input": "read_input_registers",
        }[rmap.kind]
        response = await self._call(method, rmap.address, count=rmap.words)
        data = response.bits if rmap.kind in ("coil", "discrete") else response.registers
        if len(data) < rmap.words:
            raise DriverError(f"{self._where} returned {len(data)} values for {method}, not {rmap.words}.")
        return list(data[: rmap.words])

    def _orders(self, rmap: RegisterMap) -> tuple[Order, Order]:
        return rmap.word_order or self.settings.word_order, rmap.byte_order or self.settings.byte_order

    async def read(self, channel: str) -> Reading:
        rmap = self.maps.get(channel)
        if rmap is None:
            raise DriverError(f"This modbus device has no channel {channel!r}.")
        kind, unit, allowed = self._spec(channel)
        data = await self._read_raw(rmap)
        value: float | bool | str
        if rmap.kind in ("coil", "discrete"):
            value = bool(data[0])
        else:
            words = [int(word) for word in data]
            if rmap.bit is not None:
                value = bool((words[0] >> rmap.bit) & 1)
            else:
                raw = decode(words, rmap.format, *self._orders(rmap))
                if kind == "bool":
                    value = raw != rmap.off
                elif kind == "enum":
                    names = [name for name in allowed if rmap.values[name] == raw]
                    if not names:
                        raise DriverError(f"{channel} read raw value {raw:g}, which is not in its values map.")
                    value = names[0]
                else:
                    if not math.isfinite(raw):
                        raise DriverError(f"{channel} read a float32 that is not a finite number.")
                    value = raw * rmap.scale + rmap.offset
        return self._reading(channel, value, unit)

    def _spec(self, channel: str) -> tuple[str, str | None, list[str]]:
        if channel in self.device.read:
            spec = self.device.read[channel]
            return spec.type, spec.unit, spec.values
        wspec = self.device.write[channel]
        return wspec.type, wspec.unit, wspec.values

    def _reading(self, channel: str, value: float | bool | str, unit: str | None) -> Reading:
        suspect = False
        spec = self.device.read.get(channel)
        if spec is not None and spec.range is not None and isinstance(value, float):
            suspect = not spec.range[0] <= value <= spec.range[1]
        return Reading(channel, value, unit=unit, at=time.time(), suspect=suspect)

    async def _write(self, channel: str, value: float | bool | str) -> Reading | None:
        rmap = self.maps.get(channel)
        if rmap is None or channel not in self.device.write:
            raise DriverError(f"This modbus device has no write channel {channel!r}.")
        kind, unit, _ = self._spec(channel)
        if rmap.kind == "coil":
            await self._call("write_coil", rmap.address, bool(value))
            return Reading(channel, bool(value), unit=unit)
        sent: float | bool | str
        if kind == "bool":
            raw = float(rmap.on if value else rmap.off)
            sent = bool(value)
        elif kind == "enum":
            raw = float(rmap.values[str(value)])
            sent = str(value)
        else:
            exact = (float(value) - rmap.offset) / rmap.scale
            raw = exact if rmap.format == "float32" else float(round(exact))
            sent = raw * rmap.scale + rmap.offset
        words = encode(raw, rmap.format, *self._orders(rmap))
        if len(words) == 1 and not self.settings.always_write_multiple:
            await self._call("write_register", rmap.address, words[0])
        else:
            await self._call("write_registers", rmap.address, words)
        return Reading(channel, sent, unit=unit)
