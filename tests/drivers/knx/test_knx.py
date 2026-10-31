"""The knx driver, with real xknx tunneling against the fake KNXnet/IP server and its simulated room."""

from __future__ import annotations

import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from xknx.dpt.payload import DPTArray, DPTBinary
from xknx.telegram.apci import GroupValueRead, GroupValueWrite

from openhal.drivers.base import DriverError
from openhal.drivers.knx import driver as module
from openhal.drivers.knx.conformance import device_file, wait_disconnected
from openhal.drivers.knx.driver import KnxDriver
from openhal.drivers.knx.simulator import KnxGatewaySim
from openhal.drivers.mqtt.conformance import wait_until
from openhal.kernel import Kernel
from openhal.kernel.commands import Write
from openhal.kernel.principals import human
from openhal.spec import loads, validate_path
from openhal.spec.models import DeviceFile

EXAMPLES = Path(__file__).parents[3] / "openhal" / "drivers" / "knx" / "examples"
WHO = human("tester")
EXTRA = """
read:
  window: { type: bool, map: { group_address: 3/1/1, dpt: "1.019" } }
write:
  dimmer: { unit: percent, min: 0, max: 100, map: { group_address: 1/1/3, dpt: "5.001", state_address: 1/1/4 } }
  pulses: { unit: dimensionless, min: 0, max: 1000, map: { group_address: 4/1/1, dpt: "5.010" } }
hazard: low
confirmed: { by: t, at: 2026-10-24 }
"""


@pytest.fixture
def gateway() -> Iterator[KnxGatewaySim]:
    with KnxGatewaySim() as running:
        yield running


async def connected(file: DeviceFile) -> KnxDriver:
    driver = KnxDriver(file)
    await driver.connect()
    return driver


async def kernel_for(driver: KnxDriver) -> Kernel:
    kernel = Kernel()
    kernel.register(driver.device, driver)
    await kernel.connect(driver.device.device_id)
    return kernel


def bare(channels: str, connect: str = "{ knx: 192.168.1.20 }") -> DeviceFile:
    return loads(f"device: T\nid: t\nconnect: {connect}\n{channels}\n")


def sent(gateway: KnxGatewaySim, address: str) -> list[Any]:
    return [
        telegram.payload
        for telegram in gateway.received_telegrams
        if str(telegram.destination_address) == address and isinstance(telegram.payload, GroupValueWrite)
    ]


@pytest.mark.parametrize(
    ("connect", "message"),
    [
        ("{ knx: g, connection: serial }", "tunneling"),
        ('{ knx: g, individual_address: "1.2" }', "pattern"),
        ("{ knx: g, colour: red }", "Extra inputs"),
    ],
)
def test_bad_params(connect: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        KnxDriver(bare('read:\n  x: { type: bool, map: { group_address: 1/1/1, dpt: "1.001" } }', connect))


@pytest.mark.parametrize(
    ("channels", "message"),
    [
        ("read:\n  x: { type: bool }", "needs a knx map"),
        ("read:\n  x: { type: bool, map: { group_address: 1/1/1, dpt: 1.001 } }", "quote the DPT"),
        ('read:\n  x: { type: bool, map: { group_address: 1/1/1, dpt: "999.999" } }', "doesn't support DPT"),
        ('read:\n  x: { type: bool, map: { group_address: 1/1/1/1, dpt: "1.001" } }', "not a group address"),
        ('read:\n  x: { type: bool, map: { group_address: 1/1/1, dpt: "9.001" } }', "need a 1.x DPT"),
        ('read:\n  x: { unit: degC, map: { group_address: 1/1/1, dpt: "1.001" } }', "doesn't carry a number"),
        ('read:\n  x: { unit: V, map: { group_address: 1/1/1, dpt: "9.001" } }', "doesn't convert to V"),
        ('read:\n  x: { type: enum, values: [a], map: { group_address: 1/1/1, dpt: "9.001" } }', "isn't an enum DPT"),
        ('read:\n  x: { type: enum, values: [party], map: { group_address: 1/1/1, dpt: "20.102" } }', "has no party"),
        ('read:\n  x: { type: string, map: { group_address: 1/1/1, dpt: "9.001" } }', "need DPT 16"),
        ('read:\n  x: { type: image, map: { group_address: 1/1/1, dpt: "9.001" } }', "can't carry image"),
        ('read:\n  x: { type: bool, map: { group_address: 1/1/1, dpt: "1.001", colour: red } }', "Extra inputs"),
        ("actions:\n  go: {}", "no actions"),
    ],
)
def test_bad_maps(channels: str, message: str) -> None:
    with pytest.raises(DriverError, match=message):
        KnxDriver(bare(channels))


async def test_reads_ask_the_bus_once_then_follow_it(gateway: KnxGatewaySim) -> None:
    driver = await connected(device_file(gateway))
    temperature = await driver.read("temperature")
    assert temperature.value == pytest.approx(21.5)
    assert temperature.unit == "degC"
    assert (await driver.read("light")).value is False
    assert (await driver.read("hvac_mode")).value == "comfort"
    assert (await driver.read("setpoint")).value == pytest.approx(20.0)
    reads = [str(t.destination_address) for t in gateway.received_telegrams if isinstance(t.payload, GroupValueRead)]
    assert sorted(reads) == ["1/1/2", "2/1/1", "2/1/3", "2/1/4"]
    before = driver._values["2/1/1"][0]
    gateway.report("2/1/1", "9.001", 55.0)
    await wait_until(lambda: driver._values["2/1/1"][0] != before)
    hot = await driver.read("temperature")
    assert hot.value == pytest.approx(55.0, abs=0.1)
    assert hot.suspect
    assert len([t for t in gateway.received_telegrams if isinstance(t.payload, GroupValueRead)]) == 4
    identity = await driver.identify()
    assert identity["individual_address"] == "1.1.251"
    await driver.close()


async def test_addresses_without_a_read_flag_read_as_unknown(gateway: KnxGatewaySim) -> None:
    driver = await connected(device_file(gateway, channels=EXTRA, timeout="200 ms"))
    started = time.monotonic()
    assert (await driver.read("window")).value is None
    assert time.monotonic() - started >= 0.15
    assert (await driver.read("pulses")).value is None
    await driver.close()


async def test_commands_send_group_writes(gateway: KnxGatewaySim) -> None:
    driver = await connected(device_file(gateway))
    kernel = await kernel_for(driver)
    for channel, value in (("setpoint", "22.5 degC"), ("light", True), ("hvac_mode", "economy")):
        decision = await kernel.execute(Write(device="conformance-knx", channel=channel, value=value), WHO)
        assert decision.status == "done", decision.message
    assert sent(gateway, "2/1/2")[-1].value == DPTArray((0x0C, 0x65))
    assert sent(gateway, "1/1/1")[-1].value == DPTBinary(1)
    assert sent(gateway, "2/1/4")[-1].value == DPTArray(3)
    await wait_until(lambda: "1/1/2" in driver._values and driver._values["1/1/2"][0] == DPTBinary(1))
    assert (await driver.read("light")).value is True
    assert (await driver.read("setpoint")).value == pytest.approx(22.5)
    assert (await driver.read("hvac_mode")).value == "economy"
    await driver.close()


async def test_values_are_rounded_to_the_dpt(gateway: KnxGatewaySim) -> None:
    driver = await connected(device_file(gateway, channels=EXTRA))
    kernel = await kernel_for(driver)
    decision = await kernel.execute(Write(device="conformance-knx", channel="dimmer", value="50.4 percent"), WHO)
    assert decision.status == "done", decision.message
    assert sent(gateway, "1/1/3")[-1].value == DPTArray(0x81)
    await wait_until(lambda: driver._values.get("1/1/4", (None, 0))[0] == DPTArray(0x81))
    assert (await driver.read("dimmer")).value == 51.0
    decision = await kernel.execute(Write(device="conformance-knx", channel="pulses", value="7 dimensionless"), WHO)
    assert decision.status == "done", decision.message
    assert (await driver.read("pulses")).value == 7.0
    decision = await kernel.execute(Write(device="conformance-knx", channel="pulses", value="300 dimensionless"), WHO)
    assert decision.status == "failed"
    assert "can't carry" in decision.message
    await driver.close()


async def test_a_missing_confirmation_fails_the_command(gateway: KnxGatewaySim) -> None:
    driver = await connected(device_file(gateway, timeout="100 ms"))
    kernel = await kernel_for(driver)
    gateway.no_confirm = True
    decision = await kernel.execute(Write(device="conformance-knx", channel="light", value=True), WHO)
    assert decision.status == "failed"
    assert "1/1/1" in decision.message
    await driver.close()


async def test_a_closed_tunnel_is_reported_and_reconnects(gateway: KnxGatewaySim) -> None:
    driver = await connected(device_file(gateway))
    assert (await driver.health()).connected
    gateway.kick()
    await wait_disconnected(driver)
    assert "disconnected" in (await driver.health()).detail
    with pytest.raises(DriverError, match="lost the connection"):
        await driver.read("temperature")
    await driver.connect()
    assert gateway.connects == 2
    assert (await driver.read("temperature")).value == pytest.approx(21.5)
    await driver.close()
    with pytest.raises(DriverError, match="not connected"):
        await driver.read("temperature")
    assert not (await driver.health()).connected


async def test_a_refused_tunnel_is_explained(gateway: KnxGatewaySim) -> None:
    gateway.refuse = True
    with pytest.raises(DriverError, match="Could not connect to KNX interface"):
        await connected(device_file(gateway))


async def test_a_silent_gateway_times_out() -> None:
    with KnxGatewaySim() as gateway:
        port = gateway.port
    driver = KnxDriver(device_file_for_port(port))
    started = time.monotonic()
    with pytest.raises((TimeoutError, DriverError)):
        await driver.connect()
    assert time.monotonic() - started < 15


def device_file_for_port(port: int) -> DeviceFile:
    connect = f"{{ knx: 127.0.0.1, port: {port}, local_ip: 127.0.0.1, timeout: 100 ms }}"
    return bare('read:\n  x: { type: bool, map: { group_address: 1/1/2, dpt: "1.001" } }', connect)


async def test_describe_has_nothing_to_offer(gateway: KnxGatewaySim) -> None:
    driver = await connected(device_file(gateway))
    assert await driver.describe() is None
    await driver.close()


async def test_discover_reports_gateways(monkeypatch: pytest.MonkeyPatch) -> None:
    class Gateway:
        ip_addr = "192.168.1.20"
        port = 3671
        name = "MDT IP Interface"
        individual_address = "1.1.250"

    class Scanner:
        def __init__(self, xknx: Any, timeout_in_seconds: float) -> None:
            self.timeout = timeout_in_seconds

        async def scan(self) -> list[Gateway]:
            return [Gateway()]

    import xknx.io

    monkeypatch.setattr(xknx.io, "GatewayScanner", Scanner)
    found = await KnxDriver.discover()
    assert [(item.address, item.identifiers["name"]) for item in found] == [("192.168.1.20:3671", "MDT IP Interface")]

    class Broken(Scanner):
        async def scan(self) -> list[Gateway]:
            raise OSError("no network")

    monkeypatch.setattr(xknx.io, "GatewayScanner", Broken)
    assert await KnxDriver.discover() == []


def test_routing_settings_are_accepted() -> None:
    driver = KnxDriver(
        bare(
            'read:\n  x: { type: bool, map: { group_address: 1/1/2, dpt: "1.001" } }',
            "{ knx: 224.0.23.12, connection: routing, individual_address: 1.1.240 }",
        )
    )
    assert driver.settings.connection == "routing"
    assert module.CONNECTIONS["routing"].name == "ROUTING"


@pytest.mark.parametrize("path", sorted(EXAMPLES.glob("*.hal.yaml")), ids=lambda path: path.name)
def test_examples_validate_and_load_read_only(path: Path) -> None:
    report = validate_path(path)
    assert report.ok, report.problems
    assert report.file is not None
    assert not report.file.writable
    KnxDriver(report.file)
