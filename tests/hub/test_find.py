"""`find` searches every device by text, unit, kind, hazard and connection, with no device id in advance."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest

from openhal.hub.api import create_app
from openhal.hub.config import HubConfig
from openhal.hub.find import FindError, converts, find, measures
from openhal.hub.hub import Hub
from openhal.kernel.principals import human
from openhal.spec import loads
from tests.kernel.conftest import FAN, HEATER, FakeClock

LAMP = """
device: Reading lamp
id: lamp
manufacturer: Acme
connect: { mock: lamp, initial: { brightness: 40, mode: warm } }
read:
  ambient: { unit: lux }
write:
  brightness: { unit: "%", min: 0, max: 100 }
  on: { type: bool }
  mode: { type: enum, values: [warm, cold] }
actions:
  flash:
    description: Flash the lamp once
    args:
      length: { unit: ms, min: 10, max: 500 }
safe_state: { on: false }
hazard: low
confirmed: { by: tester, at: 2026-10-24 }
"""

OVEN = """
device: Reflow oven
id: oven
connect: { mock: oven }
read:
  chamber: { unit: degF }
write:
  power: { unit: W, min: 0, max: 800 }
safe_state: { power: 0 }
hazard: high
confirmed: { by: tester, at: 2026-10-24 }
"""


@pytest.fixture
async def hub(tmp_path: Path) -> AsyncIterator[Hub]:
    clock = FakeClock()
    hub = Hub(HubConfig(home=tmp_path), clock=clock, in_memory=True)
    for text in (FAN, HEATER, LAMP, OVEN):
        hub.add_device(loads(text))
    await hub.start(load_devices=False)
    clock.advance(60)
    yield hub
    await hub.close()


def targets(result: dict[str, object]) -> list[str]:
    matches = result["matches"]
    assert isinstance(matches, list)
    return [entry["target"] for entry in matches]


async def test_text_finds_anything_that_measures_temperature(hub: Hub) -> None:
    found = find(hub, text="anything that measures temperature")
    assert set(targets(found)) == {"desk-fan.temperature", "heater.temp", "oven.chamber"}
    assert all(entry["matched"] == ["temperature"] for entry in found["matches"])  # type: ignore[union-attr]


async def test_a_unit_matches_every_channel_it_converts_to(hub: Hub) -> None:
    assert set(targets(find(hub, unit="degC"))) == {"desk-fan.temperature", "heater.temp", "oven.chamber"}
    writable_percent = find(hub, kind="writable", unit="%")
    assert targets(writable_percent) == ["desk-fan.fan_speed", "lamp.brightness"]
    assert targets(find(hub, kind="action", unit="s")) == ["heater.pulse", "lamp.flash"]
    assert targets(find(hub, unit="W", hazard="high")) == ["oven.power"]


async def test_readable_includes_write_channels_and_entries_carry_their_limits(hub: Hub) -> None:
    readable = targets(find(hub, kind="readable", text="lamp"))
    assert readable == ["lamp.ambient", "lamp.brightness", "lamp.mode", "lamp.on"]
    brightness = find(hub, text="brightness")["matches"][0]  # type: ignore[index]
    assert brightness["kind"] == "writable"
    assert (brightness["min"], brightness["max"], brightness["unit"]) == (0.0, 100.0, "%")
    assert brightness["known"] is True
    assert brightness["takes_commands"] is True
    flash = find(hub, kind="action", text="flash once")["matches"][0]  # type: ignore[index]
    assert flash["args"] == {"length": {"type": "number", "unit": "ms", "min": 10.0, "max": 500.0}}
    assert flash["description"] == "Flash the lamp once"
    oven = find(hub, text="oven power")["matches"][0]  # type: ignore[index]
    assert (oven["target"], oven["confirm"], oven["matched"]) == ("oven.power", "confirm-each-time", ["oven", "power"])


async def test_best_matches_come_first_and_filters_combine(hub: Hub) -> None:
    ranked = targets(find(hub, text="heater power"))
    assert ranked[0] == "heater.power"
    assert "oven.power" in ranked
    either = find(hub, text="acme warm")["matches"]
    assert [entry["target"] for entry in either][:1] == ["lamp.mode"]  # type: ignore[index]
    assert either[0]["matched"] == ["acme", "warm"]  # type: ignore[index]
    assert {entry["device"] for entry in either} == {"lamp"}  # type: ignore[union-attr]
    assert find(hub, hazard="medium")["count"] == 7
    assert find(hub, connected=False)["count"] == 0
    hub.kernel.devices["oven"].connected = False
    assert {entry["device"] for entry in find(hub, connected=False)["matches"]} == {"oven"}  # type: ignore[union-attr]
    assert find(hub, limit=2)["count"] == 16
    assert len(find(hub, limit=2)["matches"]) == 2  # type: ignore[arg-type]


async def test_an_unknown_unit_is_an_error_and_no_driver_is_read(hub: Hub) -> None:
    with pytest.raises(FindError, match="not a unit"):
        find(hub, unit="furlongs per fortnight per bogon")
    before = hub.kernel.devices["lamp"].driver.reads  # type: ignore[attr-defined]
    find(hub, text="lamp")
    assert hub.kernel.devices["lamp"].driver.reads == before  # type: ignore[attr-defined]
    assert hub.audit.entries(event="read") == []


async def test_after_a_stop_nothing_takes_commands(hub: Hub) -> None:
    await hub.kernel.stop_all(human(), "test")
    assert not any(entry["takes_commands"] for entry in find(hub)["matches"])  # type: ignore[union-attr]


def test_units_name_what_they_measure() -> None:
    assert measures("degC") == ("temperature",)
    assert "power" in measures("W")
    assert measures("%") == ()
    assert measures(None) == ()
    assert measures("not a unit at all") == ()
    assert converts("degF", "degC")
    assert not converts("%", "deg")
    assert not converts("s", None)


async def test_the_route_returns_matches_and_a_bad_unit_is_400(hub: Hub) -> None:
    token = hub.tokens.create("viewer", "agent", "read")[0]
    transport = httpx.ASGITransport(app=create_app(hub), client=("127.0.0.1", 50000))
    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:7420", headers=headers) as client:
        found = (await client.get("/v1/find", params={"kind": "writable", "unit": "%"})).json()
        assert [entry["target"] for entry in found["matches"]] == ["desk-fan.fan_speed", "lamp.brightness"]
        bad = await client.get("/v1/find", params={"unit": "bogons"})
        assert bad.status_code == 400
        assert "not a unit" in bad.json()["detail"]
        assert (await client.get("/v1/find", params={"kind": "sideways"})).status_code == 422
