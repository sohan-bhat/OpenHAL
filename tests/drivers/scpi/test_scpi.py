"""The scpi driver, through real PyVISA to the TCP bench supply, and through pyvisa-sim."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from openhal.drivers.base import DriverError
from openhal.drivers.scpi import families
from openhal.drivers.scpi.driver import ScpiDriver, _usb_id
from openhal.drivers.scpi.simulator import BenchSupply, ScpiServer, canonical, pyvisa_sim_file
from openhal.spec import loads
from tests.drivers.serial.kit import Bench, assert_done, assert_failed, eventually

PSU = """
device: {{ name: Bench supply, model: DP832, manufacturer: Rigol }}
id: psu
match: {{ scpi_idn: "{idn}" }}
connect: {{ scpi: "{resource}", timeout: 300 ms{extra} }}
read:
  ch1_voltage: {{ unit: V, map: {{ query: "MEAS:VOLT? CH1" }} }}
  ch1_current: {{ unit: mA, map: {{ query: "MEASure:CURRent? CH1", unit: A }} }}
  ch2_power: {{ unit: W, map: {{ query: ":meas:powe? ch2" }} }}
write:
  ch1_output: {{ type: bool, map: {{ set: "OUTP CH1,{{on_off}}", get: "OUTP? CH1" }} }}
  ch1_volts: {{ unit: V, min: 0, max: 40, map: {{ set: "SOUR1:VOLT {{value:.3f}}", get: "SOUR1:VOLT?" }} }}
  ch2_output: {{ type: bool, map: {{ set: "OUTP CH2,{{value}}", on: "1", off: "0" }} }}
  bogus: {{ type: bool, map: {{ set: "FROB {{on_off}}" }} }}
actions:
  set_ch1:
    args:
      volts: {{ unit: V, min: 0, max: 40 }}
      amps: {{ unit: A, min: 0, max: 5 }}
    map: {{ command: "APPL CH1,{{volts}},{{amps}}" }}
safe_state:
  - {{ ch1_output: false }}
hazard: medium
confirmed: {{ by: tester, at: 2026-10-24 }}
"""


@pytest.fixture
def server() -> Iterator[ScpiServer]:
    instance = ScpiServer()
    yield instance
    instance.close()


def make(server: ScpiServer, *, idn: str = "^RIGOL TECHNOLOGIES,DP832", extra: str = "") -> Bench:
    file = loads(PSU.format(resource=server.resource, idn=idn, extra=extra))
    return Bench(file, ScpiDriver(file))


def test_scpi_headers_accept_long_and_short_forms() -> None:
    assert canonical("MEASure:VOLTage?") == "MEAS:VOLT?"
    assert canonical(":meas:curr?") == "MEAS:CURR?"
    assert canonical("SOURce2:VOLT") == "SOUR2:VOLT"


async def test_connect_identifies_and_describes(server: ScpiServer) -> None:
    bench = await make(server).connect()
    driver = bench.driver
    identity = await driver.identify()
    assert identity["manufacturer"] == "RIGOL TECHNOLOGIES"
    assert identity["model"] == "DP832"
    assert identity["serial"] == "DP8C000000001"
    assert identity["firmware"] == "00.01.16"
    described = await driver.describe()
    assert described is not None
    assert set(described["read"]) == {f"ch{n}_{kind}" for n in (1, 2, 3) for kind in ("voltage", "current")}
    assert described["write"]["ch1_output"]["suggested"] is True
    assert described["actions"]["set_ch3"]["args"]["volts"]["max"] == 5
    assert described["match"]["scpi_idn"].startswith("^RIGOL")
    assert (await driver.health()).connected
    await bench.close()


async def test_reads_writes_and_actions(server: ScpiServer) -> None:
    bench = await make(server).connect()
    model = server.model
    assert (await bench.read("ch1_voltage")).value == 0.0
    assert_done(await bench.act("set_ch1", volts="5 V", amps="0.2 A"))
    assert model.voltage[1] == 5.0
    assert model.current[1] == 0.2
    assert (await bench.read("ch1_output")).value is False
    assert_done(await bench.write("ch1_output", True))
    assert model.output[1] is True
    assert (await bench.read("ch1_output")).value is True
    assert (await bench.read("ch1_voltage")).value == pytest.approx(2.0)
    current = await bench.read("ch1_current")
    assert current.unit == "mA"
    assert current.value == pytest.approx(200.0)
    assert_done(await bench.write("ch1_volts", "1500 mV"))
    assert model.voltage[1] == 1.5
    assert (await bench.read("ch1_volts")).value == 1.5
    assert (await bench.read("ch2_output")).value is None
    assert_done(await bench.write("ch2_output", True))
    assert model.output[2] is True
    assert (await bench.read("ch2_output")).value is True
    assert (await bench.read("ch2_power")).value == pytest.approx(0.0)
    assert "OUTP CH2,1" in model.commands
    await bench.close()


async def test_instrument_errors_fail_the_command(server: ScpiServer) -> None:
    bench = await make(server).connect()
    assert_failed(await bench.write("ch1_volts", "35 V"), "-222")
    assert server.model.voltage[1] == 0.0
    assert_failed(await bench.write("bogus", True), "Undefined header")
    assert (await bench.read("bogus")).value is None
    assert_failed(await bench.act("set_ch1", volts="31 V", amps="1 A"), "Data out of range")
    assert server.model.errors == []
    await bench.close()


async def test_old_errors_are_drained_on_connect(server: ScpiServer) -> None:
    server.model.errors.append('-410,"Query INTERRUPTED"')
    bench = await make(server).connect()
    assert_done(await bench.write("ch1_output", True))
    await bench.close()


async def test_without_error_checks_no_queue_reads(server: ScpiServer) -> None:
    bench = await make(server, extra=", check_errors: false").connect()
    before = server.model.commands.count("SYST:ERR?")
    assert_done(await bench.write("bogus", True))
    assert server.model.commands.count("SYST:ERR?") == before
    await bench.close()


async def test_wrong_instrument_is_refused(server: ScpiServer) -> None:
    bench = make(server, idn="^KEYSIGHT")
    with pytest.raises(DriverError, match=r"doesn't match match\.scpi_idn"):
        await bench.driver.connect()
    assert not (await bench.driver.health()).connected


async def test_timeout_then_recovery(server: ScpiServer) -> None:
    bench = await make(server).connect()
    server.latency_s = 0.6
    with pytest.raises(TimeoutError, match="didn't answer MEAS:VOLT"):
        await bench.driver.read("ch1_voltage")
    server.latency_s = 0.0
    assert_done(await bench.act("set_ch1", volts="3 V", amps="1 A"))
    assert_done(await bench.write("ch1_output", True))
    assert (await bench.read("ch1_voltage")).value == pytest.approx(3.0)
    await bench.close()


async def test_malformed_reply(server: ScpiServer) -> None:
    bench = await make(server).connect()
    server.garble = True
    with pytest.raises(DriverError, match="expected a number"):
        await bench.driver.read("ch1_voltage")
    with pytest.raises(DriverError, match="expected on or off"):
        await bench.driver.read("ch1_output")
    await bench.close()


async def test_disconnect_and_reconnect(server: ScpiServer) -> None:
    bench = await make(server).connect()
    server.drop_connections()
    await eventually(lambda: _down(bench), within=3.0)
    with pytest.raises(DriverError, match="lost its connection"):
        await bench.driver.read("ch1_voltage")
    await bench.kernel.connection_lost(bench.device, "test")
    await bench.connect()
    assert (await bench.read("ch1_voltage")).value == 0.0
    await bench.close()


async def _down(bench: Bench) -> bool:
    return not (await bench.driver.health()).connected


async def test_safe_state_comes_from_the_file(server: ScpiServer) -> None:
    bench = await make(server).connect()
    assert_done(await bench.write("ch1_output", True))
    assert await bench.stop() == "safe"
    assert server.model.output[1] is False
    await bench.close()


async def test_unreachable_resource() -> None:
    file = loads(PSU.format(resource="TCPIP0::127.0.0.1::1::SOCKET", idn="x", extra=""))
    with pytest.raises(DriverError, match=r"Could not open|failed during"):
        await ScpiDriver(file).connect()


async def test_bad_visa_library() -> None:
    file = loads(PSU.format(resource="TCPIP0::127.0.0.1::1::SOCKET", idn="x", extra=", visa_library: /nope/visa.so"))
    with pytest.raises(DriverError, match="Could not load the VISA library"):
        await ScpiDriver(file).connect()


# ---------------------------------------------------------------------- pyvisa-sim

DMM = """
device: Bench multimeter
id: dmm
match: {{ usb: ["2a8d:1301"] }}
connect: {{ scpi: {resource}, visa_library: "{library}", timeout: 500 ms }}
read:
  dc_voltage: {{ unit: mV, map: {{ query: "MEAS:VOLT:DC?", unit: V }} }}
  resistance: {{ unit: kohm, map: {{ query: "MEAS:RES?", unit: ohm }} }}
write:
  nplc: {{ unit: dimensionless, min: 0.02, max: 100, map: {{ set: "VOLT:DC:NPLC {{value:f}}", get: "VOLT:DC:NPLC?" }} }}
hazard: low
confirmed: {{ by: tester, at: 2026-10-24 }}
"""


async def test_pyvisa_sim_multimeter(tmp_path: Path) -> None:
    library = pyvisa_sim_file(tmp_path)
    file = loads(DMM.format(resource="auto", library=library))
    bench = await Bench(file, ScpiDriver(file)).connect()
    assert bench.driver.resource_name == "USB0::0x2A8D::0x1301::MY00000001::0::INSTR"
    assert (await bench.read("dc_voltage")).value == pytest.approx(1234.56789)
    assert (await bench.read("resistance")).value == pytest.approx(9.998)
    assert_done(await bench.write("nplc", "1 dimensionless"))
    assert (await bench.read("nplc")).value == 1.0
    described = await bench.driver.describe()
    assert described is not None
    assert "dc_voltage" in described["read"]
    assert "write" not in described
    await bench.close()


async def test_auto_resource_needs_one_match(tmp_path: Path) -> None:
    library = pyvisa_sim_file(tmp_path)
    file = loads(DMM.format(resource="auto", library=library).replace("2a8d:1301", "dead:beef"))
    with pytest.raises(DriverError, match="exactly one instrument"):
        await ScpiDriver(file).connect()
    file = loads(DMM.format(resource="auto", library=library).replace('match: { usb: ["2a8d:1301"] }', ""))
    with pytest.raises(DriverError, match=r"needs match\.usb"):
        await ScpiDriver(file).connect()


# ---------------------------------------------------------------------- families and validation


@pytest.mark.parametrize(
    ("idn", "kind"),
    [
        ("RIGOL TECHNOLOGIES,DP832,DP8C1,00.01.16", "supply-rigol"),
        ("Siglent Technologies,SPD3303X-E,SPD3X,1.01", "supply-rigol"),
        ("Keysight Technologies,E36312A,MY1,2.1", "supply-keysight"),
        ("Agilent Technologies,34401A,0,11-5-2", "multimeter"),
        ("KEITHLEY INSTRUMENTS INC.,MODEL 2000,1,A19", "multimeter"),
        ("RIGOL TECHNOLOGIES,DL3021,DL3A1,00.01", "load"),
        ("Siglent Technologies,SDG2042X,SDG2X,2.01", "generator"),
        ("RIGOL TECHNOLOGIES,DS1054Z,DS1ZA,00.04.04", "scope"),
        ("ACME,WIDGET9000,1,1", None),
    ],
)
def test_families_classify_idn_replies(idn: str, kind: str | None) -> None:
    assert families.classify(families.Identity.parse(idn)) == kind
    proposal = families.propose(idn)
    assert "notes" in proposal
    for section in ("write", "actions"):
        for entry in proposal.get(section, {}).values():
            assert entry["suggested"] is True


def test_keysight_supply_uses_channel_lists() -> None:
    proposal = families.propose("Keysight Technologies,E36312A,MY1,2.1")
    assert proposal["read"]["ch2_voltage"]["map"]["query"] == "MEAS:VOLT? (@2)"
    assert proposal["actions"]["set_ch1"]["args"]["volts"]["max"] == 6
    unknown = families.propose("RIGOL TECHNOLOGIES,DP899,1,1")
    assert "actions" not in unknown
    assert "ratings are unknown" in unknown["notes"]


def test_proposals_load_as_device_files() -> None:
    from openhal.spec.loader import from_data

    for idn in ("RIGOL TECHNOLOGIES,DP832,1,1", "Keysight Technologies,E36312A,1,1", "Agilent,34461A,1,1"):
        proposal = families.propose(idn)
        data = {**proposal, "connect": {"scpi": "auto"}}
        file = from_data(data)
        ScpiDriver(file)
        assert not file.writable or not (file.write or file.actions)


def test_usb_ids_from_resource_names() -> None:
    assert _usb_id("USB0::0x1AB1::0x0E11::DP8C1::INSTR") == "1ab1:0e11"
    assert _usb_id("USB0::6833::3601::DP8C1::INSTR") == "1ab1:0e11"
    assert _usb_id("TCPIP0::10.0.0.2::INSTR") is None


@pytest.mark.parametrize(
    ("snippet", "message"),
    [
        ("read: { v: { unit: V } }", "needs a map"),
        ("read: { v: { unit: V, map: { set: 'X' } } }", "query"),
        ("read: { v: { type: image, map: { query: 'X?' } } }", "images"),
        ("write: { w: { unit: V, min: 0, max: 1, map: { set: 'VOLT {on_off}' } } }", "not allowed"),
        ("write: { w: { type: bool, map: { set: 'OUTP {state}' } } }", "not allowed"),
        ("write: { w: { type: bool, map: { set: 'OUTP {on_off}', get: \"OUTP?\\nRST\" } } }", "control characters"),
        ("actions: { a: { args: { v: { unit: V, min: 0, max: 1 } }, map: { command: 'APPL {w}' } } }", "not allowed"),
    ],
)
def test_bad_maps_are_rejected(snippet: str, message: str) -> None:
    with pytest.raises(DriverError, match=message):
        ScpiDriver(loads(f"device: Bad\nconnect: {{ scpi: auto }}\n{snippet}\n"))


@pytest.mark.parametrize(
    ("params", "message"),
    [("timeout: 2", "needs a unit"), ("timeout: 2 min", "between"), ("termination: tab", "Input should be")],
)
def test_bad_params_are_rejected(params: str, message: str) -> None:
    with pytest.raises(Exception, match=message):
        ScpiDriver(loads(f"device: Bad\nconnect: {{ scpi: auto, {params} }}\n"))


async def test_discover_lists_resources(monkeypatch: pytest.MonkeyPatch) -> None:
    import pyvisa

    class FakeManager:
        def __init__(self, library: str) -> None:
            self.library = library

        def list_resources(self) -> tuple[str, ...]:
            return ("USB0::0x1AB1::0x0E11::DP8C1::INSTR", "ASRL/dev/ttyUSB0::INSTR")

    monkeypatch.setattr(pyvisa, "ResourceManager", FakeManager)
    found = await ScpiDriver.discover()
    assert [item.address for item in found] == ["USB0::0x1AB1::0x0E11::DP8C1::INSTR", "ASRL/dev/ttyUSB0::INSTR"]
    assert found[0].identifiers["usb"] == "1ab1:0e11"


def test_bench_supply_limits_current() -> None:
    model = BenchSupply()
    model.answer("APPL CH1,10,0.5")
    model.answer("OUTP CH1,ON")
    assert model.measured(1) == (5.0, 0.5)
    assert model.answer("APPL? CH1") == "CH1:30V/3A,10.000,0.5000"
