"""`openhal file validate` and `openhal file schema`."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from openhal.cli.main import app

ROOT = Path(__file__).resolve().parents[2]
runner = CliRunner()


def test_validate_examples_folder() -> None:
    result = runner.invoke(app, ["file", "validate", str(ROOT / "spec" / "examples")])
    assert result.exit_code == 0, result.output
    assert "0 invalid" in result.output
    assert "read-only" in result.output


def test_validate_reports_problems(tmp_path: Path) -> None:
    bad = tmp_path / "bad.hal.yaml"
    bad.write_text("device: x\nconnect: {driver: mock}\nwrite: {v: {unit: V, min: 5, max: 1}}\n")
    result = runner.invoke(app, ["file", "validate", str(bad)])
    assert result.exit_code == 1
    assert "is above max" in result.output


def test_validate_json(tmp_path: Path) -> None:
    good = tmp_path / "good.hal.yaml"
    good.write_text("device: Sensor\nconnect: {driver: mock}\nread: {t: {unit: degC}}\n")
    result = runner.invoke(app, ["file", "validate", "--json", str(good)])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload[0]["valid"] is True
    assert payload[0]["device_id"] == "sensor"


def test_no_files(tmp_path: Path) -> None:
    result = runner.invoke(app, ["file", "validate", str(tmp_path)])
    assert result.exit_code == 1


def test_schema_prints() -> None:
    result = runner.invoke(app, ["file", "schema"])
    assert result.exit_code == 0
    assert json.loads(result.output)["title"] == "OpenHAL device file"


def test_version() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "openhal" in result.output
