"""A Mettler Toledo balance becomes a library file through the driver writer, then runs on the serial driver.

The writer reads the MT-SICS command list the way a person pastes it from the reference manual,
the person's agent proposes the draft, a person answers the limits interview, and the saved file
runs through a kernel against a simulated balance that answers MT-SICS. The library file is the
same draft, so this checks the library entry end to end. Nothing reaches a real port.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from openhal.drivers.base import DriverError
from openhal.drivers.serial.driver import SerialDriver
from openhal.drivers.serial.simulator import SerialSimulator
from openhal.hub.hub import Hub
from openhal.spec import load
from openhal.spec.models import DeviceFile
from tests.drivers.serial.kit import Bench, assert_done, assert_failed
from tests.library.mt_sics import CONTENTS, Balance
from tests.library.writer_kit import client, hub, write_from_manual

ROOT = Path(__file__).resolve().parents[2]
LIBRARY_FILE = ROOT / "library" / "serial" / "mettler-toledo-ms-ts.hal.yaml"
__all__ = ["client", "hub"]


def bench(file: DeviceFile, balance: Balance) -> Bench:
    return Bench(file, SerialDriver(file, opener=SerialSimulator(balance).opener))


async def test_the_manual_drafts_the_balance_and_a_person_confirms_it(client: httpx.AsyncClient, hub: Hub) -> None:
    commands, first, file = await write_from_manual(
        client, hub, CONTENTS, {"newline": "crlf"}, LIBRARY_FILE, "lab-balance"
    )
    assert {"S", "SI", "TA", "I4"} <= {name for name, command in commands.items() if command["kind"] == "query"}
    assert {"Z", "T", "TAC"} <= {name for name, command in commands.items() if command["kind"] == "action"}
    assert first["read"]["stable_weight_value"]["map"]["query"] == "S"
    assert first["connect"] == {"serial": "loop://", "newline": "crlf"}
    rig = await bench(file, Balance(load_g=12.5)).connect()
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
    with pytest.raises(DriverError, match="S I"):
        await rig.read("stable_weight")
    assert_failed(await rig.act("zero"), "Z I")
    balance.load_g = 500.0
    with pytest.raises(DriverError, match=r"S \+"):
        await rig.read("weight")
    await rig.close()
