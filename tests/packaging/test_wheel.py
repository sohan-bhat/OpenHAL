"""The wheel `uv build` makes, which uv tool install and pipx install take, and the timing script."""

from __future__ import annotations

import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
TIMING = ROOT / "scripts" / "time-first-read"


@pytest.fixture(scope="module")
def wheel(tmp_path_factory: pytest.TempPathFactory) -> zipfile.ZipFile:
    uv = shutil.which("uv")
    if uv is None:
        pytest.skip("uv is not installed")
    out = tmp_path_factory.mktemp("dist")
    done = subprocess.run(
        [uv, "build", "--wheel", "--quiet", "--out-dir", str(out), str(ROOT)],
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    assert done.returncode == 0, done.stderr
    return zipfile.ZipFile(next(out.glob("*.whl")))


def test_the_wheel_has_both_commands(wheel: zipfile.ZipFile) -> None:
    name = next(item for item in wheel.namelist() if item.endswith(".dist-info/entry_points.txt"))
    entry_points = wheel.read(name).decode()
    assert "openhal = openhal.cli.main:app" in entry_points
    assert "openhald = openhal.hub.daemon:main" in entry_points


def test_the_wheel_has_the_setup_code_and_the_sample(wheel: zipfile.ZipFile) -> None:
    names = set(wheel.namelist())
    for module in ("background", "clients", "devices", "runner"):
        assert f"openhal/service/{module}.py" in names
    assert "openhal/examples/plant-waterer/mock/plant-waterer.hal.yaml" in names
    for name in ("printer.hal.yaml", "printer-cam.hal.yaml", "frames/first-layer.jpg", "frames/come-loose.jpg"):
        assert f"openhal/examples/print-babysitter/{name}" in names, "openhal demo needs the print babysitter files"


def test_the_timing_script_compiles_and_explains_itself() -> None:
    compile(TIMING.read_text(encoding="utf-8"), str(TIMING), "exec")
    done = subprocess.run([sys.executable, str(TIMING), "--help"], capture_output=True, text=True, check=False)
    assert done.returncode == 0, done.stderr
    assert "--installer" in done.stdout
    assert "--cold" in done.stdout
