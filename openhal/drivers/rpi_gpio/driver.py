"""Raspberry Pi GPIO driver. Digital outputs, digital inputs, PWM and servos, through gpiozero.

Protocol. GPIO pins on the 40-pin header, numbered by BCM GPIO number (GPIO 17 is header pin
11). gpiozero drives them through a pin factory, lgpio on Raspberry Pi OS Bookworm and on the
Pi 5, RPi.GPIO or pigpio on older systems, and a mock factory for tests.

Each pin gets a name in `pins` (`{ relay: 17, stop_button: 27 }`). A channel uses the pin with
its own name, or the one its map names. The channel type picks the device.

| Channel | gpiozero device | Value |
|---|---|---|
| read, bool | DigitalInputDevice | active (true) or inactive |
| write, bool | DigitalOutputDevice | on (true) or off |
| write, number in percent or dimensionless | PWMOutputDevice | duty cycle, 0 to 100 % or 0 to 1 |
| write, number in an angle unit with map `mode: servo` | AngularServo | angle |

Behavior worth knowing.

- On connect, outputs start inactive (`on_connect: off`), PWM at 0 and servos with no pulse.
  `on_connect: keep` leaves digital outputs at whatever level the pin has.
- `active_high: false` inverts outputs, for relay boards that switch on a low level. Inputs take
  their active level from the pull resistor (pull up means a button to ground reads true when
  pressed), or from the map's `active_high` with `pull: none`.
- When the driver closes, gpiozero releases the pins. The pin library then usually makes them
  inputs, so an output stops being driven. On an active-low relay board with no pull-up that can
  switch the relay on. Fit a pull resistor so a released pin means off.
- GPIO has no emergency behavior. The device file's safe state is applied with ordinary writes.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Annotated, Any, ClassVar, Final, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, ValidationError, model_validator

from openhal.drivers.base import Discovered, Driver, DriverError, DriverInfo, Health, Reading
from openhal.spec.models import DeviceFile
from openhal.spec.units import UnitError, convert, parse_duration, parse_quantity, parse_unit

MODEL_FILE: Final = Path("/proc/device-tree/model")
_ANGLES: Final = frozenset({"degree", "radian", "turn", "grade", "arcminute", "arcsecond", "revolution"})
Bcm = Annotated[int, Field(ge=0, le=27)]
Factory = Literal["auto", "lgpio", "rpigpio", "pigpio", "native", "mock"]


def _seconds(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, int | float) and not isinstance(value, bool):
        return float(value)
    return parse_duration(value)


Duration = Annotated[float | None, BeforeValidator(_seconds)]


class RpiGpioParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pins: dict[Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{0,47}$")], Bcm]
    active_high: bool = True
    pull: Literal["up", "down", "none"] = "up"
    bounce: Duration = None
    on_connect: Literal["off", "keep"] = "off"
    pin_factory: Factory = "auto"

    @model_validator(mode="after")
    def _unique(self) -> RpiGpioParams:
        numbers = list(self.pins.values())
        repeated = sorted({number for number in numbers if numbers.count(number) > 1})
        if repeated:
            raise ValueError(f"GPIO {', '.join(map(str, repeated))} is named more than once in pins.")
        return self


class PinMap(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pin: str | Bcm | None = None
    mode: Literal["digital", "pwm", "servo"] | None = None
    active_high: bool | None = None
    pull: Literal["up", "down", "none"] | None = None
    bounce: Duration = None
    frequency: float = Field(default=100.0, gt=0, le=100_000)
    min_angle: float = -90.0
    max_angle: float = 90.0
    min_pulse_ms: float = Field(default=1.0, gt=0, le=20)
    max_pulse_ms: float = Field(default=2.0, gt=0, le=20)
    frame_ms: float = Field(default=20.0, gt=0, le=100)

    @model_validator(mode="after")
    def _servo(self) -> PinMap:
        if self.min_angle >= self.max_angle:
            raise ValueError("min_angle must be below max_angle.")
        if self.min_pulse_ms >= self.max_pulse_ms or self.max_pulse_ms >= self.frame_ms:
            raise ValueError("Servo pulses need min_pulse_ms < max_pulse_ms < frame_ms.")
        return self


def _make_factory(name: Factory) -> Any:
    if name == "auto":
        return None
    if name == "mock":
        from gpiozero.pins.mock import MockFactory, MockPWMPin  # type: ignore[import-untyped]

        return MockFactory(pin_class=MockPWMPin)
    if name == "lgpio":
        from gpiozero.pins.lgpio import LGPIOFactory  # type: ignore[import-untyped]

        return LGPIOFactory()
    if name == "rpigpio":
        from gpiozero.pins.rpigpio import RPiGPIOFactory  # type: ignore[import-untyped]

        return RPiGPIOFactory()
    if name == "pigpio":
        from gpiozero.pins.pigpio import PiGPIOFactory  # type: ignore[import-untyped]

        return PiGPIOFactory()
    from gpiozero.pins.native import NativeFactory  # type: ignore[import-untyped]

    return NativeFactory()


def _gpio_errors() -> tuple[type[BaseException], ...]:
    from gpiozero.exc import GPIOZeroError  # type: ignore[import-untyped]

    return (GPIOZeroError, OSError, RuntimeError, ValueError)


class RpiGpioDriver(Driver):
    """Raspberry Pi GPIO pins named in the device file."""

    info: ClassVar[DriverInfo] = DriverInfo(
        name="rpi-gpio",
        protocols=("Raspberry Pi GPIO through gpiozero",),
        hazard_default="low",
        summary="Raspberry Pi GPIO pins, digital in and out, PWM and servos.",
    )
    params_model: ClassVar[type[Any] | None] = RpiGpioParams

    def __init__(self, device: DeviceFile, *, pin_factory: Any = None) -> None:
        super().__init__(device)
        self.settings = RpiGpioParams.model_validate(device.connect.params)
        self._factory_override = pin_factory
        self.pin_factory: Any = pin_factory
        self.devices: dict[str, Any] = {}
        self.plan: dict[str, tuple[str, int, PinMap]] = {}
        used: dict[int, str] = {}
        for name, spec in device.read.items():
            if spec.type != "bool":
                raise DriverError(f"{name} is a {spec.type} read channel. GPIO inputs are bool channels.")
            self._plan(name, "input", spec.map, used)
        for name, wspec in device.write.items():
            pmap = self._map(name, wspec.map)
            if wspec.type == "bool":
                mode = "digital"
            elif wspec.type == "number":
                mode = pmap.mode if pmap.mode in ("pwm", "servo") else "pwm"
                self._check_range(name, mode, wspec.unit, wspec.min, wspec.max, pmap)
            else:
                raise DriverError(f"{name} is a {wspec.type} write channel. GPIO outputs are bool or number.")
            self._plan(name, mode, wspec.map, used)
        if device.actions:
            raise DriverError("The rpi-gpio driver has no actions. Model each pin as a channel.")

    def _map(self, name: str, raw: dict[str, Any] | None) -> PinMap:
        try:
            return PinMap.model_validate(raw or {})
        except ValidationError as exc:
            problems = "; ".join(f"{'.'.join(map(str, e['loc'])) or 'map'}: {e['msg']}" for e in exc.errors())
            raise DriverError(f"{name} has an invalid rpi-gpio map. {problems}") from None

    def _plan(self, name: str, mode: str, raw: dict[str, Any] | None, used: dict[int, str]) -> None:
        pmap = self._map(name, raw)
        target = pmap.pin if pmap.pin is not None else name
        if isinstance(target, str):
            if target not in self.settings.pins:
                raise DriverError(
                    f"{name} has no pin. Add {target}: <BCM number> to pins, or give map: {{ pin: <BCM number> }}."
                )
            number = self.settings.pins[target]
        else:
            number = target
        if number in used:
            raise DriverError(f"{name} and {used[number]} both use GPIO {number}.")
        used[number] = name
        self.plan[name] = (mode, number, pmap)

    @staticmethod
    def _check_range(
        name: str, mode: str, unit: str | None, low: float | None, high: float | None, pmap: PinMap
    ) -> None:
        assert unit is not None
        assert low is not None
        assert high is not None
        if mode == "pwm":
            top = 100.0 if unit in ("percent", "%") else 1.0 if unit == "dimensionless" else None
            if top is None:
                raise DriverError(f"{name} is PWM, so its unit is percent (0 to 100) or dimensionless (0 to 1).")
            if low < 0 or high > top:
                raise DriverError(f"{name} limits {low:g} to {high:g} go past what PWM can do (0 to {top:g} {unit}).")
            return
        if str(parse_unit(unit)) not in _ANGLES:
            raise DriverError(f"{name} is a servo, so its unit must be an angle such as degree, not {unit}.")
        try:
            low_deg = convert(parse_quantity(low, default_unit=unit), "degree")
            high_deg = convert(parse_quantity(high, default_unit=unit), "degree")
        except UnitError:
            raise DriverError(f"{name} is a servo, so its unit must be an angle such as degree.") from None
        if low_deg < pmap.min_angle or high_deg > pmap.max_angle:
            raise DriverError(
                f"{name} limits go past the servo's range ({pmap.min_angle:g} to {pmap.max_angle:g} degree). "
                "Set min_angle and max_angle in the map to the servo's real range."
            )

    def stop_button_pin(self, name: str = "stop_button") -> int | None:
        """The BCM number of a pin named in `pins` but not used by a channel, for watch_stop_button."""
        number = self.settings.pins.get(name)
        if number is None or any(planned[1] == number for planned in self.plan.values()):
            return None
        return number

    # ------------------------------------------------------------------ discovery

    @classmethod
    async def discover(cls, *, model_file: Path = MODEL_FILE) -> list[Discovered]:
        """Report the Pi this hub runs on, from the device tree. Reads one file."""
        model = await asyncio.to_thread(_board_model, model_file)
        if model is None or "Raspberry Pi" not in model:
            return []
        return [Discovered(driver="rpi-gpio", address="local", identifiers={"board": model}, label=model)]

    async def identify(self) -> dict[str, str]:
        model = await asyncio.to_thread(_board_model, MODEL_FILE)
        identity = {"board": model or "unknown", "pin_factory": self.settings.pin_factory}
        if self.pin_factory is not None:
            identity["pin_factory"] = type(self.pin_factory).__name__
        return identity

    # ------------------------------------------------------------------ lifecycle

    def _open(self) -> dict[str, Any]:
        from gpiozero import AngularServo, DigitalInputDevice, DigitalOutputDevice, PWMOutputDevice  # type: ignore[import-untyped]

        if self.pin_factory is None:
            self.pin_factory = _make_factory(self.settings.pin_factory)
        factory = self.pin_factory
        opened: dict[str, Any] = {}
        try:
            for name, (mode, number, pmap) in self.plan.items():
                active_high = self.settings.active_high if pmap.active_high is None else pmap.active_high
                if mode == "input":
                    # With a pull resistor the active level follows from it (pull up means a button to
                    # ground reads true when pressed). Without one, the map's active_high decides.
                    pull = pmap.pull or self.settings.pull
                    bounce = pmap.bounce if pmap.bounce is not None else self.settings.bounce
                    pull_up = {"up": True, "down": False, "none": None}[pull]
                    opened[name] = DigitalInputDevice(
                        number,
                        pull_up=pull_up,
                        active_state=(True if pmap.active_high is None else pmap.active_high)
                        if pull_up is None
                        else None,
                        bounce_time=bounce,
                        pin_factory=factory,
                    )
                elif mode == "digital":
                    initial = False if self.settings.on_connect == "off" else None
                    opened[name] = DigitalOutputDevice(
                        number, active_high=active_high, initial_value=initial, pin_factory=factory
                    )
                elif mode == "pwm":
                    opened[name] = PWMOutputDevice(
                        number, active_high=active_high, initial_value=0, frequency=pmap.frequency, pin_factory=factory
                    )
                else:
                    opened[name] = AngularServo(
                        number,
                        initial_angle=None,
                        min_angle=pmap.min_angle,
                        max_angle=pmap.max_angle,
                        min_pulse_width=pmap.min_pulse_ms / 1000,
                        max_pulse_width=pmap.max_pulse_ms / 1000,
                        frame_width=pmap.frame_ms / 1000,
                        pin_factory=factory,
                    )
        except BaseException:
            for gpio in opened.values():
                gpio.close()
            raise
        return opened

    async def connect(self) -> None:
        await self.close()
        try:
            self.devices = await asyncio.to_thread(self._open)
        except DriverError:
            raise
        except _gpio_errors() as exc:
            raise DriverError(
                f"Could not claim the GPIO pins ({type(exc).__name__}: {exc}). Check no other program uses them, "
                "that this is a Raspberry Pi, and that the pin library (lgpio) is installed."
            ) from None

    async def close(self) -> None:
        devices, self.devices = self.devices, {}
        for gpio in devices.values():
            await asyncio.to_thread(gpio.close)

    async def health(self) -> Health:
        if not self.devices:
            return Health(connected=False, detail="GPIO pins are not claimed")
        closed = [name for name, gpio in self.devices.items() if gpio.closed]
        if closed:
            return Health(connected=False, detail=f"GPIO for {', '.join(closed)} was released")
        return Health(connected=True, detail=f"{len(self.devices)} pins")

    # ------------------------------------------------------------------ reads and writes

    def _device(self, channel: str) -> Any:
        if channel not in self.plan:
            raise DriverError(f"This rpi-gpio device has no channel {channel!r}.")
        gpio = self.devices.get(channel)
        if gpio is None or gpio.closed:
            raise DriverError("The GPIO pins are not claimed. The hub will reconnect.")
        return gpio

    async def read(self, channel: str) -> Reading:
        gpio = self._device(channel)
        mode = self.plan[channel][0]
        unit = self.device.channel_unit(channel)
        value: float | bool | None
        if mode in ("input", "digital"):
            value = bool(gpio.value)
        elif mode == "pwm":
            duty = float(gpio.value)
            value = duty * 100.0 if unit in ("percent", "%") else duty
        else:
            angle = gpio.angle
            if angle is None:
                return Reading(channel, None, unit=unit)
            assert unit is not None
            value = convert(parse_quantity(float(angle), default_unit="degree"), unit)
        return Reading(channel, value, unit=unit)

    async def _write(self, channel: str, value: float | bool | str) -> Reading | None:
        if channel not in self.device.write:
            raise DriverError(f"This rpi-gpio device has no write channel {channel!r}.")
        gpio = self._device(channel)
        mode, number, _ = self.plan[channel]
        unit = self.device.channel_unit(channel)
        try:
            if mode == "digital":
                gpio.value = bool(value)
            elif mode == "pwm":
                duty = float(value) / 100.0 if unit in ("percent", "%") else float(value)
                if not 0.0 <= duty <= 1.0:
                    raise DriverError(f"A PWM duty cycle runs from 0 to 1, not {duty:g}.")
                gpio.value = duty
            else:
                assert unit is not None
                gpio.angle = convert(parse_quantity(float(value), default_unit=unit), "degree")
        except DriverError:
            raise
        except _gpio_errors() as exc:
            raise DriverError(f"Setting GPIO {number} for {channel} failed ({exc}).") from None
        return await self.read(channel)

    async def describe(self) -> dict[str, Any] | None:
        identity = await self.identify()
        used = {number for _, number, _ in self.plan.values()}
        spare = sorted(name for name, number in self.settings.pins.items() if number not in used)
        notes = f"Board {identity['board']}. Pins in use are named in connect.pins."
        if spare:
            notes += f" Named but not used by a channel: {', '.join(map(str, spare))}."
        return {"notes": notes}


def _board_model(model_file: Path) -> str | None:
    try:
        return model_file.read_text(encoding="utf-8", errors="replace").rstrip("\x00\n ")
    except OSError:
        return None
