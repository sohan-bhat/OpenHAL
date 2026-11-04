"""Ocean Insight and Ocean Optics spectrometers through python-seabreeze. See docs/drivers/seabreeze.md.

Protocol (python-seabreeze 2.11, the `Spectrometer` class over the cseabreeze or the pure Python
pyseabreeze backend). One device file is one spectrometer, picked by its serial number or the
first one found. Channel maps are in `channels.py`, the chart in `plot.py` and the simulated
spectrometer in `simulator.py`.

- `spectrometer: sim` connects to the simulated spectrometer. Otherwise `spectrometer` is a
  serial number or `auto`, and `backend` picks cseabreeze, which ships its own USB code, or
  pyseabreeze, which needs pyusb and libusb.
- A scan is `intensities()`, the counts of every pixel for one integration time. `average`
  scans are averaged, and readings taken within `scan_age` of a scan share that scan, so reading
  the peak and the spectrum together costs one scan.
- seabreeze can set the integration time and can't read the integration time back, so the
  `integration_time` channel reads the value this driver last set, and unknown before the first
  write. A new integration time clears the stored dark and reference, which no longer match.
- `store_dark` and `store_reference` keep the next scan in the hub's memory. Absorbance and
  transmittance compare a scan against both, so block the light for the dark and put the blank in
  the light path for the reference.
- discover() lists spectrometers on USB through seabreeze's `list_devices`, which reads the USB
  descriptors and opens no spectrometer.

Safe state. None. A spectrometer only measures, so a stop has nothing to switch off.
"""

from __future__ import annotations

import asyncio
import math
import threading
import time
from collections.abc import Callable
from typing import Any, ClassVar, Final, Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from openhal.drivers.base import Discovered, Driver, DriverError, DriverInfo, Health, Reading
from openhal.drivers.seabreeze import channels, plot
from openhal.drivers.seabreeze.channels import ReadMap
from openhal.drivers.serial import mapping
from openhal.spec.models import DeviceFile
from openhal.spec.units import Quantity, convert, parse_unit

NEAR_PIXELS: Final = 2
SATURATED: Final = 0.995
Backend = Literal["cseabreeze", "pyseabreeze"]


def _spectrometers(backend: Backend) -> Any:
    import seabreeze

    try:
        seabreeze.use(backend)
    except Exception as exc:
        raise DriverError(f"seabreeze can't use the {backend} backend ({exc}).") from exc
    import seabreeze.spectrometers as spectrometers

    return spectrometers


def _list_devices(backend: Backend) -> list[Any]:
    devices: list[Any] = _spectrometers(backend).list_devices()
    return devices


class SeabreezeParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    spectrometer: str = Field(default="auto", pattern=r"^(auto|sim(:[a-z0-9-]{1,32})?|[A-Za-z0-9+_.-]{1,40})$")
    backend: Backend = "cseabreeze"
    timeout: float = Field(default=5.0, description="Longest wait for a scan, including every averaged scan.")
    scan_age: float = Field(default=0.5, description="Readings within this long of a scan share it.")
    average: int = Field(default=1, ge=1, le=100)
    dark_correction: bool = False
    nonlinearity_correction: bool = False

    @field_validator("timeout", "scan_age", mode="before")
    @classmethod
    def _duration(cls, value: Any) -> float:
        return mapping.duration(value)

    @model_validator(mode="after")
    def _ranges(self) -> SeabreezeParams:
        if not 0.1 <= self.timeout <= 9:
            raise ValueError("timeout must be between 100 ms and 9 s.")
        if not 0 <= self.scan_age <= 10:
            raise ValueError("scan_age must be between 0 s and 10 s.")
        return self

    @property
    def simulated(self) -> bool:
        return self.spectrometer == "sim" or self.spectrometer.startswith("sim:")


class SeabreezeDriver(Driver):
    """Spectrometers from Ocean Insight and Ocean Optics, scans as readings and charts."""

    info: ClassVar[DriverInfo] = DriverInfo(
        name="seabreeze",
        protocols=("Ocean spectrometers through python-seabreeze",),
        hazard_default="low",
        summary="Ocean Insight and Ocean Optics spectrometers. Spectra, peaks, absorbance and integration time.",
        safe_state_support="none",
        conformance="full",
    )
    params_model: ClassVar[type[Any] | None] = SeabreezeParams

    def __init__(self, device: DeviceFile, *, spectrometer_factory: Callable[[], Any] | None = None) -> None:
        super().__init__(device)
        self.settings = SeabreezeParams.model_validate(device.connect.params)
        self._factory = spectrometer_factory
        self.reads, self.writes, self.actions = channels.build(device)
        self.spec: Any = None
        self.nm: np.ndarray | None = None
        self.integration_us: int | None = None
        self.dark: np.ndarray | None = None
        self.reference: np.ndarray | None = None
        self._scan: tuple[float, np.ndarray] | None = None
        self._lock = threading.Lock()
        self._lost: str | None = None

    @property
    def simulated(self) -> bool:
        return self.settings.simulated

    @classmethod
    async def discover(cls) -> list[Discovered]:
        try:
            devices = await asyncio.to_thread(_list_devices, "cseabreeze")
        except Exception:  # noqa: BLE001 (no backend or no USB access means nothing to list)
            return []
        return [
            Discovered(
                driver="seabreeze",
                address=str(device.serial_number),
                identifiers={"model": str(device.model), "serial_number": str(device.serial_number)},
                label=f"Ocean {device.model}",
            )
            for device in devices
        ]

    def _open(self) -> Any:
        if self._factory is not None:
            return self._factory()
        if self.settings.simulated:
            from openhal.drivers.seabreeze import simulator

            spectrometer = simulator.spectrometer_for(self.settings.spectrometer.partition(":")[2] or "default")
            spectrometer.wavelengths()
            return spectrometer
        found = _spectrometers(self.settings.backend)
        try:
            if self.settings.spectrometer == "auto":
                return found.Spectrometer.from_first_available()
            return found.Spectrometer.from_serial_number(self.settings.spectrometer)
        except Exception as exc:
            raise DriverError(
                f"No spectrometer {self.settings.spectrometer} was found ({exc}). Check the USB cable, close "
                "OceanView, and on Linux install the udev rules with seabreeze_os_setup."
            ) from exc

    async def _call(self, what: str, function: Callable[..., Any], *args: Any) -> Any:
        if self.spec is None:
            raise DriverError(f"{self.device.device_id} is not connected. Connect the spectrometer first.")
        if self._lost is not None:
            raise DriverError(f"The spectrometer connection failed ({self._lost}). Reconnect the spectrometer.")

        def run() -> Any:
            with self._lock:
                return function(*args)

        try:
            return await asyncio.wait_for(asyncio.to_thread(run), self.settings.timeout)
        except TimeoutError:
            raise TimeoutError(f"The spectrometer didn't finish {what} within {self.settings.timeout:g} s.") from None
        except DriverError:
            raise
        except Exception as exc:
            raise DriverError(f"seabreeze returned an error for {what}. {exc}") from exc

    async def connect(self) -> None:
        await self.close()
        try:
            self.spec = await asyncio.wait_for(asyncio.to_thread(self._open), 20.0)
        except TimeoutError:
            raise TimeoutError("Opening the spectrometer took longer than 20 s.") from None
        except DriverError:
            raise
        except Exception as exc:
            raise DriverError(f"seabreeze could not open the spectrometer ({type(exc).__name__}, {exc}).") from exc
        self._lost = None
        self.nm = np.asarray(await self._call("reading the wavelengths", self.spec.wavelengths), dtype=float)

    async def identify(self) -> dict[str, str]:
        identity = {"spectrometer": self.settings.spectrometer}
        if self.spec is not None:
            identity.update(model=str(self.spec.model), serial_number=str(self.spec.serial_number))
            identity["pixels"] = str(self.spec.pixels)
        return identity

    def _scan_now(self) -> np.ndarray:
        total = np.zeros(int(self.spec.pixels), dtype=float)
        for _ in range(self.settings.average):
            total += np.asarray(
                self.spec.intensities(
                    correct_dark_counts=self.settings.dark_correction,
                    correct_nonlinearity=self.settings.nonlinearity_correction,
                ),
                dtype=float,
            )
        result: np.ndarray = total / self.settings.average
        return result

    async def _counts(self) -> np.ndarray:
        now = time.monotonic()
        if self._scan is not None and now - self._scan[0] <= self.settings.scan_age:
            return self._scan[1]
        counts: np.ndarray = await self._call("a scan", self._scan_now)
        self._scan = (time.monotonic(), counts)
        return counts

    def _near(self, counts: np.ndarray, nm: float) -> float:
        assert self.nm is not None
        if not self.nm[0] <= nm <= self.nm[-1]:
            raise DriverError(f"{nm:g} nm is outside this spectrometer's {self.nm[0]:.0f} to {self.nm[-1]:.0f} nm.")
        index = int(np.argmin(np.abs(self.nm - nm)))
        return float(counts[max(0, index - NEAR_PIXELS) : index + NEAR_PIXELS + 1].mean())

    def _ratio(self, counts: np.ndarray, nm: float) -> float:
        if self.dark is None or self.reference is None:
            raise DriverError("Store a dark and a reference spectrum first, with store_dark and store_reference.")
        light = self._near(self.reference, nm) - self._near(self.dark, nm)
        if light <= 0:
            raise DriverError(f"The reference has no light at {nm:g} nm over the dark. Store the reference again.")
        return (self._near(counts, nm) - self._near(self.dark, nm)) / light

    async def read(self, channel: str) -> Reading:
        read_map = self.reads.get(channel) or self.writes.get(channel)
        if read_map is None:
            raise DriverError(f"{self.device.device_id} has no channel {channel!r}.")
        unit = self.device.channel_unit(channel)
        if read_map.kind == "setting":
            if self.integration_us is None:
                return Reading(channel, None, unit)
            return Reading(channel, convert(Quantity(self.integration_us, parse_unit("us")), unit or "us"), unit)
        counts = await self._counts()
        value = self._value(read_map, counts)
        if isinstance(value, bytes):
            return Reading(channel, value, at=time.time())
        native = channels.native_unit(read_map)
        if isinstance(value, float) and unit and native:
            value = convert(Quantity(value, parse_unit(native)), unit)
        return Reading(channel, value, unit)

    def _value(self, read_map: ReadMap, counts: np.ndarray) -> float | bool | bytes:
        assert self.nm is not None
        top = float(self.spec.max_intensity)
        if read_map.kind == "spectrum":
            return plot.render(self.nm, counts, top)
        if read_map.kind == "peak":
            index = int(np.argmax(counts))
            return float(self.nm[index]) if read_map.peak == "wavelength" else float(counts[index])
        if read_map.kind == "wavelength":
            assert read_map.wavelength is not None
            return self._near(counts, read_map.wavelength)
        if read_map.kind == "band":
            assert read_map.band is not None
            low, high = read_map.band
            inside = (self.nm >= low) & (self.nm <= high)
            if not inside.any():
                raise DriverError(f"No pixel lies between {low:g} and {high:g} nm.")
            return float(counts[inside].mean())
        if read_map.kind == "status":
            return bool(counts.max() >= SATURATED * top)
        nm = read_map.absorbance if read_map.kind == "absorbance" else read_map.transmittance
        assert nm is not None
        ratio = self._ratio(counts, nm)
        if read_map.kind == "transmittance":
            return 100.0 * ratio
        if ratio <= 0:
            raise DriverError(f"No light reaches the detector at {nm:g} nm, so the absorbance is off scale.")
        return -math.log10(ratio)

    async def _write(self, channel: str, value: float | bool | str) -> Reading | None:
        if channel not in self.writes:
            raise DriverError(f"{self.device.device_id} has no write channel {channel!r}.")
        unit = self.device.channel_unit(channel) or "us"
        micros = round(convert(Quantity(float(value), parse_unit(unit)), "us"))
        await self._call("setting the integration time", self.spec.integration_time_micros, micros)
        self.integration_us = micros
        self._scan = None
        self.dark = self.reference = None
        return await self.read(channel)

    async def _action(self, name: str, args: dict[str, Any]) -> Any:
        action = self.actions.get(name)
        if action is None:
            raise DriverError(f"{self.device.device_id} has no action {name!r}.")
        if action.command == "clear_references":
            self.dark = self.reference = None
            return {"command": action.command}
        counts: np.ndarray = await self._call("a scan", self._scan_now)
        self._scan = (time.monotonic(), counts)
        if action.command == "store_dark":
            self.dark = counts
        else:
            self.reference = counts
        return {"command": action.command, "integration_us": self.integration_us, "peak_counts": float(counts.max())}

    async def describe(self) -> dict[str, Any] | None:
        if self.spec is None or self.nm is None:
            return None
        low, high = self.spec.integration_time_micros_limits
        longest = min(float(high), self.settings.timeout * 1e6 / self.settings.average / 2)
        each = {"suggested": True}
        return {
            "device": {"name": f"Ocean {self.spec.model} spectrometer", "model": str(self.spec.model)},
            "read": {
                "spectrum": {"type": "image"},
                "peak_wavelength": {"unit": "nm", "range": [round(float(self.nm[0]), 1), round(float(self.nm[-1]), 1)]},
                "peak_intensity": {"unit": "dimensionless", "range": [0, float(self.spec.max_intensity)]},
                "saturated": {"type": "bool"},
            },
            "write": {
                "integration_time": {
                    "unit": "ms",
                    "min": round(float(low) / 1000, 3),
                    "max": round(longest / 1000, 3),
                    **each,
                }
            },
            "actions": {"store_dark": dict(each), "store_reference": dict(each), "clear_references": dict(each)},
            "notes": (
                f"Proposed from the spectrometer, {self.spec.pixels} pixels from {self.nm[0]:.0f} to "
                f"{self.nm[-1]:.0f} nm. The integration time stops where averaged scans still fit the timeout."
            ),
        }

    async def health(self) -> Health:
        if self.spec is None:
            return Health(connected=False, detail="not connected")
        if self._lost is not None:
            return Health(connected=False, detail=self._lost)
        try:
            await self._call("a health check", self.spec.wavelengths)
        except (DriverError, TimeoutError) as exc:
            self._lost = str(exc)
            return Health(connected=False, detail=self._lost)
        kind = "simulated spectrometer" if self.simulated else "spectrometer"
        return Health(connected=True, detail=f"{kind} {self.spec.model} {self.spec.serial_number}")

    async def close(self) -> None:
        spec, self.spec = self.spec, None
        self._scan = None
        if spec is not None and not self.simulated and self._factory is None:
            try:
                await asyncio.wait_for(asyncio.to_thread(spec.close), 5.0)
            except Exception:  # noqa: BLE001 (a spectrometer that is already gone needs no closing)
                return
