"""The wheel and the sdist `uv build` makes, which uv tool install and pipx install take, and the timing script."""

from __future__ import annotations

import shutil
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

import pytest

from openhal import __version__
from openhal._brand import DISTRIBUTION_NAME

ROOT = Path(__file__).resolve().parents[2]
TIMING = ROOT / "scripts" / "time-first-read"


@pytest.fixture(scope="module")
def dist(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """One `uv build`, which makes the sdist and then the wheel from the sdist, as a release does."""
    uv = shutil.which("uv")
    if uv is None:
        pytest.skip("uv is not installed")
    out = tmp_path_factory.mktemp("dist")
    done = subprocess.run(
        [uv, "build", "--quiet", "--out-dir", str(out), str(ROOT)],
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    assert done.returncode == 0, done.stderr
    return out


@pytest.fixture(scope="module")
def wheel(dist: Path) -> zipfile.ZipFile:
    return zipfile.ZipFile(next(dist.glob("*.whl")))


def test_the_sdist_holds_the_package_and_what_the_wheel_takes_in(dist: Path) -> None:
    """The sdist leaves out the website, the dashboard, the film and the docs, so PyPI gets a small file fast."""
    with tarfile.open(next(dist.glob("*.tar.gz"))) as sdist:
        names = {Path(name).relative_to(f"{DISTRIBUTION_NAME}-{__version__}").as_posix() for name in sdist.getnames()}
    tops = {name.split("/")[0] for name in names}
    assert tops <= {
        "openhal",
        "examples",
        "library",
        "README.md",
        "LICENSE",
        "CHANGELOG.md",
        "pyproject.toml",
        "PKG-INFO",
        ".gitignore",
    }
    assert "examples/plant-waterer/mock/plant-waterer.hal.yaml" in names
    assert "examples/print-babysitter/printer.hal.yaml" in names
    assert "openhal/cli/main.py" in names


def test_the_wheel_is_the_brand_distribution(wheel: zipfile.ZipFile) -> None:
    assert Path(str(wheel.filename)).name == f"{DISTRIBUTION_NAME}-{__version__}-py3-none-any.whl"
    metadata = wheel.read(next(item for item in wheel.namelist() if item.endswith(".dist-info/METADATA"))).decode()
    assert f"\nName: {DISTRIBUTION_NAME}\n" in metadata


def test_the_wheel_has_every_command(wheel: zipfile.ZipFile) -> None:
    name = next(item for item in wheel.namelist() if item.endswith(".dist-info/entry_points.txt"))
    entry_points = wheel.read(name).decode()
    assert "openhal = openhal.cli.main:app" in entry_points
    assert "openhald = openhal.hub.daemon:main" in entry_points
    assert f"{DISTRIBUTION_NAME} = openhal.cli.main:app" in entry_points, "uvx halkit runs the halkit command"


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
