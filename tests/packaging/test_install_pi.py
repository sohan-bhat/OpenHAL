"""scripts/install-pi.sh, checked with bash -n, shellcheck when installed, and its dry run.

The dry run runs with stub commands first on PATH. Each stub records that it ran, so the test
proves the dry run prints every step and runs none of them. Nothing here touches the real HOME.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "install-pi.sh"
STUBBED = ("uv", "curl", "sudo", "usermod", "loginctl", "systemctl", "openhal", "ln", "mkdir", "sh")
BASH = shutil.which("bash")
pytestmark = pytest.mark.skipif(BASH is None, reason="bash is not installed")


def stubs(folder: Path, log: Path) -> Path:
    folder.mkdir()
    for name in STUBBED:
        stub = folder / name
        stub.write_text(f'#!/bin/sh\necho "{name} $*" >> "{log}"\n', encoding="utf-8")
        stub.chmod(0o755)
    return folder


def dry_run(tmp_path: Path, *args: str, with_uv: bool = True) -> tuple[str, str]:
    home = tmp_path / "home"
    home.mkdir()
    log = tmp_path / "ran.log"
    folder = stubs(tmp_path / "stubs", log)
    if not with_uv:
        (folder / "uv").unlink()
    env = {"HOME": str(home), "USER": "pi", "PATH": f"{folder}{os.pathsep}/usr/bin{os.pathsep}/bin"}
    done = subprocess.run(
        [str(BASH), str(SCRIPT), "--dry-run", *args], env=env, capture_output=True, text=True, timeout=60, check=False
    )
    assert done.returncode == 0, done.stdout + done.stderr
    return done.stdout, log.read_text(encoding="utf-8") if log.exists() else ""


def test_the_script_parses() -> None:
    done = subprocess.run([str(BASH), "-n", str(SCRIPT)], capture_output=True, text=True, check=False)
    assert done.returncode == 0, done.stderr


@pytest.mark.skipif(shutil.which("shellcheck") is None, reason="shellcheck is not installed")
def test_shellcheck_is_clean() -> None:
    done = subprocess.run(["shellcheck", str(SCRIPT)], capture_output=True, text=True, check=False)
    assert done.returncode == 0, done.stdout


def test_dry_run_prints_every_step_and_runs_none(tmp_path: Path) -> None:
    out, ran = dry_run(tmp_path)
    assert ran == "", f"the dry run ran commands:\n{ran}"
    assert "would run" in out
    home = tmp_path / "home"
    venv = home / ".local" / "share" / "openhal" / "venv"
    assert "venv --allow-existing --system-site-packages --python" in out
    assert "rpi-gpio,rpi-camera,pi-i2c-spi,serial,openhal-firmware" in out
    assert f"pip install --python {venv}/bin/python --compile-bytecode" in out
    assert "git+https://github.com/sohan-bhat/OpenHAL" in out
    assert "sudo usermod -aG" in out
    assert "sudo loginctl enable-linger pi" in out
    assert f"{home}/.local/bin/openhal service install" in out
    assert "curl" not in out, "uv was on PATH, so the script must not install it"
    assert out.rstrip().endswith("openhal init")


def test_dry_run_installs_uv_when_missing(tmp_path: Path) -> None:
    out, ran = dry_run(tmp_path, with_uv=False)
    assert ran == ""
    assert "https://astral.sh/uv/install.sh" in out
    assert f"would run {tmp_path / 'home'}/.local/bin/uv venv" in out


def test_a_local_source_takes_the_extras(tmp_path: Path) -> None:
    out, _ = dry_run(tmp_path, "--source", "/home/pi/openhal_hub-0.1.0-py3-none-any.whl")
    assert "'/home/pi/openhal_hub-0.1.0-py3-none-any.whl[rpi-gpio," in out


def test_every_pi_extra_exists() -> None:
    extras = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["optional-dependencies"]
    text = SCRIPT.read_text(encoding="utf-8")
    wanted = text.split('EXTRAS="', 1)[1].split('"', 1)[0].split(",")
    assert set(wanted) <= set(extras), sorted(set(wanted) - set(extras))


def test_the_real_run_refuses_other_systems(tmp_path: Path) -> None:
    if os.uname().sysname == "Linux":
        pytest.skip("this check is for systems other than Linux")
    done = subprocess.run(
        [str(BASH), str(SCRIPT)],
        env={"HOME": str(tmp_path), "PATH": "/usr/bin:/bin"},
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert done.returncode == 1
    assert "Raspberry Pi running Linux" in done.stderr
