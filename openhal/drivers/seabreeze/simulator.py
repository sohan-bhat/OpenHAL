"""A simulated Ocean spectrometer for the seabreeze driver, offline and fast.

`SimulatedSpectrometer` has the methods and properties of python-seabreeze's `Spectrometer` that
the driver calls, so the driver runs the same code against the simulator as against a real
instrument. The instrument is modelled on a USB2000+, 2048 pixels from 340 to 1025 nm with a
16 bit detector.

The light path is a tungsten halogen lamp, a cuvette and the spectrometer. The lamp is a 2900 K
black body, the cuvette holds a dye with one absorbance band at 520 nm whose strength follows
`concentration`, and every scan adds dark counts that grow with the integration time, shot noise
and read noise. A longer integration time gives more counts, up to the detector's 65535, where the
spectrum saturates. With `lamp_on` off the scan shows only the dark counts, which is how a dark
spectrum is taken.

Fault hooks. `unplug()` makes every call fail as a lost USB connection does, and `delay_s` slows
every scan.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Final

import numpy as np

PIXELS: Final = 2048
MAX_COUNTS: Final = 65535.0
LIMITS_US: Final = (1000, 65_000_000)


class SimulatedSpectrometerError(RuntimeError):
    """The simulated spectrometer reported an error, as SeaBreezeError does."""


@dataclass
class SimulatedSpectrometer:
    """A USB2000+ style spectrometer looking at a lamp through a cuvette."""

    model: str = "USB2000PLUS"
    serial_number: str = "SIM00001"
    integration_us: int = 10_000
    lamp_on: bool = True
    concentration: float = 0.6
    peak_nm: float = 520.0
    lamp_counts_per_ms: float = 4000.0
    dark_counts: float = 1500.0
    lost: bool = False
    delay_s: float = 0.0
    scans: int = 0
    seed: int | None = None
    calls: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.rng = np.random.default_rng(self.seed)
        self._wavelengths = np.linspace(340.0, 1025.0, PIXELS)

    def _check(self, what: str) -> None:
        self.calls.append(what)
        if self.lost:
            raise SimulatedSpectrometerError(f"{what} failed. The USB device is gone.")

    def unplug(self) -> None:
        self.lost = True

    def plug_in(self) -> None:
        self.lost = False

    @property
    def pixels(self) -> int:
        return PIXELS

    @property
    def max_intensity(self) -> float:
        return MAX_COUNTS

    @property
    def integration_time_micros_limits(self) -> tuple[int, int]:
        return LIMITS_US

    def integration_time_micros(self, integration_time_micros: int) -> None:
        self._check("integration_time_micros")
        low, high = LIMITS_US
        if not low <= integration_time_micros <= high:
            raise SimulatedSpectrometerError(
                f"Integration time {integration_time_micros} us is outside {low} to {high} us."
            )
        self.integration_us = int(integration_time_micros)

    def wavelengths(self) -> np.ndarray:
        self._check("wavelengths")
        return self._wavelengths.copy()

    def transmission(self) -> np.ndarray:
        """The cuvette's transmission, from its dye's absorbance band."""
        band = np.exp(-0.5 * ((self._wavelengths - self.peak_nm) / 35.0) ** 2)
        result: np.ndarray = 10.0 ** (-self.concentration * band)
        return result

    def lamp(self) -> np.ndarray:
        """The lamp's relative spectrum at the detector, a 2900 K black body times the grating's response."""
        meters = self._wavelengths * 1e-9
        planck = 1.0 / (meters**5 * (np.exp(1.4388e-2 / (meters * 2900.0)) - 1.0))
        response = np.exp(-0.5 * ((self._wavelengths - 600.0) / 210.0) ** 2)
        shape = planck * response
        result: np.ndarray = shape / shape.max()
        return result

    def intensities(self, correct_dark_counts: bool = False, correct_nonlinearity: bool = False) -> np.ndarray:
        self._check("intensities")
        if self.delay_s:
            time.sleep(self.delay_s)
        self.scans += 1
        ms = self.integration_us / 1000.0
        signal = self.lamp() * self.transmission() * self.lamp_counts_per_ms * ms if self.lamp_on else 0.0
        dark = self.dark_counts + 0.8 * ms
        mean = signal + dark
        noisy = mean + self.rng.standard_normal(PIXELS) * np.sqrt(np.maximum(mean, 1.0)) + self.rng.normal(0, 6, PIXELS)
        counts = np.clip(np.round(noisy), 0, MAX_COUNTS)
        if correct_dark_counts:
            counts = np.clip(counts - dark, 0, MAX_COUNTS)
        result: np.ndarray = counts.astype(np.float64)
        return result

    @property
    def features(self) -> dict[str, list[Any]]:
        return {}

    def close(self) -> None:
        self.calls.append("close")


_SPECTROMETERS: dict[str, SimulatedSpectrometer] = {}


def spectrometer_for(name: str = "default") -> SimulatedSpectrometer:
    """The simulated spectrometer with this name. Every connection to the name shares its state."""
    return _SPECTROMETERS.setdefault(name, SimulatedSpectrometer(serial_number=f"SIM-{name}"[:16]))


def reset_spectrometer(name: str = "default", **state: Any) -> SimulatedSpectrometer:
    """Put a fresh simulated spectrometer under this name, with any starting state given."""
    _SPECTROMETERS[name] = SimulatedSpectrometer(serial_number=f"SIM-{name}"[:16], **state)
    return _SPECTROMETERS[name]
