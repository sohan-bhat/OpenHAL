"""The seabreeze driver, against the simulated spectrometer behind the same Spectrometer methods."""

from __future__ import annotations

import io
from pathlib import Path

import pytest

pytest.importorskip("seabreeze")

from PIL import Image

from openhal.drivers.base import DriverError
from openhal.drivers.seabreeze import plot
from openhal.drivers.seabreeze.driver import SeabreezeDriver
from openhal.drivers.seabreeze.simulator import SimulatedSpectrometer, reset_spectrometer
from openhal.spec import load, loads
from tests.drivers.serial.kit import Bench, assert_done

EXAMPLE = Path(__file__).resolve().parents[3] / "openhal" / "drivers" / "seabreeze" / "examples"


def spectrometer_file(name: str, extra: str = "") -> str:
    return f"""
device: Test spectrometer
id: spectro
connect: {{ seabreeze: "sim:{name}", timeout: 3 s, scan_age: 0 s }}
read:
  spectrum: {{ type: image }}
  peak_wavelength: {{ unit: nm }}
  peak_intensity: {{ unit: dimensionless }}
  saturated: {{ type: bool }}
  green: {{ unit: dimensionless, map: {{ wavelength: 0.532 um }} }}
  band: {{ unit: dimensionless, map: {{ band: [500 nm, 540 nm] }} }}
  absorbance: {{ unit: dimensionless, map: {{ absorbance: 520 nm }} }}
  transmittance: {{ unit: percent, map: {{ transmittance: 520 nm }} }}
write:
  integration_time: {{ unit: ms, min: 1, max: 100 }}
actions:
  store_dark: {{}}
  store_reference: {{}}
  clear_references: {{}}
{extra}
hazard: low
"""


def make(name: str, text: str | None = None, **state: object) -> tuple[SeabreezeDriver, SimulatedSpectrometer, Bench]:
    spectrometer = reset_spectrometer(name, seed=5, **state)
    file = loads(text or spectrometer_file(name))
    driver = SeabreezeDriver(file)
    return driver, spectrometer, Bench(file, driver)


async def test_a_scan_gives_a_chart_a_peak_and_counts() -> None:
    driver, _spectrometer, bench = make("scan")
    await bench.connect()
    assert driver.simulated
    identity = await driver.identify()
    assert identity["model"] == "USB2000PLUS"
    assert identity["pixels"] == "2048"
    chart = (await bench.read("spectrum")).value
    assert isinstance(chart, bytes)
    assert Image.open(io.BytesIO(chart)).size == (800, 400)
    peak = (await bench.read("peak_wavelength")).value
    assert 600 < peak < 800, "the dye takes out the green, so a lamp through the cuvette peaks in the red"
    assert (await bench.read("peak_intensity")).value > (await bench.read("green")).value
    assert (await bench.read("saturated")).value is False
    assert (await bench.read("band")).value > 0
    await bench.close()


async def test_integration_time_scales_counts_and_saturates() -> None:
    _driver, spectrometer, bench = make("integration")
    await bench.connect()
    assert (await bench.read("integration_time")).value is None, "seabreeze can't read the time back"
    assert_done(await bench.write("integration_time", "5 ms"))
    assert spectrometer.integration_us == 5000
    short = (await bench.read("peak_intensity")).value
    assert_done(await bench.write("integration_time", "10 ms"))
    assert (await bench.read("integration_time")).value == pytest.approx(10.0)
    assert (await bench.read("peak_intensity")).value > 1.6 * short
    assert_done(await bench.write("integration_time", "100 ms"))
    assert (await bench.read("saturated")).value is True
    assert (await bench.write("integration_time", "2 s")).status == "blocked"
    await bench.close()


async def test_absorbance_needs_a_dark_and_a_reference() -> None:
    driver, spectrometer, bench = make("absorbance", concentration=0.0)
    await bench.connect()
    with pytest.raises(DriverError, match="Store a dark and a reference"):
        await driver.read("absorbance")
    spectrometer.lamp_on = False
    assert_done(await bench.act("store_dark"))
    spectrometer.lamp_on = True
    assert_done(await bench.act("store_reference"))
    spectrometer.concentration = 0.5
    assert (await bench.read("absorbance")).value == pytest.approx(0.5, abs=0.05)
    assert (await bench.read("transmittance")).value == pytest.approx(100 * 10**-0.5, abs=2)
    assert_done(await bench.write("integration_time", "20 ms"))
    with pytest.raises(DriverError, match="Store a dark"):
        await driver.read("absorbance")
    await bench.close()


async def test_clear_references_and_a_blocked_light_path() -> None:
    driver, spectrometer, bench = make("cleared")
    await bench.connect()
    spectrometer.lamp_on = False
    assert_done(await bench.act("store_dark"))
    assert_done(await bench.act("store_reference"))
    with pytest.raises(DriverError, match="no light"):
        await driver.read("absorbance")
    assert_done(await bench.act("clear_references"))
    assert driver.dark is None
    await bench.close()


async def test_scans_inside_scan_age_are_shared() -> None:
    text = spectrometer_file("shared").replace("scan_age: 0 s", "scan_age: 5 s")
    _driver, spectrometer, bench = make("shared", text=text)
    await bench.connect()
    await bench.read("peak_wavelength")
    await bench.read("peak_intensity")
    await bench.read("spectrum")
    assert spectrometer.scans == 1
    await bench.close()


async def test_a_lost_spectrometer_reports_unhealthy_until_reconnected() -> None:
    driver, spectrometer, bench = make("lost")
    await bench.connect()
    spectrometer.unplug()
    assert not (await driver.health()).connected
    spectrometer.plug_in()
    with pytest.raises(DriverError, match="connection failed"):
        await driver.read("peak_wavelength")
    await driver.connect()
    assert (await driver.health()).connected
    await bench.close()


async def test_a_slow_scan_times_out() -> None:
    driver, spectrometer, bench = make("slow")
    await bench.connect()
    spectrometer.delay_s = 3.5
    with pytest.raises(TimeoutError, match="didn't finish a scan"):
        await driver.read("peak_wavelength")
    spectrometer.delay_s = 0.0
    await bench.close()


async def test_a_wavelength_outside_the_detector_fails() -> None:
    text = spectrometer_file("range").replace("wavelength: 0.532 um", "wavelength: 1200 nm")
    driver, _spectrometer, bench = make("range", text=text)
    await bench.connect()
    with pytest.raises(DriverError, match="outside this spectrometer"):
        await driver.read("green")
    await bench.close()


async def test_describe_proposes_the_integration_limits() -> None:
    driver, _spectrometer, bench = make("describe")
    await bench.connect()
    proposal = await driver.describe()
    assert proposal is not None
    assert proposal["write"]["integration_time"]["min"] == pytest.approx(1.0)
    assert proposal["write"]["integration_time"]["max"] == pytest.approx(1500.0)
    assert proposal["read"]["peak_wavelength"]["range"] == [340.0, 1025.0]
    assert set(proposal["actions"]) == {"store_dark", "store_reference", "clear_references"}
    await bench.close()


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ("read:\n  light: { unit: dimensionless }", "needs a map"),
        ("read:\n  peak_wavelength: { unit: degC }", "converts to nm"),
        ("read:\n  spectrum: { unit: dimensionless }", "is an image"),
        ("read:\n  x: { unit: dimensionless, map: { band: [550 nm, 500 nm] } }", "low then high"),
        ("read:\n  x: { unit: dimensionless, map: { wavelength: 3 kg } }", "needs a length"),
        ("write:\n  peak_intensity: { unit: dimensionless, min: 0, max: 1 }", "only the integration time"),
        ("actions:\n  store_dark: { args: { n: { unit: dimensionless, min: 0, max: 1 } } }", "takes no arguments"),
    ],
)
def test_the_driver_checks_the_file(body: str, message: str) -> None:
    with pytest.raises(DriverError, match=message):
        SeabreezeDriver(loads(f"device: Spectrometer\nconnect: {{ seabreeze: sim }}\n{body}\nhazard: low\n"))


async def test_the_example_file_loads_and_runs_on_the_simulator() -> None:
    file = load(EXAMPLE / "absorbance-spectrometer.hal.yaml")
    spectrometer = reset_spectrometer("example", seed=2)
    driver = SeabreezeDriver(file, spectrometer_factory=lambda: spectrometer)
    bench = Bench(file, driver)
    await bench.connect()
    assert_done(await bench.write("integration_time", "10 ms"))
    assert_done(await bench.act("store_dark"))
    assert (await bench.read("peak_wavelength")).value > 0
    await bench.close()


def test_the_chart_marks_wavelengths_and_counts() -> None:
    import numpy as np

    nm = np.linspace(400, 700, 300)
    counts = np.exp(-0.5 * ((nm - 550) / 20) ** 2) * 30000
    image = Image.open(io.BytesIO(plot.render(nm, counts, 65535.0))).convert("RGB")
    assert image.size == (800, 400)
    colors = np.unique(np.asarray(image).reshape(-1, 3), axis=0)
    assert len(colors) > 20, "the area under the curve takes the colors of its wavelengths"
