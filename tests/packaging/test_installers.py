"""The one-line installers, website/public/install.sh and install.ps1.

Both scripts carry the distribution name, the repository, the uv version and the Python version as
one value each at the top, and these tests hold each value to its source. install.sh also runs for
real under sh with stub commands first on PATH. The curl stub answers each address with the status
a test gives it, and the uv stub records what the script asked of uv, so no test reaches the
network, installs anything or touches the real HOME. The Windows CI job runs install.ps1 for real.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tomllib
from pathlib import Path
from typing import Final

import pytest

from openhal._brand import DISTRIBUTION_NAME

ROOT: Final = Path(__file__).resolve().parents[2]
PUBLIC: Final = ROOT / "website" / "public"
SHELL_SCRIPT: Final = PUBLIC / "install.sh"
POWERSHELL_SCRIPT: Final = PUBLIC / "install.ps1"
INSTALL: Final = json.loads((ROOT / "website" / "src" / "config" / "install.json").read_text(encoding="utf-8"))
REPO_CONFIG: Final = (ROOT / "website" / "src" / "config" / "repo.mjs").read_text(encoding="utf-8")
REPOSITORY: Final = REPO_CONFIG.split('REPOSITORY_URL = "', 1)[1].split('"', 1)[0]
SH: Final = shutil.which("sh")
MAIN: Final = f"{REPOSITORY}/archive/refs/heads/main.tar.gz"
PYPI: Final = f"https://pypi.org/pypi/{DISTRIBUTION_NAME}/json"

CURL: Final = """#!/bin/sh
echo "curl $*" >> "$STUB_LOG"
for last in "$@"; do :; done
case " $* " in
  *" -w "*)
    code="$(sed -n "s#^$last ##p" "$STUB_STATUS" | head -n 1)"
    printf '%s' "${code:-404}"
    ;;
  *" -o "*)
    out=""
    take=0
    for word in "$@"; do
      if [ "$take" = 1 ]; then out="$word"; take=0; fi
      [ "$word" = "-o" ] && take=1
    done
    cat > "$out" <<'EOF'
echo "uv-installer UV_INSTALL_DIR=$UV_INSTALL_DIR UV_NO_MODIFY_PATH=$UV_NO_MODIFY_PATH $*" >> "$STUB_LOG"
mkdir -p "$UV_INSTALL_DIR"
cp "$STUB_UV" "$UV_INSTALL_DIR/uv"
EOF
    ;;
esac
"""

UV: Final = """#!/bin/sh
echo "uv $*" >> "$STUB_LOG"
case "$*" in
  "tool dir --bin") printf '%s\\n' "$STUB_BIN" ;;
  "tool install "*)
    echo "path ${PATH%%:*}" >> "$STUB_LOG"
    [ -n "${STUB_UV_FAILS:-}" ] && exit 2
    mkdir -p "$STUB_BIN"
    printf '#!/bin/sh\\necho "openhal 0.1.0"\\n' > "$STUB_BIN/openhal"
    chmod +x "$STUB_BIN/openhal"
    ;;
esac
"""

pytestmark = pytest.mark.skipif(SH is None, reason="sh is not installed")


def constant(text: str, pattern: str) -> str:
    found = re.findall(pattern, text, re.M)
    assert len(found) == 1, f"{pattern} should match exactly once, not {len(found)} times"
    return str(found[0])


def shell_value(name: str) -> str:
    return constant(SHELL_SCRIPT.read_text(encoding="utf-8"), rf'^{name}="([^"]*)"$')


def powershell_value(name: str) -> str:
    return constant(POWERSHELL_SCRIPT.read_text(encoding="utf-8"), rf"^  \${name} = '([^']*)'$")


def write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    path.chmod(0o755)
    return path


class Run:
    def __init__(self, tmp_path: Path, *, with_uv: bool = False, on_path: bool = False) -> None:
        self.home = tmp_path / "home"
        self.home.mkdir()
        self.bin = self.home / ".local" / "bin"
        self.log = tmp_path / "ran.log"
        self.log.touch()
        self.status = tmp_path / "status.txt"
        self.status.touch()
        stubs = tmp_path / "stubs"
        stubs.mkdir()
        tools = tmp_path / "tools"
        tools.mkdir()
        write(stubs / "curl", CURL)
        self.uv = write(tools / "uv", UV)
        if with_uv:
            shutil.copy(self.uv, stubs / "uv")
        folders = [str(stubs), *([str(self.bin)] if on_path else []), "/usr/bin", "/bin"]
        self.env = {
            "HOME": str(self.home),
            "PATH": os.pathsep.join(folders),
            "STUB_LOG": str(self.log),
            "STUB_STATUS": str(self.status),
            "STUB_UV": str(self.uv),
            "STUB_BIN": str(self.bin),
        }

    def answer(self, address: str, code: int) -> None:
        with self.status.open("a", encoding="utf-8") as out:
            out.write(f"{address} {code}\n")

    def __call__(self, **env: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(SH), str(SHELL_SCRIPT)],
            env={**self.env, **env},
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )

    def ran(self) -> list[str]:
        return self.log.read_text(encoding="utf-8").splitlines()

    def install_line(self) -> str:
        found = [line for line in self.ran() if line.startswith("uv tool install ")]
        assert len(found) == 1, self.ran()
        return found[0]


def test_the_distribution_name_is_the_brand_name() -> None:
    assert shell_value("DISTRIBUTION") == DISTRIBUTION_NAME
    assert powershell_value("Distribution") == DISTRIBUTION_NAME
    for script in (SHELL_SCRIPT, POWERSHELL_SCRIPT):
        assert script.read_text(encoding="utf-8").count(DISTRIBUTION_NAME) == 1, f"{script.name} names it once"


def test_the_addresses_match_the_site_and_the_repository() -> None:
    assert shell_value("REPOSITORY") == REPOSITORY
    assert powershell_value("Repository") == REPOSITORY
    assert shell_value("SITE") == INSTALL["site"]
    assert "irm $SITE/install.ps1 | iex" in SHELL_SCRIPT.read_text(encoding="utf-8")


def test_the_uv_version_is_the_one_the_release_uses() -> None:
    release = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    pinned = set(re.findall(r'uses: astral-sh/setup-uv@\S+\n\s+with:\n\s+version: "([^"]+)"', release))
    assert pinned == {shell_value("UV_VERSION")}
    assert powershell_value("UvVersion") == shell_value("UV_VERSION")


def test_the_python_version_is_one_the_package_supports() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    python = shell_value("PYTHON_VERSION")
    assert powershell_value("PythonVersion") == python
    assert f"Programming Language :: Python :: {python}" in project["classifiers"]
    assert project["requires-python"] == f">={python}"


def test_the_scripts_carry_no_comments_and_only_ascii() -> None:
    for script in (SHELL_SCRIPT, POWERSHELL_SCRIPT):
        text = script.read_text(encoding="utf-8")
        assert text.isascii(), f"{script.name} has a character outside ASCII"
        for number, line in enumerate(text.splitlines(), 1):
            if number == 1 and line.startswith("#!"):
                continue
            assert not line.lstrip().startswith("#"), f"{script.name} line {number} is a comment"
            assert " #" not in line, f"{script.name} line {number} has a comment"
        assert "<#" not in text


def test_the_powershell_script_never_exits_the_window() -> None:
    text = POWERSHELL_SCRIPT.read_text(encoding="utf-8")
    assert not re.search(r"^\s*exit\b", text, re.M | re.I), "irm | iex runs in the visitor's window"
    assert text.rstrip().endswith("}")
    assert '-ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/$UvVersion/install.ps1 | iex"' in text


def test_both_scripts_install_the_same_way() -> None:
    for script in (SHELL_SCRIPT, POWERSHELL_SCRIPT):
        text = script.read_text(encoding="utf-8")
        assert "tool install --upgrade --compile-bytecode --python" in text
        assert "--no-build" in text
        assert "--no-binary-package" in text
        assert "UV_NO_MODIFY_PATH" in text
        assert "pypi.org/pypi/" in text
        assert "/archive/refs/tags/v" in text
        assert "/archive/refs/heads/main.tar.gz" in text
        assert "OPENHAL_VERSION" in text
        assert "OPENHAL_SOURCE" in text
        assert "tool update-shell" in text
        assert text.rstrip().splitlines()[-1].strip() != ""


def test_the_shell_script_parses_under_every_shell() -> None:
    for name in ("sh", "dash", "bash"):
        shell = shutil.which(name)
        if shell is None:
            continue
        done = subprocess.run([shell, "-n", str(SHELL_SCRIPT)], capture_output=True, text=True, check=False)
        assert done.returncode == 0, f"{name}: {done.stderr}"


@pytest.mark.skipif(shutil.which("shellcheck") is None, reason="shellcheck is not installed")
def test_shellcheck_is_clean() -> None:
    done = subprocess.run(["shellcheck", "-s", "sh", str(SHELL_SCRIPT)], capture_output=True, text=True, check=False)
    assert done.returncode == 0, done.stdout


def test_before_any_release_main_installs_with_wheels_only(tmp_path: Path) -> None:
    run = Run(tmp_path)
    run.answer(PYPI, 404)
    done = run()
    assert done.returncode == 0, done.stdout + done.stderr
    ran = run.ran()
    assert f"uv-installer UV_INSTALL_DIR={run.bin} UV_NO_MODIFY_PATH=1 --quiet" in ran
    assert any(line.startswith("curl ") and "https://astral.sh/uv/" in line for line in ran)
    line = run.install_line()
    assert line.endswith(f"--no-build --no-binary-package {DISTRIBUTION_NAME} {DISTRIBUTION_NAME} @ {MAIN}")
    assert line.startswith("uv tool install --upgrade --compile-bytecode --python 3.12 ")
    assert f"path {run.bin}" in ran, "uv sees its own bin folder on PATH, so uv prints no PATH warning of its own"
    assert f"Installing OpenHAL from the main branch of {REPOSITORY}" in done.stdout
    assert f"OpenHAL 0.1.0 is now in {run.bin}." in done.stdout


def test_a_release_on_pypi_installs_the_wheel_from_pypi(tmp_path: Path) -> None:
    run = Run(tmp_path, with_uv=True)
    run.answer(PYPI, 200)
    done = run()
    assert done.returncode == 0, done.stdout + done.stderr
    assert run.install_line().endswith(f"--no-build {DISTRIBUTION_NAME}")
    assert not any("astral.sh" in line for line in run.ran()), "uv was on PATH, so the script installs no uv"


def test_a_pinned_version_comes_from_pypi_then_from_its_tag(tmp_path: Path) -> None:
    run = Run(tmp_path, with_uv=True)
    run.answer(f"https://pypi.org/pypi/{DISTRIBUTION_NAME}/0.2.0/json", 200)
    done = run(OPENHAL_VERSION="0.2.0")
    assert done.returncode == 0, done.stdout + done.stderr
    assert run.install_line().endswith(f"--no-build {DISTRIBUTION_NAME}==0.2.0")

    (tmp_path / "tagged").mkdir()
    tagged = Run(tmp_path / "tagged", with_uv=True)
    tagged.answer(f"{REPOSITORY}/archive/refs/tags/v0.2.0.tar.gz", 200)
    done = tagged(OPENHAL_VERSION="v0.2.0")
    assert done.returncode == 0, done.stdout + done.stderr
    tag = f"{DISTRIBUTION_NAME} @ {REPOSITORY}/archive/refs/tags/v0.2.0.tar.gz"
    assert tagged.install_line().endswith(f"--no-binary-package {DISTRIBUTION_NAME} {tag}")
    assert f"Installing OpenHAL from the tag v0.2.0 of {REPOSITORY}" in done.stdout


def test_a_version_found_nowhere_installs_nothing(tmp_path: Path) -> None:
    run = Run(tmp_path, with_uv=True)
    done = run(OPENHAL_VERSION="9.9.9")
    assert done.returncode == 1
    assert "OpenHAL 9.9.9 is neither on PyPI nor tagged v9.9.9" in done.stderr
    assert not any(line.startswith("uv tool install") for line in run.ran())


def test_an_unreachable_index_stops_before_installing(tmp_path: Path) -> None:
    run = Run(tmp_path, with_uv=True)
    run.answer(PYPI, 0)
    done = run()
    assert done.returncode == 1
    assert f"The installer could not reach {PYPI}." in done.stderr
    assert not any(line.startswith("uv tool install") for line in run.ran())


def test_a_source_overrides_the_lookup(tmp_path: Path) -> None:
    run = Run(tmp_path, with_uv=True)
    source = f"git+{REPOSITORY}@0123456789abcdef0123456789abcdef01234567"
    done = run(OPENHAL_SOURCE=source)
    assert done.returncode == 0, done.stdout + done.stderr
    assert run.install_line().endswith(f"--no-binary-package {DISTRIBUTION_NAME} {DISTRIBUTION_NAME} @ {source}")
    assert not any(line.startswith("curl") for line in run.ran())


def test_a_wheel_source_installs_with_no_build_at_all(tmp_path: Path) -> None:
    run = Run(tmp_path, with_uv=True)
    wheel = f"/tmp/{DISTRIBUTION_NAME}-0.1.0-py3-none-any.whl"
    done = run(OPENHAL_SOURCE=wheel)
    assert done.returncode == 0, done.stdout + done.stderr
    assert run.install_line().endswith(f"--no-build {wheel}")


def test_the_path_hint_shows_only_while_the_folder_is_missing_from_path(tmp_path: Path) -> None:
    run = Run(tmp_path, with_uv=True)
    run.answer(PYPI, 200)
    done = run()
    assert f"{run.bin} is not on your PATH yet." in done.stdout
    assert f'  export PATH="{run.bin}:$PATH"' in done.stdout
    assert done.stdout.rstrip().endswith("Set up your first device and your AI clients with\n  openhal init")

    (tmp_path / "found").mkdir()
    found = Run(tmp_path / "found", with_uv=True, on_path=True)
    found.answer(PYPI, 200)
    done = found()
    assert done.returncode == 0, done.stdout + done.stderr
    assert "is not on your PATH yet" not in done.stdout
    assert done.stdout.rstrip().endswith("openhal init")


def test_a_failed_uv_install_says_nothing_was_installed(tmp_path: Path) -> None:
    run = Run(tmp_path, with_uv=True)
    run.answer(PYPI, 200)
    done = run(STUB_UV_FAILS="1")
    assert done.returncode == 1
    assert "uv stopped with the error above, so OpenHAL is not installed." in done.stderr
    assert "openhal init" not in done.stdout


def test_windows_shells_get_the_powershell_command(tmp_path: Path) -> None:
    run = Run(tmp_path, with_uv=True)
    write(tmp_path / "stubs" / "uname", "#!/bin/sh\necho MINGW64_NT-10.0\n")
    done = run()
    assert done.returncode == 1
    assert f"irm {INSTALL['site']}/install.ps1 | iex" in done.stderr
    assert run.ran() == []
