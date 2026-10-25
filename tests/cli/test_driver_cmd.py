"""The driver SDK commands. A fresh scaffold must pass conformance and its own tests unchanged."""

from __future__ import annotations

import importlib
import importlib.util
import inspect
import json
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from typer.testing import CliRunner

import openhal.drivers
from openhal.cli.main import app
from openhal.conformance import run
from openhal.spec import load

runner = CliRunner()


def test_list_shows_every_driver_with_its_level() -> None:
    result = runner.invoke(app, ["driver", "list", "--json"])
    assert result.exit_code == 0, result.output
    rows = {row["name"]: row for row in json.loads(result.output)}
    assert rows["mock"]["conformance"] == "control"
    assert rows["uvc"]["conformance"] == "core"
    assert rows["scpi"]["status"] == "implemented"


def test_test_runs_the_conformance_suite() -> None:
    result = runner.invoke(app, ["driver", "test", "mock"])
    assert result.exit_code == 0, result.output
    assert "12 passed, 0 skipped, 0 failed" in result.output


def test_test_refuses_an_unknown_driver() -> None:
    result = runner.invoke(app, ["driver", "test", "no-such-driver"])
    assert result.exit_code == 2
    assert "There is no driver" in result.output


@pytest.fixture
def checkout(tmp_path: Path) -> Iterator[Path]:
    (tmp_path / "openhal" / "drivers").mkdir(parents=True)
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'scratch'\n")
    drivers_path = openhal.drivers.__path__
    drivers_path.append(str(tmp_path / "openhal" / "drivers"))
    yield tmp_path
    drivers_path.remove(str(tmp_path / "openhal" / "drivers"))
    for name in [name for name in sys.modules if name.startswith("openhal.drivers.x_acme_pump")]:
        del sys.modules[name]


async def test_new_scaffolds_a_driver_that_passes_conformance(checkout: Path) -> None:
    result = runner.invoke(app, ["driver", "new", "acme-pump", "--root", str(checkout), "--title", "Acme pump"])
    assert result.exit_code == 0, result.output
    package = checkout / "openhal" / "drivers" / "x_acme_pump"
    for name in ("__init__.py", "driver.py", "simulator.py", "conformance.py", "catalog.json"):
        assert (package / name).exists(), name
    assert (checkout / "docs" / "drivers" / "x-acme-pump.md").exists()
    assert (checkout / "docs" / "hardware-tests" / "x-acme-pump.md").exists()
    assert json.loads((package / "catalog.json").read_text())["status"] == "experimental"

    example = load(package / "examples" / "acme-pump.hal.yaml")
    assert example.connect.driver == "x-acme-pump"
    assert not example.writable

    conformance = importlib.import_module("openhal.drivers.x_acme_pump.conformance")
    report = await run(conformance.case())
    failures = [f"{item.name}: {item.detail}" for item in report.results if not item.ok and not item.skipped]
    assert report.ok, "\n".join(failures)

    test_path = checkout / "tests" / "drivers" / "x_acme_pump" / "test_x_acme_pump.py"
    spec = importlib.util.spec_from_file_location("scaffold_tests", test_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    tests = [value for key, value in vars(module).items() if key.startswith("test_")]
    assert len(tests) == 3
    for test in tests:
        assert inspect.iscoroutinefunction(test)
        await test()


def test_new_never_overwrites(checkout: Path) -> None:
    assert runner.invoke(app, ["driver", "new", "acme-pump", "--root", str(checkout)]).exit_code == 0
    again = runner.invoke(app, ["driver", "new", "acme-pump", "--root", str(checkout)])
    assert again.exit_code == 1
    assert "nothing was created" in again.output


def test_new_refuses_a_bad_name(checkout: Path) -> None:
    result = runner.invoke(app, ["driver", "new", "Acme_Pump", "--root", str(checkout)])
    assert result.exit_code == 2


def test_new_refuses_a_folder_that_is_not_a_checkout(tmp_path: Path) -> None:
    result = runner.invoke(app, ["driver", "new", "acme-pump", "--root", str(tmp_path)])
    assert result.exit_code == 2
    assert "not an OpenHAL checkout" in result.output
