"""A Mettler Toledo balance becomes a library file through the driver writer, then runs on the serial driver.

The writer reads the MT-SICS command list the way a person pastes it from the reference manual,
the person's agent proposes the draft, a person answers the limits interview, and the saved file
runs through a kernel against a simulated balance that answers MT-SICS. The library file is the
same draft, so this checks the library entry end to end. Nothing reaches a real port.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx
import pytest
import yaml

from openhal.drivers.serial.driver import SerialDriver
from openhal.drivers.serial.simulator import SerialSimulator
from openhal.hub.api import create_app
from openhal.hub.config import HubConfig
from openhal.hub.hub import Hub
from openhal.spec import load
from openhal.spec.loader import parse_yaml
from openhal.spec.models import DeviceFile
from tests.drivers.serial.kit import Bench, assert_done, assert_failed
from tests.kernel.conftest import FakeClock
from tests.library.mt_sics import CONTENTS, Balance

ROOT = Path(__file__).resolve().parents[2]
LIBRARY_FILE = ROOT / "library" / "serial" / "mettler-toledo-ms-ts.hal.yaml"


@pytest.fixture
async def hub(tmp_path: Path) -> AsyncIterator[Hub]:
    hub = Hub(HubConfig(home=tmp_path), clock=FakeClock(), in_memory=True)
    hub.config.devices_dir.mkdir(parents=True)
    await hub.start(load_devices=False)
    yield hub
    await hub.close()


@pytest.fixture
async def client(hub: Hub) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=create_app(hub), client=("127.0.0.1", 50000))
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:7420") as client:
        yield client


def unwrap(block: str) -> str:
    """The text inside a device-data block, which is how the writer returns what a manual said."""
    return block.splitlines()[-2]


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def library_draft() -> dict[str, Any]:
    """The library file as the agent proposes it, keeping the manual as the draft's source."""
    data = yaml.safe_load(LIBRARY_FILE.read_text(encoding="utf-8"))
    data["provenance"] = {"source": "manual", "tool": "openhal driver writer"}
    return data


def bench(file: DeviceFile, balance: Balance) -> Bench:
    return Bench(file, SerialDriver(file, opener=SerialSimulator(balance).opener))


async def test_the_manual_drafts_the_balance_and_a_person_confirms_it(client: httpx.AsyncClient, hub: Hub) -> None:
    agent, _ = hub.tokens.create("claude", "agent", "control_low")
    person, _ = hub.tokens.create("me", "human")
    started = await client.post(
        "/v1/writer/sessions",
        json={"manual_text": CONTENTS, "driver": "serial", "params": {"port": "loop://", "newline": "crlf"}},
        headers=bearer(agent),
    )
    session = started.json()
    assert started.status_code == 200, session
    found = {unwrap(command["command"]): command for command in session["detected"]["manual_commands"]}
    assert {"S", "SI", "TA", "I4"} <= {name for name, command in found.items() if command["kind"] == "query"}
    assert {"Z", "T", "TAC"} <= {name for name, command in found.items() if command["kind"] == "action"}
    drafted = parse_yaml(session["draft_yaml"])
    assert drafted["read"]["stable_weight_value"]["map"]["query"] == "S"

    proposed = await client.post(
        f"/v1/writer/sessions/{session['id']}/propose",
        json={"draft_yaml": yaml.safe_dump(library_draft())},
        headers=bearer(agent),
    )
    assert proposed.status_code == 200, proposed.json()
    questions = (await client.get(f"/v1/writer/sessions/{session['id']}/interview", headers=bearer(agent))).json()
    answers = {question["id"]: question["suggested"] for question in questions["questions"]}
    answered = (
        await client.post(
            f"/v1/writer/sessions/{session['id']}/answers", json={"answers": answers}, headers=bearer(person)
        )
    ).json()
    assert answered["status"] == "ready", answered["problems"]
    saved = (
        await client.post(
            f"/v1/writer/sessions/{session['id']}/finish", json={"save_as": "lab-balance"}, headers=bearer(person)
        )
    ).json()
    file = load(saved["path"])
    assert file.provenance.source == "manual"
    assert set(file.read) == set(load(LIBRARY_FILE).read)
    assert set(file.actions) == set(load(LIBRARY_FILE).actions)

    balance = Balance(load_g=12.5)
    rig = await bench(file, balance).connect()
    assert (await rig.read("weight")).value == pytest.approx(12.5)
    await rig.close()


async def test_the_library_file_weighs_tares_and_zeroes() -> None:
    balance = Balance(load_g=25.0)
    rig = await bench(load(LIBRARY_FILE), balance).connect()
    assert (await rig.read("weight")).value == pytest.approx(25.0)
    assert (await rig.read("serial_number")).value == "B021002593"
    assert_done(await rig.act("tare"))
    assert (await rig.read("tare_weight")).value == pytest.approx(25.0)
    balance.load_g = 30.25
    assert (await rig.read("stable_weight")).value == pytest.approx(5.25)
    assert_done(await rig.act("clear_tare"))
    assert_done(await rig.act("zero"))
    assert (await rig.read("weight")).value == pytest.approx(0.0)
    await rig.close()


async def test_an_unstable_or_overloaded_balance_fails_instead_of_guessing() -> None:
    balance = Balance(load_g=10.0, stable=False)
    rig = await bench(load(LIBRARY_FILE), balance).connect()
    assert (await rig.read("weight")).value == pytest.approx(10.0)
    with pytest.raises(Exception, match="S I"):
        await rig.read("stable_weight")
    assert_failed(await rig.act("zero"), "Z I")
    balance.load_g = 500.0
    with pytest.raises(Exception, match=r"S \+"):
        await rig.read("weight")
    await rig.close()
