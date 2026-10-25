"""`openhal library list`, `show` and `add` against a temporary home, and the hint in `openhal discover`."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
from typer.testing import CliRunner

from openhal.cli import _common, library_cmd
from openhal.cli.main import app
from openhal.spec.loader import load

ROOT = Path(__file__).resolve().parents[2]
LIBRARY = ROOT / "library"
FILES = sorted(LIBRARY.rglob("*.hal.yaml"))
runner = CliRunner()


@pytest.fixture(autouse=True)
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    folder = tmp_path / "home"
    monkeypatch.setenv("OPENHAL_HOME", str(folder))
    monkeypatch.setattr(library_cmd, "roots", lambda: [LIBRARY])
    return folder


def run(*args: str) -> tuple[int, str]:
    result = runner.invoke(app, list(args))
    return result.exit_code, result.output


def test_list_shows_every_file() -> None:
    code, out = run("library", "list")
    assert code == 0, out
    assert "rigol-dp832" in out
    assert f"{len(FILES)} files, all unverified" in out


def test_list_filters_by_driver_as_json() -> None:
    code, out = run("library", "list", "--driver", "scpi", "--json")
    assert code == 0, out
    listed = json.loads(out)
    assert {item["name"] for item in listed} == {
        path.name.removesuffix(".hal.yaml") for path in FILES if "scpi" in path.parts
    }
    assert {item["driver"] for item in listed} == {"scpi"}
    assert all(item["verification"] == "unverified" for item in listed)


def test_list_with_an_unknown_driver_says_so() -> None:
    code, out = run("library", "list", "--driver", "nothing")
    assert code == 0
    assert "no files for the nothing driver" in out


def test_show_prints_the_match_and_the_file() -> None:
    code, out = run("library", "show", "rigol-dp832")
    assert code == 0, out
    assert "match  usb 1ab1:0e11" in out
    assert "openhal library add rigol-dp832" in out
    assert (LIBRARY / "scpi" / "rigol-dp832.hal.yaml").read_text().splitlines()[1] in out


def test_show_accepts_a_path_and_prints_limits_like_the_hub_describes_them() -> None:
    code, out = run("library", "show", "scpi/rigol-dp832.hal.yaml", "--json")
    assert code == 0, out
    shown = json.loads(out)
    assert shown["actions"]["set_ch1"]["args"]["volts"]["unit"] == "V"
    assert shown["actions"]["set_ch1"]["args"]["volts"]["max"] == 5.0
    assert shown["actions"]["set_ch1"]["confirm"] == "confirm-each-time"
    assert shown["write"]["ch1_output"] == {
        "type": "bool",
        "values": [],
        "confirm": "confirm-each-time",
        "suggested": True,
    }
    assert "Suggested limits." in shown["notes"]


def test_show_an_unknown_name_suggests_close_ones() -> None:
    code, out = run("library", "show", "rigol-dp83")
    assert code == 2
    assert "Did you mean rigol-dp832" in out


def test_add_copies_the_file_read_only_and_never_overwrites(home: Path) -> None:
    source = LIBRARY / "scpi" / "rigol-dp832.hal.yaml"
    code, out = run("library", "add", "rigol-dp832")
    assert code == 0, out
    target = home / "devices" / "rigol-dp832.hal.yaml"
    assert target.read_bytes() == source.read_bytes()
    added = load(target)
    assert added.confirmed is None
    assert not added.writable
    assert "openhal file confirm" in out
    target.write_text(target.read_text() + "\n")
    edited = target.read_bytes()
    code, out = run("library", "add", "rigol-dp832")
    assert code == 1
    assert "never overwrites" in out
    assert target.read_bytes() == edited


def test_add_refuses_a_second_file_for_the_same_device(home: Path) -> None:
    devices = home / "devices"
    devices.mkdir(parents=True)
    (devices / "bench.hal.yaml").write_bytes((LIBRARY / "scpi" / "rigol-dp832.hal.yaml").read_bytes())
    code, out = run("library", "add", "rigol-dp832")
    assert code == 1
    assert "already describes a device with id rigol-dp832" in out
    assert not (devices / "rigol-dp832.hal.yaml").exists()


def test_add_refuses_a_library_file_that_carries_a_confirmation(
    tmp_path: Path, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    library = tmp_path / "library" / "mock"
    library.mkdir(parents=True)
    (library / "fan.hal.yaml").write_text(
        "device: Fan\nid: fan\nconnect: { mock: fan }\n"
        "write:\n  speed: { unit: percent, min: 0, max: 50, confirmed: { by: someone, at: 2026-10-25 } }\n"
    )
    monkeypatch.setattr(library_cmd, "roots", lambda: [library.parent])
    code, out = run("library", "add", "fan")
    assert code == 1
    assert "carries a confirmation" in out
    assert not (home / "devices" / "fan.hal.yaml").exists()


def test_discover_tells_the_person_to_add_a_matched_library_file(monkeypatch: pytest.MonkeyPatch) -> None:
    library_file = str(LIBRARY / "scpi" / "rigol-dp832.hal.yaml")
    found = {
        "matched": [
            {
                "address": "USB0::0x1AB1::0x0E11::DP8C0000001::INSTR",
                "driver": "scpi",
                "identifiers": {"usb": "1ab1:0e11"},
                "label": None,
                "library_file": library_file,
                "device_id": "rigol-dp832",
                "score": 3,
            }
        ],
        "unknown": [],
        "errors": [],
    }

    def answer(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/discover"
        return httpx.Response(200, json=found)

    monkeypatch.setattr(_common, "TRANSPORT", httpx.MockTransport(answer))
    monkeypatch.setenv("OPENHAL_TOKEN", "test-token")
    code, out = run("discover", "--driver", "scpi")
    assert code == 0, out
    assert "as rigol-dp832" in out
    assert "Add it with openhal library add rigol-dp832" in out
