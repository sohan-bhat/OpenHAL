"""The PyLabRobot driver, against PyLabRobot's own LiquidHandler on the recording chatterbox backend."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from openhal.drivers.base import DriverError
from openhal.drivers.pylabrobot.driver import PyLabRobotDriver
from openhal.drivers.pylabrobot.simulator import RecordingBackend
from openhal.spec import load, loads
from tests.drivers.serial.kit import Bench, assert_done, assert_failed, eventually

TIPS = "^tips:[A-H]([1-9]|1[0-2])(:[A-H]([1-9]|1[0-2]))?$"
WELLS = "^plate:[A-H]([1-9]|1[0-2])(:[A-H]([1-9]|1[0-2]))?$"
ROBOT = f"""
device: Test liquid handler
id: lh
connect:
  pylabrobot: chatterbox
  num_channels: 8
  action_wait: 2 s
  volumes: {{ "plate:A1": 200 uL, "plate:H12": 0.1 mL }}
  layout:
    - {{ name: tips, resource: hamilton_96_tiprack_1000uL_filter, rails: 3 }}
    - {{ name: plate, resource: cor_96_wellplate_360uL_Fb, rails: 9 }}
read:
  initialized: {{ type: bool }}
  tips_mounted: {{ unit: dimensionless }}
  channels: {{ unit: dimensionless }}
  first_tip: {{ type: bool, map: {{ channel: 0 }} }}
  a1_volume: {{ unit: uL, map: {{ container: "plate:A1" }} }}
  a2_volume: {{ unit: mL, map: {{ container: "plate:A2" }} }}
actions:
  initialize: {{}}
  pick_up_tips: {{ args: {{ tips: {{ type: string, max_length: 20, pattern: "{TIPS}" }} }} }}
  drop_tips: {{ args: {{ tips: {{ type: string, max_length: 20, pattern: "{TIPS}" }} }} }}
  return_tips: {{}}
  discard_tips: {{}}
  aspirate:
    args:
      well: {{ type: string, max_length: 20, pattern: "{WELLS}" }}
      volume: {{ unit: uL, min: 0, max: 300 }}
  dispense:
    args:
      well: {{ type: string, max_length: 20, pattern: "{WELLS}" }}
      volume: {{ unit: uL, min: 0, max: 300 }}
  transfer:
    args:
      source: {{ type: enum, values: ["plate:A1"] }}
      target: {{ type: enum, values: ["plate:A3"] }}
      volume: {{ unit: mL, min: 0, max: 0.3 }}
hazard: high
confirmed: {{ by: tester, at: 2026-10-24 }}
"""


def make(
    text: str = ROBOT, backend: RecordingBackend | None = None
) -> tuple[PyLabRobotDriver, RecordingBackend, Bench]:
    recorder = backend or RecordingBackend(num_channels=8)
    file = loads(text)
    driver = PyLabRobotDriver(file, backend=recorder)
    return driver, recorder, Bench(file, driver)


async def test_connect_builds_the_deck_without_moving_the_robot() -> None:
    driver, backend, bench = make()
    await bench.connect()
    assert backend.operations == []
    assert (await bench.read("initialized")).value is False
    assert (await bench.read("channels")).value == 8.0
    identity = await driver.identify()
    assert identity["resources"].split(", ")[-2:] == ["tips", "waste_block"] or "plate" in identity["resources"]
    assert "not initialized" in (await driver.health()).detail
    assert_failed(await bench.act("pick_up_tips", tips="tips:A1"), "isn't initialized")
    await bench.close()


async def test_initialize_then_tips_aspirate_and_dispense() -> None:
    _driver, backend, bench = make()
    await bench.connect()
    assert_done(await bench.act("initialize"))
    assert (await bench.read("initialized")).value is True
    assert_done(await bench.act("pick_up_tips", tips="tips:A1:H1"))
    assert backend.operations[-1][0] == "pick_up_tips"
    assert len(backend.operations[-1][1]) == 8
    assert (await bench.read("tips_mounted")).value == 8.0
    assert (await bench.read("first_tip")).value is True
    assert_done(await bench.act("drop_tips", tips="tips:A1:H1"))
    assert_done(await bench.act("pick_up_tips", tips="tips:A1"))
    assert (await bench.read("a1_volume")).value == pytest.approx(200.0)
    assert_done(await bench.act("aspirate", well="plate:A1", volume="50 uL"))
    assert (await bench.read("a1_volume")).value == pytest.approx(150.0)
    assert_done(await bench.act("dispense", well="plate:A2", volume="50 uL"))
    assert (await bench.read("a2_volume")).value == pytest.approx(0.05)
    assert_done(await bench.act("transfer", source="plate:A1", target="plate:A3", volume="0.1 mL"))
    assert backend.operations[-2:][0][2] == [pytest.approx(100.0)]
    assert_done(await bench.act("return_tips"))
    assert (await bench.read("tips_mounted")).value == 0.0
    await bench.close()


async def test_pylabrobot_refusals_fail_before_anything_moves() -> None:
    _driver, backend, bench = make()
    await bench.connect()
    assert_done(await bench.act("initialize"))
    assert_failed(await bench.act("aspirate", well="plate:B1", volume="10 uL"), "refused aspirate")
    assert_done(await bench.act("pick_up_tips", tips="tips:A1"))
    count = len(backend.operations)
    assert_failed(await bench.act("aspirate", well="plate:B1", volume="10 uL"), "TooLittleLiquidError")
    assert_failed(await bench.act("pick_up_tips", tips="tips:B1"), "refused pick_up_tips")
    assert len(backend.operations) == count
    assert_failed(await bench.act("aspirate", well="plate:A1:B1", volume="10 uL"), "refused aspirate")
    assert_done(await bench.act("discard_tips"))
    await bench.close()


async def test_blocked_volume_never_reaches_pylabrobot() -> None:
    _driver, backend, bench = make()
    await bench.connect()
    assert_done(await bench.act("initialize"))
    decision = await bench.act("aspirate", well="plate:A1", volume="500 uL")
    assert decision.status == "blocked"
    decision = await bench.act("aspirate", well="plate:Z1", volume="10 uL")
    assert decision.status == "blocked"
    assert backend.names() == ["setup"]
    await bench.close()


async def test_firmware_error_fails_the_action() -> None:
    driver, backend, bench = make()
    await bench.connect()
    assert_done(await bench.act("initialize"))
    backend.fail_next = 1
    assert_failed(await bench.act("pick_up_tips", tips="tips:A1"), "simulated firmware error")
    assert (await bench.read("tips_mounted")).suspect
    assert driver.uncertain == "pick_up_tips failed while it ran"
    assert_done(await bench.act("initialize"))
    assert not (await bench.read("tips_mounted")).suspect
    await bench.close()


async def test_slow_operation_returns_started_and_stop_cancels_it() -> None:
    text = ROBOT.replace("action_wait: 2 s", "action_wait: 200 ms")
    driver, backend, bench = make(text)
    await bench.connect()
    assert_done(await bench.act("initialize"))
    backend.latency_s = 5.0
    assert_done(await bench.act("pick_up_tips", tips="tips:A1"))
    assert "1 operations running" in (await driver.health()).detail
    assert await bench.stop() == "safe"
    assert backend.names() == ["setup"]
    await eventually(lambda: asyncio.sleep(0, not driver._running))
    await bench.close()


async def test_lost_instrument_and_reconnect() -> None:
    driver, backend, bench = make()
    await bench.connect()
    backend.lost = True
    assert not (await driver.health()).connected
    assert_failed(await bench.act("initialize"), "doesn't answer")
    fresh = RecordingBackend(num_channels=8)
    driver._injected = fresh
    await bench.connect()
    assert (await driver.health()).connected
    await bench.close()


async def test_setup_on_connect() -> None:
    text = ROBOT.replace("action_wait: 2 s", "action_wait: 2 s\n  setup_on_connect: true")
    _driver, backend, bench = make(text)
    await bench.connect()
    assert backend.names() == ["setup"]
    assert (await bench.read("initialized")).value is True
    await bench.close()


async def test_opentrons_deck_with_slots_and_a_saved_deck_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    text = """
device: OT-2
id: ot2
connect:
  pylabrobot: chatterbox
  deck: ot2
  layout:
    - { name: tips, resource: hamilton_96_tiprack_1000uL_filter, slot: 1 }
    - { name: plate, resource: cor_96_wellplate_360uL_Fb, slot: 2 }
read:
  tips_mounted: { unit: dimensionless }
"""
    driver, _, bench = make(text)
    await bench.connect()
    assert type(driver.deck).__name__ == "OTDeck"
    saved = tmp_path / "deck.json"
    driver.deck.save(str(saved))
    await bench.close()
    loaded = (
        "device: OT-2\nid: ot2\nconnect: { pylabrobot: chatterbox, deck_env: OT2_TEST_DECK }\n"
        "read:\n  tips_mounted: { unit: dimensionless }\n"
    )
    other, _, other_bench = make(loaded)
    monkeypatch.delenv("OT2_TEST_DECK", raising=False)
    with pytest.raises(DriverError, match="Set the OT2_TEST_DECK environment variable"):
        await other.connect()
    monkeypatch.setenv("OT2_TEST_DECK", str(saved))
    await other_bench.connect()
    assert other.deck.get_resource("tips").name == "tips"
    await other_bench.close()


@pytest.mark.parametrize(
    ("layout", "message"),
    [
        ("- { name: tips, resource: no_such_rack, rails: 3 }", "not a PyLabRobot resource factory"),
        ("- { name: tips, resource: Plate, rails: 3 }", "not a PyLabRobot resource factory"),
        ("- { name: tips, resource: hamilton_96_tiprack_1000uL_filter, slot: 3 }", "has rails, not slots"),
        (
            "- { name: tips, resource: hamilton_96_tiprack_1000uL_filter, rails: 3 }\n"
            "    - { name: more, resource: hamilton_96_tiprack_1000uL_filter, rails: 3 }",
            "refused the placement",
        ),
    ],
)
async def test_bad_layouts_fail_on_connect(layout: str, message: str) -> None:
    text = (
        f"device: Bad\nid: bad\nconnect:\n  pylabrobot: chatterbox\n  layout:\n    {layout}\n"
        "read:\n  channels: { unit: dimensionless }\n"
    )
    _driver, _, bench = make(text)
    with pytest.raises(DriverError, match=message):
        await bench.connect()


async def test_addresses_in_the_file_must_exist_on_the_deck() -> None:
    text = ROBOT.replace('values: ["plate:A3"]', 'values: ["tips:A3"]')
    _driver, _, bench = make(text)
    with pytest.raises(DriverError, match="not a plate"):
        await bench.connect()
    text = ROBOT.replace('container: "plate:A1"', 'container: "reservoir:A1"')
    _driver, _, bench = make(text)
    with pytest.raises(DriverError, match="no resource 'reservoir'"):
        await bench.connect()


async def test_describe_proposes_actions_from_the_deck() -> None:
    driver, _, bench = make()
    assert await driver.describe() is None
    await bench.connect()
    proposal = await driver.describe()
    assert proposal is not None
    assert proposal["actions"]["aspirate"]["args"]["volume"] == {"unit": "uL", "min": 0, "max": 360.0}
    assert proposal["actions"]["pick_up_tips"]["args"]["tips"]["pattern"].startswith("^(tips):")
    assert all(entry["suggested"] and entry["confirm"] == "confirm-each-time" for entry in proposal["actions"].values())
    assert proposal["read"]["plate_a1_volume"] == {"unit": "uL", "map": {"container": "plate:A1"}}
    await bench.close()


@pytest.mark.parametrize(
    ("snippet", "message"),
    [
        ("write: { speed: { unit: rpm, min: 0, max: 1 } }", "no write channels"),
        ("read: { colour: { type: string } }", "not a PyLabRobot channel"),
        ("read: { initialized: { unit: dimensionless } }", "this reading is a bool"),
        ("read: { v: { unit: V, map: { container: 'plate:A1' } } }", "needs a volume unit"),
        ("read: { v: { unit: uL, map: { container: 'plate-A1' } } }", "not a deck address"),
        ("actions: { aspirate: { args: { well: { type: string, max_length: 9 } } } }", "takes the arguments"),
        (
            "actions: { aspirate: { args: { well: { type: bool }, volume: { unit: uL, min: 0, max: 1 } } } }",
            "string or enum",
        ),
        (
            "actions: { aspirate: { args: { well: { type: enum, values: [A1] },"
            " volume: { unit: uL, min: 0, max: 1 } } } }",
            "not a deck address",
        ),
        (
            "actions: { aspirate: { args: { well: { type: enum, values: ['plate:A1'] },"
            " volume: { unit: s, min: 0, max: 1 } } } }",
            "volume unit",
        ),
        ("actions: { wiggle: {} }", "not a PyLabRobot channel or action"),
    ],
)
def test_bad_maps_are_rejected(snippet: str, message: str) -> None:
    text = f"device: Bad\nid: bad\nconnect: {{ pylabrobot: chatterbox }}\n{snippet}\n"
    with pytest.raises(DriverError, match=message):
        PyLabRobotDriver(loads(text))


@pytest.mark.parametrize(
    ("params", "message"),
    [
        ("pylabrobot: opentrons", "needs host"),
        ("pylabrobot: chatterbox, action_wait: 30 s", "action_wait"),
        ("pylabrobot: chatterbox, deck_env: DECK, layout: [{ name: a, resource: b, rails: 1 }]", "not both"),
        ("pylabrobot: chatterbox, layout: [{ name: a, resource: b, rails: 1, slot: 2 }]", "exactly one of rails"),
        (
            "pylabrobot: chatterbox, layout: [{ name: a, resource: b, rails: 1 }, { name: a, resource: c, rails: 9 }]",
            "unique",
        ),
        ("pylabrobot: robotron", "backend"),
        ("pylabrobot: chatterbox, volumes: { 'plate:A1': 5 V }", "volumes plate:A1"),
        ("pylabrobot: chatterbox, volumes: { 'A1': 5 uL }", "not a deck address"),
    ],
)
def test_bad_params_are_rejected(params: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        PyLabRobotDriver(loads(f"device: Bad\nid: bad\nconnect: {{ {params} }}\n"))


async def test_the_chatterbox_backend_from_params() -> None:
    driver = PyLabRobotDriver(
        loads(
            "device: X\nid: x\nconnect: { pylabrobot: chatterbox, num_channels: 4 }\n"
            "read:\n  channels: { unit: dimensionless }\n"
        )
    )
    bench = Bench(driver.device, driver)
    await bench.connect()
    assert isinstance(driver.backend, RecordingBackend)
    assert (await bench.read("channels")).value == 4.0
    await bench.close()


def test_example_file_loads_read_only() -> None:
    file = load(Path(__file__).parents[3] / "openhal/drivers/pylabrobot/examples/starlet.hal.yaml")
    assert not file.writable
    assert file.effective_hazard == "high"
    driver = PyLabRobotDriver(file)
    assert {"initialize", "pick_up_tips", "aspirate", "dispense"} <= set(driver.actions)


async def test_actions_need_a_kernel_grant() -> None:
    from openhal.kernel.grants import GrantError

    driver, backend, bench = make()
    await bench.connect()
    with pytest.raises(GrantError):
        await driver.action("initialize", {}, None)
    assert backend.operations == []
    await bench.close()
