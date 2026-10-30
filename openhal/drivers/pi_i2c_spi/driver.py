"""I2C and SPI driver for Raspberry Pi and other Linux boards, through smbus2 and spidev.

Protocol. I2C through the kernel's i2c-dev interface (`/dev/i2c-N`) and SPI through spidev
(`/dev/spidevB.C`). The device file is the register map. Each channel names a register, or for
SPI the bytes to clock out, and where the value sits in the bytes that come back
(`openhal.drivers.can.bits` fields with `byte`, `length`, `endian`, `signed`, `bit`, `bits`,
`scale`, `offset` and the device `unit`).

- I2C reads send the register address, then read `read_length` bytes with a repeated start. Eight
  bit registers up to 32 bytes use the SMBus block calls, and 16-bit register addresses, longer
  reads and reads without a register use I2C_RDWR.
- I2C writes send the register address followed by the payload. `preserve: true` reads the
  register first and changes only the field's bits, for configuration registers that share a byte.
- SPI is full duplex. A read clocks out `command` padded with zeros and decodes the bytes that
  came back at the same positions. A write clocks out `data` with the field placed in it.

Rules worth knowing.

- The driver only ever writes registers and byte sequences that the device file's write
  channels and actions list. Connecting writes nothing. Put configuration writes, such as
  starting conversions, in actions so they go through the safety kernel.
- Values are rounded to the field's raw step and the reading returned by a write shows the value
  actually sent. A value the field can't hold raises DriverError and nothing is written.
- `health()` reads the first read channel, so the first read channel should be a register that is
  safe to read often (not one that clears on read).
- I2C and SPI have no emergency behavior. The device file's safe state is written like any other
  value.
"""

from __future__ import annotations

import asyncio
import errno
import glob
import re
from collections.abc import Callable
from typing import Annotated, Any, ClassVar, Final, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, ValidationError, model_validator

from openhal.drivers.base import Discovered, Driver, DriverError, DriverInfo, Health, Reading
from openhal.drivers.can import bits
from openhal.spec.models import DeviceFile
from openhal.spec.units import parse_duration

SMBUS_BLOCK: Final = 32
MAX_TRANSFER: Final = 64
EREMOTEIO: Final = getattr(errno, "EREMOTEIO", 121)
I2C_BUS = re.compile(r"^(?:/dev/)?i2c-(\d{1,3})$")
SPI_BUS = re.compile(r"^(?:/dev/)?spi(?:dev)?(\d{1,2})\.(\d{1,2})$")


def _seconds(value: Any) -> Any:
    if isinstance(value, int | float) and not isinstance(value, bool):
        return float(value)
    return parse_duration(value)


Duration = Annotated[float, BeforeValidator(_seconds), Field(gt=0, le=30)]
Byte = Annotated[int, Field(ge=0, le=255)]


class PiBusParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bus: int | str
    address: int | None = Field(default=None, ge=0x03, le=0x77)
    register_width: Literal[1, 2] = 1
    speed_hz: int = Field(default=500_000, ge=1_000, le=50_000_000)
    mode: Literal[0, 1, 2, 3] = 0
    timeout: Duration = 1.0

    @model_validator(mode="after")
    def _bus(self) -> PiBusParams:
        kind, _, _ = parse_bus(self.bus)
        if kind == "i2c" and self.address is None:
            raise ValueError("I2C devices need address, for example address: 0x48.")
        if kind == "spi" and self.address is not None:
            raise ValueError("SPI devices are chosen by the chip select in bus (spi0.1), so remove address.")
        return self

    @property
    def kind(self) -> Literal["i2c", "spi"]:
        return parse_bus(self.bus)[0]

    @property
    def number(self) -> int:
        return parse_bus(self.bus)[1]

    @property
    def chip_select(self) -> int:
        return parse_bus(self.bus)[2]

    @property
    def label(self) -> str:
        if self.kind == "i2c":
            return f"i2c-{self.number} address 0x{self.address or 0:02X}"
        return f"spi{self.number}.{self.chip_select}"


def parse_bus(value: int | str) -> tuple[Literal["i2c", "spi"], int, int]:
    """`1`, `i2c-1` and `/dev/i2c-1` are I2C bus 1. `spi0.1` and `/dev/spidev0.1` are SPI bus 0, chip select 1."""
    if isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 255:
        return "i2c", value, 0
    text = str(value).strip()
    if text.isdigit():
        return "i2c", int(text), 0
    if match := I2C_BUS.match(text):
        return "i2c", int(match.group(1)), 0
    if match := SPI_BUS.match(text):
        return "spi", int(match.group(1)), int(match.group(2))
    raise ValueError(f"bus {value!r} is not an I2C bus (1, i2c-1) or an SPI device (spi0.0).")


class ReadMap(bits.BitField):
    """A value read from a register (I2C) or from the reply to `command` (SPI)."""

    reg: int | None = Field(default=None, alias="register", ge=0, le=0xFFFF)
    command: list[Byte] = Field(default=[], max_length=MAX_TRANSFER)
    read_length: int | None = Field(default=None, ge=1, le=MAX_TRANSFER)

    @property
    def size(self) -> int:
        """How many bytes the read transfers."""
        return max(self.read_length or 0, self.end, len(self.command))


class WriteMap(bits.BitField):
    """A value written into a register (I2C) or into the `data` bytes clocked out (SPI)."""

    reg: int | None = Field(default=None, alias="register", ge=0, le=0xFFFF)
    data: list[Byte] = Field(default=[], max_length=MAX_TRANSFER)
    preserve: bool = False
    state: ReadMap | None = None


class ActionMap(BaseModel):
    """Fixed bytes written to a register (I2C) or clocked out (SPI), with arguments placed in them."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    reg: int | None = Field(default=None, alias="register", ge=0, le=0xFFFF)
    data: list[Byte] = Field(default=[], max_length=MAX_TRANSFER)
    args: dict[str, bits.BitField] = {}


I2cFactory = Callable[[int], Any]
SpiFactory = Callable[[], Any]


def open_i2c(number: int) -> Any:
    """Open /dev/i2c-N with smbus2."""
    from smbus2 import SMBus

    return SMBus(number)


def open_spi() -> Any:
    """A new spidev.SpiDev, which ships with Raspberry Pi OS and installs only on Linux."""
    try:
        import spidev  # type: ignore[import-not-found, unused-ignore]
    except ImportError:
        raise DriverError(
            "The spidev package is missing. It installs only on Linux. Run uv pip install spidev on the Pi."
        ) from None
    return spidev.SpiDev()


class PiBusDriver(Driver):
    """Register-mapped I2C and SPI devices. Reads and writes only the registers the device file lists."""

    info: ClassVar[DriverInfo] = DriverInfo(
        name="pi-i2c-spi",
        protocols=("I2C through i2c-dev", "SPI through spidev"),
        hazard_default="low",
        summary="I2C and SPI sensors, ADCs, DACs and drivers on a Raspberry Pi, from a register map.",
        safe_state_support="file",
        conformance="full",
    )
    params_model: ClassVar[type[Any] | None] = PiBusParams

    def __init__(
        self, device: DeviceFile, *, i2c_factory: I2cFactory = open_i2c, spi_factory: SpiFactory = open_spi
    ) -> None:
        super().__init__(device)
        self.settings = PiBusParams.model_validate(device.connect.params)
        self._i2c_factory = i2c_factory
        self._spi_factory = spi_factory
        self._handle: Any = None
        self._lock = asyncio.Lock()
        self._sent: dict[str, float | bool | str] = {}
        self.reads: dict[str, ReadMap] = {}
        self.writes: dict[str, WriteMap] = {}
        self.actions: dict[str, ActionMap] = {}
        for name, spec in device.read.items():
            read_map = self._parse(ReadMap, f"read.{name}", spec.map)
            bits.check_channel(name, spec, read_map, sends=False)
            self._check_read(f"read.{name}", read_map)
            self.reads[name] = read_map
        for name, wspec in device.write.items():
            write_map = self._parse(WriteMap, f"write.{name}", wspec.map)
            bits.check_channel(name, wspec, write_map, sends=True)
            self._check_target(f"write.{name}", write_map.reg, max(write_map.end, len(write_map.data)))
            if write_map.preserve and self.settings.kind != "i2c":
                raise DriverError(f"write.{name}: preserve only works on I2C registers, which can be read back.")
            if write_map.state is not None:
                bits.check_channel(name, wspec, write_map.state, sends=False)
                self._check_read(f"write.{name}.state", write_map.state)
            self.writes[name] = write_map
        for name, action in device.actions.items():
            action_map = self._parse(ActionMap, f"actions.{name}", action.map)
            if set(action_map.args) != set(action.args):
                raise DriverError(
                    f"actions.{name}: map.args must place every argument the action declares "
                    f"({', '.join(sorted(action.args)) or 'none'}), and no others."
                )
            ends = [len(action_map.data)]
            for arg, field in action_map.args.items():
                bits.check_channel(f"actions.{name}.{arg}", action.args[arg], field, sends=True)
                ends.append(field.end)
            self._check_target(f"actions.{name}", action_map.reg, max(ends))
            self.actions[name] = action_map

    @staticmethod
    def _parse[M: BaseModel](model: type[M], where: str, raw: dict[str, Any] | None) -> M:
        if raw is None:
            raise DriverError(f"{where} needs a map, for example map: {{ register: 0x00, length: 2 }}.")
        try:
            return model.model_validate(raw)
        except ValidationError as exc:
            problems = "; ".join(f"{'.'.join(map(str, e['loc'])) or 'map'}: {e['msg']}" for e in exc.errors())
            raise DriverError(f"{where} has an invalid pi-i2c-spi map. {problems}") from None

    def _check_register(self, where: str, register: int | None) -> None:
        if self.settings.kind == "spi":
            if register is not None:
                raise DriverError(f"{where}: SPI maps put the register in command or data bytes, not register.")
            return
        if register is not None and register > (0xFF if self.settings.register_width == 1 else 0xFFFF):
            raise DriverError(f"{where}: register 0x{register:X} is wider than register_width allows.")

    def _check_read(self, where: str, read_map: ReadMap) -> None:
        self._check_register(where, read_map.reg)
        if self.settings.kind == "i2c" and read_map.command:
            raise DriverError(f"{where}: command bytes are for SPI. I2C reads name a register.")
        if self.settings.kind == "spi" and not read_map.command:
            raise DriverError(f"{where}: SPI reads need command, the bytes to clock out, for example [0x01, 0x80, 0].")
        if read_map.size > MAX_TRANSFER:
            raise DriverError(f"{where} would transfer {read_map.size} bytes, more than {MAX_TRANSFER}.")

    def _check_target(self, where: str, register: int | None, size: int) -> None:
        self._check_register(where, register)
        if self.settings.kind == "i2c" and register is None:
            raise DriverError(f"{where} needs register. The driver only writes registers the device file lists.")
        if self.settings.kind == "spi" and size == 0:
            raise DriverError(f"{where} needs data, the bytes to clock out.")
        if size > MAX_TRANSFER:
            raise DriverError(f"{where} would write {size} bytes, more than {MAX_TRANSFER}.")

    @property
    def _where(self) -> str:
        return self.settings.label

    @classmethod
    async def discover(cls) -> list[Discovered]:
        """List the I2C and SPI device nodes the kernel created. No bus transaction is made."""
        found: list[Discovered] = []
        for path in sorted(glob.glob("/dev/i2c-*")) + sorted(glob.glob("/dev/spidev*.*")):
            try:
                kind, number, chip = parse_bus(path)
            except ValueError:
                continue
            if kind == "i2c":
                found.append(Discovered("pi-i2c-spi", f"i2c-{number}", {"bus": f"i2c-{number}"}, f"I2C bus {number}"))
            else:
                address = f"spi{number}.{chip}"
                label = f"SPI bus {number}, chip select {chip}"
                found.append(Discovered("pi-i2c-spi", address, {"bus": address}, label))
        return found

    async def identify(self) -> dict[str, str]:
        identity = {"bus": self.settings.kind, "device": self._where}
        if self.settings.kind == "spi":
            identity["speed_hz"] = str(self.settings.speed_hz)
            identity["mode"] = str(self.settings.mode)
        return identity

    async def connect(self) -> None:
        await self.close()
        try:
            self._handle = await self._run("open", self._open)
        except DriverError:
            self._handle = None
            raise

    def _open(self) -> Any:
        if self.settings.kind == "i2c":
            return self._i2c_factory(self.settings.number)
        spi = self._spi_factory()
        spi.open(self.settings.number, self.settings.chip_select)
        spi.max_speed_hz = self.settings.speed_hz
        spi.mode = self.settings.mode
        spi.bits_per_word = 8
        return spi

    async def close(self) -> None:
        handle, self._handle = self._handle, None
        if handle is not None:
            try:
                await asyncio.to_thread(handle.close)
            except OSError:
                return

    async def _run(self, what: str, call: Callable[[], Any]) -> Any:
        timeout = self.settings.timeout
        try:
            return await asyncio.wait_for(asyncio.to_thread(call), timeout)
        except TimeoutError:
            raise TimeoutError(f"{self._where} did not finish the {what} within {timeout:g} s.") from None
        except OSError as exc:
            raise DriverError(self._explain(what, exc)) from None

    def _explain(self, what: str, exc: OSError) -> str:
        if exc.errno in (EREMOTEIO, errno.ENXIO, errno.EIO):
            if self.settings.kind == "i2c":
                return (
                    f"Nothing acknowledged the {what} at {self._where} ({exc}). Check the wiring, power and "
                    f"address, for example with i2cdetect -y {self.settings.number}."
                )
            return f"The SPI {what} on {self._where} failed ({exc}). Check the wiring and chip select."
        if exc.errno == errno.ENOENT:
            device = (
                f"/dev/i2c-{self.settings.number}"
                if self.settings.kind == "i2c"
                else f"/dev/spidev{self.settings.number}.{self.settings.chip_select}"
            )
            return f"{device} doesn't exist. Enable {self.settings.kind.upper()} with raspi-config and reboot."
        if exc.errno in (errno.EACCES, errno.EPERM):
            return f"Permission denied on {self._where}. Add the hub's user to the {self.settings.kind} group."
        return f"The {what} on {self._where} failed ({exc})."

    def _check_open(self) -> Any:
        if self._handle is None:
            raise DriverError(f"{self._where} is not open. Connect the device first.")
        return self._handle

    def _i2c_read(self, handle: Any, register: int | None, size: int) -> bytes:
        from smbus2 import i2c_msg

        address = self.settings.address
        assert address is not None
        if register is not None and self.settings.register_width == 1 and size <= SMBUS_BLOCK:
            return bytes(handle.read_i2c_block_data(address, register, size))
        reply = i2c_msg.read(address, size)
        if register is None:
            handle.i2c_rdwr(reply)
        else:
            handle.i2c_rdwr(i2c_msg.write(address, self._register_bytes(register)), reply)
        return bytes(reply)

    def _i2c_write(self, handle: Any, register: int, payload: bytes) -> None:
        from smbus2 import i2c_msg

        address = self.settings.address
        assert address is not None
        if self.settings.register_width == 1 and len(payload) <= SMBUS_BLOCK:
            handle.write_i2c_block_data(address, register, list(payload))
            return
        handle.i2c_rdwr(i2c_msg.write(address, self._register_bytes(register) + payload))

    def _register_bytes(self, register: int) -> bytes:
        return register.to_bytes(self.settings.register_width, "big")

    def _spi_transfer(self, handle: Any, payload: bytes) -> bytes:
        return bytes(handle.xfer2(list(payload)))

    async def _fetch(self, read_map: ReadMap) -> bytes:
        handle = self._check_open()
        if self.settings.kind == "i2c":
            data = await self._run("read", lambda: self._i2c_read(handle, read_map.reg, read_map.size))
        else:
            payload = bytes(read_map.command) + bytes(read_map.size - len(read_map.command))
            data = await self._run("transfer", lambda: self._spi_transfer(handle, payload))
        if len(data) != read_map.size:
            raise DriverError(f"{self._where} returned {len(data)} bytes, not {read_map.size}.")
        return bytes(data)

    async def read(self, channel: str) -> Reading:
        if channel in self.reads:
            return await self._decode(channel, self.reads[channel])
        if channel in self.writes:
            write_map = self.writes[channel]
            if write_map.state is not None:
                return await self._decode(channel, write_map.state)
            self._check_open()
            return Reading(channel, self._sent.get(channel), unit=self.device.channel_unit(channel))
        raise DriverError(f"This pi-i2c-spi device has no channel {channel!r}.")

    async def _decode(self, channel: str, read_map: ReadMap) -> Reading:
        spec = self.device.read.get(channel) or self.device.write[channel]
        async with self._lock:
            data = await self._fetch(read_map)
        where = f"{self._where} for {channel}"
        value = bits.to_value(bits.extract(data, read_map, where), spec, read_map, where)
        return Reading(channel, value, unit=self.device.channel_unit(channel), suspect=bits.suspect(value, spec))

    async def _write(self, channel: str, value: float | bool | str) -> Reading | None:
        write_map = self.writes.get(channel)
        if write_map is None:
            raise DriverError(f"This pi-i2c-spi device has no write channel {channel!r}.")
        handle = self._check_open()
        where = f"write.{channel}"
        raw, sent = bits.to_raw(value, self.device.write[channel], write_map, where)
        async with self._lock:
            if write_map.preserve:
                assert write_map.reg is not None
                current = await self._run("read", lambda: self._i2c_read(handle, write_map.reg, write_map.end))
                payload = bytearray(current)
            else:
                payload = bytearray(write_map.data) + bytearray(max(0, write_map.end - len(write_map.data)))
            bits.insert(payload, write_map, raw, where)
            await self._send(handle, write_map.reg, bytes(payload))
        self._sent[channel] = sent
        if write_map.state is not None:
            return None
        return Reading(channel, sent, unit=self.device.channel_unit(channel))

    async def _send(self, handle: Any, register: int | None, payload: bytes) -> None:
        if self.settings.kind == "i2c":
            assert register is not None
            await self._run("write", lambda: self._i2c_write(handle, register, payload))
        else:
            await self._run("transfer", lambda: self._spi_transfer(handle, payload))

    async def _action(self, name: str, args: dict[str, Any]) -> Any:
        action_map = self.actions.get(name)
        if action_map is None:
            raise DriverError(f"This pi-i2c-spi device has no action {name!r}.")
        handle = self._check_open()
        spec = self.device.actions[name]
        size = max([len(action_map.data)] + [field.end for field in action_map.args.values()])
        payload = bytearray(action_map.data) + bytearray(size - len(action_map.data))
        for arg, field in action_map.args.items():
            raw, _ = bits.to_raw(args[arg], spec.args[arg], field, f"actions.{name}.{arg}")
            bits.insert(payload, field, raw, f"actions.{name}.{arg}")
        async with self._lock:
            await self._send(handle, action_map.reg, bytes(payload))
        target = f"register 0x{action_map.reg:02X}" if action_map.reg is not None else "the bus"
        return {"sent": payload.hex(" ").upper(), "to": target}

    async def health(self) -> Health:
        if self._handle is None:
            return Health(connected=False, detail=f"{self._where} not open")
        probe = next(iter(self.reads.values()), None)
        if probe is None:
            probe = next((write_map.state for write_map in self.writes.values() if write_map.state), None)
        if probe is not None:
            try:
                async with self._lock:
                    await self._fetch(probe)
            except (DriverError, TimeoutError) as exc:
                return Health(connected=False, detail=str(exc))
        return Health(connected=True, detail=self._where)
