"""The http driver against the simulated smart plug (httpx.MockTransport, no network)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
import pytest

from openhal.drivers.base import DriverError
from openhal.drivers.http.conformance import FILE
from openhal.drivers.http.driver import HttpDriver
from openhal.drivers.http.openapi import describe_openapi
from openhal.drivers.http.simulator import OPENAPI, TINY_JPEG, SimulatedPlug
from openhal.drivers.http.values import parse_path, render
from openhal.kernel import Kernel
from openhal.kernel.commands import Action, Write
from openhal.kernel.principals import human
from openhal.spec import loads, validate_path
from openhal.spec.models import DeviceFile

EXAMPLES = Path(__file__).parents[3] / "openhal" / "drivers" / "http" / "examples"
WHO = human("tester")


def make(text: str | None = None, plug: SimulatedPlug | None = None, **kwargs: Any) -> tuple[HttpDriver, SimulatedPlug]:
    plug = plug or SimulatedPlug()
    file = FILE if text is None else loads(text)
    return HttpDriver(file, transport=plug.transport(), **kwargs), plug


async def kernel_for(driver: HttpDriver) -> Kernel:
    kernel = Kernel()
    kernel.register(driver.device, driver)
    await kernel.connect(driver.device.device_id)
    return kernel


def device(connect: str, read: str = "", write: str = "", extra: str = "") -> str:
    text = f"device: Test\nid: test\nconnect: {connect}\n"
    if read:
        text += f"read:\n{read}\n"
    if write:
        text += f"write:\n{write}\n"
    return text + extra + "hazard: low\nconfirmed: { by: tester, at: 2026-10-24 }\n"


BASE = '{ http: "http://plug.local" }'


# ---------------------------------------------------------------------- parameters and maps


@pytest.mark.parametrize(
    ("connect", "message"),
    [
        ('{ http: "ftp://plug.local" }', "http:// or https://"),
        ('{ http: "http://user:pw@plug.local" }', "credentials"),
        ('{ http: "http://plug.local", headers: { X-Api-Key: abc } }', "credential"),
        ('{ http: "http://plug.local", token_env: "lower" }', "pattern"),
        ('{ http: "http://plug.local", health: "status" }', "start with /"),
        ('{ http: "http://plug.local", timeout: 0 s }', "greater than 0"),
        ('{ http: "http://plug.local", colour: blue }', "Extra inputs"),
    ],
)
def test_bad_params_are_rejected(connect: str, message: str) -> None:
    file = loads(device(connect, read="  x: { unit: W, map: { path: /x } }"))
    with pytest.raises(ValueError, match=message):
        HttpDriver(file)


@pytest.mark.parametrize(
    ("read", "write", "extra", "message"),
    [
        ("  x: { unit: W }", "", "", "needs a map"),
        ("  x: { unit: W, map: { path: x } }", "", "", "start"),
        ("  x: { unit: W, map: { path: /x, json: 'a..b' } }", "", "", "invalid key"),
        ("  x: { unit: W, map: { path: /x, json: 'a[x]' } }", "", "", "brackets"),
        ("  x: { unit: W, map: { path: /x, scale: 0 } }", "", "", "zero"),
        ("  x: { unit: W, map: { path: /x, verb: GET } }", "", "", "Extra inputs"),
        ("", "  y: { type: bool, map: { path: /y, body: { v: '{speed}' } } }", "", "Only {value}"),
        (
            "",
            "",
            "actions:\n  go: { args: { n: { unit: s, min: 0, max: 1 } }, map: { path: '/go/{m}' } }\n",
            "not its args",
        ),
    ],
)
def test_bad_maps_are_rejected(read: str, write: str, extra: str, message: str) -> None:
    file = loads(device(BASE, read=read, write=write, extra=extra))
    with pytest.raises(DriverError, match=message):
        HttpDriver(file)


def test_json_paths_and_templates() -> None:
    assert parse_path("$.relays[0].on") == ("relays", 0, "on")
    assert parse_path("temp.c") == ("temp", "c")
    assert parse_path("$['odd key']") == ("odd key",)
    assert parse_path("[2]") == (2,)
    with pytest.raises(ValueError, match="unclosed"):
        parse_path("a[1")
    assert render({"on": "{value}", "note": "set to {value}"}, {"value": True}) == {"on": True, "note": "set to true"}
    assert render(["{value}", 3], {"value": 2.0}) == [2.0, 3]


# ---------------------------------------------------------------------- reads


async def test_reads_every_channel_type() -> None:
    driver, plug = make()
    plug.relay, plug.dimmer, plug.mode = True, 255, "eco"
    await driver.connect()
    power = await driver.read("power")
    assert power.value == pytest.approx(63.2)
    assert power.unit == "W"
    assert (await driver.read("label")).value == "bench plug"
    assert (await driver.read("snapshot")).value == TINY_JPEG
    assert (await driver.read("relay")).value is True
    assert (await driver.read("level")).value == 255
    assert (await driver.read("mode")).value == "eco"
    await driver.close()


async def test_text_format_scale_offset_and_range() -> None:
    text = device(
        BASE,
        read=(
            "  watts: { unit: kW, range: [0, 0.01], map: { path: /api/power.txt, scale: 0.001 } }\n"
            "  shifted: { unit: W, map: { path: /api/status, json: power.w, offset: 100 } }"
        ),
    )
    driver, _ = make(text)
    await driver.connect()
    watts = await driver.read("watts")
    assert watts.value == pytest.approx(0.0032)
    assert watts.suspect is False
    assert (await driver.read("shifted")).value == pytest.approx(103.2)
    await driver.close()


async def test_out_of_range_reading_is_suspect() -> None:
    text = device(BASE, read="  power: { unit: W, range: [10, 20], map: { path: /api/status, json: power.w } }")
    driver, _ = make(text)
    await driver.connect()
    assert (await driver.read("power")).suspect is True


async def test_bool_words_and_enum_checks() -> None:
    text = device(
        BASE,
        read=(
            "  mode_is_auto: { type: bool, map: { path: /api/mode, on: auto, off: [manual, eco] } }\n"
            "  mode: { type: enum, values: [auto, manual], map: { path: /api/mode } }\n"
            "  label_flag: { type: bool, map: { path: /api/status, json: label } }"
        ),
    )
    driver, plug = make(text)
    await driver.connect()
    assert (await driver.read("mode_is_auto")).value is True
    plug.mode = "eco"
    assert (await driver.read("mode_is_auto")).value is False
    with pytest.raises(DriverError, match="not one of auto, manual"):
        await driver.read("mode")
    with pytest.raises(DriverError, match="neither an on word"):
        await driver.read("label_flag")


async def test_write_channel_without_state_reports_last_value() -> None:
    text = device(BASE, write="  relay: { type: bool, map: { path: /api/relay, body: { on: '{value}' } } }")
    driver, plug = make(text)
    kernel = await kernel_for(driver)
    assert (await driver.read("relay")).value is None
    decision = await kernel.execute(Write(device="test", channel="relay", value=True), WHO)
    assert decision.status == "done"
    assert plug.relay is True
    assert (await driver.read("relay")).value is True


async def test_malformed_and_missing_values_raise() -> None:
    driver, plug = make()
    await driver.connect()
    plug.malformed = True
    with pytest.raises(DriverError, match="expected JSON"):
        await driver.read("power")
    plug.malformed = False
    text = device(BASE, read="  ghost: { unit: W, map: { path: /api/status, json: power.kw } }")
    other, _ = make(text, plug=plug)
    await other.connect()
    with pytest.raises(DriverError, match=r"no field \$\.power\.kw"):
        await other.read("ghost")
    text = device(BASE, read="  first: { unit: W, map: { path: /api/status, json: 'label[3]' } }")
    indexed, _ = make(text, plug=plug)
    await indexed.connect()
    with pytest.raises(DriverError, match="no item"):
        await indexed.read("first")
    text = device(BASE, read="  word: { unit: W, map: { path: /api/status, json: label } }")
    wordy, _ = make(text, plug=plug)
    await wordy.connect()
    with pytest.raises(DriverError, match="not a number"):
        await wordy.read("word")


async def test_unknown_channel_and_not_connected() -> None:
    driver, _ = make()
    with pytest.raises(DriverError, match="not connected"):
        await driver.read("power")
    await driver.connect()
    with pytest.raises(DriverError, match="no channel"):
        await driver.read("nope")


# ---------------------------------------------------------------------- writes and actions


async def test_writes_through_the_kernel_send_the_mapped_requests() -> None:
    driver, plug = make()
    kernel = await kernel_for(driver)
    for channel, value in (("relay", True), ("level", "128 dimensionless"), ("mode", "eco")):
        decision = await kernel.execute(Write(device="conformance-plug", channel=channel, value=value), WHO)
        assert decision.status == "done", decision.message
    assert (plug.relay, plug.dimmer, plug.mode) == (True, 128, "eco")
    sent = [entry for entry in plug.log if entry[0] in ("POST", "PUT") or entry[1] == "/api/mode"]
    assert ("POST", "/api/relay", {"on": True}) in sent
    assert ("PUT", "/api/dimmer", {"level": 128}) in sent
    assert ("GET", "/api/mode", {"set": "eco"}) in sent


async def test_on_off_words_scale_and_path_quoting() -> None:
    text = device(
        BASE,
        write=(
            "  relay: { type: bool, map: { path: /api/relay, body: { on: '{value}' }, on: true, off: false } }\n"
            "  level: { unit: percent, min: 0, max: 100, map: { path: /api/dimmer, method: PUT,"
            " body: { level: '{value}' }, scale: 0.4 } }\n"
            "  label: { type: string, max_length: 20, map: { path: '/api/label/{value}', method: POST } }"
        ),
    )
    driver, plug = make(text)
    kernel = await kernel_for(driver)
    await kernel.execute(Write(device="test", channel="level", value="40 %"), WHO)
    assert plug.dimmer == 100
    decision = await kernel.execute(Write(device="test", channel="label", value="a b/c"), WHO)
    assert decision.status == "failed"
    assert ("POST", "/api/label/a%20b%2Fc", {}) in plug.log


async def test_write_errors_fail_the_command() -> None:
    driver, plug = make()
    kernel = await kernel_for(driver)
    plug.status_override = 500
    decision = await kernel.execute(Write(device="conformance-plug", channel="relay", value=True), WHO)
    assert decision.status == "failed"
    assert "500" in decision.message
    plug.status_override = None
    plug.online = False
    decision = await kernel.execute(Write(device="conformance-plug", channel="relay", value=True), WHO)
    assert decision.status == "failed"
    assert "reachable" in decision.message


async def test_actions_render_args_and_return_results() -> None:
    text = device(
        BASE,
        extra=(
            "actions:\n"
            "  reboot: { args: { delay_s: { unit: s, min: 0, max: 10 } },"
            " map: { path: /api/reboot, body: { delay_s: '{delay_s}' }, json: delay_s } }\n"
            "  ping: { map: { path: /api/reboot } }\n"
            "  missing: { map: { path: /api/missing } }\n"
        ),
    )
    driver, plug = make(text)
    kernel = await kernel_for(driver)
    decision = await kernel.execute(Action(device="test", action="reboot", args={"delay_s": "2 s"}), WHO)
    assert decision.status == "done", decision.message
    assert plug.reboots == 1
    assert ("POST", "/api/reboot", {"delay_s": 2.0}) in plug.log
    decision = await kernel.execute(Action(device="test", action="ping"), WHO)
    assert decision.status == "done"
    decision = await kernel.execute(Action(device="test", action="missing"), WHO)
    assert decision.status == "failed"
    assert "404" in decision.message


# ---------------------------------------------------------------------- connection, timeouts, auth


async def test_connect_fails_cleanly_when_offline() -> None:
    plug = SimulatedPlug(online=False)
    driver, _ = make(plug=plug)
    with pytest.raises(DriverError, match="reachable"):
        await driver.connect()
    assert (await driver.health()).connected is False


async def test_health_tracks_the_device() -> None:
    driver, plug = make()
    await driver.connect()
    health = await driver.health()
    assert health.connected
    assert health.latency_ms is not None
    plug.online = False
    assert (await driver.health()).connected is False
    plug.online = True
    await driver.close()
    assert (await driver.health()).connected is False


async def test_slow_device_times_out() -> None:
    text = device(
        '{ http: "http://plug.local", timeout: 0.2 s }',
        read="  power: { unit: W, map: { path: /api/status, json: power.w } }",
    )
    driver, plug = make(text)
    await driver.connect()
    plug.delay_s = 1.0
    with pytest.raises(TimeoutError, match=r"no answer within 0\.2 s"):
        await driver.read("power")


async def test_httpx_timeouts_become_timeout_errors() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    file = loads(device(BASE, read="  power: { unit: W, map: { path: /x } }"))
    driver = HttpDriver(file, transport=httpx.MockTransport(handler))
    with pytest.raises(TimeoutError):
        await driver.connect()


async def test_token_comes_from_the_environment() -> None:
    connect = '{ http: "http://plug.local", token_env: PLUG_TOKEN }'
    text = device(connect, read="  power: { unit: W, map: { path: /api/status, json: power.w } }")
    plug = SimulatedPlug(require_token="s3cret")
    missing, _ = make(text, plug=plug, environ=lambda name: None)
    with pytest.raises(DriverError, match="PLUG_TOKEN is not set"):
        await missing.connect()
    wrong, _ = make(text, plug=plug, environ=lambda name: "nope")
    await wrong.connect()
    with pytest.raises(DriverError, match="401"):
        await wrong.read("power")
    right, _ = make(text, plug=plug, environ=lambda name: "s3cret")
    await right.connect()
    assert (await right.read("power")).value == pytest.approx(3.2)


async def test_oversized_responses_are_refused() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"1" * 5000)

    connect = '{ http: "http://plug.local", max_response_bytes: 1024 }'
    file = loads(device(connect, read="  power: { unit: W, map: { path: /x } }"))
    driver = HttpDriver(file, transport=httpx.MockTransport(handler))
    with pytest.raises(DriverError, match="max_response_bytes"):
        await driver.connect()


# ---------------------------------------------------------------------- identify and describe


async def test_identify_with_and_without_a_path() -> None:
    driver, _ = make()
    identity = await driver.identify()
    assert identity["model"] == "SIM-PLUG"
    plain, _ = make(device(BASE, read="  power: { unit: W, map: { path: /x } }"))
    assert await plain.identify() == {"base_url": "http://plug.local"}
    assert await plain.describe() is None
    assert await HttpDriver.discover() == []


async def test_describe_proposes_loadable_sections() -> None:
    driver, _ = make()
    await driver.connect()
    described = await driver.describe()
    assert described is not None
    assert described["read"]["api_status_power_w"] == {"unit": "W", "map": {"path": "/api/status", "json": "$.power.w"}}
    assert described["read"]["api_status_mode"]["type"] == "enum"
    level = described["write"]["set_api_dimmer_level"]
    assert level["suggested"] is True
    assert (level["min"], level["max"], level["step"]) == (0, 255, 1)
    assert described["write"]["set_api_relay_on"]["type"] == "bool"
    assert described["actions"]["api_reboot"]["suggested"] is True
    assert "path parameters" in described["notes"]
    file = DeviceFile.model_validate(
        {
            "device": described["device"],
            "connect": {"http": "http://plug.local"},
            "read": described["read"],
            "write": described["write"],
            "actions": described["actions"],
            "notes": described["notes"],
        }
    )
    assert not file.writable
    HttpDriver(file, transport=SimulatedPlug().transport())


def body(properties: dict[str, Any]) -> dict[str, Any]:
    return {"content": {"application/json": {"schema": {"properties": properties}}}}


def test_describe_tolerates_odd_documents() -> None:
    assert "not an OpenAPI 3" in describe_openapi({"swagger": "2.0"})["notes"]
    assert "not an OpenAPI 3" in describe_openapi([1, 2])["notes"]
    odd = {
        "openapi": "3.0.3",
        "paths": {
            "/loop": {"get": {"responses": {"200": {"content": {"application/json": {"schema": {"$ref": "#/a"}}}}}}},
            "/remote": {"get": {"responses": {"200": {"$ref": "https://example.com/x"}}}},
            "/text": {
                "post": {
                    "requestBody": {
                        "content": {"application/json": {"schema": {"properties": {"s": {"type": "string"}}}}}
                    }
                }
            },
            "/n": {
                "put": {
                    "requestBody": {
                        "content": {"application/json": {"schema": {"properties": {"n": {"type": "number"}}}}}
                    }
                }
            },
        },
        "components": {},
    }
    described = describe_openapi(odd)
    assert "write" not in described
    assert "without maxLength" in described["notes"]
    assert "no minimum and maximum" in described["notes"]
    assert describe_openapi(OPENAPI, limit=1)["read"].keys() == {"api_status_relay_on"}


# ---------------------------------------------------------------------- examples


@pytest.mark.parametrize("path", sorted(EXAMPLES.glob("*.hal.yaml")), ids=lambda path: path.name)
def test_examples_validate_and_load(path: Path) -> None:
    report = validate_path(path)
    assert report.ok, report.problems
    assert report.file is not None
    HttpDriver(report.file)
