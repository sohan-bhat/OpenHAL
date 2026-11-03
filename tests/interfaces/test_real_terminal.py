"""The installed `openhal` in its own terminal session, the way a person runs the command.

The command runs as a child process whose controlling terminal is a pseudo-terminal, with nothing
patched, so the picker opens the real terminal device. kqueue on macOS returns an error for
/dev/tty, so this test fails if the picker reads from that alias. The child gets `DEADLINE_S` and
is then stopped, so the test can't hang.
"""

from __future__ import annotations

import os
import select
import signal
import sys
import time
from pathlib import Path

import pytest

pytestmark = [
    pytest.mark.skipif(sys.platform == "win32", reason="pseudo-terminals are POSIX only"),
    pytest.mark.filterwarnings("ignore:This process .* is multi-threaded:DeprecationWarning"),
]

OPENHAL = Path(sys.executable).parent / "openhal"
DEADLINE_S = 60.0


def session(args: list[str], keys: dict[str, str], home: Path) -> tuple[int, str]:
    """Run `openhal` with a terminal of its own. Each key in `keys` is text to wait for, and its value the keys."""
    import pty

    env = {
        **os.environ,
        "OPENHAL_HOME": str(home),
        "OPENHAL_URL": "http://127.0.0.1:9",
        "TERM": "xterm-256color",
        "COLUMNS": "120",
    }
    pid, controller = pty.fork()
    if pid == 0:
        os.execve(str(OPENHAL), ["openhal", *args], env)
    shown = b""
    waiting = dict(keys)
    started = time.monotonic()
    try:
        while time.monotonic() - started < DEADLINE_S:
            ready, _, _ = select.select([controller], [], [], 0.05)
            if not ready:
                continue
            try:
                chunk = os.read(controller, 65536)
            except OSError:
                break
            if not chunk:
                break
            shown += chunk
            if b"\x1b[6n" in chunk:
                os.write(controller, b"\x1b[1;1R")
            for after, send in list(waiting.items()):
                if after.encode() in shown:
                    os.write(controller, send.encode())
                    del waiting[after]
        else:
            os.kill(pid, signal.SIGKILL)
    finally:
        _, status = os.waitpid(pid, 0)
        os.close(controller)
    return os.waitstatus_to_exitcode(status), shown.decode("utf-8", errors="replace")


def test_a_picker_in_a_real_terminal_session(tmp_path: Path) -> None:
    code, shown = session(["library", "show"], {"Pick a library name": "rigol-dp832\r"}, tmp_path / "home")
    assert code == 0, shown
    assert "Rigol DP832" in shown
    assert "openhal library add rigol-dp832" in shown
