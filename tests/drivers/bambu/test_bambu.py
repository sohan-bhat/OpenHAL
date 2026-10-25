"""The bambu driver, with a real paho-mqtt client over TLS against the simulated printer."""

from __future__ import annotations

import asyncio
import json
import socket
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from openhal.drivers.bambu import driver as module
from openhal.drivers.bambu.conformance import SERIAL, TOKEN_ENV, device_file, environ
from openhal.drivers.bambu.driver import BambuDriver
from openhal.drivers.bambu.protocol import merge, parse_notify
from openhal.drivers.bambu.simulator import PrinterBroker, SimulatedPrinter
from openhal.drivers.base import DriverError
from openhal.drivers.mqtt.conformance import wait_until
from openhal.kernel import Kernel
from openhal.kernel.commands import Action, Write
from openhal.kernel.principals import human
from openhal.spec import loads, validate_path
from openhal.spec.models import DeviceFile

EXAMPLES = Path(__file__).parents[3] / "openhal" / "drivers" / "bambu" / "examples"
WHO = human("tester")
PIN = "a" * 64
NOTIFY = (
    "NOTIFY * HTTP/1.1\r\nHOST: 239.255.255.250:1990\r\nServer: UPnP/1.0\r\nLocation: 192.168.1.50\r\n"
    "NT: urn:bambulab-com:device:3dprinter:1\r\nUSN: 01S00A123456789\r\nCache-Control: max-age=1800\r\n"
    "DevModel.bambu.com: C11\r\nDevName.bambu.com: Workshop P1P\r\nDevConnect.bambu.com: lan\r\n"
    "DevBind.bambu.com: free\r\n\r\n"
)


@pytest.fixture
def broker() -> Iterator[PrinterBroker]:
    with PrinterBroker(SERIAL) as running:
        yield running


@pytest.fixture
def printer(broker: PrinterBroker) -> SimulatedPrinter:
    return SimulatedPrinter(broker, SERIAL).attach()


def bare(
    channels: str, connect: str = f"{{ bambu: printer.local, serial: {SERIAL}, cert_sha256: {PIN} }}"
) -> DeviceFile:
    return loads(f"device: T\nid: t\nconnect: {connect}\n{channels}\n")


async def connected(file: DeviceFile, **kwargs: Any) -> BambuDriver:
    driver = BambuDriver(file, environ=kwargs.pop("environ", environ), **kwargs)
    await driver.connect()
    return driver


async def kernel_for(driver: BambuDriver) -> Kernel:
    kernel = Kernel()
    kernel.register(driver.device, driver)
    await kernel.connect(driver.device.device_id)
    return kernel


def requests(printer: SimulatedPrinter, section: str) -> list[dict[str, Any]]:
    return [request[section] for request in printer.requests if section in request]


@pytest.mark.parametrize(
    ("connect", "message"),
    [
        (f"{{ bambu: p, serial: {SERIAL} }}", "cert_sha256"),
        (f"{{ bambu: p, serial: {SERIAL}, cert_sha256: abc }}", "64 hex digits"),
        (f"{{ bambu: p, serial: {SERIAL}, cert_sha256: 12:34:56 }}", "must be quoted"),
        ("{ bambu: p, serial: 'not a serial', cert_sha256: " + PIN + " }", "pattern"),
        (f"{{ bambu: p, serial: {SERIAL}, cert_sha256: {PIN}, colour: red }}", "Extra inputs"),
        (f"{{ bambu: p, serial: {SERIAL}, cert_sha256: {PIN}, safe_stop: cancel }}", "'stop' or 'pause'"),
    ],
)
def test_bad_params(connect: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        BambuDriver(bare("read:\n  state: { type: string }", connect))


def test_fingerprints_with_colons_are_accepted() -> None:
    pin = ":".join(["AB"] * 32)
    driver = BambuDriver(
        bare("read:\n  state: { type: string }", f"{{ bambu: p, serial: {SERIAL}, cert_sha256: '{pin}' }}")
    )
    assert driver.settings.cert_sha256 == "ab" * 32


@pytest.mark.parametrize(
    ("channels", "message"),
    [
        ("read:\n  fan: { unit: percent }", "known field"),
        ("read:\n  fan: { unit: percent, map: { field: '$..x' } }", "invalid key"),
        ("read:\n  fan: { unit: percent, map: { field: fan, unit: zorkmids } }", "zorkmids"),
        ("read:\n  cam: { type: image, map: { field: ipcam } }", "image"),
        ("write:\n  nozzle: { unit: degC, min: 0, max: 250 }", "speed_level and chamber_light"),
        ("write:\n  x: { type: bool, map: { control: heater } }", "invalid bambu map"),
        ("write:\n  speed_level: { type: enum, values: [warp] }", "values from silent"),
        ("write:\n  chamber_light: { type: enum, values: [on] }", "bool channel"),
        ("actions:\n  home: {}", "pause, resume and stop"),
        ("actions:\n  stop: { args: { now: { type: bool } } }", "no arguments"),
    ],
)
def test_bad_maps(channels: str, message: str) -> None:
    with pytest.raises(DriverError, match=message):
        BambuDriver(bare(channels))


def test_partial_reports_merge_into_the_state() -> None:
    state: dict[str, Any] = {"a": 1, "ams": {"tray_now": "0", "ams": [1]}}
    merge(state, {"b": 2, "ams": {"tray_now": "1"}})
    assert state == {"a": 1, "b": 2, "ams": {"tray_now": "1", "ams": [1]}}


async def test_reads_come_from_the_report(broker: PrinterBroker, printer: SimulatedPrinter) -> None:
    printer.start_print()
    driver = await connected(device_file(broker))
    assert (await driver.read("state")).value == "running"
    nozzle = await driver.read("nozzle_temp")
    assert nozzle.value == pytest.approx(219.6)
    assert nozzle.unit == "degC"
    assert (await driver.read("progress")).value == 37.0
    assert (await driver.read("remaining")).value == 42.0
    assert (await driver.read("job")).value == "bracket.3mf"
    assert (await driver.read("speed_level")).value == "standard"
    assert (await driver.read("chamber_light")).value is False
    assert driver.versions == {"firmware": "01.08.05.00", "motion_controller": "00.00.30.10"}
    assert (await driver.identify())["firmware"] == "01.08.05.00"
    pushes = requests(printer, "pushing")
    assert pushes[0]["command"] == "pushall"
    await driver.close()


async def test_partial_printers_keep_the_fields_they_do_not_repeat(broker: PrinterBroker) -> None:
    printer = SimulatedPrinter(broker, SERIAL, partial=True).attach()
    del printer.report["chamber_temper"]
    driver = await connected(device_file(broker))
    assert (await driver.read("chamber_temp")).value is None
    printer.push({"bed_temper": 61.5})
    await wait_until(lambda: driver._state.get("bed_temper") == 61.5)
    assert (await driver.read("bed_temp")).value == 61.5
    assert (await driver.read("nozzle_temp")).value == 24.5
    printer.push({"bed_temper": 140.0})
    await wait_until(lambda: driver._state.get("bed_temper") == 140.0)
    assert (await driver.read("bed_temp")).suspect
    await driver.close()


async def test_custom_fields_scale_and_convert(broker: PrinterBroker, printer: SimulatedPrinter) -> None:
    printer.report["cooling_fan_speed"] = "15"
    printer.report["ams"] = {"ams": [{"temp": "77.0"}]}
    extra = (
        "  fan: { unit: percent, map: { field: cooling_fan_speed, scale: 6.666666666666667 } }\n"
        "  ams_temp: { unit: degC, map: { field: 'ams.ams[0].temp', unit: degF } }\n"
        "  wifi_signal: { type: string }\n"
    )
    file = device_file(broker)
    text = file.model_dump_json()
    assert text
    custom = loads(
        "device: T\nid: t\nconnect: " + json.dumps(file.connect.params | {"driver": "bambu"}) + "\nread:\n" + extra
    )
    driver = await connected(custom)
    assert (await driver.read("fan")).value == pytest.approx(100.0)
    assert (await driver.read("ams_temp")).value == pytest.approx(25.0)
    assert (await driver.read("wifi_signal")).value == "-44dBm"
    await driver.close()


async def test_unexpected_report_values_fail_the_read(broker: PrinterBroker, printer: SimulatedPrinter) -> None:
    driver = await connected(device_file(broker))
    printer.push({"gcode_state": "CALIBRATING", "nozzle_temper": "hot", "spd_lvl": 9})
    await wait_until(lambda: driver._state.get("gcode_state") == "CALIBRATING")
    with pytest.raises(DriverError, match="not one of"):
        await driver.read("state")
    with pytest.raises(DriverError, match="not a number"):
        await driver.read("nozzle_temp")
    with pytest.raises(DriverError, match="not 1 to 4"):
        await driver.read("speed_level")
    printer.push({"lights_report": "broken"})
    await wait_until(lambda: driver._state.get("lights_report") == "broken")
    with pytest.raises(DriverError, match="not a list"):
        await driver.read("chamber_light")
    with pytest.raises(DriverError, match="no channel"):
        await driver.read("missing")
    await driver.close()


async def test_writes_send_documented_commands(broker: PrinterBroker, printer: SimulatedPrinter) -> None:
    driver = await connected(device_file(broker))
    kernel = await kernel_for(driver)
    decision = await kernel.execute(Write(device="conformance-bambu", channel="speed_level", value="silent"), WHO)
    assert decision.status == "done", decision.message
    decision = await kernel.execute(Write(device="conformance-bambu", channel="chamber_light", value=True), WHO)
    assert decision.status == "done", decision.message
    speed = requests(printer, "print")[-1]
    assert (speed["command"], speed["param"]) == ("print_speed", "1")
    light = requests(printer, "system")[-1]
    assert (light["command"], light["led_node"], light["led_mode"]) == ("ledctrl", "chamber_light", "on")
    await wait_until(lambda: driver._state.get("spd_lvl") == 1)
    assert (await driver.read("speed_level")).value == "silent"
    await wait_until(lambda: printer.report["lights_report"][0]["mode"] == "on")
    await asyncio.sleep(0.1)
    assert (await driver.read("chamber_light")).value is True
    await driver.close()


async def test_pause_resume_and_stop(broker: PrinterBroker, printer: SimulatedPrinter) -> None:
    printer.start_print()
    driver = await connected(device_file(broker))
    kernel = await kernel_for(driver)
    decision = await kernel.execute(Action(device="conformance-bambu", action="pause"), WHO)
    assert decision.status == "done", decision.message
    await wait_until(lambda: driver._state.get("gcode_state") == "PAUSE")
    assert (await kernel.read("conformance-bambu", "state", WHO)).value == "pause"
    blocked = await kernel.execute(Action(device="conformance-bambu", action="pause"), WHO)
    assert blocked.status == "blocked"
    decision = await kernel.execute(Action(device="conformance-bambu", action="resume"), WHO)
    assert decision.status == "done", decision.message
    await wait_until(lambda: driver._state.get("gcode_state") == "RUNNING")
    decision = await kernel.execute(Action(device="conformance-bambu", action="stop"), WHO)
    assert decision.status == "done", decision.message
    await wait_until(lambda: driver._state.get("gcode_state") == "FAILED")
    assert [body["command"] for body in requests(printer, "print")] == ["pause", "resume", "stop"]
    await driver.close()


async def test_firmware_that_wants_authorization_is_explained(broker: PrinterBroker) -> None:
    printer = SimulatedPrinter(broker, SERIAL, authorization=True).attach()
    printer.start_print()
    driver = await connected(device_file(broker))
    kernel = await kernel_for(driver)
    decision = await kernel.execute(Action(device="conformance-bambu", action="pause"), WHO)
    assert decision.status == "failed"
    assert "Developer Mode" in decision.message
    assert "mqtt message verify failed" in decision.message
    assert (await driver.read("state")).value == "running"
    await driver.close()


async def test_a_printer_that_does_not_reply_still_takes_the_command(broker: PrinterBroker) -> None:
    printer = SimulatedPrinter(broker, SERIAL, silent=True).attach()
    driver = await connected(device_file(broker, reply_wait="200 ms"))
    kernel = await kernel_for(driver)
    decision = await kernel.execute(Action(device="conformance-bambu", action="stop"), WHO)
    assert decision.status == "done", decision.message
    assert requests(printer, "print")[-1]["command"] == "stop"
    await driver.close()


@pytest.mark.parametrize(("setting", "sent"), [("", "stop"), (", safe_stop: pause", "pause")])
async def test_stop_runs_the_native_safe_state(
    broker: PrinterBroker, printer: SimulatedPrinter, setting: str, sent: str
) -> None:
    printer.start_print()
    driver = await connected(device_file(broker, extra=setting))
    kernel = await kernel_for(driver)
    report = await kernel.stop_all(WHO, "test")
    assert report.devices[0].status == "safe"
    assert requests(printer, "print")[-1]["command"] == sent
    await driver.close()


async def test_missing_access_code_names_the_variable(broker: PrinterBroker) -> None:
    driver = BambuDriver(device_file(broker), environ=lambda name: None)
    with pytest.raises(DriverError, match=TOKEN_ENV):
        await driver.connect()


async def test_wrong_access_code_is_refused(broker: PrinterBroker, printer: SimulatedPrinter) -> None:
    driver = BambuDriver(device_file(broker), environ=lambda name: "87654321")
    with pytest.raises(DriverError, match="Check the access code"):
        await driver.connect()
    assert not (await driver.health()).connected


async def test_a_different_certificate_stops_before_the_login(broker: PrinterBroker, printer: SimulatedPrinter) -> None:
    file = loads(device_file(broker).model_dump_json().replace(broker.fingerprint, "b" * 64))
    driver = BambuDriver(file, environ=environ)
    with pytest.raises(DriverError, match="access code was not sent"):
        await driver.connect()
    assert broker.connections == 0


async def test_ca_file_checks_the_serial_in_the_certificate(broker: PrinterBroker, printer: SimulatedPrinter) -> None:
    target = f"bambu: 127.0.0.1, port: {broker.port}, serial: {SERIAL}, token_env: {TOKEN_ENV}"
    extra = f"{{ {target}, ca_file: '{broker.cert_path}' }}"
    channels = "read:\n  state: { type: string }"
    driver = await connected(loads(f"device: T\nid: t\nconnect: {extra}\n{channels}\n"))
    assert (await driver.read("state")).value == "idle"
    await driver.close()
    other = extra.replace(SERIAL, "01S00A000000001")
    with pytest.raises(DriverError, match="not 01S00A000000001"):
        await connected(loads(f"device: T\nid: t\nconnect: {other}\n{channels}\n"))
    broken = extra.replace(str(broker.cert_path), "/no/such/ca.pem")
    with pytest.raises(DriverError, match="Could not load ca_file"):
        await connected(loads(f"device: T\nid: t\nconnect: {broken}\n{channels}\n"))


async def test_a_wrong_serial_gets_no_report(broker: PrinterBroker, printer: SimulatedPrinter) -> None:
    driver = BambuDriver(device_file(broker, serial="01S00A000000001", timeout="500 ms"), environ=environ)
    with pytest.raises(DriverError, match="Check the serial number"):
        await driver.connect()


async def test_nothing_listening_is_reported() -> None:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    file = bare(
        "read:\n  state: { type: string }",
        f"{{ bambu: 127.0.0.1, port: {port}, serial: {SERIAL}, cert_sha256: {PIN} }}",
    )
    driver = BambuDriver(file, environ=lambda name: "x")
    with pytest.raises(DriverError, match="LAN-only mode"):
        await driver.connect()


async def test_a_lost_session_is_reported_and_reconnects(broker: PrinterBroker, printer: SimulatedPrinter) -> None:
    driver = await connected(device_file(broker))
    broker.kick_all()
    await wait_until(lambda: not driver.connected)
    assert not (await driver.health()).connected
    with pytest.raises(DriverError, match="not connected"):
        await driver.read("state")
    await driver.connect()
    assert (await driver.health()).connected
    assert "IDLE" in (await driver.health()).detail
    await driver.close()


async def test_a_missing_puback_drops_the_session(broker: PrinterBroker, printer: SimulatedPrinter) -> None:
    driver = await connected(device_file(broker, timeout="500 ms"))
    kernel = await kernel_for(driver)
    broker.hold_acks = True
    decision = await kernel.execute(Action(device="conformance-bambu", action="stop"), WHO)
    assert decision.status == "failed"
    assert "can't arrive late" in decision.message
    assert not driver.connected


async def test_describe_proposes_channels_from_the_report(broker: PrinterBroker, printer: SimulatedPrinter) -> None:
    driver = await connected(device_file(broker))
    proposal = await driver.describe()
    assert proposal is not None
    assert proposal["read"]["nozzle_temp"] == {"unit": "degC"}
    assert proposal["read"]["state"]["type"] == "enum"
    assert proposal["write"]["speed_level"]["suggested"] is True
    assert set(proposal["actions"]) == {"pause", "resume", "stop"}
    await driver.close()
    assert await driver.describe() is None


def test_notify_parsing() -> None:
    found = parse_notify(NOTIFY, "192.168.1.50")
    assert found is not None
    assert found.address == "192.168.1.50"
    assert found.identifiers == {"serial": "01S00A123456789", "model": "C11", "name": "Workshop P1P", "mode": "lan"}
    assert parse_notify(NOTIFY.replace("bambulab-com", "other"), "x") is None


async def test_discover_listens_for_notify_broadcasts(monkeypatch: pytest.MonkeyPatch) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    monkeypatch.setattr(module, "DISCOVERY_PORT", port)
    monkeypatch.setattr(module, "DISCOVERY_S", 0.5)

    async def announce() -> None:
        await asyncio.sleep(0.1)
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sender:
            sender.sendto(b"garbage", ("127.0.0.1", port))
            sender.sendto(NOTIFY.encode(), ("127.0.0.1", port))

    found, _ = await asyncio.gather(BambuDriver.discover(), announce())
    assert [item.identifiers["serial"] for item in found] == ["01S00A123456789"]


async def test_discover_skips_a_port_another_process_holds(monkeypatch: pytest.MonkeyPatch) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as holder:
        holder.bind(("", 0))
        monkeypatch.setattr(module, "DISCOVERY_PORT", holder.getsockname()[1])
        assert await BambuDriver.discover() == []


@pytest.mark.parametrize("path", sorted(EXAMPLES.glob("*.hal.yaml")), ids=lambda path: path.name)
def test_examples_validate_and_load_read_only(path: Path) -> None:
    report = validate_path(path)
    assert report.ok, report.problems
    assert report.file is not None
    assert not report.file.writable
    BambuDriver(report.file)
