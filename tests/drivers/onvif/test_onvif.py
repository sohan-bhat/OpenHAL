"""The onvif driver, with its own SOAP client against the simulated PTZ camera."""

from __future__ import annotations

import asyncio
import base64
import datetime as dt
import socket
import threading
from pathlib import Path
from typing import Any

import pytest

from openhal.drivers.base import DriverError
from openhal.drivers.onvif import discovery, soap
from openhal.drivers.onvif.conformance import TOKEN_ENV, device_file, environ
from openhal.drivers.onvif.driver import OnvifDriver
from openhal.drivers.onvif.simulator import OnvifCameraSim
from openhal.kernel import Kernel
from openhal.kernel.commands import Action, Write
from openhal.kernel.principals import human
from openhal.spec import loads, validate_path
from openhal.spec.models import DeviceFile

EXAMPLES = Path(__file__).parents[3] / "openhal" / "drivers" / "onvif" / "examples"
WHO = human("tester")
MATCHES = (
    f'<?xml version="1.0"?><s:Envelope xmlns:s="{soap.SOAP}" xmlns:d="{discovery.WSD}"><s:Body><d:ProbeMatches>'
    "<d:ProbeMatch><d:XAddrs>http://192.168.1.40/onvif/device_service http://[fe80::1]/onvif/device_service</d:XAddrs>"
    "<d:Scopes>onvif://www.onvif.org/name/Garage%20PTZ onvif://www.onvif.org/hardware/DS-2DE2A404IW "
    "onvif://www.onvif.org/Profile/Streaming</d:Scopes></d:ProbeMatch>"
    "<d:ProbeMatch><d:Scopes>onvif://www.onvif.org/name/Broken</d:Scopes></d:ProbeMatch>"
    "</d:ProbeMatches></s:Body></s:Envelope>"
).encode()


@pytest.fixture
def camera() -> OnvifCameraSim:
    return OnvifCameraSim()


async def connected(file: DeviceFile, camera: OnvifCameraSim, **kwargs: Any) -> OnvifDriver:
    driver = OnvifDriver(file, transport=camera.transport(), environ=kwargs.pop("environ", environ))
    await driver.connect()
    return driver


async def kernel_for(driver: OnvifDriver) -> Kernel:
    kernel = Kernel()
    kernel.register(driver.device, driver)
    await kernel.connect(driver.device.device_id)
    return kernel


def bare(channels: str, connect: str = "{ onvif: camera.local }") -> DeviceFile:
    return loads(
        f"device: T\nid: t\nconnect: {connect}\n{channels}\nhazard: low\nconfirmed: {{ by: t, at: 2026-10-24 }}\n"
    )


def test_password_digest_matches_the_onvif_example() -> None:
    nonce = base64.b64decode("LKqI6G/AikKCQrN0zqZFlg==")
    assert soap.digest(nonce, "2010-09-16T07:50:45Z", "userpassword") == "tuOSpGlFlIXsozq4HFNeeGeFLEI="
    header = soap.security_header("admin", "pw", dt.datetime(2026, 10, 24, 12, 0, 1, 500, tzinfo=dt.UTC), nonce)
    assert "<Created " in header
    assert ">2026-10-24T12:00:01Z</Created>" in header
    assert soap.digest(nonce, "2026-10-24T12:00:01Z", "pw") in header


def test_replies_parse_faults_and_refuse_junk() -> None:
    fault = soap.envelope(
        "<s:Fault><s:Code><s:Value>s:Sender</s:Value><s:Subcode><s:Value>ter:NotAuthorized</s:Value></s:Subcode>"
        "</s:Code><s:Reason><s:Text>Sender not Authorized</s:Text></s:Reason></s:Fault>"
    )
    with pytest.raises(soap.SoapFaultError) as caught:
        soap.parse(fault)
    assert caught.value.not_authorized
    assert str(caught.value) == "ter:NotAuthorized: Sender not Authorized"
    with pytest.raises(ValueError, match="not XML"):
        soap.parse(b"<<")
    with pytest.raises(ValueError, match="not a SOAP envelope"):
        soap.parse(b"<html/>")
    with pytest.raises(ValueError, match="no SOAP body"):
        soap.parse(f'<s:Envelope xmlns:s="{soap.SOAP}"/>')
    with pytest.raises(ValueError, match="not XML"):
        soap.parse(b'<!DOCTYPE x [<!ENTITY a "aaaa">]><x>&a;</x>')
    assert soap.device_time(soap.parse(soap.envelope("<x/>"))) is None
    assert soap.vector(0.5, None, None) == '<tt:PanTilt x="0.5" y="0"/>'
    assert soap.vector(None, None, 0.25) == '<tt:Zoom x="0.25"/>'


def test_probe_and_probe_matches() -> None:
    probe = discovery.probe("uuid:1").decode()
    assert "<d:Types>dn:NetworkVideoTransmitter</d:Types>" in probe
    assert "<a:MessageID>uuid:1</a:MessageID>" in probe
    found = discovery.parse_matches(MATCHES)
    assert len(found) == 1
    assert found[0].address == "192.168.1.40"
    assert found[0].identifiers["name"] == "Garage PTZ"
    assert found[0].identifiers["hardware"] == "DS-2DE2A404IW"
    assert discovery.parse_matches(b"junk") == []


async def test_discover_sends_one_probe_and_reads_the_matches(monkeypatch: pytest.MonkeyPatch) -> None:
    responder = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    responder.bind(("127.0.0.1", 0))
    responder.settimeout(3)
    probes: list[bytes] = []

    def answer() -> None:
        data, sender = responder.recvfrom(65535)
        probes.append(data)
        responder.sendto(b"not xml", sender)
        responder.sendto(MATCHES, sender)

    thread = threading.Thread(target=answer, daemon=True)
    thread.start()
    monkeypatch.setattr(discovery, "GROUP", "127.0.0.1")
    monkeypatch.setattr(discovery, "PORT", responder.getsockname()[1])
    monkeypatch.setattr(discovery, "LISTEN_S", 0.5)
    try:
        found = await OnvifDriver.discover()
    finally:
        thread.join(timeout=3)
        responder.close()
    assert len(probes) == 1
    assert b"NetworkVideoTransmitter" in probes[0]
    assert [camera.identifiers["name"] for camera in found] == ["Garage PTZ"]


@pytest.mark.parametrize(
    ("channels", "message"),
    [
        ("read:\n  brightness: { unit: percent }", "name the channel after a field"),
        ("read:\n  pan: { type: string }", "needs type number"),
        ("read:\n  model: { unit: dimensionless }", "needs type string"),
        ("read:\n  x: { unit: degree, map: { field: pan, unit: V } }", "doesn't convert"),
        ("read:\n  x: { unit: degree, map: { field: focus } }", "invalid onvif map"),
        ("write:\n  model: { type: string, max_length: 9 }", "only pan, tilt and zoom"),
        ("actions:\n  wiggle: {}", "name the action after an operation"),
        ("actions:\n  go: { map: { operation: fly } }", "invalid onvif map"),
        ("actions:\n  home: { args: { speed: { unit: dimensionless, min: 0, max: 1 } } }", "takes no arguments"),
        ("actions:\n  move: { args: { focus: { unit: dimensionless, min: 0, max: 1 } } }", "not focus"),
    ],
)
def test_bad_maps(channels: str, message: str) -> None:
    with pytest.raises(DriverError, match=message):
        OnvifDriver(bare(channels))


@pytest.mark.parametrize(
    ("connect", "message"),
    [("{ onvif: c, scheme: ftp }", "'http' or 'https'"), ("{ onvif: c, colour: red }", "Extra inputs")],
)
def test_bad_params(connect: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        OnvifDriver(bare("read:\n  model: { type: string }", connect))


async def test_identity_profile_and_uris(camera: OnvifCameraSim) -> None:
    driver = await connected(device_file(), camera)
    assert (await driver.read("manufacturer")).value == "OpenHAL simulator"
    assert (await driver.read("model")).value == "PTZ-1"
    assert (await driver.read("stream_uri")).value == "rtsp://camera.local:554/stream/profile_1"
    assert (await driver.read("snapshot_uri")).value == "http://camera.local/snapshot/profile_1.jpg"
    identity = await driver.identify()
    assert (identity["firmware"], identity["serial"], identity["profile"]) == ("2.4.1", "SIM0001", "profile_1")
    assert camera.operations()[:4] == ["GetSystemDateAndTime", "GetDeviceInformation", "GetCapabilities", "GetProfiles"]
    await driver.close()


async def test_profiles_are_chosen_by_token_or_name(camera: OnvifCameraSim) -> None:
    channels = "read:\n  profile: { type: string }\n  stream_uri: { type: string }"
    driver = await connected(device_file(channels=channels, extra=", profile: SubStream"), camera)
    assert (await driver.read("profile")).value == "SubStream"
    assert (await driver.read("stream_uri")).value == "rtsp://camera.local:554/stream/profile_2"
    await driver.close()
    with pytest.raises(DriverError, match=r"has no profile .Night.\. It has profile_1, profile_2"):
        await connected(device_file(channels=channels, extra=", profile: Night"), camera)
    with pytest.raises(DriverError, match="has no PTZ"):
        await connected(device_file(extra=", profile: profile_2"), camera)


async def test_a_camera_clock_far_ahead_still_authenticates(camera: OnvifCameraSim) -> None:
    camera.clock_skew = dt.timedelta(hours=3)
    driver = await connected(device_file(), camera)
    assert (await driver.read("model")).value == "PTZ-1"
    await driver.close()


async def test_credentials_are_checked(camera: OnvifCameraSim) -> None:
    with pytest.raises(DriverError, match="did not accept the credentials for GetDeviceInformation"):
        await connected(device_file(), camera, environ=lambda name: "wrong")
    with pytest.raises(DriverError, match=TOKEN_ENV):
        await connected(device_file(), camera, environ=lambda name: None)
    with pytest.raises(DriverError, match="username needs token_env"):
        await connected(bare("read:\n  model: { type: string }", "{ onvif: camera.local, username: admin }"), camera)


async def test_position_reads_are_scaled(camera: OnvifCameraSim) -> None:
    camera.pan, camera.tilt, camera.zoom = 0.25, -0.1, 0.5
    driver = await connected(device_file(), camera)
    pan = await driver.read("pan")
    assert pan.value == pytest.approx(42.5)
    assert pan.unit == "degree"
    assert (await driver.read("tilt")).value == pytest.approx(-0.1)
    assert (await driver.read("zoom")).value == pytest.approx(0.5)
    assert (await driver.read("moving")).value is False
    await driver.close()


async def test_axis_changes_use_absolute_moves(camera: OnvifCameraSim) -> None:
    camera.tilt = 0.2
    driver = await connected(device_file(), camera)
    kernel = await kernel_for(driver)
    decision = await kernel.execute(Write(device="conformance-onvif", channel="pan", value="45 degree"), WHO)
    assert decision.status == "done", decision.message
    assert camera.pan == pytest.approx(45 / 170, abs=1e-4)
    assert camera.tilt == pytest.approx(0.2)
    decision = await kernel.execute(Write(device="conformance-onvif", channel="zoom", value="0.4 dimensionless"), WHO)
    assert decision.status == "done", decision.message
    move = [body for name, body in camera.calls if name == "AbsoluteMove"][-1]
    assert soap.find(move, "PanTilt") is None
    assert soap.attribute(soap.find(move, "Zoom"), "x") == pytest.approx(0.4)
    assert (await driver.read("pan")).value == pytest.approx(45.0, abs=0.02)
    await driver.close()


async def test_actions_move_presets_home_and_stop(camera: OnvifCameraSim) -> None:
    driver = await connected(device_file(), camera)
    kernel = await kernel_for(driver)
    args = {"pan": "0.5 dimensionless", "tilt": "0 dimensionless", "duration": "0.3 s"}
    decision = await kernel.execute(Action(device="conformance-onvif", action="move", args=args), WHO)
    assert decision.status == "done", decision.message
    move = [body for name, body in camera.calls if name == "ContinuousMove"][-1]
    assert soap.text(move, "Timeout") == "PT0.3S"
    assert (await driver.read("moving")).value is True
    await asyncio.sleep(0.4)
    assert (await driver.read("moving")).value is False
    assert camera.pan == pytest.approx(0.075, abs=0.02)
    decision = await kernel.execute(Action(device="conformance-onvif", action="goto_preset", args={"preset": "2"}), WHO)
    assert decision.status == "done", decision.message
    assert (camera.pan, camera.tilt, camera.zoom) == (0.6, -0.2, 0.3)
    for name in ("home", "stop"):
        decision = await kernel.execute(Action(device="conformance-onvif", action=name), WHO)
        assert decision.status == "done", decision.message
    assert (camera.pan, camera.tilt, camera.zoom) == (0.0, 0.0, 0.0)
    assert camera.operations()[-1] == "Stop"
    await driver.close()


async def test_relative_and_partial_absolute_moves(camera: OnvifCameraSim) -> None:
    channels = (
        "actions:\n  step: { args: { pan: { unit: dimensionless, min: -0.2, max: 0.2 } } }\n"
        "  aim: { args: { tilt: { unit: dimensionless, min: -1, max: 1 } }, map: { operation: go_to } }\n"
        "  goto_preset: { args: { preset: { type: enum, values: ['1', '9'] } } }"
    )
    camera.pan = 0.3
    driver = await connected(
        bare(channels, f"{{ onvif: camera.local, username: admin, token_env: {TOKEN_ENV} }}"), camera
    )
    kernel = await kernel_for(driver)
    decision = await kernel.execute(Action(device="t", action="step", args={"pan": "0.1 dimensionless"}), WHO)
    assert decision.status == "done", decision.message
    assert camera.pan == pytest.approx(0.4)
    decision = await kernel.execute(Action(device="t", action="aim", args={"tilt": "0.5 dimensionless"}), WHO)
    assert decision.status == "done", decision.message
    assert (camera.pan, camera.tilt) == (pytest.approx(0.4), pytest.approx(0.5))
    decision = await kernel.execute(Action(device="t", action="goto_preset", args={"preset": "9"}), WHO)
    assert decision.status == "failed"
    assert "NoToken" in decision.message
    await driver.close()


async def test_stop_is_the_native_safe_state(camera: OnvifCameraSim) -> None:
    driver = await connected(device_file(), camera)
    kernel = await kernel_for(driver)
    report = await kernel.stop_all(WHO, "test")
    assert report.devices[0].status == "safe"
    stop = [body for name, body in camera.calls if name == "Stop"][-1]
    assert (soap.text(stop, "PanTilt"), soap.text(stop, "Zoom")) == ("true", "true")
    await driver.close()


async def test_faults_junk_and_timeouts(camera: OnvifCameraSim) -> None:
    driver = await connected(device_file(timeout="200 ms"), camera)
    camera.fault_next = "Motor jammed"
    with pytest.raises(DriverError, match="returned an error for GetStatus \\(ter:Action: Motor jammed\\)"):
        await driver.read("pan")
    camera.garbage = True
    with pytest.raises(DriverError, match="isn't SOAP"):
        await driver.read("pan")
    camera.garbage = False
    camera.latency_s = 1.5
    with pytest.raises(TimeoutError, match="sent no reply to GetStatus"):
        await driver.read("pan")
    camera.latency_s = 0.0
    camera.offline = True
    with pytest.raises(DriverError, match="Could not reach"):
        await driver.read("pan")
    health = await driver.health()
    assert not health.connected
    camera.offline = False
    assert (await driver.health()).connected
    await driver.close()
    with pytest.raises(DriverError, match="not connected"):
        await driver.read("model")
    assert not (await driver.health()).connected


async def test_an_unreachable_camera_fails_to_connect(camera: OnvifCameraSim) -> None:
    camera.offline = True
    driver = OnvifDriver(device_file(), transport=camera.transport(), environ=environ)
    with pytest.raises(DriverError, match=r"Could not reach ONVIF camera camera\.local for GetSystemDateAndTime"):
        await driver.connect()
    assert not (await driver.health()).connected


async def test_describe_proposes_ptz_channels_and_presets(camera: OnvifCameraSim) -> None:
    driver = await connected(device_file(), camera)
    proposal = await driver.describe()
    assert proposal is not None
    assert proposal["write"]["zoom"] == {"unit": "dimensionless", "min": 0, "max": 1, "suggested": True}
    assert proposal["actions"]["goto_preset"]["args"]["preset"]["values"] == ["1", "2"]
    assert proposal["device"]["manufacturer"] == "OpenHAL simulator"
    await driver.close()
    assert await driver.describe() is None


@pytest.mark.parametrize("path", sorted(EXAMPLES.glob("*.hal.yaml")), ids=lambda path: path.name)
def test_examples_validate_and_load_read_only(path: Path) -> None:
    report = validate_path(path)
    assert report.ok, report.problems
    assert report.file is not None
    assert not report.file.writable
    OnvifDriver(report.file)
