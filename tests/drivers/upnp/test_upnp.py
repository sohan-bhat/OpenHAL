"""The upnp driver, with async-upnp-client against the fake media renderer."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from openhal.drivers.base import DriverError
from openhal.drivers.upnp.conformance import SPEAKER, device_file
from openhal.drivers.upnp.driver import UpnpDriver, default_requester, find_service
from openhal.drivers.upnp.proposals import snake
from openhal.drivers.upnp.simulator import LOCATION, FakeRenderer
from openhal.kernel import Kernel
from openhal.kernel.commands import Action, Write
from openhal.kernel.principals import human
from openhal.spec import loads, validate_path
from openhal.spec.models import DeviceFile

EXAMPLES = Path(__file__).parents[3] / "openhal" / "drivers" / "upnp" / "examples"
WHO = human("tester")
GET_VOLUME = (
    "{ service: RenderingControl, action: GetVolume, args: { InstanceID: 0, Channel: Master }, output: CurrentVolume }"
)


@pytest.fixture
def renderer() -> FakeRenderer:
    return FakeRenderer()


async def connected(file: DeviceFile, renderer: FakeRenderer) -> UpnpDriver:
    driver = UpnpDriver(file, requester=renderer)
    await driver.connect()
    return driver


async def kernel_for(driver: UpnpDriver) -> Kernel:
    kernel = Kernel()
    kernel.register(driver.device, driver)
    await kernel.connect(driver.device.device_id)
    return kernel


def bare(channels: str, extra: str = "") -> DeviceFile:
    tail = "hazard: low\nconfirmed: { by: t, at: 2026-10-24 }\n"
    return loads(f"device: T\nid: t\nconnect: {{ upnp: {LOCATION}{extra} }}\n{channels}\n{tail}")


@pytest.mark.parametrize(
    ("connect", "message"),
    [("{ upnp: ftp://speaker/desc.xml }", "pattern"), (f"{{ upnp: {LOCATION}, colour: red }}", "Extra inputs")],
)
def test_bad_params(connect: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        UpnpDriver(loads(f"device: T\nconnect: {connect}\nread:\n  v: {{ unit: percent, map: {GET_VOLUME} }}\n"))


@pytest.mark.parametrize(
    ("channels", "message"),
    [
        ("read:\n  v: { unit: percent }", "needs a map"),
        ("read:\n  v: { unit: percent, map: { service: RenderingControl, action: GetVolume } }", "output"),
        ("read:\n  v: { type: image, map: { service: X, action: Y, output: Z } }", "don't return images"),
        (
            "write:\n  v: { unit: percent, min: 0, max: 9, map: { service: R, action: SetVolume, args: { D: 3 } } }",
            "only {value}",
        ),
        (
            "write:\n  v: { unit: percent, min: 0, max: 9, map: { service: R, action: S, "
            "args: { D: '{value}', E: '{x}' } } }",
            "only {value}",
        ),
        (
            "actions:\n  seek: { args: { track: { unit: dimensionless, min: 1, max: 9 } }, "
            "map: { service: A, action: Seek } }",
            "every argument",
        ),
        ("read:\n  v: { unit: percent, map: { service: R, action: 'Get Volume', output: X } }", "pattern"),
    ],
)
def test_bad_maps(channels: str, message: str) -> None:
    with pytest.raises(DriverError, match=message):
        UpnpDriver(bare(channels))


@pytest.mark.parametrize(
    ("channels", "message"),
    [
        (
            "read:\n  v: { unit: percent, map: { service: Mixer, action: GetVolume, output: CurrentVolume } }",
            "no service Mixer. It has AVTransport, RenderingControl",
        ),
        (
            "read:\n  v: { unit: percent, map: { service: RenderingControl, action: GetLoudness, output: X } }",
            "no action GetLoudness",
        ),
        (
            "read:\n  v: { unit: percent, map: { service: RenderingControl, action: GetVolume, "
            "args: { InstanceID: 0 }, output: CurrentVolume } }",
            "missing Channel",
        ),
        (
            "read:\n  v: { unit: percent, map: { service: RenderingControl, action: GetVolume, args: { InstanceID: 0, "
            "Channel: Master, Zone: 1 }, output: CurrentVolume } }",
            "unknown Zone",
        ),
        (
            "read:\n  v: { unit: percent, map: { service: RenderingControl, action: GetVolume, args: { InstanceID: 0, "
            "Channel: Master }, output: Volume } }",
            "no output Volume. It has CurrentVolume",
        ),
        (f"read:\n  v: {{ type: bool, map: {GET_VOLUME} }}", "is ui2, not boolean"),
        (
            "read:\n  v: { type: enum, values: [PLAYING, DANCING], map: { service: AVTransport, "
            "action: GetTransportInfo, args: { InstanceID: 0 }, output: CurrentTransportState } }",
            "not DANCING",
        ),
        (
            "read:\n  v: { unit: percent, map: { service: AVTransport, action: GetTransportInfo, "
            "args: { InstanceID: 0 }, output: CurrentTransportState } }",
            "not a number",
        ),
    ],
)
async def test_maps_are_checked_against_the_scpd(renderer: FakeRenderer, channels: str, message: str) -> None:
    with pytest.raises(DriverError, match=message):
        await connected(bare(channels), renderer)


async def test_services_are_found_by_id_type_or_short_name(renderer: FakeRenderer) -> None:
    driver = await connected(device_file(), renderer)
    assert driver.upnp is not None
    for name in (
        "RenderingControl",
        "urn:upnp-org:serviceId:RenderingControl",
        "urn:schemas-upnp-org:service:RenderingControl:1",
    ):
        service = find_service(driver.upnp, name)
        assert service is not None
        assert service.service_type.endswith("RenderingControl:1")
    assert find_service(driver.upnp, "ContentDirectory") is None
    identity = await driver.identify()
    assert (identity["friendly_name"], identity["model"]) == ("Simulated speaker", "MR-1")


async def test_reads_call_get_actions(renderer: FakeRenderer) -> None:
    driver = await connected(device_file(), renderer)
    assert (await driver.read("transport_state")).value == "STOPPED"
    volume = await driver.read("volume")
    assert volume.value == 25.0
    assert volume.unit == "percent"
    assert (await driver.read("mute")).value is False
    name, args = renderer.calls[-1]
    assert (name, args) == ("GetMute", {"InstanceID": "0", "Channel": "Master"})
    soap = renderer.requests[-1]
    assert soap.method == "POST"
    assert soap.headers["SOAPAction"] == '"urn:schemas-upnp-org:service:RenderingControl:1#GetMute"'


async def test_commands_and_actions_call_soap_actions(renderer: FakeRenderer) -> None:
    driver = await connected(device_file(), renderer)
    kernel = await kernel_for(driver)
    decision = await kernel.execute(Write(device="conformance-upnp", channel="volume", value="30 percent"), WHO)
    assert decision.status == "done", decision.message
    decision = await kernel.execute(Write(device="conformance-upnp", channel="mute", value=True), WHO)
    assert decision.status == "done", decision.message
    decision = await kernel.execute(Action(device="conformance-upnp", action="play"), WHO)
    assert decision.status == "done", decision.message
    assert renderer.calls[-3:] == [
        ("SetVolume", {"InstanceID": "0", "Channel": "Master", "DesiredVolume": "30"}),
        ("SetMute", {"InstanceID": "0", "Channel": "Master", "DesiredMute": "1"}),
        ("Play", {"InstanceID": "0", "Speed": "1"}),
    ]
    assert (renderer.volume, renderer.mute, renderer.state) == (30, True, "PLAYING")
    assert (await driver.read("volume")).value == 30.0
    assert (await driver.read("transport_state")).value == "PLAYING"


async def test_action_arguments_and_values_without_readback(renderer: FakeRenderer) -> None:
    channels = (
        "write:\n  level:\n    unit: percent\n    min: 0\n    max: 50\n"
        "    map: { service: RenderingControl, action: SetVolume, args: { InstanceID: 0, Channel: Master, "
        "DesiredVolume: '{value}' }, scale: 0.5 }\n"
        "actions:\n  seek:\n    args: { track: { unit: dimensionless, min: 1, max: 99 } }\n"
        "    map: { service: AVTransport, action: Seek, args: { InstanceID: 0, Unit: TRACK_NR, Target: '{track}' } }"
    )
    driver = await connected(bare(channels), renderer)
    assert (await driver.read("level")).value is None
    kernel = await kernel_for(driver)
    decision = await kernel.execute(Write(device="t", channel="level", value="20 percent"), WHO)
    assert decision.status == "done", decision.message
    assert renderer.volume == 40
    assert (await driver.read("level")).value == 20.0
    decision = await kernel.execute(Action(device="t", action="seek", args={"track": "3 dimensionless"}), WHO)
    assert decision.status == "done", decision.message
    assert renderer.calls[-1] == ("Seek", {"InstanceID": "0", "Unit": "TRACK_NR", "Target": "3"})
    assert renderer.track == 3


async def test_soap_faults_become_driver_errors(renderer: FakeRenderer) -> None:
    driver = await connected(device_file(), renderer)
    kernel = await kernel_for(driver)
    renderer.fault_next = 501
    decision = await kernel.execute(Action(device="conformance-upnp", action="play"), WHO)
    assert decision.status == "failed"
    assert "UPnP error 501 for Play (Action Failed)" in decision.message
    renderer.garbage = True
    with pytest.raises(DriverError, match="doesn't parse"):
        await driver.read("transport_state")


async def test_a_device_that_goes_away(renderer: FakeRenderer) -> None:
    driver = await connected(device_file(), renderer)
    renderer.unplugged = True
    with pytest.raises(DriverError, match="sent no reply to GetTransportInfo"):
        await driver.read("transport_state")
    health = await driver.health()
    assert not health.connected
    assert "Cannot connect" in health.detail
    with pytest.raises(DriverError, match="stopped sending replies"):
        await driver.read("transport_state")
    with pytest.raises(DriverError, match="Could not fetch the description"):
        await driver.connect()
    renderer.unplugged = False
    await driver.connect()
    assert (await driver.health()).connected
    await driver.close()
    with pytest.raises(DriverError, match="not connected"):
        await driver.read("transport_state")


async def test_slow_devices_time_out(renderer: FakeRenderer) -> None:
    driver = await connected(device_file(timeout="200 ms"), renderer)
    renderer.latency_s = 2.0
    with pytest.raises(TimeoutError, match="sent no reply to GetTransportInfo"):
        await driver.read("transport_state")
    assert not (await driver.health()).connected
    with pytest.raises(TimeoutError, match="didn't send its description"):
        await driver.connect()


async def test_a_wrong_location_is_explained(renderer: FakeRenderer) -> None:
    file = loads(f"device: T\nconnect: {{ upnp: {LOCATION.replace('device_description', 'nothing')} }}\n{SPEAKER}")
    with pytest.raises(DriverError, match="description"):
        await connected(file, renderer)


async def test_describe_proposes_channels_from_the_scpd(renderer: FakeRenderer) -> None:
    driver = await connected(device_file(), renderer)
    proposal = await driver.describe()
    assert proposal is not None
    assert proposal["read"]["current_transport_state"]["type"] == "enum"
    volume = proposal["write"]["volume"]
    assert (volume["min"], volume["max"], volume["suggested"]) == (0, 100, True)
    assert volume["map"]["state"]["output"] == "CurrentVolume"
    assert proposal["write"]["mute"]["type"] == "bool"
    assert set(proposal["actions"]) == {"play", "pause", "stop"}
    await driver.close()
    assert await driver.describe() is None


async def test_discover_collects_ssdp_answers(monkeypatch: pytest.MonkeyPatch) -> None:
    import async_upnp_client.search as search

    async def fake_search(callback: Any, **options: Any) -> None:
        assert options["search_target"] == "upnp:rootdevice"
        headers = {
            "location": LOCATION,
            "st": "upnp:rootdevice",
            "usn": "uuid:5f9e::upnp:rootdevice",
            "server": "Linux UPnP/1.0",
        }
        await callback(headers)
        await callback(headers)
        await callback({"st": "upnp:rootdevice"})

    monkeypatch.setattr(search, "async_search", fake_search)
    found = await UpnpDriver.discover()
    assert [(item.address, item.label) for item in found] == [(LOCATION, "Linux UPnP/1.0")]

    async def broken(callback: Any, **options: Any) -> None:
        raise OSError("no multicast route")

    monkeypatch.setattr(search, "async_search", broken)
    assert await UpnpDriver.discover() == []


def test_default_requester_and_names() -> None:
    from async_upnp_client.aiohttp import AiohttpRequester

    assert isinstance(default_requester(2.5), AiohttpRequester)
    assert snake("CurrentTransportState") == "current_transport_state"
    assert snake("3D") == "v_3_d"


@pytest.mark.parametrize("path", sorted(EXAMPLES.glob("*.hal.yaml")), ids=lambda path: path.name)
def test_examples_validate_and_load_read_only(path: Path) -> None:
    report = validate_path(path)
    assert report.ok, report.problems
    assert report.file is not None
    assert not report.file.writable
    UpnpDriver(report.file)
