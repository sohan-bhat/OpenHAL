"""A New Era syringe pump becomes a library file through the driver writer, then runs on the serial driver.

The pump replies in STX and ETX packets, which the serial driver reads with `framing: stx-etx`.
The writer reads the RS-232 command summary from the pump's manual, nested brackets and all, and
the saved file runs through a kernel against a simulated pump. Nothing reaches a real port.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from openhal.drivers.base import DriverError
from openhal.drivers.serial.driver import SerialDriver
from openhal.drivers.serial.simulator import SerialSimulator
from openhal.hub.hub import Hub
from openhal.spec import loads
from openhal.spec.models import DeviceFile
from openhal.writer import manual
from tests.drivers.serial.kit import Bench, assert_done, assert_failed
from tests.library.new_era import SUMMARY, Pump
from tests.library.writer_kit import client, hub, write_from_manual

ROOT = Path(__file__).resolve().parents[2]
LIBRARY_FILE = ROOT / "library" / "serial" / "new-era-ne-500.hal.yaml"
__all__ = ["client", "hub"]


def bench(file: DeviceFile, pump: Pump) -> Bench:
    return Bench(file, SerialDriver(file, opener=SerialSimulator(pump).opener))


def confirmed() -> DeviceFile:
    text = LIBRARY_FILE.read_text(encoding="utf-8")
    return loads(text.replace("suggested: true", "suggested: false") + "confirmed: { by: tester, at: 2026-11-03 }\n")


def test_the_command_summary_parses_with_nested_brackets() -> None:
    commands = {command.command: command for command in manual.extract(SUMMARY)}
    assert set(commands) == {"DIA", "RAT", "VOL", "DIR", "RUN", "PUR", "STP", "DIS", "CLD", "VER"}
    assert commands["RAT"].argument == "{C | I ] [ <float> [ UM | MM | UH | MH ]]"
    assert commands["RAT"].description == "Pumping rate"
    assert commands["DIA"].kind == "set"
    assert commands["DIS"].kind == "query"
    assert commands["VER"].kind == "query"
    assert commands["RUN"].kind == "action"
    assert commands["CLD"].kind == "action"
    assert commands["RUN"].careful
    assert commands["PUR"].careful
    sections = manual.draft_sections(list(commands.values()))
    assert set(sections["write"]) == {"dia", "rat", "vol", "dir"}
    assert "RUN" in sections["notes"]


async def test_the_manual_drafts_the_pump_and_a_person_confirms_it(client: httpx.AsyncClient, hub: Hub) -> None:
    params = {"baud": 19200, "newline": "cr", "framing": "stx-etx"}
    commands, first, file = await write_from_manual(client, hub, SUMMARY, params, LIBRARY_FILE, "lab-pump")
    assert commands["DIS"]["kind"] == "query"
    assert first["connect"]["framing"] == "stx-etx"
    rig = await bench(file, Pump(infused=1.25)).connect()
    assert (await rig.read("infused_volume")).value == pytest.approx(1.25)
    assert (await rig.read("status")).value == "stopped"
    await rig.close()


async def test_the_library_file_sets_up_runs_and_stops_the_pump() -> None:
    pump = Pump(time_scale=3600.0)
    rig = await bench(confirmed(), pump).connect()
    assert (await rig.read("firmware")).value == "NE500V3.928"
    assert_done(await rig.act("use_millilitres"))
    assert_done(await rig.write("diameter", "14.43 mm"))
    assert_done(await rig.write("direction", "withdraw"))
    assert (await rig.read("direction")).value == "withdraw"
    assert_done(await rig.write("direction", "infuse"))
    assert_done(await rig.write("rate", "12.5 mL/h"))
    assert pump.sent[-1] == "RAT12.5MH"
    assert (await rig.read("rate")).value == pytest.approx(12.5)
    assert_done(await rig.write("volume", "2 mL"))
    assert_done(await rig.act("run"))
    assert (await rig.read("status")).value == "infusing"
    assert_failed(await rig.write("diameter", "10 mm"), "?NA")
    assert await rig.stop() in ("safe", "done")
    assert pump.status == "P"
    assert (await rig.read("status")).value == "paused"
    assert (await rig.read("infused_volume")).value > 0
    await rig.close()


async def test_the_kernel_blocks_a_rate_past_the_file_limit() -> None:
    pump = Pump()
    rig = await bench(confirmed(), pump).connect()
    decision = await rig.write("rate", "80 mL/h")
    assert decision.status == "blocked"
    assert not any(command.startswith("RAT8") for command in pump.sent)
    await rig.close()


async def test_stx_etx_framing_drops_noise_before_the_packet() -> None:
    pump = Pump()
    sim = SerialSimulator(pump)
    file = confirmed()
    rig = Bench(file, SerialDriver(file, opener=sim.opener))
    await rig.connect()
    sim.push(b"\x00\xff")
    assert (await rig.read("status")).value == "stopped"
    pump.status = "Q"
    with pytest.raises(DriverError, match="00Q"):
        await rig.read("status")
    await rig.close()
