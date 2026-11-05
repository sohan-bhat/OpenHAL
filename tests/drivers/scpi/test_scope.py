"""The simulated bench oscilloscope, on its own and through the scpi driver and a real kernel."""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

import pytest

from openhal import images
from openhal.drivers.scpi import families, simulator
from openhal.drivers.scpi.driver import ScpiDriver, ScpiParams
from openhal.drivers.scpi.scope import INVALID, BenchScope, block
from openhal.drivers.scpi.screen import si
from openhal.spec import loads
from tests.drivers.serial.kit import Bench, assert_done

EXAMPLE = Path(simulator.__file__).parent / "examples" / "simulated-scope.hal.yaml"


def number(reply: str | bytes | None) -> float:
    assert isinstance(reply, str)
    return float(reply)


def tuned() -> BenchScope:
    scope = BenchScope()
    for command in (":CHANnel1:SCALe 0.2", ":tim:scal 200E-6", ":TRIG:EDGE:LEV 0"):
        scope.answer(command)
    return scope


def test_the_scope_starts_as_someone_left_it() -> None:
    scope = BenchScope()
    assert scope.answer("*IDN?") == "OpenHAL,SIM-SCOPE-4,SIM00000001,0.1.0"
    assert scope.answer(":TRIG:STAT?") == "AUTO"
    assert number(scope.answer(":MEAS:FREQ? CHAN1")) == INVALID
    assert 0.5 < number(scope.answer(":MEAS:VPP? CHAN1")) < 1.3
    scope.answer("*RST")
    assert number(scope.answer(":CHAN1:SCAL?")) == 1.0
    assert number(scope.answer(":TIM:SCAL?")) == 0.001


def test_measurements_after_finding_the_signal() -> None:
    scope = tuned()
    assert scope.answer(":TRIG:STAT?") == "TD"
    assert number(scope.answer(":MEAS:FREQ? CHANNEL1")) == pytest.approx(1000.0, rel=0.01)
    assert number(scope.answer(":MEAS:PER? CHAN1")) == pytest.approx(0.001, rel=0.01)
    assert number(scope.answer(":MEAS:VPP? CHAN1")) == pytest.approx(0.987, abs=0.02)
    assert number(scope.answer(":MEAS:RIS? CHAN1")) == pytest.approx(2.2e-4, rel=0.08)
    assert number(scope.answer(":MEAS:FALL? CHAN1")) == pytest.approx(2.2e-4, rel=0.08)
    assert number(scope.answer(":MEAS:VAVG? CHAN1")) == pytest.approx(0.0, abs=0.01)
    assert [item for item, _ in scope.readouts] == ["VPP", "RIS", "FALL", "VAVG"]
    scope.answer(":CHAN1:SCAL 0.1")
    assert number(scope.answer(":MEAS:VPP? CHAN1")) == INVALID
    assert number(scope.answer(":MEAS:FREQ? CHAN1")) == pytest.approx(1000.0, rel=0.01)
    scope.answer(":TIM:SCAL 50E-6")
    assert number(scope.answer(":MEAS:FREQ? CHAN1")) == INVALID


def test_timing_holds_with_edges_on_the_screen_edges() -> None:
    scope = tuned()
    for k in range(40):
        acquisition = scope.acquire(1000.0 + k * 0.137)
        assert scope.measure("FREQ", 1, acquisition) == pytest.approx(1000.0, rel=0.01)
        assert scope.measure("RIS", 1, acquisition) == pytest.approx(2.2e-4, rel=0.08)
        scope.answer(":TIM:POS 0")


def test_describe_proposes_the_example_channels() -> None:
    from openhal.spec.loader import from_data

    proposal = families.propose(BenchScope.idn)
    assert re.search(proposal["match"]["scpi_idn"], BenchScope.idn)
    assert proposal["write"]["gen_amplitude"]["suggested"] is True
    file = from_data({**proposal, "connect": {"scpi": "sim:scope"}})
    ScpiDriver(file)
    assert "screen" in file.read
    assert not file.writable


def test_the_generator_and_its_own_range() -> None:
    scope = tuned()
    scope.answer(":SOUR:FUNC SINusoid")
    assert scope.answer(":SOUR:FUNC?") == "SIN"
    gain = 1 / (1 + (2 * 3.14159265 * 1000 * 1e-4) ** 2) ** 0.5
    assert number(scope.answer(":MEAS:VPP? CHAN1")) == pytest.approx(gain, abs=0.02)
    scope.answer(":SOUR:VOLT 7")
    assert scope.answer(":SYST:ERR?") == '-222,"Data out of range"'
    assert number(scope.answer(":SOUR:VOLT?")) == 1.0
    scope.answer(":OUTP OFF")
    assert scope.answer(":OUTP?") == "0"
    assert number(scope.answer(":MEAS:VPP? CHAN1")) == pytest.approx(0.0, abs=0.02)
    scope.answer(":FROB 1")
    assert scope.answer("SYST:ERR?") == '-113,"Undefined header"'


def test_trigger_modes_hold_the_screen() -> None:
    scope = tuned()
    scope.answer(":SING")
    assert scope.answer(":TRIG:STAT?") == "STOP"
    held = scope.acquire().traces[1].volts
    assert scope.acquire(scope.clock() + 5).traces[1].volts == held
    scope.answer(":RUN;:TRIG:SWE NORMal;:TRIG:EDGE:LEV 3")
    assert scope.answer(":TRIG:STAT?") == "WAIT"
    scope.answer(":TRIG:EDGE:SLOP NEGative;:TRIG:EDGE:LEV 0.2")
    assert scope.answer(":TRIG:STAT?") == "TD"


def test_waveform_fetch_matches_its_preamble() -> None:
    scope = tuned()
    scope.answer(":WAV:SOUR CHAN1;:WAV:FORM ASCii")
    fields = str(scope.answer(":WAV:PRE?")).split(",")
    assert fields[2] == "1000"
    assert float(fields[4]) == pytest.approx(2e-6)
    volts = [float(value) for value in str(scope.answer(":WAV:DATA?")).split(",")]
    assert len(volts) == 1000
    assert max(volts) - min(volts) == pytest.approx(0.987, abs=0.02)
    scope.answer(":WAV:FORM BYTE")
    data = scope.answer(":WAV:DATA?")
    assert isinstance(data, bytes)
    assert data.startswith(b"#41000")
    yinc, yorigin = float(fields[7]), float(fields[8])
    assert (data[6 + 500] - 128) * yinc - yorigin == pytest.approx(volts[500], abs=0.02)


def test_the_screen_is_a_png_block() -> None:
    scope = tuned()
    scope.answer(":MEAS:FREQ? CHAN1")
    data = scope.answer(":DISP:DATA? PNG")
    assert isinstance(data, bytes)
    digits = int(chr(data[1]))
    png = data[2 + digits :]
    assert int(data[2 : 2 + digits]) == len(png)
    assert images.mime_type(png) == "image/png"
    assert images.size(png) == (800, 480)
    assert block(b"abc") == b"#13abc"
    assert [si(2e-4, "s"), si(0.05, "s"), si(999.7, "Hz", 4), si(-0.5, "V"), si(INVALID, "V")] == [
        "200us",
        "50.0ms",
        "1.000kHz",
        "-500mV",
        "*****",
    ]


@pytest.fixture
def scope() -> Iterator[BenchScope]:
    yield simulator.reset("scope")
    simulator.reset("scope")


def confirmed_example() -> str:
    return EXAMPLE.read_text(encoding="utf-8") + "confirmed: { by: tester, at: 2026-11-04 }\n"


async def test_the_example_file_drives_the_simulator(scope: BenchScope) -> None:
    file = loads(confirmed_example())
    driver = ScpiDriver(file)
    bench = await Bench(file, driver).connect()
    assert driver.simulated
    screen = await bench.read("screen")
    assert isinstance(screen.value, bytes)
    assert images.mime_type(screen.value) == "image/png"
    assert (await bench.read("trigger_status")).value == "auto"
    with pytest.raises(Exception, match="SCPI's code"):
        await bench.read("frequency")
    assert_done(await bench.write("ch1_scale", "200 mV"))
    assert_done(await bench.write("timebase", "200 us"))
    assert_done(await bench.write("trigger_level", "0 V"))
    assert scope.channels[1].scale == pytest.approx(0.2)
    assert scope.timebase == pytest.approx(2e-4)
    assert (await bench.read("trigger_status")).value == "triggered"
    assert (await bench.read("frequency")).value == pytest.approx(1000.0, rel=0.01)
    assert (await bench.read("period")).value == pytest.approx(1.0, rel=0.01)
    assert (await bench.read("vpp")).value == pytest.approx(0.987, abs=0.02)
    assert (await bench.read("rise_time")).value == pytest.approx(220, rel=0.08)
    assert_done(await bench.write("gen_function", "sine"))
    assert (await bench.read("gen_function")).value == "sine"
    blocked = await bench.write("gen_amplitude", "5 V")
    assert (blocked.status, blocked.code) == ("blocked", "above_max")
    assert scope.generator.amplitude == 1.0
    assert_done(await bench.write("gen_amplitude", "1.5 V"))
    assert scope.generator.amplitude == pytest.approx(1.5)
    assert_done(await bench.act("single"))
    assert (await bench.read("trigger_status")).value == "stopped"
    assert await bench.stop() == "safe"
    assert scope.generator.output is False
    await bench.close()


SUPPLY = """
device: { name: Bench supply, model: DP832, manufacturer: Rigol }
id: psu
connect: { scpi: "sim:supply", timeout: 1 s }
read:
  ch1_voltage: { unit: V, map: { query: "MEAS:VOLT? CH1" } }
write:
  ch1_output: { type: bool, map: { set: "OUTP CH1,{on_off}", get: "OUTP? CH1" } }
confirmed: { by: tester, at: 2026-11-04 }
"""


async def test_the_simulated_supply_by_name() -> None:
    supply = simulator.reset("supply")
    file = loads(SUPPLY)
    bench = await Bench(file, ScpiDriver(file)).connect()
    assert_done(await bench.write("ch1_output", True))
    assert supply.output[1] is True
    assert (await bench.read("ch1_voltage")).value == 0.0
    await bench.close()
    simulator.reset("supply")


def test_simulated_resources_are_named() -> None:
    assert ScpiParams.model_validate({"resource": "sim:supply"}).simulated
    assert not ScpiParams.model_validate({"resource": "TCPIP0::10.0.0.5::5025::SOCKET"}).simulated
    with pytest.raises(ValueError, match="sim:scope"):
        ScpiParams.model_validate({"resource": "sim:laser"})
    assert simulator.serve("supply") is simulator.serve("supply")
    assert simulator.serve("supply").resource.startswith("TCPIP0::127.0.0.1::")
